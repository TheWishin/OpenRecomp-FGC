"""Assemble a launcher/T4 test bundle, without builds or Git.

The launcher release scanner and T4's make_test_zip catalog both run before
anything is written. Only the pinned portable runtime may add binary files.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 32 * 1024 * 1024
LAUNCHER_FOLDER = "OpenRecomp-FGC"
T4_FOLDER = "T4"
START_HIER = (
    "Alles in einen neuen Ordner entpacken.\n"
    "OpenRecomp-FGC\\run.cmd doppelklicken.\n"
    "Auf dem Bildschirm Tekken 4 wählen und den Schritten folgen.\n"
    "Vorher installieren: Visual Studio 2022 Build Tools (Desktopentwicklung mit C++), Git, CMake, Ninja.\n"
    "Eigene Tekken-4-USA-ISO (SLUS-20328) nötig. Online: T4-Lobby (Adresse vom Server-Betreiber) "
    "oder direkte IP/VPN, UDP-Port 7400 beim Host.\n"
).encode("utf-8")
START_HERE = (
    "Tekken 4 beta for PC (OpenRecomp-FGC launcher)\n"
    "\n"
    "You need your own Tekken 4 USA v1.00 ISO (SLUS-20328). No game data is included;\n"
    "the game is built on your PC from your ISO.\n"
    "\n"
    "Install first (Windows 10/11 x64): Visual Studio 2022 Build Tools with\n"
    "\"Desktop development with C++\" (MSVC v143 and a Windows SDK), Git, CMake 3.20+ and Ninja,\n"
    "with git, cmake and ninja on PATH. Python is included.\n"
    "\n"
    "1. Unpack everything into a new, empty folder.\n"
    "2. Double-click OpenRecomp-FGC\\run.cmd.\n"
    "3. Choose Tekken 4, pick your ISO and follow the steps (the first build takes a few minutes).\n"
    "\n"
    "Online: a T4 lobby server (guest or account, player list, chat, quick match, challenges;\n"
    "ask its organizer for the address), or direct IP / a VPN such as Tailscale, where the host\n"
    "needs UDP port 7400 reachable. No ranked. Both players need the same beta version.\n"
    "German: START_HIER.txt\n"
).encode("utf-8")
# These are the launcher's own branding, deliberately omitted for this
# image-free source bundle. Unexpected files still fail the launcher scan.
OMITTED_BRANDING = {
    "openrecomp/ui/assets/icon.ico", "openrecomp/ui/assets/icon.svg",
    "openrecomp/ui/assets/logo-mark-light.svg", "openrecomp/ui/assets/logo-mark.svg",
    "openrecomp/ui/assets/logo-wordmark-light.svg", "openrecomp/ui/assets/logo-wordmark.svg",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg",
                  ".svgz", ".tif", ".tiff", ".avif", ".dds", ".tga", ".icns", ".cur"}


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package = _module("t4_bundle_launcher_scan", ROOT / "tools" / "package_release.py")


def no_links(path):
    for candidate in (Path(path), *Path(path).parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError("Links and junctions cannot be bundled")


def snapshot(path):
    no_links(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE_SIZE:
        raise ValueError("Missing or oversized source input")
    return path.read_bytes()


def clean_patch_header(data):
    """Clean only the mail preamble; retain the complete diff byte for byte."""
    marker = re.search(br"(?m)^diff --git(?:[ \t]|\r?$)", data)
    if marker is None:
        return data
    header = []
    removed_coauthor = False
    for line in data[:marker.start()].splitlines(keepends=True):
        content = line.rstrip(b"\r\n")
        if content.lower().startswith(b"co-authored-by:"):
            removed_coauthor = True
            continue
        if content.lower().startswith(b"from:"):
            line = b"From: T4 test" + line[len(content):]
        header.append(line)
    cleaned_header = b"".join(header)
    if removed_coauthor and not cleaned_header.strip(b"\r\n"):
        cleaned_header = b""
    return cleaned_header + data[marker.start():]


def clean_t4_entries(entries):
    """Transform bundle snapshots, never the T4 source files or other inputs."""
    return [(name, clean_patch_header(data)
             if len(Path(name).parts) == 2 and Path(name).parts[0] == "patches"
             and Path(name).suffix == ".patch" else data) for name, data in entries]


def scan_clean_t4_entries(scanner, scan_entries, originals, cleaned):
    """Keep original hash provenance for the publisher's guest-path check only."""
    publisher = getattr(scanner, "publish_source", None)
    if publisher is None:
        return scan_entries(cleaned)
    original_data = dict(originals)
    allowed = {}
    for name, data in cleaned:
        parts = package.safe_name(name).parts
        if len(parts) != 2 or parts[0] != "patches" or Path(name).suffix != ".patch":
            continue
        original = original_data.get(name)
        if original is None:
            continue
        before = re.search(br"(?m)^diff --git(?:[ \t]|\r?$)", original)
        after = re.search(br"(?m)^diff --git(?:[ \t]|\r?$)", data)
        if before is None or after is None:
            continue
        if original[before.start():] != data[after.start():]:
            raise ValueError("Patch cleanup changed diff content: " + name)
        header = data[:after.start()].decode("utf-8-sig")
        if (hashlib.sha256(original).hexdigest() in publisher.GUEST_PATH_SHA256
                and not publisher.PERSONAL.search(header)):
            allowed[name] = data
    scan_file = publisher.scan_file
    path_reason = "personal or machine-specific path"

    def scan_copy(name, data):
        reasons = list(scan_file(name, data))
        if name in allowed and data == allowed[name]:
            return [reason for reason in reasons if reason != path_reason]
        # The publisher may already exempt an unchanged listed hash. A patch
        # still needs the header/diff checks above, even without header edits.
        try:
            personal = publisher.PERSONAL.search(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            personal = False  # The publisher retains its binary refusal.
        if personal and path_reason not in reasons:
            reasons.append(path_reason)
        return reasons

    try:
        publisher.scan_file = scan_copy
        return scan_entries(cleaned)
    finally:
        publisher.scan_file = scan_file


def load_t4_scanner(root):
    """Read the catalog used by make_test_zip.ps1; never write bytecode there."""
    root = Path(root).absolute()
    no_links(root)
    for name in ("make_test_zip.ps1", "test_zip.py", "publish_source.py"):
        path = root / "tools" / name
        no_links(path)
        if not path.is_file():
            raise ValueError("T4 test source is incomplete: tools/" + name)
    old_bytecode = sys.dont_write_bytecode
    old_path = sys.path[:]
    old_publish = sys.modules.get("publish_source")
    try:
        sys.dont_write_bytecode = True
        publisher = _module("t4_bundle_publish_source", root / "tools/publish_source.py")
        sys.modules["publish_source"] = publisher
        return _module("t4_bundle_test_zip", root / "tools/test_zip.py")
    finally:
        sys.dont_write_bytecode = old_bytecode
        sys.path[:] = old_path
        if old_publish is None:
            sys.modules.pop("publish_source", None)
        else:
            sys.modules["publish_source"] = old_publish


def scan_bundle_entries(entries, runtime_cache=None):
    """Check source bytes and the exact pinned portable-runtime inventory."""
    entries = list(entries)
    runtime_prefix = LAUNCHER_FOLDER + "/portable/"
    runtime = [(name[len(runtime_prefix):], data) for name, data in entries
               if name.startswith(runtime_prefix)]
    if runtime:
        _module("t4_bundle_portable", ROOT / "tools/portable_runtime.py").validate_entries(runtime, cache_root=runtime_cache)
    checked, seen = [], {}
    for name, data in entries:
        path = package.safe_name(name)
        for count in range(1, len(path.parts) + 1):
            prefix = "/".join(path.parts[:count])
            previous = seen.setdefault(prefix.casefold(), prefix)
            if previous != prefix:
                raise ValueError("Case-colliding bundle paths")
        if name in {previous for previous, _ in checked}:
            raise ValueError("Duplicate bundle path")
        if name.startswith(runtime_prefix):
            # The complete inventory above binds each path, size and SHA-256 to
            # the pinned upstream artifacts; no other binary path is exempt.
            checked.append((name, data))
            continue
        if len(data) > MAX_FILE_SIZE:
            raise ValueError("Oversized bundle input: " + name)
        if (path.suffix.lower() in IMAGE_SUFFIXES | package.FORBIDDEN_SUFFIXES
                | {".exe", ".dll", ".pyd", ".zip", ".7z", ".rar", ".gz", ".tar"}
                or any(part.lower() in package.FORBIDDEN_PARTS for part in path.parts)):
            raise ValueError("Forbidden bundle material: " + name)
        if (data.startswith((b"MZ", b"PK\x03\x04", b"7z\xbc\xaf\x27\x1c", b"Rar!", b"\x1f\x8b",
                             b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
                             b"BM", b"II*\x00", b"MM\x00*", b"\x00\x00\x01\x00", b"DDS "))
                or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
                or re.search(br"<svg(?:\s|>)", data[:4096], re.I)):
            raise ValueError("Binary, archive or image content: " + name)
        package.scan_stream(io.BytesIO(data), name)
        if path.suffix.lower() == ".json" and path.parts[:2] == (LAUNCHER_FOLDER, "games"):
            manifest = json.loads(data)
            if not isinstance(manifest, dict) or manifest.get("locations"):
                raise ValueError("Shipped game manifests must have no fixed install locations")
        checked.append((name, data))
    required = {"START_HERE.txt", "START_HIER.txt", LAUNCHER_FOLDER + "/run.cmd", LAUNCHER_FOLDER + "/requirements.txt",
                LAUNCHER_FOLDER + "/LICENSE", T4_FOLDER + "/LICENSE"}
    if not required <= {name for name, _ in checked}:
        raise ValueError("Bundle must retain start files and both licenses")
    return checked


def bundle_entries(root, t4_root, runtime_root=None, runtime_cache=None):
    runtime_cache = ROOT / "dist/portable-cache" if runtime_cache is None else Path(runtime_cache)
    root, t4_root = Path(root).absolute(), Path(t4_root).absolute()
    no_links(root)
    no_links(t4_root)
    # Existing independent scanners are authoritative for their own catalogs.
    selected = package.source_files(root)
    scanner = load_t4_scanner(t4_root)
    # source_entries scans internally. Retain its original snapshots for both
    # scans, while sending only cleaned copies through the existing checks.
    scan_entries = scanner.scan_entries
    originals = []

    def scan_copies(entries):
        originals[:] = list(entries)
        return scan_clean_t4_entries(scanner, scan_entries, originals, clean_t4_entries(originals))

    try:
        scanner.scan_entries = scan_copies
        t4_entries = scanner.source_entries(t4_root)
    finally:
        scanner.scan_entries = scan_entries
    if not originals:
        originals = list(t4_entries)
    t4_entries = clean_t4_entries(t4_entries)
    entries = [("START_HERE.txt", START_HERE), ("START_HIER.txt", START_HIER)]
    for name, path in sorted(selected.items()):
        no_links(path)
        if name not in OMITTED_BRANDING:
            entries.append((LAUNCHER_FOLDER + "/" + name, snapshot(path)))
    for name in ("run.cmd", "requirements.txt"):
        path = root / name
        no_links(path)
        package.scan_file(path, name)
        entries.append((LAUNCHER_FOLDER + "/" + name, snapshot(path)))
    # Re-scan T4's snapshots with the same scan used by its source test zip.
    checked_t4 = scan_clean_t4_entries(scanner, scan_entries, originals, t4_entries)
    entries.extend((T4_FOLDER + "/" + name, data) for name, data in checked_t4)
    if runtime_root is not None:
        runtime = _module("t4_bundle_portable", ROOT / "tools/portable_runtime.py")
        entries.extend((LAUNCHER_FOLDER + "/portable/" + name, data)
                       for name, data in runtime.runtime_entries(runtime_root, cache_root=runtime_cache))
    return scan_bundle_entries(entries, runtime_cache)


def create_bundle(root, t4_root, archive=None, runtime_root=None, runtime_cache=None):
    root = Path(root).absolute()
    no_links(root)
    archive = Path(archive) if archive is not None else root / "dist" / (
        "openrecomp-t4-test-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip")
    archive = archive.absolute()
    no_links(archive)
    relative = archive.relative_to(root)
    if len(relative.parts) != 2 or relative.parts[0] != "dist" or archive.suffix.lower() != ".zip":
        raise ValueError("Bundle output must be a zip directly in dist")
    if archive.exists():
        raise ValueError("Bundle already exists; nothing was overwritten")
    entries = bundle_entries(root, t4_root, runtime_root, runtime_cache)
    archive.parent.mkdir(parents=True, exist_ok=True)
    no_links(archive.parent)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in entries:
            output.writestr(name, data)
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:
            raise ValueError("Bundle CRC check failed")
        scan_bundle_entries(((name, output.read(name)) for name in output.namelist()), runtime_cache)
    return archive, len(entries)


def default_t4_source(root):
    # Maintainer source fallback; the distributed launcher discovers sibling T4.
    return Path(root).parent / "OpenRecomp-work" / "T4-codex-sunday"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--t4-source", type=Path)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--runtime", type=Path, help="Verified portable runtime prepared by fetch_portable_runtime.ps1")
    parser.add_argument("--runtime-cache", type=Path, help="Pinned dependency archive cache (default: dist/portable-cache)")
    args = parser.parse_args(argv)
    try:
        if not args.check_only and args.runtime is None:
            raise ValueError("Creating a test ZIP requires --runtime; use make_t4_test_bundle.ps1 to fetch it first")
        source = args.t4_source or default_t4_source(args.root)
        if args.check_only:
            entries = bundle_entries(args.root, source, args.runtime, args.runtime_cache)
            print("Both source scans passed: {} files. Nothing written.".format(len(entries)))
        else:
            archive, count = create_bundle(args.root, source, runtime_root=args.runtime, runtime_cache=args.runtime_cache)
            print("Test bundle: {}".format(archive))
            with zipfile.ZipFile(archive) as output:
                unpacked = sum(entry.file_size for entry in output.infolist())
            print("Size: {:,} bytes ZIP; {:,} bytes unpacked; {} files.".format(
                archive.stat().st_size, unpacked, count))
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        print("Test bundle refused: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
