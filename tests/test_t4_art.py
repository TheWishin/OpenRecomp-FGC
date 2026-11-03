"""Tekken 4 tile picture: read from a synthetic disc that has the real layout but no game data."""
import hashlib
import os
import struct
import tempfile
import time
import unittest
import zlib
from unittest import mock

from openrecomp import t4_art
from openrecomp.adapters.t4 import T4

MANIFEST = dict(id="t4", short="T4", title="T4", numeral="4", accent="#ffffff", subtitle="", sections=["settings"])
W, H = t4_art.PORTRAIT_SIZE
KEY = 0x1234


# ------------------------------------------------------------------ a disc built from nothing
def pack_lz(data):
    """Encoder for the game's LZ: runs of one byte as distance-1 references, the rest as literals."""
    items, i = [], 0
    while i < len(data):
        run = 1
        while i + run < len(data) and data[i + run] == data[i] and run < 32:
            run += 1
        if i > 0 and data[i - 1] == data[i] and run >= 3:
            items.append((False, struct.pack(">H", (run % 32) << 11 | 1)))
            i += run
        else:
            items.append((True, data[i:i + 1]))
            i += 1
    out = bytearray()
    for k in range(0, len(items), 7):
        group = items[k:k + 7]
        out.append(sum(1 << b for b, (lit, _) in enumerate(group) if lit) | 1 << len(group))
        for _lit, body in group:
            out += body
    out.append(0)
    return bytes(out)


def tim2(w=W, h=H, swizzled=True):
    clut = bytearray()
    for k in range(256):
        clut += bytes((k, 255 - k, 7, 0x80))
    pixels = bytes((x + y) % 32 for y in range(h) for x in range(w))
    image = pixels + bytes(-len(pixels) % 16)
    header = struct.pack("<IIIHHBBBBHH", 48 + len(image) + 1024, 1024, len(image), 48, 256, 0, 1,
                         3 if swizzled else 0x83, 5, w, h)
    return b"TIM2" + bytes((4, 0, 1, 0)) + bytes(8) + header + bytes(48 - len(header)) + image + bytes(clut)


def coded(data, key=KEY):
    """The stored form: words of the first 4 KB are ~(word - key); checksum = sum of the decoded words."""
    data = bytearray(data)
    checksum = sum(struct.unpack_from(f"<{len(data) // 4}I", data)) & 0xFFFFFFFF
    if key >= 0:
        n = min(4096, len(data)) // 4
        words = struct.unpack_from(f"<{n}I", data)
        struct.pack_into(f"<{n}I", data, 0, *[~(word - key) & 0xFFFFFFFF for word in words])
    return bytes(data), checksum


def fake_elf(entry):
    table = t4_art.FILE_TABLE
    body = bytearray(16 * (t4_art.JIN_PORTRAIT + 1))
    body[16 * t4_art.JIN_PORTRAIT:] = entry
    header = bytearray(0x34 + 32)
    header[:4] = b"\x7fELF"
    struct.pack_into("<I", header, 0x1C, 0x34)
    struct.pack_into("<H", header, 0x2C, 1)
    struct.pack_into("<5I", header, 0x34, 1, len(header), table, table, len(body))
    return bytes(header + body)


def dir_record(name, lba, size, folder=False):
    label = name.encode("ascii") if name in ("\0", "\1") else (name + ("" if folder else ";1")).encode("ascii")
    rec = bytearray(33 + len(label) + (len(label) + 1) % 2)
    rec[0] = len(rec)
    struct.pack_into("<I", rec, 2, lba)
    struct.pack_into("<I", rec, 10, size)
    rec[25] = 2 if folder else 0
    rec[32] = len(label)
    rec[33:33 + len(label)] = label
    return bytes(rec)


def build_iso(path, packed=None, key=KEY, checksum_delta=0, elf_patch=None, sector=2048, offset=0):
    """ISO9660 with SLUS_203.28 and TEKKEN/DATA.BIN; returns the fake ELF's SHA-1."""
    if packed is None:
        packed = pack_lz(tim2())
    stored, checksum = coded(packed, key)
    data_sector = 3
    entry = struct.pack("<IIIhh", data_sector, len(packed), (checksum + checksum_delta) & 0xFFFFFFFF,
                        t4_art.JIN_PORTRAIT, key)
    elf = fake_elf(entry)
    if elf_patch:
        elf = elf_patch(elf)
    elf_lba, tekken_lba, data_lba = 20, 19, 40
    data = bytes(data_sector * 2048) + stored
    root = dir_record("\0", 18, 2048, True) + dir_record("\1", 18, 2048, True) \
        + dir_record("SLUS_203.28", elf_lba, len(elf)) + dir_record("TEKKEN", tekken_lba, 2048, True)
    tekken = dir_record("\0", tekken_lba, 2048, True) + dir_record("\1", 18, 2048, True) \
        + dir_record("DATA.BIN", data_lba, len(data))
    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[156:156 + 34] = dir_record("\0", 18, 2048, True)
    struct.pack_into("<H", pvd, 128, 2048)
    blocks = {16: bytes(pvd), 18: root, 19: tekken}
    for k in range(0, len(elf), 2048):
        blocks[elf_lba + k // 2048] = elf[k:k + 2048]
    for k in range(0, len(data), 2048):
        blocks[data_lba + k // 2048] = data[k:k + 2048]
    with open(path, "wb") as f:
        for lba in range(max(blocks) + 1):
            user = blocks.get(lba, b"").ljust(2048, b"\0")
            f.write(bytes(offset) + user + bytes(sector - offset - 2048))
    return hashlib.sha1(elf).hexdigest()


def read_png(path):
    with open(path, "rb") as f:
        blob = f.read()
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
    i, idat, w, h = 8, b"", 0, 0
    while i < len(blob):
        n = struct.unpack_from(">I", blob, i)[0]
        kind, body = blob[i + 4:i + 8], blob[i + 8:i + 8 + n]
        if kind == b"IHDR":
            w, h = struct.unpack_from(">II", body)
        elif kind == b"IDAT":
            idat += body
        i += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[y * (4 * w + 1) + 1:(y + 1) * (4 * w + 1)] for y in range(h)]
    return w, h, rows


class Extract(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.iso = os.path.join(self.tmp, "Tekken 4 (USA).iso")
        self.out = os.path.join(self.tmp, "home", "art", "t4", t4_art.FILE_NAME)

    def make(self, **kwargs):
        sha1 = build_iso(self.iso, **kwargs)
        with mock.patch.object(t4_art, "ELF_SHA1", sha1):
            return t4_art.make_hero(self.iso, self.out)

    def test_portrait_becomes_a_png_with_its_palette_and_soft_edges(self):
        self.assertEqual(self.make(), self.out)
        w, h, rows = read_png(self.out)
        self.assertEqual((w, h), (W, H))
        x, y = W - 1, 24                                 # index (x + y) % 32 = 15 -> CSM1 swaps 8-15 with 16-23
        self.assertEqual(tuple(rows[y][4 * x:4 * x + 4]), (23, 232, 7, 255))
        x, y = W - 9, 0                                  # index 239 % 32 = 15 again
        self.assertEqual(tuple(rows[y][4 * x:4 * x + 3]), (23, 232, 7))
        self.assertEqual(rows[H - 1][3], 0)              # bottom-left corner faded out
        self.assertEqual(rows[0][3], 0)                  # left edge faded out
        self.assertEqual(rows[0][4 * (W - 1) + 3], 255)  # top right keeps the picture
        self.assertFalse(os.path.exists(self.out + ".openrecomp.tmp"))

    def test_linear_palette_is_not_reordered(self):
        self.make(packed=pack_lz(tim2(swizzled=False)))
        _w, _h, rows = read_png(self.out)
        x = W - 1                                        # y = 24: index 15
        self.assertEqual(tuple(rows[24][4 * x:4 * x + 3]), (15, 240, 7))

    def test_raw_sector_images_read_the_same(self):
        self.make(sector=2352, offset=24)
        self.assertEqual(read_png(self.out)[:2], (W, H))

    def test_other_disc_is_refused_and_writes_nothing(self):
        build_iso(self.iso)
        with self.assertRaises(t4_art.ArtError):
            t4_art.make_hero(self.iso, self.out)      # the real SLUS-20328 hash never matches the fake program
        self.assertFalse(os.path.exists(self.out))

    def test_checksum_mismatch_is_refused(self):
        with self.assertRaisesRegex(t4_art.ArtError, "checksum"):
            self.make(checksum_delta=1)
        self.assertFalse(os.path.exists(self.out))

    def test_plain_file_without_key_is_read_as_is(self):
        self.make(key=-1)
        self.assertTrue(os.path.isfile(self.out))

    def test_wrong_picture_size_is_refused(self):
        with self.assertRaisesRegex(t4_art.ArtError, "size"):
            self.make(packed=pack_lz(tim2(w=64, h=64)))

    def test_not_an_iso(self):
        with open(self.iso, "wb") as f:
            f.write(bytes(64 * 1024))
        with self.assertRaises(t4_art.ArtError):
            t4_art.make_hero(self.iso, self.out)


class Unpack(unittest.TestCase):
    def test_back_references_repeat_and_reach_before_the_start(self):
        # flag 0b1101: literal 'A', reference (distance 1, length 4), literal 'B'; then end
        self.assertEqual(t4_art.unpack_lz(bytes((0b1101, 0x41, 0x20, 0x01, 0x42, 0))), b"AAAAAB")
        # a reference before the first byte reads zeros, length 0 = 32
        self.assertEqual(t4_art.unpack_lz(bytes((0b10, 0x00, 0x05, 0))), bytes(32))

    def test_round_trip(self):
        data = tim2(32, 16)
        self.assertEqual(t4_art.unpack_lz(pack_lz(data)), data)

    def test_cut_short_is_an_art_error(self):
        with self.assertRaises(t4_art.ArtError):
            t4_art.unpack_lz(bytes((0b10, 0x00)))

    def test_size_limit(self):
        with self.assertRaisesRegex(t4_art.ArtError, "large"):
            t4_art.unpack_lz(bytes((0b10, 0x00, 0x01) * 40 + (0,)), limit=1000)


class Core:
    def __init__(self, iso=""):
        self.iso = iso

    def load_settings(self):
        return dict(iso=self.iso)

    def effective_iso(self, settings):
        return settings.get("iso") if os.path.isfile(settings.get("iso") or "") else ""


class AdapterHero(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=os.path.join(self.tmp, "home")))
        self.iso = os.path.join(self.tmp, "t4.iso")
        self.sha1 = build_iso(self.iso)
        self.art = os.path.join(self.tmp, "home", "art", "t4")

    def adapter(self, iso=None):
        return T4(MANIFEST, {}, "fake-root", core=Core(self.iso if iso is None else iso))

    def wait(self, adapter):
        for _ in range(500):
            if not adapter._art_busy:
                return
            time.sleep(0.01)
        self.fail("the picture thread did not finish")

    def test_verified_iso_gives_the_tile_jin_once(self):
        a = self.adapter()
        with mock.patch.object(t4_art, "ELF_SHA1", self.sha1):
            self.assertEqual(a.hero(), "")               # started in the background
            self.wait(a)
            path = a.hero()
        self.assertEqual(path, os.path.join(self.art, t4_art.FILE_NAME))
        self.assertTrue(os.path.isfile(path))
        with mock.patch.object(t4_art, "make_hero") as make:
            self.assertEqual(self.adapter().hero(), path)   # cached: the disc is not read again
        make.assert_not_called()

    def test_players_own_picture_wins(self):
        os.makedirs(self.art)
        own = os.path.join(self.art, "hero.png")
        with open(own, "wb") as f:
            f.write(b"x")
        with mock.patch.object(t4_art, "make_hero") as make:
            self.assertEqual(self.adapter().hero(), own)
        make.assert_not_called()

    def test_without_an_iso_the_tile_stays_plain(self):
        a = self.adapter(iso=os.path.join(self.tmp, "missing.iso"))
        with mock.patch.object(t4_art, "make_hero") as make:
            self.assertEqual(a.hero(), "")
        make.assert_not_called()

    def test_core_without_iso_support(self):
        a = self.adapter()
        a.core = object()
        self.assertEqual(a.hero(), "")
        self.assertFalse(a._art_busy)

    def test_wrong_disc_is_tried_once_and_noted(self):
        a = self.adapter()                               # real hash: the fake program is refused
        self.assertEqual(a.hero(), "")
        self.wait(a)
        self.assertIn("SLUS-20328", a.art_note)
        with mock.patch.object(t4_art, "make_hero") as make:
            self.assertEqual(a.hero(), "")
        make.assert_not_called()


if __name__ == "__main__":
    unittest.main()
