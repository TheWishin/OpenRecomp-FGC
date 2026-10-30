"""Register the player's T4 install; archives stay in the player's data folder."""
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from ..manifest import user_dir

MAX_ARCHIVE = 8_000_000_000
MAX_UNPACKED = 16_000_000_000
MAX_FILES = 100_000
_BAD_NAME = re.compile(r'[<>:"|?*\x00-\x1f\\]')
_DEVICES = {"con", "prn", "aux", "nul", "conin$", "conout$"}
_DEVICES.update(f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(10))
_DEVICES.update(prefix + n for prefix in ("com", "lpt") for n in ("¹", "²", "³"))


def install_root(path):
    """An install itself, or the sole T4 install directly inside an enclosing folder."""
    root = Path(path)
    if (root / "launcher" / "t4core.py").is_file():
        return str(root.resolve())
    if not root.is_dir():
        return None
    roots = [child for child in root.iterdir() if child.is_dir()
             and (child / "launcher" / "t4core.py").is_file()]
    return str(roots[0].resolve()) if len(roots) == 1 else None


def _members(archive):
    entries = archive.infolist()
    if len(entries) > MAX_FILES or sum(entry.file_size for entry in entries) > MAX_UNPACKED:
        raise ValueError("@t4.zip_too_large")
    seen, files, parents, checked = set(), set(), set(), []
    for entry in entries:
        name = entry.filename
        parts = PurePosixPath(name).parts
        mode = entry.external_attr >> 16
        if (not parts or entry.orig_filename != name or name.startswith("/") or "//" in name or "." in name.split("/")
                or any(p in (".", "..") or _BAD_NAME.search(p) or p.endswith((" ", "."))
                       or p.split(".")[0].casefold() in _DEVICES for p in parts)
                or entry.flag_bits & 1 or entry.external_attr & 0x400
                or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ValueError("@t4.zip_invalid")
        key = "/".join(parts).casefold()
        if key in seen or any("/".join(parts[:n]).casefold() in files for n in range(1, len(parts))):
            raise ValueError("@t4.zip_invalid")
        if not entry.is_dir() and key in parents:
            raise ValueError("@t4.zip_invalid")
        seen.add(key)
        parents.update("/".join(parts[:n]).casefold() for n in range(1, len(parts)))
        if not entry.is_dir():
            files.add(key)
        checked.append((entry, parts))
    roots = {parts[:-2] for entry, parts in checked
             if not entry.is_dir() and len(parts) in (2, 3) and parts[-2:] == ("launcher", "t4core.py")}
    if len(roots) != 1:
        raise ValueError("@t4.install_invalid")
    prefix = next(iter(roots))
    if any(parts[:len(prefix)] != prefix for _entry, parts in checked):
        raise ValueError("@t4.zip_invalid")
    return checked, prefix


def unpack_install(path):
    """Validate the entire zip before writing, then publish an isolated extraction atomically."""
    path = Path(path)
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError("@t4.zip_too_large")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        source.seek(0)
        with zipfile.ZipFile(source) as archive:
            entries, prefix = _members(archive)
            parent = Path(user_dir()) / "installs" / "t4"
            parent.mkdir(parents=True, exist_ok=True)
            dest = parent / digest
            if dest.exists() or dest.is_symlink():
                root = dest.joinpath(*prefix)
                if dest.is_symlink() or not (root / "launcher" / "t4core.py").is_file():
                    raise ValueError("@t4.install_invalid")
                return str(root)
            stage = Path(tempfile.mkdtemp(prefix="pending-", dir=parent))
            try:
                written = 0
                for entry, parts in entries:
                    target = stage.joinpath(*parts)
                    if entry.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as data, target.open("xb") as out:
                        count = 0
                        while chunk := data.read(1024 * 1024):
                            count += len(chunk)
                            written += len(chunk)
                            if count > entry.file_size or written > MAX_UNPACKED:
                                raise ValueError("@t4.zip_too_large")
                            out.write(chunk)
                        if count != entry.file_size:
                            raise ValueError("@t4.zip_invalid")
                if dest.exists():
                    raise ValueError("@t4.install_busy")
                stage.rename(dest)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            return str(dest.joinpath(*prefix))


def install_source(manifest, config, path):
    """No import or game start here: only validate/register the player's chosen source."""
    try:
        if Path(path).is_file() and Path(path).suffix.casefold() == ".zip":
            root = unpack_install(path)
        else:
            root = install_root(path)
        if not root:
            return "@t4.install_invalid"
    except ValueError as error:
        message = str(error)
        return message if message in ("@t4.zip_too_large", "@t4.zip_invalid", "@t4.install_invalid",
                                      "@t4.install_busy") else "@t4.zip_invalid"
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return "@t4.install_failed"
    config.setdefault("roots", {})[manifest["id"]] = root
    return "reload"
