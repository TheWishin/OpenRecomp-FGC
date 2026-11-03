"""tools/make_installer.py and tools/installer/setup.cpp: payload format, bundle checks, texts, manifest.

Compiling the real Setup needs Visual Studio's C++ tools and takes a while: set OPENRECOMP_SETUP_BUILD_TEST=1
for that test (the release check and the installer proof run it).
"""
import hashlib
import io
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import make_installer as mi  # noqa: E402

SETUP = (ROOT / "tools" / "installer" / "setup.cpp").read_text(encoding="utf-8")


def bundle(extra=(), skip=()):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        for name in ("START_HERE.txt", "OpenRecomp-FGC/portable/pythonw.exe", "OpenRecomp-FGC/portable/python312._pth",
                     "OpenRecomp-FGC/openrecomp/app.py", "OpenRecomp-FGC/openrecomp/__init__.py", "T4/tools/build_game.ps1"):
            if name not in skip:
                z.writestr(name, '__version__ = "1.2.3"\n' if name.endswith("__init__.py") else name * 50)
        for name, content in extra:
            z.writestr(name, content)
    data.seek(0)
    return data


class BundleTest(unittest.TestCase):
    def test_launcher_and_t4_taken_start_texts_left_out(self):
        files = mi.bundle_files(bundle())
        names = [n for n, _ in files]
        self.assertIn("OpenRecomp-FGC/portable/pythonw.exe", names)
        self.assertIn("T4/tools/build_game.ps1", names)
        self.assertNotIn("START_HERE.txt", names)
        self.assertEqual(mi.bundle_version(files), "1.2.3")

    def test_refuses_game_files_traversal_and_foreign_folders(self):
        for name in ("OpenRecomp-FGC/game.iso", "T4/disc/SLUS_203.28", "OpenRecomp-FGC/x/EBOOT.BIN",
                     "OpenRecomp-FGC/a/../../evil.txt", "Other/readme.txt", "OpenRecomp-FGC/trail. /x"):
            with self.subTest(name=name), self.assertRaises(mi.InstallerError):
                mi.bundle_files(bundle(extra=[(name, b"x")]))

    def test_refuses_a_bundle_without_the_portable_runtime(self):
        with self.assertRaises(mi.InstallerError):
            mi.bundle_files(bundle(skip=("OpenRecomp-FGC/portable/pythonw.exe",)))


@unittest.skipUnless(os.name == "nt", "the Windows Compression API")
class PayloadTest(unittest.TestCase):
    def test_round_trip_with_every_method_and_checksums(self):
        files = [("a/empty.txt", b""), ("a/small.txt", b"hello"), ("b/text.py", b"print('x')\n" * 5000),
                 ("c/random.bin", os.urandom(200_000))]
        blob, unpacked = mi.build_payload(files, "0.9.0")
        self.assertEqual(unpacked, sum(len(d) for _, d in files))
        header, back = mi.parse_payload(blob)
        self.assertEqual(header["version"], "0.9.0")
        self.assertEqual(back, files)
        self.assertLess(len(blob), unpacked)        # the text compresses, random data is stored

    def test_damaged_payload_is_refused(self):
        blob, _ = mi.build_payload([("x.txt", b"some text " * 1000)], "0.9.0")
        damaged = bytearray(blob)
        damaged[-5] ^= 0xFF
        with self.assertRaises(mi.InstallerError):
            mi.parse_payload(bytes(damaged))
        with self.assertRaises(mi.InstallerError):
            mi.parse_payload(blob + b"!")

    def test_entry_layout_is_what_setup_reads(self):
        blob, _ = mi.build_payload([("dir/file.txt", b"abc")], "1.0.0")
        self.assertEqual(blob[:8], b"ORSETUP1")
        (length,) = struct.unpack_from("<I", blob, 8)
        pos = 12 + length
        (n,) = struct.unpack_from("<I", blob, pos)
        self.assertEqual(blob[pos + 4:pos + 4 + n], b"dir/file.txt")
        size, stored, method = struct.unpack_from("<QQI", blob, pos + 4 + n)
        self.assertEqual((size, stored, method), (3, 3, mi.STORED))
        self.assertEqual(blob[pos + 4 + n + 20:pos + 4 + n + 52], hashlib.sha256(b"abc").digest())


class SetupSourceTest(unittest.TestCase):
    def test_every_language_has_every_text(self):
        count = len(re.search(r"enum Text \{(.*?)T_COUNT", SETUP, re.S).group(1).split(","))
        blocks = re.findall(r'\{L"(\w\w)", \{(.*?)\n    \}\},', SETUP, re.S)
        self.assertEqual([code for code, _ in blocks], ["en", "de", "es", "fr", "ja", "ko", "pt"])
        for code, body in blocks:
            texts = re.findall(r'^\s+L"(?:[^"\\]|\\.)*",$', body, re.M)
            self.assertEqual(len(texts), count - 1, code)

    def test_per_user_without_admin_rights(self):
        manifest = (ROOT / "tools" / "installer" / "setup.manifest").read_text(encoding="utf-8")
        self.assertIn('level="asInvoker"', manifest)
        self.assertIn("HKEY_CURRENT_USER, UNINSTALL_KEY", SETUP)
        self.assertNotIn("HKEY_LOCAL_MACHINE", SETUP)

    def test_uninstall_keeps_games_and_saves(self):
        body = SETUP[SETUP.index("static void remove_settings"):SETUP.index("static std::vector<std::wstring> leftovers")]
        self.assertNotIn('L"installs"', body)
        self.assertIn('L"settings.json"', body)          # t4-source\<id>\settings.json only; save\ stays
        self.assertIn("is_game_entry(f)", SETUP[SETUP.index("static int uninstall"):])


@unittest.skipUnless(os.environ.get("OPENRECOMP_SETUP_BUILD_TEST") == "1", "set OPENRECOMP_SETUP_BUILD_TEST=1")
class BuildTest(unittest.TestCase):
    def test_compiles_the_uninstaller_without_warnings(self):
        with tempfile.TemporaryDirectory() as work:
            out = Path(work) / "Uninstall.exe"
            warnings = mi.compile_program(work, out, "0.1.0", description="test", filename="Uninstall.exe",
                                          icon=ROOT / "openrecomp" / "ui" / "assets" / "icon.ico")
            self.assertEqual(warnings, [])
            self.assertEqual(out.read_bytes()[:2], b"MZ")


if __name__ == "__main__":
    unittest.main()
