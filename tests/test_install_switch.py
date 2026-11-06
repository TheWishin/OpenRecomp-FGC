"""0.1.3: the installs of a game the launcher knows, and switching between them on the Build page; the Build page's game
card for a good folder; the T5DR page's folder row; the update notice names the folder it updates."""
import json
import os
import tempfile
import unittest
from unittest import mock

from openrecomp import i18n, known_installs
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


def t4_install(parent, name="T4", version="0.1.3", ours=False):
    root = os.path.join(parent, name)
    os.makedirs(os.path.join(root, "launcher"), exist_ok=True)
    open(os.path.join(root, "launcher", "t4core.py"), "w").close()
    with open(os.path.join(root, "release.json"), "w", encoding="utf-8") as f:
        json.dump(dict(version=version), f)
    if ours:
        with open(os.path.join(root, "openrecomp-release.json"), "w", encoding="utf-8") as f:
            json.dump(dict(game="t4", version=version, installed_by="OpenRecomp-FGC"), f)
    return root


class KnownInstalls(unittest.TestCase):
    def test_remembered_installs_that_still_exist_current_first(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = t4_install(os.path.join(temp, "a")), t4_install(os.path.join(temp, "b"), version="0.1.2")
            gone = os.path.join(temp, "gone", "T4")
            config = {}
            self.assertTrue(known_installs.remember(config, "t4", a, b, gone))
            self.assertFalse(known_installs.remember(config, "t4", a))          # nothing new
            with mock.patch.object(known_installs, "_launcher_parent", return_value=os.path.join(temp, "launcher-parent")):
                listed = known_installs.known(config, "t4", b)
            self.assertEqual(listed, [(b, "0.1.2"), (a, "0.1.3")])

    def test_a_developers_checkouts_beside_the_launcher_are_no_installs(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = t4_install(temp)                                             # the bundle zip's T4 folder
            dev = os.path.join(temp, "T4-codex")                                  # a git checkout: no release marker
            os.makedirs(os.path.join(dev, "launcher"))
            open(os.path.join(dev, "launcher", "t4core.py"), "w").close()
            with mock.patch.object(known_installs, "_launcher_parent", return_value=temp), \
                    mock.patch.object(known_installs.mf, "user_dir", return_value=os.path.join(temp, "home")):
                self.assertEqual([r for r, _v in known_installs.known({}, "t4")], [bundle])

    def test_installs_this_launcher_made_are_listed(self):
        with tempfile.TemporaryDirectory() as temp:
            home = os.path.join(temp, "home")
            ours = t4_install(os.path.join(home, "installs", "t4"), ours=True)
            with mock.patch.object(known_installs, "_launcher_parent", return_value=os.path.join(temp, "x")), \
                    mock.patch.object(known_installs.mf, "user_dir", return_value=home):
                self.assertEqual([r for r, _v in known_installs.known({}, "t4")], [ours])


class SwitchFake(Fake):
    def __init__(self, installs, folder_ok=True):
        super().__init__(manifest("t4", adapter="t4"))
        self.installs = installs
        self.root = installs[0][0] if installs else ""
        self.folder_ok = folder_ok

    def known_installs(self):
        return list(self.installs)

    def sources(self):
        return [dict(id="folder", label="@t4.game_folder", value=self.root, ok=self.folder_ok, kind="file_or_folder",
                     exts=[], dirs=[], hint="@t4.folder_change_hint", note="" if self.folder_ok else "@t4.folder_old")]


class BuildPage(unittest.TestCase):
    def page(self, adapter):
        nav = Nav([Game(adapter.m, adapter)], language="en", on_setup=lambda *a: True)
        nav.screen = "hub"
        nav.sec[nav.game.id] = "build"
        return nav, i18n.localize(nav.view(), "en")["build"]

    def test_a_good_folder_is_done_and_a_wrong_one_says_why(self):
        _nav, page = self.page(SwitchFake([("C:/g/T4", "0.1.3")]))
        game = next(c for c in page["cards"] if c["id"] == "game")
        self.assertEqual(game["status"], "done")
        self.assertEqual(game["text"], "Play, Build and Online use this folder.")
        _nav, page = self.page(SwitchFake([("C:/g/T4", "0.1.2")], folder_ok=False))
        game = next(c for c in page["cards"] if c["id"] == "game")
        self.assertEqual(game["status"], "todo")
        self.assertNotIn("no bundled build tools", game["text"])

    def test_the_switch_lists_the_other_installs(self):
        adapter = SwitchFake([("C:/g/T4", "0.1.3"), ("D:/old/T4", "0.1.2")])
        nav, page = self.page(adapter)
        labels = [a["label"] for c in page["cards"] for a in c["actions"]]
        self.assertIn("Install in use", labels)
        item = next(it for it in nav.items() if it.get("id") == "install_switch")
        self.assertEqual([r["k"] for r in item["detail"]["rows"]], [{"_literal": "C:/g/T4"}, {"_literal": "D:/old/T4"}])
        item["run"]()
        self.assertEqual(nav.overlay, "picker")
        self.assertEqual(nav.picker["target"], "source:folder")
        self.assertEqual(nav.picker["choices"], ["D:/old/T4", "C:/g/T4"])
        # one install only: no switch
        nav, _page = self.page(SwitchFake([("C:/g/T4", "0.1.3")]))
        self.assertFalse(any(it.get("id") == "install_switch" for it in nav.items()))


class T5Page(unittest.TestCase):
    def test_the_t5dr_build_page_has_the_folder_row(self):
        from openrecomp.adapters import t5dr
        with open(t5dr.__file__, encoding="utf-8") as f:
            source = f.read()
        self.assertIn('dict(id="folder", label="@t5.game_folder"', source)
        for code in ("en", "de", "es", "fr", "ja", "ko", "pt-BR"):
            catalog = i18n.catalog(code)
            for key in ("t5.game_folder", "t5.folder_change_hint", "build.install_in_use", "build.folder_in_use",
                        "setup.update_in_folder"):
                self.assertIn(key, catalog, (code, key))


class UpdateNotice(unittest.TestCase):
    def test_the_update_row_names_the_folder(self):
        adapter = SwitchFake([(r"C:\Games\T4", "0.1.2")])
        nav = Nav([Game(adapter.m, adapter)], language="en", on_setup=lambda *a: True)
        nav._setup = lambda gid: dict(available=True, installed="0.1.2", latest="0.1.3", phase="ready", size=1)
        nav._setup_supported = lambda g: True
        row = nav._setup_items(nav.game, "build")[0]
        self.assertIn(r"Folder: C:\Games\T4", i18n.localize(row["hint"], "en"))
        self.assertIn({"k": "Game folder", "v": r"C:\Games\T4"}, i18n.localize(row["detail"]["rows"], "en"))


if __name__ == "__main__":
    unittest.main()
