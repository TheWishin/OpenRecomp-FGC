"""The Tekken 4 tile's picture, read from the player's own ISO into their user folder (never shipped).

Tekken 4 (USA, SLUS-20328 v1.00) keeps its files in TEKKEN/DATA.BIN behind a table in the program (ELF): 16 bytes
per file -- sector (from the start of DATA.BIN), size, checksum, index, key. The first 4 KB of a file are coded
(word = ~word + key, key < 0 = plain) and the sum of its words is the checksum. The character-select portraits are
LZ-packed TIM2 pictures (248x307, 256 colours); entry 253 is Jin in his hooded jacket, the cover's look.

Only the player's verified disc is read (the program's SHA-1 must match), nothing is written next to it, and the
result is PNGs in <user folder>/art/t4/. Fighter portraits also accept the extracted disc directory from a build.
Standard library only; no text here is ever shown to the player (a
failure leaves the plain tile, its reason only goes to T4.art_note).
"""
import hashlib
import os
import struct
import tempfile
import zlib

from .adapters.t4_region import US_BOOT as ELF_NAME, US_ELF_SHA1 as ELF_SHA1

FILE_NAME = "hero_jin.png"
DATA_NAME = "TEKKEN/DATA.BIN"
FILE_TABLE = 0x313380                    # where the program keeps the DATA.BIN table (virtual address)
JIN_PORTRAIT = 253                       # table entry of Jin's select portrait
PORTRAIT_SIZE = (248, 307)
MAX_PACKED = 1 << 20
MAX_PICTURE = 4 << 20
# SLUS-20328 select renders, each decoded and visually checked. Alternate costume renders at 267-270
# are deliberately excluded; the square player portraits use one consistent render per character.
FIGHTER_PORTRAITS = {
    "paul": 244, "law": 245, "lei": 246, "king": 247, "yoshimitsu": 248, "nina": 249,
    "hwoarang": 250, "xiaoyu": 251, "christie": 252, "jin": 253, "julia": 254, "kuma": 255,
    "bryan": 256, "heihachi": 257, "kazuya": 258, "lee": 259, "steve": 260, "marduk": 261,
    "combot": 262, "panda": 263, "violet": 264, "eddy": 265, "miharu": 266,
}
# (sector size, offset of the 2048 user bytes): plain ISO, raw MODE1, raw MODE2/XA, 2336-byte sectors
LAYOUTS = ((2048, 0), (2352, 16), (2352, 24), (2336, 8))


class ArtError(Exception):
    pass


class Disc:
    def __init__(self, path):
        self.f = open(path, "rb")
        try:
            self.ss, self.off = self._layout()
        except BaseException:
            self.f.close()
            raise

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _layout(self):
        for ss, off in LAYOUTS:
            self.f.seek(16 * ss + off)
            head = self.f.read(6)
            if len(head) == 6 and head[0] == 1 and head[1:6] == b"CD001":
                return ss, off
        raise ArtError("not an ISO9660 image")

    def read(self, lba, length):
        parts = []
        while length > 0:
            self.f.seek(lba * self.ss + self.off)
            part = self.f.read(min(length, 2048) if self.ss != 2048 else length)
            if not part:
                raise ArtError("the image ends early")
            parts.append(part)
            length -= len(part)
            lba += (len(part) + 2047) // 2048
        return b"".join(parts)

    def find(self, name):
        """(lba, size) of a file by its path, e.g. TEKKEN/DATA.BIN."""
        root = self.read(16, 2048)[156:190]
        lba, size = struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0]
        parts = name.upper().split("/")
        for depth, part in enumerate(parts):
            found = None
            data = self.read(lba, min(size, 1 << 20))
            i = 0
            while i < len(data):
                n = data[i]
                if n == 0:
                    i = (i // 2048 + 1) * 2048
                    continue
                rec = data[i:i + n]
                i += n
                if len(rec) < 33:
                    break
                label = rec[33:33 + rec[32]].decode("latin-1").split(";")[0].upper()
                if label == part and bool(rec[25] & 2) == (depth < len(parts) - 1):
                    found = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
                    break
            if found is None:
                raise ArtError(f"{name} is not on the disc")
            lba, size = found
        return lba, size


def elf_reader(elf):
    if elf[:4] != b"\x7fELF":
        raise ArtError("the program is not an ELF")
    phoff, phnum = struct.unpack_from("<I", elf, 0x1C)[0], struct.unpack_from("<H", elf, 0x2C)[0]
    segments = []
    for k in range(phnum):
        kind, offset, vaddr, _paddr, filesz = struct.unpack_from("<5I", elf, phoff + 32 * k)
        if kind == 1:
            segments.append((vaddr, offset, filesz))

    def read(address, length):
        for vaddr, offset, filesz in segments:
            if vaddr <= address and address + length <= vaddr + filesz:
                return elf[offset + address - vaddr:offset + address - vaddr + length]
        raise ArtError("the file table is not in the program")
    return read


def unpack_lz(src, limit=MAX_PICTURE):
    """The game's LZ: a flag byte (bits from the lowest, the top set bit ends it; 0 = end), 1 = one literal byte,
    0 = big-endian u16 back reference: distance = low 11 bits (0 = 2048), length = next 5 bits (0 = 32)."""
    out = bytearray()
    i = 0
    try:
        flags = src[i]
        i += 1
        while flags:
            while flags >= 2:
                if flags & 1:
                    out.append(src[i])
                    i += 1
                else:
                    word = (src[i] << 8) | src[i + 1]
                    i += 2
                    start = len(out) - ((word & 0x7FF) or 0x800)
                    for k in range((word >> 11 & 0x1F) or 0x20):
                        out.append(out[start + k] if start + k >= 0 else 0)
                if len(out) > limit:
                    raise ArtError("the picture unpacks too large")
                flags >>= 1
            if i >= len(src):
                break
            flags = src[i]
            i += 1
    except IndexError:
        raise ArtError("the packed picture is cut short") from None
    return bytes(out)


def tim2_rgba(data):
    """(width, height, RGBA bytes) of the first picture of a TIM2 with a 16- or 256-colour 32-bit palette."""
    if len(data) < 64 or data[:4] != b"TIM2":
        raise ArtError("not a TIM2 picture")
    _total, clut_size, image_size, header, colours, _fmt, _mip, clut_type, image_type, w, h = \
        struct.unpack_from("<IIIHHBBBBHH", data, 16)
    bits = {4: 4, 5: 8}.get(image_type)
    if bits is None or clut_type & 0x3F != 3 or colours not in (16, 256) or not (0 < w <= 1024 and 0 < h <= 1024):
        raise ArtError("unexpected TIM2 picture layout")
    pixels = data[16 + header:16 + header + image_size]
    clut = data[16 + header + image_size:16 + header + image_size + clut_size]
    if len(pixels) < (w * h * bits + 7) // 8 or len(clut) < colours * 4:
        raise ArtError("the TIM2 picture is cut short")
    palette = [bytes((clut[4 * k], clut[4 * k + 1], clut[4 * k + 2], min(255, clut[4 * k + 3] * 2)))
               for k in range(colours)]                    # GS alpha: 0x80 = opaque
    if colours == 256 and not clut_type & 0x80:            # CSM1: entries 8-15 and 16-23 of each 32 swapped
        palette = [palette[(k & ~0x18) | (k & 8) << 1 | (k & 0x10) >> 1] for k in range(256)]
    out = bytearray()
    if bits == 8:
        for y in range(h):
            out += b"".join(palette[p] for p in pixels[y * w:(y + 1) * w])
    else:
        for y in range(h):
            for x in range(w):
                b = pixels[(y * w + x) // 2]
                out += palette[b >> 4 if x & 1 else b & 15]
    return w, h, bytes(out)


def soften(w, h, rgba, left=0.12, bottom=0.30):
    """Fade the left and bottom edges out, so the bust melts into the tile instead of ending in a hard line."""
    out = bytearray(rgba)
    for y in range(h):
        fy = min(1.0, (h - 1 - y) / max(1.0, bottom * h))
        for x in range(w):
            f = min(fy, min(1.0, x / max(1.0, left * w)))
            if f < 1.0:
                a = 4 * (y * w + x) + 3
                out[a] = int(out[a] * f * f * (3 - 2 * f))
    return bytes(out)


def png_bytes(w, h, rgba):
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def read_entry(disc, index):
    """The decoded bytes of one DATA.BIN file (checksum verified)."""
    elf_lba, elf_size = disc.find(ELF_NAME)
    if not 0 < elf_size <= 16 << 20:
        raise ArtError("unexpected program size")
    elf = disc.read(elf_lba, elf_size)
    sector, size, checksum, key = file_entry(elf, index)
    data_lba, data_size = disc.find(DATA_NAME)
    if (sector * 2048 + size) > data_size:
        raise ArtError("the file table points past DATA.BIN")
    return decode_entry(disc.read(data_lba + sector, size), checksum, key)


def file_entry(elf, index):
    if hashlib.sha1(elf).hexdigest() != ELF_SHA1:
        raise ArtError("not Tekken 4 (USA) SLUS-20328")
    sector, size, checksum, number, key = struct.unpack("<IIIhh", elf_reader(elf)(FILE_TABLE + 16 * index, 16))
    if number != index or not 0 < size <= MAX_PACKED:
        raise ArtError("unexpected file table entry")
    return sector, size, checksum, key


def decode_entry(stored, checksum, key):
    data = bytearray(stored)
    if key >= 0:
        n = min(4096, len(data)) // 4
        words = struct.unpack_from(f"<{n}I", data)
        struct.pack_into(f"<{n}I", data, 0, *[(~word + key) & 0xFFFFFFFF for word in words])
    whole = len(data) // 4
    if sum(struct.unpack_from(f"<{whole}I", data)) & 0xFFFFFFFF != checksum:
        raise ArtError("the file's checksum does not match")
    return bytes(data)


def source_stamp(source):
    """A source identity for retrying only when the player's disc files change."""
    paths = [os.path.join(source, ELF_NAME), os.path.join(source, *DATA_NAME.split("/"))] \
        if os.path.isdir(source) else [source]
    try:
        stamps = []
        for path in paths:
            info = os.stat(path)
            stamps.append((os.path.normcase(os.path.abspath(path)), info.st_size, info.st_mtime_ns))
        return tuple(stamps)
    except OSError:
        return None


def read_source_entry(source, index):
    """Read only the verified ELF and one packed picture, from a disc directory or ISO."""
    if not os.path.isdir(source):
        with Disc(source) as disc:
            return read_entry(disc, index)
    with open(os.path.join(source, ELF_NAME), "rb") as stream:
        elf = stream.read((16 << 20) + 1)
    if not 0 < len(elf) <= 16 << 20:
        raise ArtError("unexpected program size")
    sector, size, checksum, key = file_entry(elf, index)
    with open(os.path.join(source, *DATA_NAME.split("/")), "rb") as stream:
        if sector * 2048 + size > os.fstat(stream.fileno()).st_size:
            raise ArtError("the file table points past DATA.BIN")
        stream.seek(sector * 2048)
        stored = stream.read(size)
    if len(stored) != size:
        raise ArtError("DATA.BIN ends early")
    return decode_entry(stored, checksum, key)


def make_fighter(source, key, path):
    """Cache a fighter's square head crop from the player's ISO or extracted disc, atomically."""
    return _make_fighter(source, key, path)


def make_fighter_render(source, key, path, mirrored=False):
    """Keep the complete native select cut-out for a VS card, including its original alpha."""
    return _make_fighter(source, key, path, full=True, mirrored=mirrored)


def _make_fighter(source, key, path, full=False, mirrored=False):
    if not isinstance(key, str) or key not in FIGHTER_PORTRAITS:
        raise ArtError("unknown fighter")
    before = source_stamp(source)
    if before is None:
        raise ArtError("the portrait source is missing")
    w, h, rgba = tim2_rgba(unpack_lz(read_source_entry(source, FIGHTER_PORTRAITS[key])))
    if (w, h) != PORTRAIT_SIZE:
        raise ArtError("unexpected portrait size")
    # These select renders put the head at the top. Keep the original alpha, without the tile's edge fade.
    height = h if full else w
    rgba = rgba[:w * height * 4]
    if mirrored:
        from .fighter_render import mirror_rgba
        rgba = mirror_rgba(rgba, w, height)
    picture = png_bytes(w, height, rgba)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".fighter-", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            stream.write(picture)
        if source_stamp(source) != before:
            raise ArtError("the portrait source changed")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return path


def make_hero(iso, path):
    """Write Jin's portrait from the ISO to path (PNG, atomically). ArtError/OSError on anything unexpected."""
    with Disc(iso) as disc:
        packed = read_entry(disc, JIN_PORTRAIT)
    w, h, rgba = tim2_rgba(unpack_lz(packed))
    if (w, h) != PORTRAIT_SIZE:
        raise ArtError("unexpected portrait size")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".openrecomp.tmp"
    with open(temporary, "wb") as f:
        f.write(png_bytes(w, h, soften(w, h, rgba)))
    os.replace(temporary, path)
    return path
