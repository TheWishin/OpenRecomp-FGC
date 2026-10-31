"""Games on the launcher: one JSON manifest per game (games/*.json, plus the player's own in the user folder)."""
import json
import math
import ntpath
import os
import re
import tempfile
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
BUILTIN_DIR = os.path.join(os.path.dirname(HERE), "games")
SECTIONS = ("play", "online", "build", "replays", "settings")
ADAPTERS = ("t5dr", "t4", "generic")
TOTAL_SLOTS = 6                        # the shelf always shows at least this many places
MAX_MANIFEST_BYTES = 64 * 1024
SCHEMA_VERSION = 1
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")
_REPOSITORY = re.compile(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})/[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}\Z")
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])(?:\..*)?\Z", re.I)


class ManifestError(Exception):
    pass


def _object(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ManifestError("Invalid or unsupported manifest fields.")
    return value


def _text(value, limit=512, empty=False):
    if (not isinstance(value, str) or len(value) > limit or (not empty and not value.strip())
            or any(ord(c) < 32 or ord(c) == 127 or 0x202A <= ord(c) <= 0x202E
                   or 0x2066 <= ord(c) <= 0x2069 for c in value)):
        raise ManifestError("Invalid manifest text.")
    return value


def _list(value, limit=64):
    if not isinstance(value, list) or len(value) > limit:
        raise ManifestError("Invalid manifest list.")
    return value


def safe_relative_path(path):
    """An install-relative path, safe on Windows even when validation runs elsewhere."""
    _text(path, 240)
    if (ntpath.isabs(path) or ntpath.splitdrive(path)[0] or any(c in path for c in ':<>"|?*%$')
            or "\\" in path or path.startswith("~")):
        raise ManifestError("Paths must stay inside the game folder.")
    parts = path.split("/")
    if any(p in ("", ".", "..") or p[-1:] in (" ", ".") or _RESERVED.fullmatch(p) for p in parts):
        raise ManifestError("Paths must stay inside the game folder.")
    return path


def resolve_path(root, path):
    """Resolve an allowed relative path and reject existing symlinks or junction escapes."""
    safe_relative_path(path)
    root = os.path.realpath(os.path.abspath(root))
    target = os.path.realpath(os.path.join(root, *path.split("/")))
    try:
        inside = os.path.normcase(os.path.commonpath((root, target))) == os.path.normcase(root)
    except ValueError:
        inside = False
    if not inside:
        raise ManifestError("Paths must stay inside the game folder.")
    return target


def repository(value):
    """A GitHub owner/repo, never an arbitrary URL or transport."""
    _text(value, 140)
    if not _REPOSITORY.fullmatch(value) or value.split("/")[1] in (".", "..") or value.endswith(".git"):
        raise ManifestError("Use a GitHub owner/repo.")
    return value


def github_url(value):
    """Strict public HTTPS GitHub URL for callers handling author release metadata."""
    _text(value, 2048)
    try:
        p = urlsplit(value)
    except ValueError as e:
        raise ManifestError("Only public HTTPS GitHub URLs are allowed.") from e
    if (p.scheme != "https" or p.netloc != "github.com" or p.query or p.fragment
            or "%" in p.path or "\\" in value or any(s in (".", "..") for s in p.path.split("/"))):
        raise ManifestError("Only public HTTPS GitHub URLs are allowed.")
    return value


def validate_external(m):
    """Version 1 is data only: it can select no Python adapter, hooks, imports or environment."""
    allowed = ("schema_version", "id", "title", "numeral", "accent", "adapter", "platform", "author",
               "repository", "releases", "requirements", "exe", "args", "cwd", "build", "settings",
               "controls", "online", "replays", "logo", "license", "credits", "short", "subtitle",
               "version", "order", "sections")
    required = ("schema_version", "id", "title", "numeral", "accent", "adapter", "platform", "author",
                "repository", "exe", "license", "credits")
    _object(m, allowed, required)
    if type(m["schema_version"]) is not int or m["schema_version"] != SCHEMA_VERSION or m["adapter"] != "generic":
        raise ManifestError("Unsupported public manifest version or adapter.")
    if not isinstance(m["id"], str) or not _ID.fullmatch(m["id"]) or _RESERVED.fullmatch(m["id"]):
        raise ManifestError("Invalid game id.")
    if m["id"].lower() in ("t4", "t5dr"):
        raise ManifestError("A third-party game cannot replace a built-in game.")
    for key in ("title", "author", "license"):
        _text(m[key], 160)
    _text(m["numeral"], 12)
    _text(m["platform"], 24)
    repository(m["repository"])
    if not isinstance(m["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", m["accent"]):
        raise ManifestError("Invalid accent colour.")
    for key in ("short", "subtitle", "version"):
        if key in m:
            _text(m[key], 160, empty=key == "subtitle")
    if "order" in m and (type(m["order"]) is not int or not 0 <= m["order"] <= 10000):
        raise ManifestError("Invalid game order.")
    for key in ("exe", "cwd", "replays", "logo"):
        if key in m:
            safe_relative_path(m[key])
    if not m["exe"].lower().endswith(".exe"):
        raise ManifestError("The game must name its own executable.")
    if "version" in m:
        match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*))?", m["version"])
        if (not match or len(m["version"]) > 100
                or any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in (match.group(4) or "").split("."))):
            raise ManifestError("Versions must use a semantic release tag.")
    for arg in _list(m.get("args", []), 32):
        _text(arg, 1024, empty=True)
    for credit in _list(m["credits"], 32):
        _text(credit, 256)
    sections = _list(m.get("sections", ["play", "settings"]), len(SECTIONS))
    if not sections or any(not isinstance(s, str) or s not in SECTIONS for s in sections) or len(set(sections)) != len(sections):
        raise ManifestError("Invalid game sections.")
    seen = set()
    for requirement in _list(m.get("requirements", []), 16):
        _object(requirement, ("id", "label", "kind", "version", "sha256"), ("id", "label", "kind", "version", "sha256"))
        if (not isinstance(requirement["id"], str) or not _ID.fullmatch(requirement["id"])
                or requirement["id"] in seen or requirement["id"] == "folder"):
            raise ManifestError("Invalid or duplicate requirement id.")
        seen.add(requirement["id"])
        _text(requirement["label"], 160)
        _text(requirement["version"], 160)
        if requirement["kind"] not in ("iso", "file") or not isinstance(requirement["sha256"], str) or not _SHA256.fullmatch(requirement["sha256"]):
            raise ManifestError("Requirements need a file kind and SHA-256.")
    if "releases" in m:
        releases = _object(m["releases"], ("channel", "asset", "verification"), ("channel", "asset", "verification"))
        if releases["channel"] not in ("stable", "prerelease"):
            raise ManifestError("Invalid release channel.")
        safe_relative_path(releases["asset"])
        if "/" in releases["asset"] or not releases["asset"].lower().endswith(".zip"):
            raise ManifestError("A release asset must name a ZIP file.")
        verification = _object(releases["verification"], ("method", "sha256"), ("method",))
        if verification["method"] == "sha256":
            if not isinstance(verification.get("sha256"), str) or not _SHA256.fullmatch(verification["sha256"]):
                raise ManifestError("A pinned release needs its SHA-256.")
        elif verification["method"] != "github-sha256" or "sha256" in verification:
            raise ManifestError("Unsupported release verification.")
    if "build" in m:
        build = _object(m["build"], ("instructions",), ("instructions",))
        _text(build["instructions"], 2048)
    if "settings" in m:
        settings = _object(m["settings"], ("file", "cyclers"), ("file", "cyclers"))
        safe_relative_path(settings["file"])
        seen = set()
        for cycler in _list(settings["cyclers"], 32):
            _object(cycler, ("id", "label", "key", "options"), ("id", "label", "key", "options"))
            if not isinstance(cycler["id"], str) or not _ID.fullmatch(cycler["id"]) or cycler["id"] in seen:
                raise ManifestError("Invalid or duplicate setting id.")
            seen.add(cycler["id"])
            _text(cycler["label"], 160)
            _text(cycler["key"], 80)
            if not cycler["options"]:
                raise ManifestError("A setting needs options.")
            for option in _list(cycler["options"], 32):
                _object(option, ("value", "label"), ("value", "label"))
                _text(option["label"], 160)
                value = option["value"]
                if isinstance(value, str):
                    _text(value, 256, empty=True)
                elif value is not None and (type(value) not in (int, float, bool) or (type(value) is float and not math.isfinite(value))):
                    raise ManifestError("Setting options must be JSON scalars.")
    if "controls" in m:
        controls = _object(m["controls"], ("file",), ("file",))
        safe_relative_path(controls["file"])
    # These paths are preserved across updates; they must never cover executable code.
    data_paths = [m[key]["file"] for key in ("settings", "controls") if key in m]
    if "replays" in m:
        data_paths.append(m["replays"])
    executable = m["exe"].casefold()
    for path in data_paths:
        path = path.casefold()
        if path == executable or path.startswith(executable + "/") or executable.startswith(path + "/"):
            raise ManifestError("Player data must not overlap the executable.")
    online = _object(m.get("online", {"mode": "none"}), ("mode", "arrangement"), ("mode",))
    if online["mode"] not in ("none", "own", "lobby"):
        raise ManifestError("Invalid online mode.")
    if "arrangement" in online:
        _text(online["arrangement"], 512)
    if online["mode"] == "lobby" and not online.get("arrangement"):
        raise ManifestError("Lobby integration needs an arrangement.")
    out = dict(m)
    out.setdefault("subtitle", "")
    out.setdefault("short", m["title"])
    out.setdefault("args", [])
    out.setdefault("requirements", [])
    out["sections"] = list(sections)
    out["online"] = dict(online)
    return out


def user_dir():
    base = os.environ.get("OPENRECOMP_HOME")
    if not base:
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "OpenRecomp")
    return os.path.abspath(os.path.expandvars(os.path.expanduser(base)))


def user_games_dir():
    return os.path.join(user_dir(), "games")


def art_dir(game_id):
    return os.path.join(user_dir(), "art", game_id)


def validate(m):
    """The manifest with its defaults, ManifestError when something a screen needs is missing."""
    if not isinstance(m, dict):
        raise ManifestError("The manifest is not a JSON object.")
    if "schema_version" in m:
        return validate_external(m)
    for key in ("id", "title", "numeral", "accent", "adapter"):
        if not isinstance(m.get(key), str) or not m[key].strip():
            raise ManifestError(f"The manifest has no \"{key}\".")
    if m["adapter"] not in ADAPTERS:
        raise ManifestError(f"Unknown adapter \"{m['adapter']}\".")
    if not all(c.isalnum() or c in "-_" for c in m["id"]):
        raise ManifestError("The id may only hold letters, digits, - and _.")
    if len(m["accent"]) != 7 or m["accent"][0] != "#":
        raise ManifestError("accent must be a colour like #5B93FF.")
    sections = m.get("sections") or ["play", "settings"]
    bad = [s for s in sections if s not in SECTIONS]
    if bad:
        raise ManifestError(f"Unknown section: {bad[0]}.")
    if m["adapter"] == "generic" and not m.get("exe"):
        raise ManifestError("A generic game needs \"exe\".")
    out = dict(m)
    out["sections"] = list(sections)
    out.setdefault("subtitle", "")
    out.setdefault("platform", "")
    out.setdefault("short", m["title"])
    out.setdefault("locations", [])
    return out


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ManifestError("Duplicate JSON fields are not allowed.")
        out[key] = value
    return out


def parse_bytes(data):
    """Parse a bounded JSON document without duplicate fields or non-JSON numbers."""
    if not isinstance(data, bytes) or len(data) > MAX_MANIFEST_BYTES:
        raise ManifestError("The manifest exceeds the size limit.")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("Invalid JSON number")))
        return validate(value)
    except (UnicodeError, ValueError, RecursionError, TypeError) as e:
        raise ManifestError("The manifest is not valid JSON.") from e


def load_file(path):
    try:
        with open(path, "rb") as f:
            return parse_bytes(f.read(MAX_MANIFEST_BYTES + 1))
    except OSError as e:
        raise ManifestError(f"Cannot read the file: {e}") from e


def load_all(dirs=None):
    """-> (manifests, problems). Public user files cannot select trusted adapters."""
    found, problems = {}, []
    for d in dirs or (BUILTIN_DIR, user_games_dir()):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith(".json"):
                continue
            path = os.path.join(d, name)
            try:
                m = load_file(path)
                if os.path.normcase(os.path.abspath(d)) == os.path.normcase(os.path.abspath(user_games_dir())):
                    m = validate_external(m)
            except ManifestError as e:
                problems.append(f"{name}: {e}")
                continue
            found[m["id"]] = m
    return sorted(found.values(), key=lambda m: (m.get("order", 100), m["title"])), problems


def install(path):
    """Atomically register a public manifest, without copying game files or executing code."""
    m = validate_external(load_file(path))
    os.makedirs(user_games_dir(), exist_ok=True)
    dest = os.path.join(user_games_dir(), m["id"] + ".json")
    if os.path.islink(dest):
        raise ManifestError("A manifest destination cannot be a link.")
    resolve_path(user_games_dir(), m["id"] + ".json")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=user_games_dir(),
                                         prefix=".manifest-", suffix=".tmp", delete=False) as f:
            tmp = f.name
            json.dump(m, f, ensure_ascii=False, indent=1)
        os.replace(tmp, dest)
    except OSError as e:
        raise ManifestError("Cannot save the manifest.") from e
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    return m


def load_config():
    try:
        with open(os.path.join(user_dir(), "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError("The configuration is not a JSON object.")
    folder = user_dir()
    path = os.path.join(folder, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    except FileNotFoundError:
        pass
    else:
        if not isinstance(existing, dict):
            raise ValueError("The existing configuration is not a JSON object.")
    os.makedirs(folder, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                         prefix=".config-", suffix=".tmp", delete=False) as f:
            tmp = f.name
            json.dump(cfg, f, indent=1)
        os.replace(tmp, path)
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
