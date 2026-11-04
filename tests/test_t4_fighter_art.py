"""Fighter cache extraction uses synthetic disc data and never needs a game install."""
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from openrecomp import t4_art
from openrecomp.adapters.t4 import T4
from test_t4_art import Core, MANIFEST, build_iso, pack_lz, read_png, tim2


class FighterExtract(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.iso = self.tmp / "synthetic.iso"
        self.out = self.tmp / "home" / "art" / "t4" / "fighters" / "jin.png"
        self.sha1 = build_iso(str(self.iso))
        self.enterContext(mock.patch.object(t4_art, "ELF_SHA1", self.sha1))
        self.enterContext(mock.patch.object(t4_art, "FIGHTER_PORTRAITS", {"jin": t4_art.JIN_PORTRAIT}))

    def extracted(self):
        root = self.tmp / "disc"
        (root / "TEKKEN").mkdir(parents=True)
        with t4_art.Disc(str(self.iso)) as disc:
            for name in (t4_art.ELF_NAME, t4_art.DATA_NAME):
                lba, size = disc.find(name)
                (root / name).write_bytes(disc.read(lba, size))
        return root

    def make(self, source=None):
        return t4_art.make_fighter(str(source or self.iso), "jin", str(self.out))

    def test_iso_becomes_an_unfaded_square_head_crop(self):
        self.assertEqual(self.make(), str(self.out))
        w, h, rows = read_png(str(self.out))
        self.assertEqual((w, h), (248, 248))
        # The square starts at the portrait's top; hero art instead fades these edges.
        self.assertEqual(tuple(rows[0][:4]), (0, 255, 7, 255))
        # At source (0, 247), index 23 maps to CSM1 palette entry 15.
        self.assertEqual(tuple(rows[247][:4]), (15, 240, 7, 255))
        self.assertFalse(Path(str(self.out) + ".openrecomp.tmp").exists())

    def test_raw_sector_iso_has_the_same_crop(self):
        self.sha1 = build_iso(str(self.iso), sector=2352, offset=24)
        self.make()
        self.assertEqual(read_png(str(self.out))[:2], (248, 248))

    def test_extracted_files_give_identical_png_and_are_unchanged(self):
        root = self.extracted()
        original = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        self.make()
        expected = self.out.read_bytes()
        self.out.unlink()
        self.assertEqual(self.make(root), str(self.out))
        self.assertEqual(self.out.read_bytes(), expected)
        self.assertEqual({path: path.read_bytes() for path in original}, original)
        self.assertEqual({path for path in root.rglob("*") if path.is_file()}, set(original))

    def test_unknown_fighter_is_rejected_without_reading_source(self):
        for key in ("unknown", "../jin", "jin/other", "", None):
            with self.subTest(key=key), mock.patch.object(t4_art, "Disc") as disc:
                with self.assertRaises(t4_art.ArtError):
                    t4_art.make_fighter("missing.iso", key, str(self.out))
                disc.assert_not_called()
                self.assertFalse(self.out.exists())

    def test_extracted_program_must_match_verified_disc(self):
        root = self.extracted()
        boot = root / t4_art.ELF_NAME
        boot.write_bytes(boot.read_bytes() + b"changed")
        with self.assertRaisesRegex(t4_art.ArtError, "SLUS-20328"):
            self.make(root)
        self.assertFalse(self.out.exists())

    def test_extracted_entry_checksum_is_checked(self):
        root = self.extracted()
        data = root / t4_art.DATA_NAME
        body = bytearray(data.read_bytes())
        body[-4] ^= 1
        data.write_bytes(body)
        with self.assertRaisesRegex(t4_art.ArtError, "checksum"):
            self.make(root)
        self.assertFalse(self.out.exists())

    def test_extracted_entry_cannot_read_past_data_file(self):
        root = self.extracted()
        data = root / t4_art.DATA_NAME
        data.write_bytes(data.read_bytes()[:-1])
        with self.assertRaises(t4_art.ArtError):
            self.make(root)
        self.assertFalse(self.out.exists())

    def test_wrong_picture_dimensions_do_not_write_a_cache(self):
        sha1 = build_iso(str(self.iso), packed=pack_lz(tim2(w=64, h=64)))
        with mock.patch.object(t4_art, "ELF_SHA1", sha1):
            with self.assertRaisesRegex(t4_art.ArtError, "size"):
                self.make()
        self.assertFalse(self.out.exists())

    def test_source_stamp_tracks_both_extracted_files(self):
        root = self.extracted()
        previous = t4_art.source_stamp(str(root))
        self.assertEqual(t4_art.source_stamp(str(root)), previous)
        for name in (t4_art.DATA_NAME, t4_art.ELF_NAME):
            path = root / name
            path.write_bytes(path.read_bytes() + b"x")
            current = t4_art.source_stamp(str(root))
            self.assertNotEqual(current, previous)
            previous = current

    def test_source_change_during_decode_does_not_publish_a_cache(self):
        read_entry = t4_art.read_source_entry

        def changing_source(source, index):
            packed = read_entry(source, index)
            with self.iso.open("ab") as stream:
                stream.write(b"changed during decode")
            return packed

        with mock.patch.object(t4_art, "read_source_entry", side_effect=changing_source):
            with self.assertRaisesRegex(t4_art.ArtError, "source changed"):
                self.make()
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.out.parent.iterdir()), [])

    def test_failed_publish_preserves_existing_cache_and_cleans_unique_temporaries(self):
        self.out.parent.mkdir(parents=True)
        self.out.write_bytes(b"previous synthetic cache")
        attempted = []

        def failed_replace(temporary, destination):
            self.assertEqual(destination, str(self.out))
            self.assertTrue(Path(temporary).is_file())
            attempted.append(temporary)
            raise OSError("synthetic publish failure")

        with mock.patch.object(t4_art.os, "replace", side_effect=failed_replace):
            for _ in range(2):
                with self.assertRaisesRegex(OSError, "synthetic publish failure"):
                    self.make()
        self.assertEqual(len(set(attempted)), 2)
        self.assertTrue(all(not Path(path).exists() for path in attempted))
        self.assertEqual(self.out.read_bytes(), b"previous synthetic cache")
        self.assertEqual(list(self.out.parent.iterdir()), [self.out])


class FighterAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.tmp / "home")))
        self.iso = self.tmp / "synthetic.iso"
        self.sha1 = build_iso(str(self.iso))
        self.enterContext(mock.patch.object(t4_art, "ELF_SHA1", self.sha1))
        self.enterContext(mock.patch.object(t4_art, "FIGHTER_PORTRAITS", {"jin": t4_art.JIN_PORTRAIT}))
        self.path = self.tmp / "home" / "art" / "t4" / "fighters" / "jin.png"

    def adapter(self):
        adapter = T4(MANIFEST, {}, str(self.tmp / "install"), core=Core(str(self.iso)))
        adapter.ready = lambda: True
        return adapter

    def wait(self, adapter):
        for _ in range(500):
            if not adapter._fighter_art_busy:
                return
            time.sleep(0.01)
        self.fail("fighter extraction did not finish")

    def test_first_use_after_build_extracts_then_reuses_user_cache(self):
        adapter = self.adapter()
        self.assertEqual(adapter.fighter_image("jin"), "")
        self.wait(adapter)
        self.assertEqual(adapter.fighter_image("jin"), str(self.path))
        self.assertEqual(read_png(str(self.path))[:2], (248, 248))
        with mock.patch.object(t4_art, "make_fighter") as make:
            cached = self.adapter()
            cached.ready = lambda: False
            self.assertEqual(cached.fighter_image("jin"), str(self.path))
        make.assert_not_called()

    def test_repeated_view_reads_share_one_background_extraction(self):
        adapter = self.adapter()
        entered, release = threading.Event(), threading.Event()

        def extracting(*_args):
            entered.set()
            release.wait(5)

        with mock.patch.object(t4_art, "make_fighter", side_effect=extracting) as make:
            try:
                self.assertEqual(adapter.fighter_image("jin"), "")
                self.assertTrue(entered.wait(2))
                for _ in range(10):
                    self.assertEqual(adapter.fighter_image("jin"), "")
                make.assert_called_once()
            finally:
                release.set()
                self.wait(adapter)

    def install_disc(self, adapter):
        root = Path(adapter.root) / "game" / "disc"
        (root / "TEKKEN").mkdir(parents=True)
        with t4_art.Disc(str(self.iso)) as disc:
            for name in (t4_art.ELF_NAME, t4_art.DATA_NAME):
                lba, size = disc.find(name)
                (root / name).write_bytes(disc.read(lba, size))

    def test_extracted_build_disc_is_used_without_an_iso(self):
        adapter = self.adapter()
        self.install_disc(adapter)
        adapter.core = object()
        self.assertEqual(adapter.fighter_image("jin"), "")
        self.wait(adapter)
        self.assertEqual(adapter.fighter_image("jin"), str(self.path))

    def test_extracted_build_disc_is_preferred_over_configured_iso(self):
        adapter = self.adapter()
        self.install_disc(adapter)
        adapter.core.effective_iso = mock.Mock(side_effect=AssertionError("ISO should not be queried"))
        self.assertEqual(adapter.fighter_image("jin"), "")
        self.wait(adapter)
        self.assertEqual(adapter.fighter_image("jin"), str(self.path))
        adapter.core.effective_iso.assert_not_called()

    def test_without_finished_build_no_source_is_decoded(self):
        adapter = self.adapter()
        with mock.patch.object(t4_art, "make_fighter") as make:
            adapter.ready = lambda: False
            self.assertEqual(adapter.fighter_image("jin"), "")
            adapter.ready = lambda: True
            adapter._pipeline["running"] = True
            self.assertEqual(adapter.fighter_image("jin"), "")
        make.assert_not_called()

    def test_unknown_and_traversal_keys_do_not_extract_or_read_arbitrary_cache(self):
        adapter = self.adapter()
        other = self.path.with_name("unknown.png")
        other.parent.mkdir(parents=True)
        other.write_bytes(b"synthetic user cache")
        with mock.patch.object(t4_art, "make_fighter") as make:
            for key in ("unknown", "../jin", "jin/other", "", None):
                self.assertEqual(adapter.fighter_image(key), "")
        make.assert_not_called()

    def test_failed_source_is_tried_once_and_changed_source_can_retry(self):
        adapter = self.adapter()
        with mock.patch.object(t4_art, "make_fighter", side_effect=t4_art.ArtError("bad portrait")) as make:
            self.assertEqual(adapter.fighter_image("jin"), "")
            self.wait(adapter)
            self.assertEqual(adapter.fighter_image("jin"), "")
            make.assert_called_once()
            self.assertIn("bad portrait", adapter.art_note)
        # A changed source gets another chance in the same launcher process.
        with self.iso.open("ab") as stream:
            stream.write(b"x")
        self.assertEqual(adapter.fighter_image("jin"), "")
        self.wait(adapter)
        self.assertEqual(adapter.fighter_image("jin"), str(self.path))

    def test_jin_hero_is_not_used_as_a_square_fighter_cache(self):
        adapter = self.adapter()
        hero = self.path.parent.parent / t4_art.FILE_NAME
        hero.parent.mkdir(parents=True)
        hero.write_bytes(b"synthetic hero")
        adapter.ready = lambda: False
        self.assertEqual(adapter.fighter_image("jin"), "")


if __name__ == "__main__":
    unittest.main()
