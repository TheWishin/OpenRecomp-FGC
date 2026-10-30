"""Games on the launcher: one JSON manifest per game (games/*.json, plus the player's own in the user folder)."""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BUILTIN_DIR = os.path.join(os.path.dirname(HERE), "games")
SECTIONS = ("play", "online", "build", "replays", "settings")
ADAPTERS = ("t5dr", "t4", "generic")
TOTAL_SLOTS = 6                        # the shelf always shows at least this many places


class ManifestError(Exception):
    pass


def user_dir():
    base = os.environ.get("OPENRECOMP_HOME")
    if not base:
        base = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "OpenRecomp")
    return base


def user_games_dir():
    return os.path.join(user_dir(), "games")


def art_dir(game_id):
    return os.path.join(user_dir(), "art", game_id)


def validate(m):
    """The manifest with its defaults, ManifestError when something a screen needs is missing."""
    if not isinstance(m, dict):
        raise ManifestError("Das Manifest ist kein JSON-Objekt.")
    for key in ("id", "title", "numeral", "accent", "adapter"):
        if not isinstance(m.get(key), str) or not m[key].strip():
            raise ManifestError(f"Im Manifest fehlt \"{key}\".")
    if m["adapter"] not in ADAPTERS:
        raise ManifestError(f"Unbekannter Adapter \"{m['adapter']}\".")
    if not all(c.isalnum() or c in "-_" for c in m["id"]):
        raise ManifestError("Die id darf nur Buchstaben, Ziffern, - und _ enthalten.")
    if len(m["accent"]) != 7 or m["accent"][0] != "#":
        raise ManifestError("accent muss eine Farbe wie #5B93FF sein.")
    sections = m.get("sections") or ["play", "settings"]
    bad = [s for s in sections if s not in SECTIONS]
    if bad:
        raise ManifestError(f"Unbekannter Bereich: {bad[0]}.")
    if m["adapter"] == "generic" and not m.get("exe"):
        raise ManifestError("Ein generic-Spiel braucht \"exe\".")
    out = dict(m)
    out["sections"] = list(sections)
    out.setdefault("subtitle", "")
    out.setdefault("short", m["title"])
    out.setdefault("locations", [])
    return out


def load_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            return validate(json.load(f))
    except OSError as e:
        raise ManifestError(f"Datei nicht lesbar: {e}") from e
    except ValueError as e:
        raise ManifestError(f"Kein gültiges JSON: {e}") from e


def load_all(dirs=None):
    """-> (manifests, problems). Built-in ones first, a later file with the same id replaces an earlier one."""
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
            except ManifestError as e:
                problems.append(f"{name}: {e}")
                continue
            found[m["id"]] = m
    return sorted(found.values(), key=lambda m: (m.get("order", 100), m["title"])), problems


def install(path):
    """Copy a player's manifest into the user folder. -> the manifest; ManifestError when it is not valid."""
    m = load_file(path)
    os.makedirs(user_games_dir(), exist_ok=True)
    dest = os.path.join(user_games_dir(), m["id"] + ".json")
    if os.path.abspath(path) != os.path.abspath(dest):
        shutil.copyfile(path, dest)
    return m


def load_config():
    try:
        with open(os.path.join(user_dir(), "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(user_dir(), exist_ok=True)
    path = os.path.join(user_dir(), "config.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    os.replace(tmp, path)
