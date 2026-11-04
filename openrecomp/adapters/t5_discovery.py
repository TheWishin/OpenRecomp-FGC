"""Read-only, bounded discovery before offering a second T5DR install."""
import collections
import glob
import json
import os
import re
import string
import struct


MAX_METADATA = 256 * 1024
PATH_KEYS = {"root", "folder", "path", "install", "install_dir", "install_path", "installlocation",
             "t5dr_root", "t5dr", "out", "out_dir", "recent", "recent_folders", "recent_paths",
             "last_folder", "last_directory", "last_dir", "game_folder", "game_dir", "roots",
             "location", "installdir", "recent_directories"}


def _launcher_folder():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _drive_roots():
    return os.listdrives() if hasattr(os, "listdrives") else [
        letter + ":\\" for letter in string.ascii_uppercase if os.path.isdir(letter + ":\\")]


def _path(value, base=""):
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return ""
    value = os.path.expandvars(os.path.expanduser(value.strip()))
    # App Paths, DisplayIcon and uninstall records can name an executable, with arguments.
    match = re.match(r'^"([^\"]+)"', value)
    if match:
        value = match.group(1)
    elif ".exe" in value.lower():
        value = value[:value.lower().index(".exe") + 4]
    if base and not os.path.isabs(value):
        value = os.path.join(base, value)
    if value.lower().endswith((".exe", ".json")):
        value = os.path.dirname(value)
    return os.path.realpath(value)


def _metadata_paths(value, base="", selected=False, depth=0):
    if depth > 5:
        return []
    if isinstance(value, str):
        path = _path(value, base) if selected else ""
        return [path] if path else []
    if isinstance(value, list):
        return [path for item in value[:128] for path in _metadata_paths(item, base, selected, depth + 1)]
    if isinstance(value, dict):
        return [path for key, item in list(value.items())[:128]
                for path in _metadata_paths(item, base, selected or str(key).lower() in PATH_KEYS, depth + 1)]
    return []


def _json_paths(folder):
    try:
        with open(os.path.join(folder, "launcher.json"), encoding="utf-8-sig") as stream:
            data = stream.read(MAX_METADATA + 1)
        if len(data) <= MAX_METADATA:
            return _metadata_paths(json.loads(data), folder)
    except (OSError, ValueError, UnicodeError):
        pass
    return []


def _registry_paths():
    try:
        import winreg
    except ImportError:
        return []
    paths = []

    def values(hive, name):
        try:
            with winreg.OpenKey(hive, name, 0, winreg.KEY_READ) as key:
                found = {}
                for index in range(256):
                    try:
                        field, value, _kind = winreg.EnumValue(key, index)
                        found[field.lower()] = value
                    except OSError:
                        break
                return found
        except OSError:
            return {}

    hives = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
    for hive in hives:
        for prefix in (r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                       r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
            try:
                with winreg.OpenKey(hive, prefix, 0, winreg.KEY_READ) as key:
                    for index in range(4096):
                        try:
                            name = winreg.EnumKey(key, index)
                        except OSError:
                            break
                        record = values(hive, prefix + "\\" + name)
                        title = (name + " " + str(record.get("displayname", ""))).lower()
                        if "t5dr" in title or "tekken 5" in title:
                            paths.extend(record.get(field) for field in
                                         ("installlocation", "displayicon", "uninstallstring"))
            except OSError:
                pass
        for name in (r"Software\T5DR Online", r"Software\T5DROnline", r"Software\T5DR",
                     r"Software\T5DR Online\Setup", r"Software\T5DROnline\Setup",
                     r"Software\T5DR Online\Launcher", r"Software\T5DROnline\Launcher",
                     r"Software\Microsoft\Windows\CurrentVersion\App Paths\T5DR Online.exe"):
            record = values(hive, name)
            paths.extend(value for field, value in record.items()
                         if field in PATH_KEYS or field in ("", "installdir", "location", "recentfolders"))
    # RunMRU can retain the old launcher's location even after a portable move.
    record = values(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU")
    paths.extend(value.rstrip("\1") for value in record.values()
                 if isinstance(value, str) and ("t5dr" in value.lower() or "tekken 5" in value.lower()))
    # These retain redirected Desktop/Documents/Downloads locations (including OneDrive).
    record = values(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
    paths.extend(record.get(field) for field in
                 ("desktop", "personal", "{374de290-123f-4565-9164-39c4925e467b}"))
    return [path for value in paths for path in _metadata_paths(value, selected=True)]


def _shortcut_path(path):
    """Read only a shortcut's local LinkInfo target; never execute or resolve it through COM."""
    try:
        with open(path, "rb") as stream:
            data = stream.read(MAX_METADATA + 1)
        if len(data) > MAX_METADATA or len(data) < 76 or struct.unpack_from("<I", data)[0] != 76:
            return ""
        flags = struct.unpack_from("<I", data, 20)[0]
        offset = 76
        if flags & 1:
            offset += 2 + struct.unpack_from("<H", data, offset)[0]
        if not flags & 2:
            return ""
        size, header, link_flags, _volume, local = struct.unpack_from("<5I", data, offset)
        if size < 28 or offset + size > len(data) or not link_flags & 1:
            return ""
        unicode_offset = struct.unpack_from("<I", data, offset + 28)[0] if header >= 36 else 0
        start = unicode_offset or local
        if not 0 < start < size:
            return ""
        target = data[offset + start:offset + size]
        if unicode_offset:
            target = target[:next((i for i in range(0, len(target) - 1, 2)
                                   if target[i:i + 2] == b"\0\0"), len(target))]
            return target.decode("utf-16-le")
        return target.split(b"\0", 1)[0].decode("mbcs" if os.name == "nt" else "utf-8")
    except (OSError, ValueError, UnicodeError, struct.error):
        return ""


def _recent_paths():
    recent = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Recent")
    if not os.path.isabs(recent):
        return []
    try:
        with os.scandir(recent) as entries:
            names = sorted((entry.path for entry in entries if entry.name.lower().endswith(".lnk")),
                           key=str.casefold)[:512]
        return [target for name in names if (target := _shortcut_path(name))]
    except OSError:
        return []


def _directories(folder):
    try:
        with os.scandir(folder) as entries:
            result = []
            for entry in entries:
                try:
                    if (entry.is_dir(follow_symlinks=False) and not entry.is_symlink()
                            and not os.path.isjunction(entry.path)):
                        result.append(entry.path)
                except OSError:
                    pass
            return sorted(result, key=str.casefold)
    except OSError:
        return []


def _complete(folder):
    return (os.path.isfile(os.path.join(folder, "T5DR Online.exe"))
            and (os.path.isfile(os.path.join(folder, "launcher", "core.py"))
                 or all(os.path.isfile(os.path.join(folder, name)) for name in
                        ("release.json", os.path.join("python", "python.exe")))))


def existing_installs(manifest, config, parent=""):
    """Canonical existing roots, sorted for an explicit player choice; no runtime imports or writes."""
    launcher = _launcher_folder()
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    common = [os.path.join(home, name) for name in ("Desktop", "Downloads", "Documents")]
    bases = common + [launcher, os.path.dirname(launcher)] + ([parent] if parent else []) + _drive_roots()
    hints = _metadata_paths(config) + _registry_paths() + _recent_paths()
    hints += [os.environ.get("OPENRECOMP_T5DR_ROOT", "")]
    for pattern in manifest.get("locations") or []:
        if isinstance(pattern, str):
            hints.extend(glob.glob(os.path.expandvars(pattern)))
    pending = collections.deque([(folder, 2, False) for folder in bases]
                                + [(folder, 1, True) for folder in hints if folder])
    seen, found, metadata = {}, {}, set()
    metadata_hints = 0
    while pending:
        folder, remaining, hint = pending.popleft()
        folder = _path(folder)
        if not folder:
            continue
        # A recent build/output folder can be below its owning install.
        if hint:
            above = folder
            for _ in range(3):
                above = os.path.dirname(above)
                if _complete(above):
                    found[os.path.normcase(above)] = above
        key = os.path.normcase(folder)
        if seen.get(key, -1) >= remaining:
            continue
        seen[key] = remaining
        if _complete(folder):
            found[key] = folder
        if key not in metadata:
            metadata.add(key)
            paths = _json_paths(folder)[:max(0, 512 - metadata_hints)]
            metadata_hints += len(paths)
            pending.extend((path, 0, True) for path in paths)
        if remaining:
            pending.extend((child, remaining - 1, False) for child in _directories(folder))
    return sorted(found.values(), key=str.casefold)
