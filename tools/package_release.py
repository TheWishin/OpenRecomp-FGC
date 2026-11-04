"""Offline launcher-only release assembly. Never fetches or builds anything.

Inputs are separately prepared, reviewed distributions, not an installed venv.
See docs/PACKAGING.md for the inventory and corresponding-source contract.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
CHANNEL = re.compile(r"[a-z0-9][a-z0-9._-]{2,79}\Z")
SOURCE_GROUPS = {
    "openrecomp": ("__init__.py", "__main__.py", "app.py", "manifest.py", "nav.py", "nav_common.py",
                   "nav_build.py", "nav_dialog.py", "nav_drawer.py", "nav_grid.py", "nav_hub.py", "nav_keyboard.py",
                   "nav_online.py", "nav_online_layout.py", "nav_online_login.py", "nav_settings_page.py", "nav_picker.py", "nav_sections.py", "nav_shelf.py", "nav_tools.py",
                   "nav_accounts.py", "nav_challenges.py", "nav_community.py", "nav_moderation.py",
                   "nav_private_chat.py", "nav_profiles.py",
                   "nav_rules.py", "nav_spectating.py", "nav_tournaments.py",
                   "pad.py", "ranks.py", "stall.py", "updater.py", "update_service.py", "file_dialog.py",
                   "game_library.py", "game_updates.py", "nav_library.py",
                   "game_releases.py", "game_setup.py", "app_game_setup.py", "nav_game_setup.py", "t4_art.py"),
    "openrecomp/adapters": ("__init__.py", "base.py", "launch_guard.py", "support.py", "t4.py", "t4_install.py",
                           "t4_online.py", "t4_source.py", "t4_prerequisites.py", "t5dr.py", "t5_controls.py", "t5_match.py", "t5_online.py",
                           "t5_coexist.py", "t5_compatibility.py", "t4_region.py",
                           "t5_accounts.py", "t5_challenges.py", "t5_community.py", "t5_features.py",
                           "t5_moderation.py", "t5_private_chat.py", "t5_profiles.py", "t5_rules.py",
                           "t5_spectating.py", "t5_tournaments.py"),
    "openrecomp/data": ("t4_ranks.json", "known_games.json"),
    # The T4 lobby server the launcher ships with: one "T4 Online" entry, a placeholder (no server) until the
    # beta server is deployed and tools/set_t4_server.py fills in its address and certificate fingerprint.
    "openrecomp/vendor": ("servers.json",),
    # The T4 lobby's client side only (MIT, from T5DR Online's open-source lobby); no server code.
    "openrecomp/vendor/t4lobby": ("__init__.py", "LICENSE", "buildid.py", "client.py", "handover.py", "i18n.py",
                                  "i18n_known.py", "nat.py", "portmap.py", "proto.py", "servers.py", "spectate.py",
                                  "t4game.py", "tour_client.py"),
    "openrecomp/i18n": ("__init__.py", "de.json", "en.json", "es.json", "fr.json", "ja.json", "ko.json", "pt-BR.json"),
    "openrecomp/ui": ("BuildAction.qml", "BuildPage.qml", "Glyph.qml", "Hub.qml", "Main.qml", "OnlineCard.qml", "OnlineHub.qml", "OnlineLogin.qml", "Overlays.qml", "ResultCell.qml", "SettingsHub.qml", "Shelf.qml"),
    "openrecomp/ui/assets": ("icon.ico", "icon.svg", "logo-mark-light.svg", "logo-mark.svg", "logo-wordmark-light.svg", "logo-wordmark.svg"),
    "openrecomp/ui/fonts": ("BigShoulders-800.ttf", "BigShoulders-900.ttf", "IBMPlexMono-400.ttf",
                            "IBMPlexMono-500.ttf", "IBMPlexMono-600.ttf", "IBMPlexSans-400.ttf",
                            "IBMPlexSans-500.ttf", "IBMPlexSans-600.ttf", "OFL-BigShoulders.txt",
                            "OFL-IBMPlexMono.txt", "OFL-IBMPlexSans.txt"),
    "games": ("t4.json", "t5dr.json"),
    "docs": ("PACKAGING.md", "INSTALLING.md", "UPDATES.md", "T4_FIRST_RUN.md", "T4_ONLINE.md", "T5DR_ONLINE.md",
             "T5DR_COEXISTENCE.md", "HAND_CHECK.md", "ADD_YOUR_GAME.md", "GAME_SETUP.md", "INSTALLER.md",
             "RELEASING.md", "RELEASE_KEYS.md"),
}
SOURCE_FILES = {folder + "/" + name for folder, names in SOURCE_GROUPS.items() for name in names}
SOURCE_FILES.update(("LICENSE", "README.md"))
RUNTIME_ROOTS = {"pythonw.exe", "python.exe", "python3.dll", "python312.dll", "python312.zip",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt", "DLLs", "Lib",
                 "libcrypto-3.dll", "libssl-3.dll", "libffi-8.dll", "sqlite3.dll", "python.cat"}
RUNTIME_ROOTS.update(name + ".pyd" for name in (
    "_asyncio", "_bz2", "_ctypes", "_decimal", "_elementtree", "_hashlib", "_lzma", "_msi",
    "_multiprocessing", "_overlapped", "_queue", "_socket", "_sqlite3", "_ssl", "_uuid", "_wmi",
    "_zoneinfo", "pyexpat", "select", "unicodedata"))
PACKAGES = {"PySide6", "shiboken6", "PySide6_Essentials-6.8.2.1.dist-info", "shiboken6-6.8.2.1.dist-info"}
REQUIRED_RUNTIME = {"pythonw.exe", "python312.dll", "python312.zip", "_ctypes.pyd", "_socket.pyd", "_ssl.pyd", "_hashlib.pyd",
                    "libcrypto-3.dll", "libssl-3.dll", "libffi-8.dll", "vcruntime140.dll",
                    "Lib/site-packages/PySide6/__init__.py", "Lib/site-packages/shiboken6/__init__.py",
                    "Lib/site-packages/shiboken6/Shiboken.pyd", "Lib/site-packages/shiboken6/shiboken6.abi3.dll",
                    "Lib/site-packages/PySide6/plugins/platforms/qwindows.dll",
                    "Lib/site-packages/PySide6/qml/QtQuick/qmldir", "Lib/site-packages/PySide6/qml/QtQuick/qtquick2plugin.dll",
                    "Lib/site-packages/PySide6/qml/QtQuick/Window/qmldir", "Lib/site-packages/PySide6/qml/QtQuick/Window/quickwindowplugin.dll"}
REQUIRED_RUNTIME.update("Lib/site-packages/PySide6/" + name for name in (
    "QtCore.pyd", "QtGui.pyd", "QtQml.pyd", "QtQuick.pyd", "Qt6Core.dll", "Qt6Gui.dll", "Qt6Qml.dll", "Qt6Quick.dll"))
FORBIDDEN_PARTS = {"native", "gamedata", "game", "bios", "keys", "saves", "save", "logs", "screenshots",
                   "__pycache__", ".git", ".venv", "node_modules"}
FORBIDDEN_SUFFIXES = {".iso", ".pkg", ".rap", ".rif", ".elf", ".self", ".bin", ".img", ".cue",
                      ".mcr", ".ps2", ".ps3", ".sav", ".log", ".key", ".pem", ".p12", ".pfx"}
SOURCE_SIGNATURES = (b"\x7fELF", b"\x7fPKG", b"SCE\x00", b"PS-X EXE")
REQUIRED_LICENSES = {"LGPL-3.0.txt", "GPL-3.0.txt", "Qt-NOTICES.txt", "PySide6-NOTICES.txt",
                     "shiboken6-NOTICES.txt", "Python-LICENSE.txt", "REPLACEMENT.txt"}
REQUIRED_SOURCES = {"Qt": "6.8.2", "PySide6": "6.8.2.1", "shiboken6": "6.8.2.1"}
BOOT = '''"""Relocatable entry point; no user Python or user site-packages."""
import os
from pathlib import Path
import runpy
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "python" / "Lib" / "site-packages"))
sys.path.insert(0, str(root))
os.chdir(root)
if os.environ.get("OPENRECOMP_HOME"):
    os.environ["OPENRECOMP_HOME"] = os.path.abspath(os.path.expanduser(os.path.expandvars(os.environ["OPENRECOMP_HOME"])))
runpy.run_module("openrecomp", run_name="__main__")
'''


class PackageError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def windows_pe(path, gui=False):
    """Reject renamed scripts and non-Windows/non-x64 binaries before assembly."""
    with Path(path).open("rb") as stream:
        head = stream.read(64)
        if len(head) != 64 or head[:2] != b"MZ":
            return False
        offset = struct.unpack_from("<I", head, 60)[0]
        if not 64 <= offset <= 1024 * 1024:
            return False
        stream.seek(offset)
        pe = stream.read(94)
    return (len(pe) == 94 and pe[:4] == b"PE\0\0" and struct.unpack_from("<H", pe, 4)[0] == 0x8664
            and struct.unpack_from("<H", pe, 24)[0] == 0x20b
            and (not gui or struct.unpack_from("<H", pe, 92)[0] == 2))


def safe_name(name):
    """Portable archive spelling, including Windows aliases and alternate streams."""
    if not isinstance(name, str) or not name or "\\" in name:
        raise PackageError("Invalid inventory path")
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ("", ".", "..") for x in name.split("/")):
        raise PackageError("Invalid inventory path")
    devices = {"con", "prn", "aux", "nul", "conin$", "conout$"}
    devices.update(f"{s}{n}" for s in ("com", "lpt") for n in range(10))
    devices.update(f"{s}{n}" for s in ("com", "lpt") for n in "¹²³")
    for part in p.parts:
        if (re.search(r'[<>:"|?*\x00-\x1f]', part) or part.endswith((".", " "))
                or part.split(".")[0].lower() in devices):
            raise PackageError("Invalid inventory path")
    return p


def checked_files(folder):
    """No symlinks, junctions or case aliases in any supplied tree."""
    folder = Path(folder)
    if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
        raise PackageError("Input must be a plain directory")
    found, folded = {}, set()
    for current, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            p = Path(current) / name
            rel = p.relative_to(folder).as_posix()
            safe_name(rel)
            if p.is_symlink() or p.is_junction():
                raise PackageError("Links and junctions cannot be packaged")
            if rel.casefold() in folded:
                raise PackageError("Case aliases cannot be packaged")
            folded.add(rel.casefold())
            if p.is_file():
                found[rel] = p
    return found


def scan_stream(stream, name, library=False):
    """Also used for compressed stdlib members, without extracting them."""
    head = stream.read(128 * 1024)
    if head.startswith(SOURCE_SIGNATURES) or head[0x8001:0x8006] == b"CD001":
        raise PackageError("Game image or executable signature: " + name)
    tail, block = b"", head
    while block:
        data = tail + block
        if b"-----BEGIN " in data and b"PRIVATE KEY-----" in data:
            # Libraries legitimately contain delimiter literals. A PEM payload is
            # different from those code strings; launcher text permits neither.
            if not library or re.search(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=]{16,}[\r\n]", data):
                raise PackageError("Private key content is forbidden: " + name)
        if not library:
            if re.search(rb"[A-Za-z]:\\(?:Users|Documents and Settings)\\|/home/[^/\s]+/|/Users/[^/\s]+/", data):
                raise PackageError("Personal paths cannot be packaged: " + name)
            # Require a complete address token. Glyph tables can contain runs
            # of @-separated bytes that only resemble a substring of an address.
            if re.search(rb"(?<![A-Za-z0-9._%+@-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.@-])", data):
                raise PackageError("Personal email addresses cannot be packaged: " + name)
        tail = data[-512:]
        block = stream.read(128 * 1024)


def scan_file(path, name, library=False):
    """Refuse recognizable game material and private/player data, also in inputs."""
    p = safe_name(name)
    if any(x.lower() in FORBIDDEN_PARTS for x in p.parts) or p.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise PackageError("Game, player or secret material is forbidden: " + name)
    with Path(path).open("rb") as stream:
        scan_stream(stream, name, library)
    if not library and p.suffix.lower() in {".exe", ".dll", ".pyd", ".png", ".jpg", ".jpeg", ".webp"}:
        raise PackageError("Unapproved binary or game picture: " + name)
    if p.suffix.lower() == ".json" and not library:
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as e:
            raise PackageError("Invalid shipped JSON: " + name) from e
        if p.parts[0] == "games":
            if not isinstance(value, dict):
                raise PackageError("Shipped game manifests must be JSON objects")
            if value.get("locations"):
                raise PackageError("Shipped game manifests must have no fixed install locations")


def verify_inventory(folder, inventory):
    actual = checked_files(folder)
    if not isinstance(inventory, dict) or not inventory or set(actual) != set(inventory):
        raise PackageError("Runtime/license tree must exactly match its reviewed SHA-256 inventory")
    for name, path in actual.items():
        expected = inventory[name]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(path) != expected:
            raise PackageError("Inventory checksum failed: " + name)
        scan_file(path, name, library=True)
    return actual


def runtime_files(folder, contract):
    if contract.get("python") != "3.12" or contract.get("pyside6") != "6.8.2.1":
        raise PackageError("Require private CPython 3.12 and pinned PySide6 6.8.2.1")
    files = verify_inventory(folder, contract.get("runtime"))
    for name in files:
        p = PurePosixPath(name)
        if p.parts[0] not in RUNTIME_ROOTS or any(x.lower() in {"scripts", "test", "tests", "idlelib", "pip"} for x in p.parts):
            raise PackageError("Unexpected runtime component: " + name)
        if p.parts[:2] == ("Lib", "site-packages") and (len(p.parts) < 4 or p.parts[2] not in PACKAGES):
            raise PackageError("Unexpected Python package: " + name)
        if p.suffix.lower() == ".exe" and name not in ("python.exe", "pythonw.exe"):
            raise PackageError("Unexpected executable: " + name)
    if not REQUIRED_RUNTIME <= files.keys():
        raise PackageError("Runtime is incomplete")
    for name in ("pythonw.exe", "python312.dll"):
        if not windows_pe(files[name]):
            raise PackageError("Windows runtime must contain real PE files")
    # Reject hidden additions in the embedded standard library too.
    with zipfile.ZipFile(files["python312.zip"]) as z:
        seen = set()
        if len(z.infolist()) > 20000 or sum(e.file_size for e in z.infolist()) > 300 * 1024 * 1024:
            raise PackageError("Embedded standard library exceeds its limits")
        for entry in z.infolist():
            p = safe_name(entry.filename.rstrip("/"))
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (entry.orig_filename != entry.filename or str(p).casefold() in seen
                    or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                    or entry.external_attr & 0x400 or entry.flag_bits & 1):
                raise PackageError("Unsafe embedded standard library")
            seen.add(str(p).casefold())
            if any(x.lower() in FORBIDDEN_PARTS for x in p.parts) or (not entry.is_dir() and p.suffix.lower() not in {".py", ".pyc", ".txt", ".pickle", ".css", ".json"}):
                raise PackageError("Unexpected embedded standard library member")
            if not entry.is_dir():
                with z.open(entry) as stream:
                    scan_stream(stream, "python312.zip/" + str(p), library=True)
    return files


def license_files(folder, contract):
    files = verify_inventory(folder, contract.get("licenses"))
    if not REQUIRED_LICENSES <= files.keys():
        raise PackageError("Complete license texts, notices and replacement instructions are required")
    for name in REQUIRED_LICENSES:
        if files[name].stat().st_size < 40:
            raise PackageError("License/notice text is incomplete: " + name)
    sources = contract.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(REQUIRED_SOURCES):
        raise PackageError("Exact corresponding Qt, PySide6 and shiboken6 source archives are required")
    for component, version in REQUIRED_SOURCES.items():
        source = sources[component]
        if not isinstance(source, dict) or source.get("version") != version or source.get("path") not in files:
            raise PackageError("Corresponding source missing: " + component)
        if not source["path"].endswith((".tar.xz", ".tar.gz", ".zip")):
            raise PackageError("Corresponding source must be an archive")
    return files


def source_files(root):
    selected = {}
    for directory in ("openrecomp", "games"):
        base = Path(root) / directory
        if not base.is_dir() or base.is_symlink() or base.is_junction():
            raise PackageError("Source must be a plain directory")
        # Cache files are local Python output; never traverse them into the payload.
        for current, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for directory_name in dirs:
                p = Path(current) / directory_name
                if p.is_symlink() or p.is_junction():
                    raise PackageError("Source links cannot be packaged")
            for filename in files:
                p = Path(current) / filename
                name = p.relative_to(root).as_posix()
                if p.is_symlink() or name not in SOURCE_FILES:
                    raise PackageError("Unexpected source payload: " + name)
                scan_file(p, name)
                selected[name] = p
    documents = SOURCE_FILES - {name for name in SOURCE_FILES if name.startswith(("openrecomp/", "games/"))}
    for name in sorted(documents):
        p = Path(root) / name
        if (p.is_symlink() or p.is_junction() or not p.is_file()
                or p.parent.is_symlink() or p.parent.is_junction()):
            raise PackageError("Source links cannot be packaged")
        scan_file(p, name)
        selected[name] = p
    if set(selected) != SOURCE_FILES:
        raise PackageError("The explicit launcher source payload is incomplete")
    return selected


def release_trust(channel):
    # Direct script invocation starts with tools/ on sys.path, not the repo root.
    sys.path.insert(0, str(ROOT))
    from openrecomp import updater
    try:
        trust = updater.configured_channel()
    except updater.UpdateError as e:
        raise PackageError(str(e)) from e
    if trust.name != channel or not trust.public_keys:
        raise PackageError("Configure the project's channel and signing public key before packaging")
    return trust


def validate_release(version, channel):
    if not VERSION.fullmatch(version or ""):
        raise PackageError("Release version must be plain vX.Y.Z")
    if not CHANNEL.fullmatch(channel or ""):
        raise PackageError("Choose this project's unique lowercase release channel")


def output_folder(path):
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise PackageError("Release output must not use links or junctions")
    return path


def assemble(root, runtime, starter, licenses, contract_path, output, version, channel):
    """Explicit invocation only: checks all inputs before creating a release zip."""
    validate_release(version, channel)
    root, output, starter = Path(root), output_folder(output), Path(starter)
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise PackageError("Inventory must be a JSON object")
    source = source_files(root)
    runtime = runtime_files(runtime, contract)
    licenses = license_files(licenses, contract)
    # The release must embed owner-reviewed trust, not accept unsigned updates.
    release_trust(channel)
    if not starter.is_file() or starter.is_symlink() or not windows_pe(starter, gui=True):
        raise PackageError("Supply the compiled native Windows starter")
    if digest(starter) != contract.get("starter_sha256"):
        raise PackageError("Starter checksum differs from reviewed inventory")
    scan_file(starter, "OpenRecomp.exe", library=True)
    basename = "OpenRecomp-" + version
    archive = output / (basename + ".zip")
    for artifact in (archive, output / "SHA256SUMS"):
        if artifact.exists() or artifact.is_symlink() or artifact.is_junction():
            raise PackageError("Refusing to overwrite release artifacts")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="openrecomp-package-", dir=output) as temporary:
        stage = Path(temporary) / basename
        stage.mkdir()
        payload = dict(source)
        payload.update(("python/" + n, p) for n, p in runtime.items())
        payload.update(("LICENSES/" + n, p) for n, p in licenses.items())
        payload["OpenRecomp.exe"] = starter
        reviewed = {"python/" + n: checksum for n, checksum in contract["runtime"].items()}
        reviewed.update(("LICENSES/" + n, checksum) for n, checksum in contract["licenses"].items())
        reviewed["OpenRecomp.exe"] = contract["starter_sha256"]
        for name, path in payload.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            # Bind the shipped bytes to the review, even if an input changes
            # between validation and copying. Scan source from this snapshot too.
            if name in reviewed and digest(target) != reviewed[name]:
                raise PackageError("Input changed after review: " + name)
            scan_file(target, name, library=name in reviewed)
        (stage / "openrecomp_boot.py").write_text(BOOT, encoding="utf-8")
        # CPython's embeddable distribution resolves these relative to its executable.
        (stage / "python" / "python312._pth").write_text("python312.zip\n.\nLib\nLib/site-packages\n..\n", encoding="utf-8")
        (stage / "release.json").write_text(json.dumps({"project": "openrecomp-fgc", "version": version,
            "channel": channel}, indent=2) + "\n", encoding="utf-8")
        with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, path in sorted(checked_files(stage).items()):
                z.write(path, basename + "/" + name)
        unpacked = sum(p.stat().st_size for p in checked_files(stage).values())
    checksum = digest(archive)
    with (output / "SHA256SUMS").open("x", encoding="ascii") as sums:
        sums.write(f"{checksum}  {archive.name}\n")
    return {"archive": archive.name, "zip_bytes": archive.stat().st_size, "unpacked_bytes": unpacked,
            "sha256": checksum}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-only", action="store_true", help="Check the launcher source payload without assembling a release")
    for arg in ("runtime", "starter", "licenses", "inventory", "out", "version", "channel"):
        parser.add_argument("--" + arg)
    args = parser.parse_args(argv)
    try:
        if args.scan_only:
            if any(getattr(args, name) is not None for name in ("runtime", "starter", "licenses", "inventory", "out", "version", "channel")):
                parser.error("--scan-only cannot be combined with release assembly arguments")
            selected = source_files(ROOT)
            facts = {"scan": "passed", "source_files": len(selected)}
        else:
            missing = ["--" + name for name in ("runtime", "starter", "licenses", "inventory", "out", "version", "channel")
                       if getattr(args, name) is None]
            if missing:
                parser.error("the following arguments are required: " + ", ".join(missing))
            facts = assemble(ROOT, args.runtime, args.starter, args.licenses, args.inventory,
                             args.out, args.version, args.channel)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        parser.exit(1, "Package refused: " + str(e) + "\n")
    print(json.dumps(facts, sort_keys=True))


if __name__ == "__main__":
    main()
