"""Build OpenRecomp-FGC-Setup-<version>.exe from a bundle zip (the one tools/make_test_bundle.ps1 makes).

The setup is our own small Windows program (tools/installer/setup.cpp), compiled here with the MSVC tools of
Visual Studio 2022 Build Tools: no installer framework, no packer, nothing downloaded. It carries the bundle's
OpenRecomp-FGC/ folder (and its T4/ source, when the bundle has one) as an RCDATA resource in our own simple
format: every file compressed with the Windows Compression API (LZMS or XPRESS Huffman, whichever is smaller)
and checked against its SHA-256 before Setup places anything. The same program without that resource is the
uninstaller Setup writes into the install folder.

    python tools\\make_installer.py --bundle dist\\openrecomp-fgc-test-....zip [--out dist] [--version 0.1.0]
        [--game t5dr=<folder> --game t4=<folder> --name <Setup file name>]

A full Setup (--game) also carries each game's GitHub release files untouched (its zip, SHA256SUMS,
SHA256SUMS.sig) under bundled-games/<game>/; Setup unpacks them into its staging folder only and lets the
installed launcher install the chosen games with its own release checks (openrecomp/bundled_games.py).

The bundle's own scans (make_test_bundle) stay the gate for its content; this tool refuses the obvious game
file types again and never adds anything but the bundle's files and the uninstaller.
"""
import argparse
import ctypes
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "installer"
MAGIC = b"ORSETUP1"
UNINSTALL_EXE = "Uninstall OpenRecomp.exe"
LAUNCHER = "OpenRecomp-FGC"
GAMES = ("T4",)
STORED, XPRESS_HUFF, LZMS = 0, 4, 5
MAX_FILES = 100_000
# Never in a setup, whatever the bundle says (its own scan is the real gate).
REFUSED_SUFFIXES = (".iso", ".pkg", ".rap", ".elf", ".self", ".sprx", ".bin", ".img", ".rif", ".edat", ".sdat",
                    ".mcd", ".ps2", ".bios", ".key", ".pem")
REFUSED_NAMES = ("eboot.bin", "param.sfo", "slus_203.28")
REQUIRED = (f"{LAUNCHER}/portable/pythonw.exe", f"{LAUNCHER}/portable/python312._pth", f"{LAUNCHER}/openrecomp/app.py")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?\Z")
BUNDLE_DIR = "bundled-games"             # setup.cpp GAMES_DIR
BUNDLE_GAMES = ("t5dr", "t4")            # setup.cpp GAME_IDS
BUNDLE_ZIPS = {"t5dr": re.compile(r"T5DR-Online-\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?\.zip\Z"),
               "t4": re.compile(r"OpenRecomp-Tekken4-v\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?\.zip\Z")}


class InstallerError(Exception):
    pass


# ------------------------------------------------------------------------------------------------ compression
def _cabinet():
    if os.name != "nt":
        raise InstallerError("The setup is built on Windows (it uses the Windows Compression API).")
    lib = ctypes.WinDLL("cabinet")
    handle = ctypes.c_void_p
    lib.CreateCompressor.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(handle)]
    lib.Compress.argtypes = [handle, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                             ctypes.POINTER(ctypes.c_size_t)]
    lib.CloseCompressor.argtypes = [handle]
    lib.CreateDecompressor.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(handle)]
    lib.Decompress.argtypes = [handle, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                               ctypes.POINTER(ctypes.c_size_t)]
    lib.CloseDecompressor.argtypes = [handle]
    return lib


def compress(data, method):
    lib = _cabinet()
    h = ctypes.c_void_p()
    if not lib.CreateCompressor(method, None, ctypes.byref(h)):
        raise InstallerError(f"CreateCompressor({method}) failed")
    try:
        room = len(data) + len(data) // 8 + 65536
        out = ctypes.create_string_buffer(room)
        got = ctypes.c_size_t()
        src = ctypes.create_string_buffer(data, len(data)) if data else None
        if not lib.Compress(h, src, len(data), out, room, ctypes.byref(got)):
            raise InstallerError("Compress failed")
        return out.raw[:got.value]
    finally:
        lib.CloseCompressor(h)


def decompress(data, size, method):
    if method == STORED:
        return data
    lib = _cabinet()
    h = ctypes.c_void_p()
    if not lib.CreateDecompressor(method, None, ctypes.byref(h)):
        raise InstallerError("CreateDecompressor failed")
    try:
        out = ctypes.create_string_buffer(max(1, size))
        got = ctypes.c_size_t()
        src = ctypes.create_string_buffer(data, len(data))
        if not lib.Decompress(h, src, len(data), out, size, ctypes.byref(got)) or got.value != size:
            raise InstallerError("Decompress failed")
        return out.raw[:size]
    finally:
        lib.CloseDecompressor(h)


def pack(data):
    """(method, stored bytes): the smallest of LZMS, XPRESS Huffman and stored."""
    best = (STORED, data)
    if len(data) >= 64:
        for method in (XPRESS_HUFF, LZMS) if len(data) >= 4096 else (XPRESS_HUFF,):
            packed = compress(data, method)
            if len(packed) < len(best[1]) * 0.98:
                best = (method, packed)
    return best


# ------------------------------------------------------------------------------------------------ payload
def bundle_files(bundle):
    """[(relative path, bytes)] of the launcher and the T4 source in a bundle zip; refuses anything odd."""
    files = []
    seen = set()
    with zipfile.ZipFile(bundle) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES:
            raise InstallerError("The bundle has too many files.")
        for entry in entries:
            name = entry.filename
            if entry.is_dir():
                continue
            parts = PurePosixPath(name).parts
            mode = entry.external_attr >> 16
            if (not parts or name.startswith("/") or "\\" in name or ":" in name
                    or any(p in ("", ".", "..") or p != p.rstrip(". ") for p in parts)
                    or entry.flag_bits & 1 or (mode and (mode & 0o170000) not in (0, 0o100000))):
                raise InstallerError(f"Unexpected path in the bundle: {name!r}")
            if parts[0] not in (LAUNCHER,) + GAMES:
                if len(parts) == 1:
                    continue                    # START_HERE.txt and friends: the setup explains itself
                raise InstallerError(f"Unexpected folder in the bundle: {parts[0]!r}")
            low = name.casefold()
            if low.endswith(REFUSED_SUFFIXES) or PurePosixPath(low).name in REFUSED_NAMES:
                raise InstallerError(f"Refused a game-like file in the bundle: {name!r}")
            if low in seen:
                raise InstallerError(f"Duplicate path in the bundle: {name!r}")
            seen.add(low)
            files.append((name, archive.read(entry)))
    missing = [r for r in REQUIRED if r.casefold() not in seen]
    if missing:
        raise InstallerError("The bundle has no launcher with its portable runtime: missing " + ", ".join(missing))
    return sorted(files, key=lambda item: item[0].casefold())


def game_files(games):
    """[(bundled-games/<game>/<name>, bytes)] for {game: folder with exactly its release zip, SHA256SUMS, .sig}."""
    files = []
    for game, folder in sorted((games or {}).items()):
        if game not in BUNDLE_GAMES:
            raise InstallerError(f"Unknown bundled game {game!r} (expected one of {', '.join(BUNDLE_GAMES)}).")
        names = sorted(p.name for p in Path(folder).iterdir())
        zips = [n for n in names if BUNDLE_ZIPS[game].fullmatch(n)]
        if len(zips) != 1 or set(names) != {zips[0], "SHA256SUMS", "SHA256SUMS.sig"}:
            raise InstallerError(f"{folder}: expected exactly the {game} release zip, SHA256SUMS and SHA256SUMS.sig, "
                                 f"found {names}")
        for name in names:
            files.append((f"{BUNDLE_DIR}/{game}/{name}", (Path(folder) / name).read_bytes()))
    return files


def build_payload(files, version, name="OpenRecomp-FGC", progress=None):
    header = f"name={name}\nversion={version}\nfiles={len(files)}\n".encode("utf-8")
    out = io.BytesIO()
    out.write(MAGIC)
    out.write(struct.pack("<I", len(header)))
    out.write(header)
    unpacked = 0
    for index, (path, data) in enumerate(files):
        # a bundled release zip is already compressed: stored as it is (LZMS over 100 MB would only cost time)
        method, stored = (STORED, data) if path.startswith(BUNDLE_DIR + "/") else pack(data)
        raw = path.encode("utf-8")
        out.write(struct.pack("<I", len(raw)) + raw)
        out.write(struct.pack("<QQI", len(data), len(stored), method))
        out.write(hashlib.sha256(data).digest())
        out.write(stored)
        unpacked += len(data)
        if progress and index % 200 == 0:
            progress(index, len(files))
    return out.getvalue(), unpacked


def parse_payload(blob):
    """The payload's files as [(path, bytes)] after the same checks Setup makes (for tests and --check)."""
    if blob[:8] != MAGIC:
        raise InstallerError("not a setup payload")
    (length,) = struct.unpack_from("<I", blob, 8)
    header = dict(line.split("=", 1) for line in blob[12:12 + length].decode("utf-8").splitlines() if "=" in line)
    pos = 12 + length
    files = []
    for _ in range(int(header["files"])):
        (n,) = struct.unpack_from("<I", blob, pos)
        path = blob[pos + 4:pos + 4 + n].decode("utf-8")
        pos += 4 + n
        size, stored, method = struct.unpack_from("<QQI", blob, pos)
        pos += 20
        digest = blob[pos:pos + 32]
        pos += 32
        data = decompress(blob[pos:pos + stored], size, method)
        pos += stored
        if hashlib.sha256(data).digest() != digest:
            raise InstallerError(f"{path}: checksum mismatch")
        files.append((path, data))
    if pos != len(blob):
        raise InstallerError("trailing bytes in the payload")
    return header, files


# ------------------------------------------------------------------------------------------------ compiling
def vcvars():
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise InstallerError("vswhere.exe not found: install Visual Studio 2022 Build Tools (C++).")
    found = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                           capture_output=True, text=True, check=False).stdout.strip().splitlines()
    for base in found:
        bat = Path(base) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
        if bat.is_file():
            return bat
    raise InstallerError("No MSVC x64 tools found (Visual Studio 2022 Build Tools, Desktop development with C++).")


RC = """#include <winver.h>
1 ICON "{icon}"
1 24 "{manifest}"
{payload}
VS_VERSION_INFO VERSIONINFO
 FILEVERSION {v1},{v2},{v3},0
 PRODUCTVERSION {v1},{v2},{v3},0
 FILEFLAGSMASK 0x3fL
 FILEFLAGS 0x0L
 FILEOS VOS_NT_WINDOWS32
 FILETYPE VFT_APP
 FILESUBTYPE 0x0L
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904b0"
    BEGIN
      VALUE "CompanyName", "OpenRecomp-FGC project"
      VALUE "FileDescription", "{description}"
      VALUE "FileVersion", "{version}"
      VALUE "InternalName", "{internal}"
      VALUE "LegalCopyright", "MIT licence. Contains no game data."
      VALUE "OriginalFilename", "{filename}"
      VALUE "ProductName", "OpenRecomp-FGC"
      VALUE "ProductVersion", "{version}"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
"""


def compile_program(work, out, version, *, payload=None, description, filename, icon):
    """setup.cpp -> out (.exe). With payload (a file path): the Setup, else the uninstaller."""
    work = Path(work)
    nums = (re.findall(r"\d+", version.split("-")[0]) + ["0", "0", "0"])[:3]
    manifest = work / "setup.manifest"
    manifest.write_bytes((SRC / "setup.manifest").read_bytes().replace(b"\r\n", b"\n"))
    rc = work / (out.stem.replace(" ", "_") + ".rc")
    slash = lambda p: str(p).replace("\\", "/")  # noqa: E731
    rc.write_text(RC.format(icon=slash(icon), manifest=slash(manifest),
                            payload=f'PAYLOAD RCDATA "{slash(payload)}"' if payload else "",
                            v1=nums[0], v2=nums[1], v3=nums[2], version=version, description=description,
                            internal=out.stem, filename=filename), encoding="utf-8")
    res = rc.with_suffix(".res")
    obj = work / "setup.obj"
    built = work / ("linked_" + out.stem.replace(" ", "_") + ".exe")
    cmd = (f'call "{vcvars()}" >nul && rc.exe /nologo /fo "{res}" "{rc}" && '
           f'cl.exe /nologo /c /O2 /MT /GS /guard:cf /W4 /EHsc /std:c++17 /utf-8 /DUNICODE /D_UNICODE '
           f'"{SRC / "setup.cpp"}" /Fo"{obj}" && '
           f'link.exe /nologo /OUT:"{built}" /SUBSYSTEM:WINDOWS /MANIFEST:NO /INCREMENTAL:NO /DYNAMICBASE '
           f'/NXCOMPAT /GUARD:CF /RELEASE /OPT:REF /OPT:ICF "{obj}" "{res}"')
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors="replace", check=False)
    if result.returncode != 0 or not built.is_file():
        raise InstallerError("Compiling the setup failed:\n" + result.stdout + result.stderr)
    warnings = [line for line in result.stdout.splitlines() if ": warning " in line]
    shutil.copy2(built, out)
    return warnings


def bundle_version(files):
    text = next((data.decode("utf-8") for path, data in files if path == f"{LAUNCHER}/openrecomp/__init__.py"), "")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def make(bundle, out_dir, version=None, log=print, games=None, name=None):
    """games: {game: release folder} for a full Setup; name: the Setup's file name (default the launcher-only one)."""
    files = bundle_files(bundle) + game_files(games)
    version = version or bundle_version(files)
    if not VERSION_RE.match(version):
        raise InstallerError(f"--version {version!r}: expected MAJOR.MINOR.PATCH")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    setup = out_dir / (name or f"OpenRecomp-FGC-Setup-{version}.exe")
    icon = ROOT / "openrecomp" / "ui" / "assets" / "icon.ico"
    with tempfile.TemporaryDirectory(prefix="orsetup-") as work:
        work = Path(work)
        uninstaller = work / "Uninstall_OpenRecomp.exe"
        warnings = compile_program(work, uninstaller, version, description="OpenRecomp-FGC Uninstall",
                                   filename=UNINSTALL_EXE, icon=icon)
        files.append((UNINSTALL_EXE, uninstaller.read_bytes()))
        files.sort(key=lambda item: item[0].casefold())
        log(f"packing {len(files)} files...")
        blob, unpacked = build_payload(files, version, progress=lambda i, n: log(f"  {i}/{n}"))
        payload = work / "payload.bin"
        payload.write_bytes(blob)
        warnings += compile_program(work, setup, version, payload=payload, description="OpenRecomp-FGC Setup",
                                    filename=setup.name, icon=icon)
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (out_dir / (setup.name + ".sha256")).write_text(f"{digest} *{setup.name}\n", encoding="ascii")
    facts = dict(setup=str(setup), version=version, files=len(files), unpacked_bytes=unpacked,
                 payload_bytes=len(blob), setup_bytes=setup.stat().st_size, sha256=digest,
                 t4=any(path.startswith("T4/") for path, _ in files), warnings=warnings,
                 games=sorted({path.split("/")[1] for path, _ in files if path.startswith(BUNDLE_DIR + "/")}))
    for key, value in facts.items():
        log(f"{key}: {value}")
    return facts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bundle", required=True, help="the bundle zip (OpenRecomp-FGC/ and optional T4/)")
    parser.add_argument("--out", default=str(ROOT / "dist"))
    parser.add_argument("--version", default=None, help="default: the launcher's __version__ in the bundle")
    parser.add_argument("--game", action="append", default=[], metavar="GAME=FOLDER",
                        help="a full Setup: that game's release files (zip, SHA256SUMS, SHA256SUMS.sig)")
    parser.add_argument("--name", default=None, help="the Setup's file name")
    args = parser.parse_args(argv)
    try:
        games = dict(item.split("=", 1) for item in args.game)
        make(args.bundle, args.out, args.version, games=games, name=args.name)
    except (InstallerError, OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"make_installer: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
