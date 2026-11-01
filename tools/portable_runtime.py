"""Verify portable files against the exact contents of pinned upstream archives.

The source scanners stay strict. Only byte-identical members of these three
immutable archives (and the explicit path configuration below) are runtime data.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = Path(__file__).with_name("portable_runtime.lock.json")
DEFAULT_CACHE = ROOT / "dist" / "portable-cache"
MAX_ARCHIVE_SIZE = 128 * 1024 * 1024
MAX_MEMBER_SIZE = 128 * 1024 * 1024
MAX_RUNTIME_SIZE = 512 * 1024 * 1024


def safe_name(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Unsafe portable runtime path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("Unsafe portable runtime path")
    devices = {"con", "prn", "aux", "nul", "conin$", "conout$"}
    devices.update("{}{}".format(prefix, number) for prefix in ("com", "lpt")
                   for number in "0123456789¹²³")
    for part in path.parts:
        if (any(char in '<>:"|?*' or ord(char) < 32 for char in part)
                or part.endswith((".", " ")) or part.split(".")[0].lower() in devices):
            raise ValueError("Unsafe portable runtime path")
    return path


def remember_name(name, spellings):
    path = safe_name(name)
    for count in range(1, len(path.parts) + 1):
        prefix = "/".join(path.parts[:count])
        previous = spellings.setdefault(prefix.casefold(), prefix)
        if previous != prefix:
            raise ValueError("Case-colliding portable runtime path")

def no_links(path):
    path = Path(path)
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError("Links and junctions cannot be portable runtime inputs")


def load_lock():
    lock = json.loads(LOCK.read_text(encoding="utf-8-sig"))
    if lock.get("schema") != 1 or not lock.get("archives"):
        raise ValueError("Unsupported portable runtime lock")
    return lock


def expected_entries(cache_root=None):
    """Derive the full allowlist only after checking whole archive SHA-256 sums."""
    cache = Path(cache_root) if cache_root is not None else DEFAULT_CACHE
    no_links(cache)
    lock = load_lock()
    entries, spellings = {}, {}
    total = 0
    for archive in lock["archives"]:
        filename = safe_name(archive["filename"])
        if len(filename.parts) != 1:
            raise ValueError("Runtime cache archive must have a simple filename")
        path = cache / filename.name
        no_links(path)
        if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_SIZE:
            raise ValueError("Missing or oversized pinned runtime archive: " + filename.name)
        data = path.read_bytes()
        if (hashlib.sha256(data).hexdigest() != archive["sha256"]
                or ("size" in archive and len(data) != archive["size"])):
            raise ValueError("Pinned runtime archive SHA-256 or size mismatch: " + filename.name)
        prefix = archive.get("target_prefix", "")
        if prefix:
            safe_name(prefix)
        members = set()
        with zipfile.ZipFile(io.BytesIO(data)) as source:
            for member in source.infolist():
                if member.is_dir():
                    safe_name(member.filename.rstrip("/"))
                    continue
                safe_name(member.filename)
                if member.filename in members:
                    raise ValueError("Duplicate pinned archive member")
                members.add(member.filename)
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode) or member.flag_bits & 1:
                    raise ValueError("Linked or encrypted pinned archive member")
                if member.file_size > MAX_MEMBER_SIZE:
                    raise ValueError("Oversized pinned runtime member")
                name = (prefix.rstrip("/") + "/" if prefix else "") + member.filename
                safe_name(name)
                folded = name.casefold()
                if folded in spellings:
                    raise ValueError("Duplicate or case-colliding portable runtime path")
                remember_name(name, spellings)
                content = source.read(member)
                total += len(content)
                if total > MAX_RUNTIME_SIZE:
                    raise ValueError("Oversized portable runtime")
                entries[name] = content
    for resource in lock.get("downloads", []):
        filename = safe_name(resource["filename"])
        if len(filename.parts) != 1:
            raise ValueError("Runtime resource must have a simple cache filename")
        path = cache / filename.name
        no_links(path)
        if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_SIZE:
            raise ValueError("Missing or oversized pinned runtime resource: " + filename.name)
        data = path.read_bytes()
        if (hashlib.sha256(data).hexdigest() != resource["sha256"]
                or ("size" in resource and len(data) != resource["size"])):
            raise ValueError("Pinned runtime resource SHA-256 or size mismatch: " + filename.name)
        name = resource["target"]
        safe_name(name)
        if name.casefold() in spellings:
            raise ValueError("Duplicate or case-colliding runtime resource path")
        entries[name] = data
        remember_name(name, spellings)
        if resource.get("licenses_prefix"):
            license_prefix = resource["licenses_prefix"]
            safe_name(license_prefix)
            with zipfile.ZipFile(io.BytesIO(data)) as source:
                members = [member for member in source.infolist() if not member.is_dir()]
                names = [safe_name(member.filename) for member in members]
                roots = {name.parts[0] for name in names}
                strip_root = len(roots) == 1 and all(len(name.parts) > 1 for name in names)
                license_data = []
                for member, member_path in zip(members, names):
                    relative = PurePosixPath(*member_path.parts[1:]) if strip_root else member_path
                    if not (relative.parts[0] == "LICENSES" or (len(relative.parts) == 1
                            and relative.name.upper().startswith(("LICENSE", "COPYING")))):
                        continue
                    if (stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1
                            or member.file_size > MAX_MEMBER_SIZE):
                        raise ValueError("Invalid pinned license archive member")
                    name = license_prefix.rstrip("/") + "/" + relative.as_posix()
                    if name.casefold() in spellings:
                        raise ValueError("Duplicate or case-colliding pinned license path")
                    remember_name(name, spellings)
                    content = source.read(member)
                    entries[name] = content
                    license_data.append(content.upper())
                for heading in (b"GNU LESSER GENERAL PUBLIC LICENSE", b"GNU GENERAL PUBLIC LICENSE"):
                    if not any(heading in notice and b"VERSION 3" in notice for notice in license_data):
                        raise ValueError("Pinned license archive lacks LGPLv3/GPLv3 texts")
    for name, generated in lock.get("files", {}).items():
        safe_name(name)
        content = generated["content_utf8"].encode("utf-8")
        if (len(content) != generated["size"]
                or hashlib.sha256(content).hexdigest() != generated["sha256"]):
            raise ValueError("Generated runtime file does not match the lock")
        if name.casefold() in spellings and spellings[name.casefold()] != name:
            raise ValueError("Case-colliding generated runtime path")
        entries[name] = content
        remember_name(name, spellings)
    required = {"python.exe", "pythonw.exe", "python312.dll", "python312.zip", "python312._pth",
                "LICENSE.txt", "Lib/site-packages/PySide6/__init__.py",
                "Lib/site-packages/shiboken6/__init__.py"}
    if not required <= entries.keys():
        raise ValueError("Pinned runtime is incomplete")
    if sum(len(data) for data in entries.values()) > MAX_RUNTIME_SIZE:
        raise ValueError("Oversized portable runtime")
    return sorted(entries.items())


def validate_entries(entries, expected=None, cache_root=None):
    """Validate snapshots, including snapshots read back from the final zip."""
    reference = dict(expected_entries(cache_root) if expected is None else expected)
    checked, seen = [], set()
    for name, data in entries:
        safe_name(name)
        if name.casefold() in seen:
            raise ValueError("Duplicate or case-colliding portable runtime path")
        seen.add(name.casefold())
        if name not in reference or data != reference[name]:
            raise ValueError("Unlisted or modified portable runtime file: " + name)
        checked.append((name, data))
    if {name for name, _ in checked} != reference.keys():
        raise ValueError("Portable runtime is missing pinned files")
    return checked


def runtime_entries(runtime_root, cache_root=None):
    root = Path(runtime_root).absolute()
    no_links(root)
    if not root.is_dir():
        raise ValueError("Portable runtime directory is missing")
    cache = Path(cache_root) if cache_root is not None else root.parent / "portable-cache"
    reference = expected_entries(cache)
    entries = []
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            no_links(Path(current) / name)
        for name in files:
            path = Path(current) / name
            if not path.is_file() or path.stat().st_size > MAX_MEMBER_SIZE:
                raise ValueError("Invalid or oversized portable runtime input")
            entries.append((path.relative_to(root).as_posix(), path.read_bytes()))
    return validate_entries(entries, expected=reference)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--catalog", action="store_true")
    args = parser.parse_args(argv)
    try:
        entries = (runtime_entries(args.runtime, args.cache) if args.runtime
                   else expected_entries(args.cache))
        if args.catalog:
            for name, data in entries:
                print("{}  {}  {}".format(hashlib.sha256(data).hexdigest(), len(data), name))
        print("Portable runtime: {} files; {:,} bytes.".format(len(entries), sum(len(data) for _, data in entries)))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print("Portable runtime refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())





