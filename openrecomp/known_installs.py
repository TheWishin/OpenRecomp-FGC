"""The installs of a game this launcher knows, for the Build page's switch (0.1.3): "Install in use" lists them and
picking one makes it THE folder for Play, Build and Online (config roots, the same as choosing the folder by hand).

Known = the folder in use, every folder the player used before (config known_roots, remembered whenever the chosen
folder changes), the installs this launcher made (its marker says installed_by OpenRecomp-FGC: beside the launcher, in
the launcher's own installs folder) -- each only while it still is an install of that game. Cheap: no drive scan, so the
page can ask on every redraw."""
import glob
import json
import os

from . import manifest as mf

MAX_REMEMBERED = 12
_MARKERS = {"t4": (("launcher", "t4core.py"),), "t5dr": (("launcher", "core.py"),)}
# Beside the launcher only the names a bundle zip / Setup gives a game folder; a developer's checkouts there are no
# installs of a player (they have no release marker either).
_FOLDER_GLOB = {"t4": ("T4",), "t5dr": ("T5DR-Online-*",)}


def _key(path):
    return os.path.normcase(os.path.realpath(path))


def is_install(gid, root):
    """A folder that holds this game's install (never a parent folder, never a half-unpacked one)."""
    if not isinstance(root, str) or not root or not os.path.isdir(root):
        return False
    markers = _MARKERS.get(gid)
    if not markers:
        return False
    return all(os.path.isfile(os.path.join(root, *parts)) for parts in markers)


def remember(config, gid, *roots):
    """Note roots as known installs of gid (newest first); returns True when the list changed. The caller saves."""
    known = config.setdefault("known_roots", {})
    if not isinstance(known, dict):
        known = config["known_roots"] = {}
    old = [r for r in known.get(gid) or [] if isinstance(r, str)]
    new = []
    for root in [r for r in roots if isinstance(r, str) and r] + old:
        if _key(root) not in {_key(r) for r in new}:
            new.append(os.path.abspath(root))
    new = new[:MAX_REMEMBERED]
    if new != old:
        known[gid] = new
        return True
    return False


def _made_here(gid, root):
    try:
        with open(os.path.join(root, "openrecomp-release.json"), encoding="utf-8") as stream:
            marker = json.load(stream)
    except (OSError, ValueError):
        return False
    return isinstance(marker, dict) and marker.get("game") == gid and marker.get("installed_by") == "OpenRecomp-FGC"


def _released(root):
    return any(os.path.isfile(os.path.join(root, name)) for name in ("release.json", "openrecomp-release.json"))


def _launcher_parent():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def candidates(config, gid):
    out = list((config.get("known_roots") or {}).get(gid) or [])
    chosen = (config.get("roots") or {}).get(gid)
    if isinstance(chosen, str):
        out.insert(0, chosen)
    parents = [_launcher_parent()]
    try:
        parents.append(os.path.join(mf.user_dir(), "installs", gid))
    except Exception:  # noqa: BLE001 -- no user folder yet: nothing installed there either
        pass
    for parent in parents:
        for pattern in _FOLDER_GLOB.get(gid, ()):
            for path in sorted(glob.glob(os.path.join(glob.escape(parent), pattern))):
                if _made_here(gid, path) or (_released(path) and os.path.normcase(parent) == os.path.normcase(_launcher_parent())):
                    out.append(path)
    return out


def known(config, gid, current=""):
    """[(root, version)] -- the folder in use first, then the others that still are installs of gid."""
    from .game_releases import installed_version
    seen, out = set(), []
    for root in ([current] if current else []) + candidates(config, gid):
        if not isinstance(root, str) or not root:
            continue
        key = _key(root)
        if key in seen or not is_install(gid, root):
            continue
        seen.add(key)
        version = installed_version(gid, root)
        if not version and gid == "t4":
            from .adapters.t4 import release_version
            version = release_version(root)
        out.append((os.path.abspath(root), version or ""))
    return out
