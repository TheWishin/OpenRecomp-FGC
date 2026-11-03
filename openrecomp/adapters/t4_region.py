"""The launcher's Tekken 4 is the US release only (SLUS-20328 v1.00, our line us-slus20328).

Another T4 project with the same layout exists for the PAL disc (SCES-50878). Its scripts accept a PAL image and
build it without complaint, so the launcher looks at the tree itself before it verifies an image, builds or plays,
and refuses with a message wherever the tree names another disc: its disc check pins another boot file or ELF,
its build script pins another ELF, its launcher core plays another ELF, its extracted game is another ELF, or the
disc check's own answer (BOOT2 / ELF_SHA1 lines) names another disc. Never a quiet build of the wrong version.
"""
import hashlib
import os
import re

US_SERIAL = "SLUS-20328"
US_BOOT = "SLUS_203.28"
US_ELF_SHA1 = hex(0xa4b7dde20a2918c550badd127a245db155c36815)[2:].zfill(40)    # SHA-1 of SLUS_203.28 v1.00
NOT_US = "@t4.region.not_us"

_BOOT = re.compile(r"""^EXPECTED_BOOT\s*=\s*["']([^"']+)["']""", re.M)
_SHA1 = re.compile(r"""^EXPECTED_SHA1\s*=\s*["']([0-9A-Fa-f]{40})["']""", re.M)
_PS_SHA1 = re.compile(r"""\$ExpectedElfSha1\s*=\s*['"]([0-9A-Fa-f]{40})['"]""")
_CORE_ELF = re.compile(r"""^GAME_ELF\s*=.*["']([A-Z]{4}_\d{3}\.\d{2})["']""", re.M)
_SERIAL_FILE = re.compile(r"^[A-Z]{4}_\d{3}\.\d{2}$")
_elf_cache = {}


def _read(path, limit=2_000_000):
    try:
        with open(path, "rb") as stream:
            return stream.read(limit).decode("utf-8", "replace")
    except OSError:
        return None


def _elf_sha1(path):
    try:
        info = os.stat(path)
    except OSError:
        return None
    key = (os.path.normcase(os.path.abspath(path)), info.st_size, info.st_mtime_ns)
    if key not in _elf_cache:
        h = hashlib.sha1()
        try:
            with open(path, "rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    h.update(block)
        except OSError:
            return None
        _elf_cache.clear()
        _elf_cache[key] = h.hexdigest()
    return _elf_cache[key]


def tree_problem(root):
    """NOT_US (an i18n key) when the T4 tree at root names another disc than Tekken 4 USA; else None."""
    if not root:
        return None
    iso_tool = _read(os.path.join(root, "tools", "iso_extract.py"))
    if iso_tool is not None:
        boot, sha1 = _BOOT.search(iso_tool), _SHA1.search(iso_tool)
        if (boot and boot.group(1).upper() != US_BOOT) or (sha1 and sha1.group(1).lower() != US_ELF_SHA1):
            return NOT_US
    build = _read(os.path.join(root, "tools", "build_game.ps1"))
    pinned = _PS_SHA1.search(build or "")
    if pinned and pinned.group(1).lower() != US_ELF_SHA1:
        return NOT_US
    core = _read(os.path.join(root, "launcher", "t4core.py"))
    elf = _CORE_ELF.search(core or "")
    if elf and elf.group(1).upper() != US_BOOT:
        return NOT_US
    disc = os.path.join(root, "game", "disc")
    try:
        names = os.listdir(disc)
    except OSError:
        names = []
    for name in names:
        if _SERIAL_FILE.match(name.upper()) and name.upper() != US_BOOT:
            return NOT_US
        if name.upper() == US_BOOT:
            digest = _elf_sha1(os.path.join(disc, name))
            if digest and digest != US_ELF_SHA1:
                return NOT_US
    return None


def checked_disc_problem(output):
    """NOT_US when the disc check's own output names another boot file or ELF; else None."""
    for line in str(output or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == "ELF_SHA1" and parts[1].lower() != US_ELF_SHA1:
            return NOT_US
        if len(parts) == 2 and parts[0] == "BOOT2" and parts[1].upper() != US_BOOT:
            return NOT_US
    return None
