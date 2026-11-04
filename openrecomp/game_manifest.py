"""Game manifest version 2: a game on the shelf from one JSON file, without launcher code (docs/ADD_A_GAME.md).

Version 2 says where the game is (marker files + places to look), how to start and stop it (exe, arguments,
working folder, environment, close the window first), its tile picture (the player's own files only), which
settings to show (choice / toggle into an environment variable, an argument, an INI key or a JSON key), whether
it has online play of its own, and where its releases are for the update check (GitHub repository, asset name,
signature key or "unsigned"). It is data only: no code, no shell, no %VAR% expansion, every path stays inside the
game's folder (checked again when it is used). Unknown fields are reported and ignored; anything else wrong
makes the manifest "broken" and the shelf shows the reason.

Bundled manifests (games/*.json) may also name a built-in adapter (`code_adapter`) that does what needs code;
when that adapter is not part of this launcher, the manifest alone is used. A player's own manifest
(%OPENRECOMP_HOME%\\games\\*.json) never selects code.
"""
import json
import os
import re

SCHEMA = 2
SECTIONS = ("play", "online", "build", "replays", "settings")
CODE_ADAPTERS = ("tag2",)                    # built-in adapters a bundled manifest may hand the game to
RESERVED_IDS = ("t4", "t5dr")
LANGS = ("en", "de", "es", "fr", "ja", "ko", "pt-BR")
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_ENV = re.compile(r"[A-Z_][A-Z0-9_]{0,63}\Z")
# Never set by a manifest: what decides where Windows and Python find programs and the player's folders.
_ENV_DENIED = re.compile(r"(PATH|PATHEXT|COMSPEC|SYSTEMROOT|SYSTEMDRIVE|WINDIR|TEMP|TMP|APPDATA|LOCALAPPDATA|USERPROFILE|"
                         r"HOMEDRIVE|HOMEPATH|PROGRAMDATA|PROGRAMFILES.*|COMMONPROGRAMFILES.*|PSMODULEPATH|"
                         r"__COMPAT_LAYER|PYTHON.*|OPENRECOMP.*|QT_.*|SSL_.*|REQUESTS_.*|.*_PROXY)\Z")
_SEMVER = re.compile(r"v?(\d{1,6})\.(\d{1,6})\.(\d{1,6})(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?")
_CACHE_NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\.(?:png|jpg|jpeg|webp)\Z")
_SEARCH_VARS = ("%USERPROFILE%", "%LOCALAPPDATA%", "{beside}")
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGE = 8 * 1024 * 1024
MAX_TEXT_FILE = 1024 * 1024

FIELDS = {
    "": ("schema_version", "id", "title", "short", "subtitle", "platform", "numeral", "accent", "order", "sections",
         "author", "license", "credits", "source", "code_adapter", "install", "start", "stop", "art", "updates",
         "online", "settings", "shelf"),
    "install": ("detect", "search"),
    "start": ("exe", "args", "cwd", "env"),
    "stop": ("close_window_seconds",),
    "art": ("file", "cache"),
    "updates": ("repository", "repository_id", "asset", "channel", "verification", "installed_version"),
    "verification": ("method", "key", "sums", "signature", "format", "statement"),
    "online": ("mode", "note"),
    "setting": ("id", "label", "type", "options", "default", "target"),
    "option": ("value", "label"),
    "target": ("env", "arg", "ini", "json", "section", "key"),
    "version_rule": ("file", "json_key", "prefix"),
}


class ManifestError(Exception):
    pass


def _fail(where, why):
    raise ManifestError(f"{where}: {why}" if where else why)


def _obj(value, where, kind, warnings, required=()):
    if not isinstance(value, dict):
        _fail(where, "must be an object")
    for key in value:
        if key not in FIELDS[kind]:
            warnings.append(f"{where + '.' if where else ''}{key}: unknown field, ignored")
    for key in required:
        if key not in value:
            _fail(where, f'"{key}" is missing')
    return value


def _text(value, where, limit=200, empty=False):
    if (not isinstance(value, str) or len(value) > limit or (not empty and not value.strip())
            or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF or 0x202A <= ord(c) <= 0x202E
                   or 0x2066 <= ord(c) <= 0x2069 for c in value)):
        _fail(where, f"must be plain text of at most {limit} characters")
    return value


def _label(value, where):
    """A label: one text, or one text per language ({"en": ..., "de": ...}; English is needed)."""
    if isinstance(value, dict):
        if "en" not in value or any(k not in LANGS for k in value):
            _fail(where, "a label per language needs \"en\" and only " + ", ".join(LANGS))
        return {k: _text(v, f"{where}.{k}", 160) for k, v in value.items()}
    return _text(value, where, 160)


def label_text(label, lang):
    if isinstance(label, dict):
        return label.get(lang) or label.get((lang or "").split("-")[0]) or label["en"]
    return label


def _list(value, where, limit):
    if not isinstance(value, list) or len(value) > limit:
        _fail(where, f"must be a list of at most {limit}")
    return value


def _path(value, where):
    from .manifest import ManifestError as V1Error, safe_relative_path
    try:
        return safe_relative_path(_text(value, where, 240))
    except V1Error:
        _fail(where, "must be a path inside the game's folder (with /, no drive, no ..)")


def _search(value, where):
    """A place to look for an install: one of %USERPROFILE%, %LOCALAPPDATA%, {beside} (the folder that holds the
    launcher's folder), then relative parts; * only in the last part."""
    _text(value, where, 240)
    head = next((v for v in _SEARCH_VARS if value.startswith(v + "/")), None)
    if head is None:
        _fail(where, "must start with %USERPROFILE%/, %LOCALAPPDATA%/ or {beside}/")
    rest = value[len(head) + 1:].split("/")
    if (not rest or any(p in ("", ".", "..") or any(c in p for c in ':<>"|?\\%$') for p in rest)
            or any("*" in p for p in rest[:-1])):
        _fail(where, "the parts after the start must be plain folder names (* only in the last one)")
    return value


def validate(m, builtin=False):
    """-> (manifest with defaults, warnings). ManifestError with the reason when it cannot be used."""
    warnings = []
    _obj(m, "", "", warnings, ("schema_version", "id", "title", "platform", "numeral", "accent", "start"))
    if type(m["schema_version"]) is not int or m["schema_version"] != SCHEMA:
        _fail("schema_version", f"must be {SCHEMA}")
    if not isinstance(m["id"], str) or not _ID.fullmatch(m["id"]):
        _fail("id", "lower-case letters, digits, - and _ only (at most 64)")
    if m["id"] in RESERVED_IDS:
        _fail("id", "is a built-in game")
    for key, limit in (("title", 120), ("platform", 24), ("numeral", 12)):
        _text(m[key], key, limit)
    for key in ("short", "subtitle", "author", "license", "source"):
        if key in m:
            _text(m[key], key, 160, empty=key == "subtitle")
    if not isinstance(m["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", m["accent"]):
        _fail("accent", "must be a colour like #F2A33A")
    if "order" in m and (type(m["order"]) is not int or not 0 <= m["order"] <= 10000):
        _fail("order", "must be a whole number 0..10000")
    for i, credit in enumerate(_list(m.get("credits", []), "credits", 32)):
        _text(credit, f"credits[{i}]", 256)
    sections = _list(m.get("sections", ["play", "settings"]), "sections", len(SECTIONS))
    if not sections or any(s not in SECTIONS for s in sections) or len(set(sections)) != len(sections):
        _fail("sections", "must name some of " + ", ".join(SECTIONS) + " once each")
    if m.get("shelf", "always") not in ("always", "found"):
        _fail("shelf", 'must be "always" or "found" (only when the game is found on this PC)')
    if "code_adapter" in m:
        if not builtin:
            _fail("code_adapter", "only a manifest that comes with the launcher may name launcher code")
        if m["code_adapter"] not in CODE_ADAPTERS:
            _fail("code_adapter", "unknown")

    install = _obj(m.get("install", {}), "install", "install", warnings)
    detect = _list(install.get("detect", []), "install.detect", 8)
    for i, p in enumerate(detect):
        _path(p, f"install.detect[{i}]")
    for i, p in enumerate(_list(install.get("search", []), "install.search", 8)):
        _search(p, f"install.search[{i}]")

    start = _obj(m["start"], "start", "start", warnings, ("exe",))
    _path(start["exe"], "start.exe")
    if not start["exe"].lower().endswith(".exe"):
        _fail("start.exe", "must name the game's own .exe")
    for i, a in enumerate(_list(start.get("args", []), "start.args", 64)):
        _text(a, f"start.args[{i}]", 1024, empty=True)
    if "cwd" in start:
        _path(start["cwd"], "start.cwd")
    env = _obj(start.get("env", {}), "start.env", "start", [], ())   # names checked below, not as fields
    for name, value in env.items():
        if not _ENV.fullmatch(name) or _ENV_DENIED.fullmatch(name):
            _fail(f"start.env.{name}", "this variable name cannot be set by a manifest")
        _text(value, f"start.env.{name}", 1024, empty=True)

    stop = _obj(m.get("stop", {}), "stop", "stop", warnings)
    wait = stop.get("close_window_seconds", 0)
    if type(wait) is not int or not 0 <= wait <= 30:
        _fail("stop.close_window_seconds", "must be 0..30")

    art = _obj(m.get("art", {}), "art", "art", warnings)
    if "file" in art:
        _path(art["file"], "art.file")
        if not art["file"].lower().endswith(IMAGE_TYPES):
            _fail("art.file", "must be a PNG, JPG or WebP picture")
    if "cache" in art and (not isinstance(art["cache"], str) or not _CACHE_NAME.fullmatch(art["cache"])):
        _fail("art.cache", "must be a picture file name like hero.png")

    if "updates" in m:
        _updates(m["updates"], warnings)

    online = _obj(m.get("online", {"mode": "none"}), "online", "online", warnings, ("mode",))
    if online["mode"] not in ("none", "external"):
        _fail("online.mode", "must be none or external")
    if "note" in online:
        _label(online["note"], "online.note")

    seen = set()
    for i, s in enumerate(_list(m.get("settings", []), "settings", 32)):
        _setting(s, f"settings[{i}]", seen, warnings)

    out = dict(m)
    out.update(adapter="manifest", short=m.get("short", m["title"]), subtitle=m.get("subtitle", ""),
               sections=list(sections), locations=[], builtin=bool(builtin))
    return out, warnings


def _updates(u, warnings):
    from .manifest import ManifestError as V1Error, repository
    _obj(u, "updates", "updates", warnings, ("repository", "repository_id", "asset", "verification"))
    try:
        repository(u["repository"])
    except V1Error:
        _fail("updates.repository", "must be a GitHub owner/repo")
    if not isinstance(u["repository_id"], str) or not re.fullmatch(r"[1-9][0-9]{0,11}", u["repository_id"]):
        _fail("updates.repository_id", "must be the repository's number (GitHub API: id)")
    asset = _text(u["asset"], "updates.asset", 120)
    plain = asset.replace("{version}", "1.0.0").replace("{tag}", "v1.0.0")
    if ("{version}" not in asset and "{tag}" not in asset) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.zip", plain):
        _fail("updates.asset", "must be a .zip name with {version} or {tag} in it")
    if u.get("channel", "stable") not in ("stable", "prerelease"):
        _fail("updates.channel", "must be stable or prerelease")
    v = _obj(u["verification"], "updates.verification", "verification", warnings, ("method",))
    if v["method"] == "ed25519":
        if not isinstance(v.get("key"), str) or not re.fullmatch(r"[0-9a-f]{64}", v["key"]):
            _fail("updates.verification.key", "must be the Ed25519 public key (64 lower-case hex digits)")
        for key, default in (("sums", "SHA256SUMS"), ("signature", "SHA256SUMS.sig")):
            name = _text(v.get(key, default), f"updates.verification.{key}", 80)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
                _fail(f"updates.verification.{key}", "must be a file name of the release")
        for key in ("format", "statement"):
            if key in v:
                _text(v[key], f"updates.verification.{key}", 120)
    elif v["method"] in ("github-sha256", "unsigned"):
        extra = set(v) - {"method"}
        if extra:
            _fail("updates.verification", f"{v['method']} takes no {', '.join(sorted(extra))}")
    else:
        _fail("updates.verification.method", "must be ed25519, github-sha256 or unsigned")
    for i, rule in enumerate(_list(u.get("installed_version", []), "updates.installed_version", 4)):
        _obj(rule, f"updates.installed_version[{i}]", "version_rule", warnings, ("file",))
        _path(rule["file"], f"updates.installed_version[{i}].file")
        if ("json_key" in rule) == ("prefix" in rule):
            _fail(f"updates.installed_version[{i}]", "needs json_key or prefix (one of them)")
        _text(rule.get("json_key", rule.get("prefix")), f"updates.installed_version[{i}]", 80)


def _setting(s, where, seen, warnings):
    _obj(s, where, "setting", warnings, ("id", "label", "type", "target"))
    if not isinstance(s["id"], str) or not _ID.fullmatch(s["id"]) or s["id"] in seen:
        _fail(f"{where}.id", "missing, not a plain id, or used twice")
    seen.add(s["id"])
    _label(s["label"], f"{where}.label")
    if s["type"] == "toggle":
        if "options" in s:
            _fail(f"{where}.options", "a toggle has no options (it is on or off)")
        if "default" in s and type(s["default"]) is not bool:
            _fail(f"{where}.default", "a toggle's default is true or false")
    elif s["type"] == "choice":
        options = _list(s.get("options"), f"{where}.options", 32)
        if not options:
            _fail(f"{where}.options", "a choice needs options")
        values = []
        for j, o in enumerate(options):
            _obj(o, f"{where}.options[{j}]", "option", warnings, ("value", "label"))
            if isinstance(o["value"], str):
                _text(o["value"], f"{where}.options[{j}].value", 256, empty=True)
            elif type(o["value"]) not in (int, bool):
                _fail(f"{where}.options[{j}].value", "must be text, a whole number or true/false")
            _label(o["label"], f"{where}.options[{j}].label")
            values.append(o["value"])
        if "default" in s and not any(type(v) is type(s["default"]) and v == s["default"] for v in values):
            _fail(f"{where}.default", "must be one of the options' values")
    else:
        _fail(f"{where}.type", "must be choice or toggle")
    t = _obj(s["target"], f"{where}.target", "target", warnings)
    kinds = [k for k in ("env", "arg", "ini", "json") if k in t]
    if len(kinds) != 1:
        _fail(f"{where}.target", "needs exactly one of env, arg, ini, json")
    kind = kinds[0]
    if kind == "env":
        if not isinstance(t["env"], str) or not _ENV.fullmatch(t["env"]) or _ENV_DENIED.fullmatch(t["env"]):
            _fail(f"{where}.target.env", "this variable name cannot be set by a manifest")
    elif kind == "arg":
        _text(t["arg"], f"{where}.target.arg", 200)
        if t["arg"].count("{value}") != 1:
            _fail(f"{where}.target.arg", "must hold {value} once, e.g. --scale={value}")
    else:
        _path(t[kind], f"{where}.target.{kind}")
        _text(t.get("key", ""), f"{where}.target.key", 80)
        if kind == "ini":
            _text(t.get("section", ""), f"{where}.target.section", 80)
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", t["key"]) or not re.fullmatch(r"[A-Za-z0-9_. -]+", t["section"]):
                _fail(f"{where}.target", "an INI target needs a plain section and key")


def broken(path, data, error):
    """A shelf entry for a manifest that cannot be used: its title when it has one, and the reason."""
    m = data if isinstance(data, dict) else {}
    gid = m.get("id") if isinstance(m.get("id"), str) and _ID.fullmatch(m.get("id") or "") else ""
    gid = gid or re.sub(r"[^a-z0-9_-]", "-", os.path.splitext(os.path.basename(path))[0].lower())[:64] or "broken"
    title = m.get("title") if isinstance(m.get("title"), str) and 0 < len(m.get("title")) <= 120 else gid
    return dict(id=gid, title=title, short=title, subtitle="", platform="", numeral="!", accent="#8A8F98",
                adapter="broken", sections=["play"], locations=[], order=m.get("order", 9000) if type(m.get("order")) is int else 9000,
                broken=f"{os.path.basename(path)}: {error}")


# ------------------------------------------------------------------------------------------------ installed version
def installed_version(root, rules):
    """The first version a rule finds in the install: a JSON key of a JSON file, or the version right after a
    prefix in a text file (files are read up to 1 MB; no pattern language)."""
    for rule in rules or ():
        try:
            from .manifest import resolve_path
            path = resolve_path(root, rule["file"])
            with open(path, "rb") as f:
                raw = f.read(MAX_TEXT_FILE + 1)
            if len(raw) > MAX_TEXT_FILE:
                continue
            text = raw.decode("utf-8-sig", "replace")
            if "json_key" in rule:
                value = json.loads(text).get(rule["json_key"])
                found = value if isinstance(value, str) else ""
            else:
                at = text.find(rule["prefix"])
                found = text[at + len(rule["prefix"]):at + len(rule["prefix"]) + 40] if at >= 0 else ""
            m = _SEMVER.match(found.strip()) if found else None
            if m:
                return m.group(0).lstrip("v")
        except Exception:  # noqa: BLE001 -- a player's file may hold anything
            continue
    return ""


# ------------------------------------------------------------------------------------------------ INI settings
def ini_read(path, section, key):
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT_FILE + 1)
    except FileNotFoundError:
        return None
    if len(raw) > MAX_TEXT_FILE:
        raise ValueError("the INI file is too large")
    current = ""
    for line in raw.decode("utf-8-sig").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1].strip()
        elif current.lower() == section.lower() and "=" in s and not s.startswith((";", "#")):
            k, v = s.split("=", 1)
            if k.strip().lower() == key.lower():
                return v.strip()
    return None


def ini_write(path, section, key, value):
    """Set one key; every other line stays as it was. Atomic replace."""
    import tempfile
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT_FILE + 1)
    except FileNotFoundError:
        raw = b""
    if len(raw) > MAX_TEXT_FILE:
        raise ValueError("the INI file is too large")
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    current, section_end, done = "", None, False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if current.lower() == section.lower() and section_end is None:
                section_end = i
            current = s[1:-1].strip()
        elif current.lower() == section.lower() and "=" in s and not s.startswith((";", "#")):
            if s.split("=", 1)[0].strip().lower() == key.lower():
                lines[i] = f"{key}={value}"
                done = True
                break
    if not done:
        if current.lower() == section.lower() and section_end is None:
            section_end = len(lines)
        if section_end is None:
            lines += ([""] if lines and lines[-1].strip() else []) + [f"[{section}]", f"{key}={value}"]
        else:
            while section_end > 0 and not lines[section_end - 1].strip():
                section_end -= 1                   # after the section's last line, before the blank line(s)
            lines.insert(section_end, f"{key}={value}")
    data = (nl.join(lines) + nl).encode("utf-8")
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".ini-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write((b"\xef\xbb\xbf" if bom else b"") + data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def setting_text(value):
    """How a setting's value is written into an argument, the environment or an INI file."""
    if value is True:
        return "1"
    if value is False:
        return "0"
    return str(value)


def json_read(path):
    """A game's JSON settings file as an object ({} when it does not exist)."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_TEXT_FILE + 1)
    except FileNotFoundError:
        return {}
    if len(raw) > MAX_TEXT_FILE:
        raise ValueError("the JSON file is too large")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("the JSON file is not an object")
    return value


def json_write(path, key, value):
    """Set one top-level key; the other keys stay. Atomic replace."""
    import tempfile
    data = json_read(path)
    data[key] = value
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".json-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def arg_text(template, value):
    return template.replace("{value}", setting_text(value))


# ------------------------------------------------------------------------------------------------ finding and stopping
def launcher_parent():
    """The folder that holds the launcher's folder ({beside}): where Setup puts the games."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(here)


def search_paths(patterns):
    """install.search with its start resolved; existing folders only."""
    import glob
    out = []
    for p in patterns or ():
        if p.startswith("{beside}/"):
            base, rest = launcher_parent(), p[len("{beside}/"):]
        else:
            var, rest = p.split("/", 1)
            base = os.environ.get(var.strip("%"), "")
            if not base:
                continue
        parts = rest.split("/")
        pattern = os.path.join(glob.escape(base), *[glob.escape(x) for x in parts[:-1]], parts[-1])
        for path in sorted(glob.glob(pattern)):
            if os.path.isdir(path) and path not in out:
                out.append(path)
    return out


def close_windows(pid):
    """WM_CLOSE to the visible top-level windows of process pid (Process.CloseMainWindow). Returns how many."""
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):   # GW_OWNER
            found.append(hwnd)
        return True
    user32.EnumWindows(proc(each), 0)
    for hwnd in found:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
    return len(found)


# ------------------------------------------------------------------------------------------------ update check
UPDATE_CACHE = "manifest-updates.json"
UPDATE_SECONDS = 3600


def release_source(m):
    """The manifest's releases as a game_releases.Source (that repository's API and download rules only)."""
    from . import game_releases as gr
    u = m["updates"]
    v = u["verification"]
    signed = v["method"] == "ed25519"
    return gr.Source(id=m["id"], title=m["title"], repository=u["repository"], repository_id=u["repository_id"],
                     asset=u["asset"], top="", folder="", sums=(v.get("sums", "SHA256SUMS"),) if signed else (),
                     signature=v.get("signature", "SHA256SUMS.sig") if signed else "", keys=(v["key"],) if signed else (),
                     statement=v.get("statement", f"OpenRecomp-game-release-signature-v1:{m['id']}"),
                     sig_format=v.get("format", "openrecomp-game-sig/1"))


def _cache_path():
    from .manifest import user_dir
    return os.path.join(user_dir(), UPDATE_CACHE)


def cached_update(m, now=None):
    import time
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            entry = json.load(f).get(m["id"])
        if (isinstance(entry, dict) and entry.get("repository") == (m.get("updates") or {}).get("repository")
                and 0 <= (now or time.time()) - entry.get("checked", 0) < UPDATE_SECONDS):
            return entry
    except (OSError, ValueError, AttributeError):
        pass
    return None


def store_update(m, entry):
    from .manifest import user_dir
    try:
        try:
            with open(_cache_path(), encoding="utf-8") as f:
                data = json.load(f)
            data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            data = {}
        data[m["id"]] = entry
        os.makedirs(user_dir(), exist_ok=True)
        tmp = _cache_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, _cache_path())
    except OSError:
        pass


def check_release(m, opener=None):
    """One update check: dict(checked, repository, offer=dict(version, tag, name, signed, sha256, size) | None, error).
    ed25519: the release's SHA256SUMS + signature are downloaded (small files) and must verify with the manifest's
    key and name the zip with GitHub's digest; otherwise nothing is offered."""
    import tempfile
    import time
    from . import game_releases as gr
    u = m["updates"]
    src = release_source(m)
    entry = dict(checked=time.time(), repository=u["repository"], offer=None, error="")
    try:
        offer = gr.latest(src, u.get("channel", "stable"), opener=opener)
        if offer and u["verification"]["method"] == "ed25519":
            if not offer.get("sig") or not offer.get("sums"):
                raise gr.ReleaseError("@setup.err_signature", "the release is not signed")
            with tempfile.TemporaryDirectory(prefix="openrecomp-check-") as work:
                sums_path, sig_path = os.path.join(work, "sums"), os.path.join(work, "sig")
                gr.download(src, offer["sums"]["url"], sums_path, limit=gr.MAX_SUMS, opener=opener)
                gr.download(src, offer["sig"]["url"], sig_path, limit=gr.MAX_SIG, opener=opener)
                with open(sums_path, "rb") as f, open(sig_path, "rb") as g:
                    sums, sig = f.read(), g.read()
            gr.check_signature(src, offer["version"], sums, sig, keys=src.keys)
            want = gr.parse_sums(sums.decode("utf-8", "replace"), offer["zip"]["name"])
            if not want or (offer["zip"].get("sha256") and want != offer["zip"]["sha256"]):
                raise gr.ReleaseError("@setup.err_checksum", "SHA256SUMS does not name the zip")
        if offer:
            entry["offer"] = dict(version=offer["version"], tag=offer["tag"], name=offer["name"],
                                  signed=u["verification"]["method"] == "ed25519",
                                  sha256=offer["zip"].get("sha256"), size=offer["zip"]["size"])
    except gr.ReleaseError as e:
        entry["error"] = e.key
    except Exception as e:  # noqa: BLE001 -- never a dead check
        entry["error"] = repr(e)[:200]
    return entry
