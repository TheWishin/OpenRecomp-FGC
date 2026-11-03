"""Assemble the launcher test bundle for both games, without builds or Git.

One zip: the launcher with its portable runtime, the T4 source catalog (built
in the launcher) and the start texts. Tekken 5 DR is not inside: the player
puts their own installed T5DR Online folder next to it. The launcher release
scanner and T4's make_test_zip catalog both run before anything is written.
Only the pinned portable runtime may add binary files, and every entry,
runtime included, is checked against this PC's own user name, profile path,
computer name and Git e-mail before and after writing.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_SIZE = 32 * 1024 * 1024
LAUNCHER_FOLDER = "OpenRecomp-FGC"
T4_FOLDER = "T4"
T5DR_FOLDER = "T5DR-Online-1.2.0"
ARCHIVE_PREFIX = "openrecomp-fgc-test-"
# Short on purpose: the German guide never asks for a runtime or a download.
START_HIER = (
    "OpenRecomp-FGC Testpaket: Tekken 4 und Tekken 5 DR. Keine Spieldaten enthalten.\n"
    "1. Alles in einen neuen, leeren Ordner entpacken, z. B. C:\\Spiele\\FGC-Test (nicht direkt auf C:\\ oder D:\\).\n"
    "2. OpenRecomp-FGC\\run.cmd doppelklicken (fragt Windows nach, \"Trotzdem ausführen\").\n"
    "   Im Regal ein Spiel wählen und den Schritten folgen.\n"
    "\n"
    "Tekken 4: wird im Launcher aus der eigenen USA-ISO (SLUS-20328) gebaut, ca. 6 Minuten.\n"
    "Vorher installieren: Visual Studio 2022 Build Tools (Desktopentwicklung mit C++), Git, CMake, Ninja.\n"
    "Der Launcher prüft die Werkzeuge und zeigt die winget-Befehle für fehlende.\n"
    "Online: T4-Lobby (Adresse vom Server-Betreiber) oder Host/Join per IP oder VPN (UDP-Port 7400 beim Host).\n"
    "\n"
    "Tekken 5 DR: braucht einen eigenen Ordner " + T5DR_FOLDER + " und das eigene Paket (.pkg + .rap).\n"
    "Den Ordner " + T5DR_FOLDER + " in denselben Ordner legen, neben OpenRecomp-FGC und T4.\n"
    "Einmal in T5DR Online.exe BUILD GAME mit .pkg und .rap drücken; danach Spielen und Online hier.\n"
    "\n"
    "Nach dem Spielen: Logs sammeln (T4) bzw. Problembericht (T5DR) und das Zip privat schicken.\n"
    "Englisch: START_HERE.txt\n"
).encode("utf-8")
START_HERE = (
    "OpenRecomp-FGC test bundle: Tekken 4 and Tekken 5 Dark Resurrection\n"
    "\n"
    "No game data is included. You use your own copies of both games.\n"
    "Python and Qt for the launcher are included; it needs no installation and downloads nothing on start.\n"
    "\n"
    "1. Unpack everything into a new, empty folder such as C:\\Games\\FGC-Test (not directly on C:\\ or D:\\).\n"
    "2. Double-click OpenRecomp-FGC\\run.cmd. If Windows warns about a downloaded file, choose \"Run anyway\"\n"
    "   (or first: zip file > Properties > Unblock, then unpack).\n"
    "3. Pick a game on the shelf and follow the steps on screen.\n"
    "\n"
    "Tekken 4 (USA v1.00, SLUS-20328): built on your PC from your own ISO, in the launcher\n"
    "(Tekken 4 > Build; the first build takes about 6 minutes).\n"
    "  Install first (Windows 10/11 x64): Visual Studio 2022 Build Tools with\n"
    "  \"Desktop development with C++\" (MSVC v143 and a Windows SDK), Git, CMake 3.20+ and Ninja,\n"
    "  with git, cmake and ninja on PATH. The launcher checks them and shows winget commands for missing ones.\n"
    "  Online: a T4 lobby server (guest or account, player list, chat, quick match, challenges; ask its\n"
    "  organizer for the address), or Host / Join by direct IP or a VPN such as Tailscale. No ranked for T4.\n"
    "  The host needs UDP port 7400 reachable. Both players need this same bundle.\n"
    "\n"
    "Tekken 5 Dark Resurrection: needs your own T5DR Online 1.2.0 folder and your own package\n"
    "(.pkg + .rap, US PSN NPUB30009). It is not inside this zip.\n"
    "  Put the unpacked " + T5DR_FOLDER + " folder into this same folder:\n"
    "      <your folder>\\OpenRecomp-FGC\n"
    "      <your folder>\\T4\n"
    "      <your folder>\\" + T5DR_FOLDER + "\n"
    "  The launcher finds it there (else: Tekken 5 > Build > Choose T5DR install).\n"
    "  Build the game once in T5DR's own launcher: " + T5DR_FOLDER + "\\T5DR Online.exe, BUILD GAME,\n"
    "  with your .pkg and .rap (Tekken 5 > Build > T5DR Online launcher opens it). T5DR brings its own compiler.\n"
    "  Then Play and Online (lobby, Quick Match, Ranked, rooms) work from OpenRecomp-FGC.\n"
    "\n"
    "After playing: Collect logs (Tekken 4) or the problem report (Tekken 5) writes a zip on your PC;\n"
    "send it to us privately.\n"
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


def local_terms(root=None, extra=()):
    """This PC's own identifiers, read at run time and never stored: none may be in a bundle."""
    terms = [str(term) for term in extra if term]
    for name in ("USERNAME", "USERPROFILE", "COMPUTERNAME"):
        value = os.environ.get(name, "")
        if value:
            terms.append(value)
    profile = os.environ.get("USERPROFILE", "")
    if profile:
        terms.append(profile.replace("\\", "/"))
    try:
        email = subprocess.run(["git", "config", "user.email"], cwd=str(root or ROOT), capture_output=True,
                               text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        email = ""
    if email:
        terms.append(email)
    # Very short names would match ordinary words and library bytes.
    out = []
    for term in terms:
        if len(term) >= 4 and term.casefold() not in {t.casefold() for t in out}:
            out.append(term)
    return out


def scan_private_terms(entries, terms):
    """Every entry, the pinned runtime included, in UTF-8 and UTF-16 spelling, any case."""
    needles = [term.casefold().encode(encoding) for term in terms for encoding in ("utf-8", "utf-16-le")]
    for name, data in entries:
        haystacks = (name.casefold().encode("utf-8"), data.lower())
        if any(needle in haystack for needle in needles for haystack in haystacks):
            raise ValueError("This PC's own user name, profile path, computer name or e-mail is in: " + name)
    return len(terms)


def bundle_note(lines):
    lines = [str(line).strip() for line in lines if str(line).strip()]
    if len(lines) > 20 or any(len(line) > 200 for line in lines):
        raise ValueError("Bundle note lines are too long")
    head = ["OpenRecomp-FGC test bundle",
            "Tekken 4: " + T4_FOLDER + " folder (source, built in the launcher)",
            "Tekken 5 DR: your own " + T5DR_FOLDER + " folder next to it (not included)"]
    return ("\n".join(head + lines) + "\n").encode("utf-8")


def bundle_entries(root, t4_root, runtime_root=None, runtime_cache=None, note=(), terms=None):
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
    entries = [("START_HERE.txt", START_HERE), ("START_HIER.txt", START_HIER), ("BUNDLE.txt", bundle_note(note))]
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
    checked = scan_bundle_entries(entries, runtime_cache)
    scan_private_terms(checked, local_terms(root) if terms is None else terms)
    return checked


def create_bundle(root, t4_root, archive=None, runtime_root=None, runtime_cache=None, dist=None, note=(), terms=None):
    root = Path(root).absolute()
    no_links(root)
    dist = (root / "dist" if dist is None else Path(dist)).absolute()
    archive = Path(archive) if archive is not None else dist / (
        ARCHIVE_PREFIX + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".zip")
    archive = archive.absolute()
    no_links(archive)
    if archive.parent != dist or archive.suffix.lower() != ".zip":
        raise ValueError("Bundle output must be a zip directly in dist")
    if archive.exists():
        raise ValueError("Bundle already exists; nothing was overwritten")
    terms = local_terms(root) if terms is None else list(terms)
    entries = bundle_entries(root, t4_root, runtime_root, runtime_cache, note=note, terms=terms)
    archive.parent.mkdir(parents=True, exist_ok=True)
    no_links(archive.parent)
    output = zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9)
    try:
        # A refused bundle never stays behind half-checked.
        with output:
            for name, data in entries:
                output.writestr(name, data)
        with zipfile.ZipFile(archive) as output:
            if output.testzip() is not None:
                raise ValueError("Bundle CRC check failed")
            written = [(name, output.read(name)) for name in output.namelist()]
        scan_private_terms(scan_bundle_entries(written, runtime_cache), terms)
    except BaseException:
        archive.unlink(missing_ok=True)
        raise
    return archive, len(entries)


RELEASE_TAG = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?")


def release_archive_name(tag):
    """The T4 release asset the launcher's installer looks for (game_releases SOURCES["t4"], docs/GAME_SETUP.md):
    OpenRecomp-Tekken4-<tag>.zip, with T4/ inside, tag like v0.1.0-beta.2."""
    if not RELEASE_TAG.fullmatch(str(tag)):
        raise ValueError("Release tag must look like v0.1.0 or v0.1.0-beta.2, not {!r}".format(tag))
    return "OpenRecomp-Tekken4-{}.zip".format(tag)


def write_checksums(archive):
    """<zip>.sha256 and SHA256SUMS beside the zip (the installer accepts either); returns the hex digest."""
    archive = Path(archive)
    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    line = "{} *{}\n".format(digest.hexdigest(), archive.name).encode("ascii")
    for target in (archive.with_name(archive.name + ".sha256"), archive.with_name("SHA256SUMS")):
        no_links(target)
        target.write_bytes(line)
    return digest.hexdigest()


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
    parser.add_argument("--dist", type=Path, help="Folder the zip is written to (default: dist in --root)")
    parser.add_argument("--note", action="append", default=[], help="A line for BUNDLE.txt, e.g. the launcher commit")
    parser.add_argument("--forbid", action="append", default=[],
                        help="One more private word that must not be in any file (read at run time, never stored)")
    parser.add_argument("--release-tag", help="Name the zip OpenRecomp-Tekken4-<tag>.zip (the T4 release asset) "
                                              "and write <zip>.sha256 + SHA256SUMS beside it")
    args = parser.parse_args(argv)
    try:
        if not args.check_only and args.runtime is None:
            raise ValueError("Creating a test ZIP requires --runtime; use make_t4_test_bundle.ps1 to fetch it first")
        source = args.t4_source or default_t4_source(args.root)
        terms = local_terms(args.root, args.forbid)
        if args.check_only:
            entries = bundle_entries(args.root, source, args.runtime, args.runtime_cache, note=args.note, terms=terms)
            print("Both source scans passed: {} files. Nothing written.".format(len(entries)))
            print("Private-word scan passed: {} words of this PC in none of the files.".format(len(terms)))
        else:
            dist = (args.root / "dist" if args.dist is None else args.dist).absolute()
            named = dist / release_archive_name(args.release_tag) if args.release_tag else None
            archive, count = create_bundle(args.root, source, archive=named, runtime_root=args.runtime,
                                           runtime_cache=args.runtime_cache, dist=dist, note=args.note, terms=terms)
            print("Private-word scan passed: {} words of this PC in none of the files.".format(len(terms)))
            if args.release_tag:
                print("Checksums: {}.sha256 and SHA256SUMS ({})".format(archive.name, write_checksums(archive)))
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
