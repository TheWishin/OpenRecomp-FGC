"""Owner feedback on the test bundle: the Tekken 4 game folder opens the Windows FOLDER dialog first (the release zip
is a second row), the ISO dialog names the Tekken 4 disc image, and a mouse click opens Explorer at once."""
import os
import tempfile
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Missing
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_t4 import MANIFEST, FakeCore

T4_MANIFEST = dict(MANIFEST, adapter="t4", sections=["play", "online", "build", "settings"])


class Core(FakeCore):
    def effective_iso(self, settings):
        return settings.get("iso", "")


def t4_missing():
    adapter = Missing(T4_MANIFEST, {})
    return Nav([Game(adapter.m, adapter)], language="en", native_picker=True), adapter


class T4GameFolder(unittest.TestCase):
    def test_missing_t4_is_called_the_tekken_4_game_folder(self):
        _nav, adapter = t4_missing()
        source = adapter.sources()[0]
        self.assertEqual((source["label"], source["title"], source["kind"]),
                         ("@t4.game_folder", "@t4.choose_game_folder", "file_or_folder"))
        self.assertEqual(i18n.text("en", "t4.game_folder"), "Tekken 4 game folder")

    def test_shelf_click_opens_the_folder_dialog_not_a_zip_dialog(self):
        nav, _adapter = t4_missing()
        nav.device = "kb"                         # what Backend.clickTile does
        nav.click_tile(0)
        self.assertIsNone(nav.overlay, "no launcher list first")
        request = nav.native_request()
        self.assertEqual((request["kind"], request["filters"]), ("folder", []))
        self.assertEqual(request["title"], "Choose your Tekken 4 game folder")

    def test_shelf_with_a_pad_still_opens_the_list_with_folders_and_zips(self):
        nav, _adapter = t4_missing()
        with mock.patch.object(nav, "_picker_entries", return_value=[]):
            nav.act("confirm", device="xbox")
        self.assertEqual((nav.overlay, nav.picker["kind"], nav.picker["exts"]), ("picker", "file_or_folder", [".zip"]))
        self.assertIsNone(nav.pending_native)

    def test_build_has_a_second_row_for_a_release_zip(self):
        nav, adapter = t4_missing()
        rows = nav._items_build_rows(nav.game)
        ids = [r.get("id") for r in rows]
        self.assertEqual(ids[:2], ["folder", "folder:zip"])
        self.assertEqual(rows[1]["label"], "@picker.have_zip")
        nav.device = "kb"
        rows[0]["run"]()
        self.assertEqual(nav.native_request()["kind"], "folder")
        rows[1]["run"]()
        request = nav.native_request()
        self.assertEqual((request["kind"], request["title"]), ("file", "Choose the release zip"))
        self.assertEqual(request["filters"][0], ("Release zip (*.zip)", "*.zip"))
        with tempfile.TemporaryDirectory() as d:
            release = os.path.join(d, "T4-release.zip")
            open(release, "w").close()
            with mock.patch.object(adapter, "set_source", return_value="") as set_source:
                nav.native_result(request, release)
            set_source.assert_called_once_with("folder", release)

    def test_complete_release_step_also_opens_the_folder_dialog(self):
        core = Core()
        core.bundled_toolchain = lambda: False
        adapter = T4(T4_MANIFEST, {}, "fake-root", core=core)
        source = adapter.sources()[0]
        self.assertEqual((source["id"], source["kind"], source["title"]), ("folder", "file_or_folder", "@t4.choose_game_folder"))
        nav = Nav([Game(adapter.m, adapter)], language="en", native_picker=True)
        nav.device = "kb"
        nav._open_source_picker(source)
        self.assertEqual(nav.native_request()["kind"], "folder")


class T4Iso(unittest.TestCase):
    def adapter(self, iso=""):
        core = Core()
        adapter = T4(T4_MANIFEST, {}, "fake-root", core=core)
        adapter.s["iso"] = iso
        return adapter

    def test_iso_dialog_names_the_tekken_4_disc_image(self):
        adapter = self.adapter()
        source = next(s for s in adapter.sources() if s["id"] == "iso")
        nav = Nav([Game(adapter.m, adapter)], language="en", native_picker=True)
        nav.device = "kb"
        nav._open_source_picker(source)
        request = nav.native_request()
        self.assertEqual(request["title"], "Choose your Tekken 4 USA disc image (ISO)")
        self.assertEqual(request["filters"], [("Tekken 4 disc image (*.iso)", "*.iso"), ("All files (*.*)", "*.*")])

    def test_iso_starts_in_the_last_iso_folder_never_the_game_folder(self):
        with tempfile.TemporaryDirectory() as game, tempfile.TemporaryDirectory() as isos:
            adapter = self.adapter()
            adapter.root = game
            source = next(s for s in adapter.sources() if s["id"] == "iso")
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            self.assertNotEqual(source["dirs"][0], game)
            nav = Nav([Game(adapter.m, adapter)], language="en", native_picker=True)
            nav.device = "kb"
            nav._open_source_picker(source)
            if os.path.isdir(downloads):
                self.assertEqual(nav.native_request()["start"], downloads)
            nav.picker_dirs = {".iso": isos, "folder": game}
            nav._open_source_picker(source)
            self.assertEqual(nav.native_request()["start"], isos)

    def test_the_isos_own_folder_is_the_first_hint(self):
        with tempfile.TemporaryDirectory() as isos:
            iso = os.path.join(isos, "t4.iso")
            open(iso, "w").close()
            source = next(s for s in self.adapter(iso).sources() if s["id"] == "iso")
            self.assertEqual(source["dirs"][0], isos)


class MouseOpensExplorerAtOnce(unittest.TestCase):
    def test_one_click_on_a_file_row_opens_explorer_with_no_list(self):
        a = Fake(manifest())
        nav = Nav([Game(a.m, a)], language="en", native_picker=True)
        nav.act("confirm", device="xbox")
        nav.act("next", device="xbox")
        nav.act("next", device="xbox")
        nav.device = "kb"                         # what Backend.clickRow does
        index = next(i for i, item in enumerate(nav.items()) if item.get("id") == "iso")
        nav.click_row(index)
        self.assertIsNone(nav.overlay)
        self.assertEqual(nav.native_request()["kind"], "file")

    def test_file_and_folder_memory_are_kept_apart(self):
        a = Fake(manifest())
        saved = []
        nav = Nav([Game(a.m, a)], language="en", native_picker=True, on_picker_dir=lambda k, f: saved.append(k))
        with tempfile.TemporaryDirectory() as isos, tempfile.TemporaryDirectory() as games:
            iso = os.path.join(isos, "x.iso")
            open(iso, "w").close()
            nav.device = "kb"
            nav._open_picker("source:iso", "@game_iso", [".iso"], [], "file")
            nav.native_result(nav.native_request(), iso)
            nav._open_picker("library_folder", "@library.local", [], [games], "folder")
            self.assertEqual(nav.native_request()["start"], games)
            nav._open_picker("source:pkg", "@package", [".pkg"], [games], "file")
            self.assertEqual(nav.native_request()["start"], games, "the ISO folder is not the package folder")
            self.assertEqual(saved, [".iso"])


if __name__ == "__main__":
    unittest.main()
