"""The T4 Build page (0.1.5): the ISO row comes first and says what to do, the folder row is plainly a folder action,
and what a finished build changed is read again at once (a match started right after a build once did not launch the
game until the launcher was restarted)."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav
from test_build_page import Page, cards, page
from test_t4 import MANIFEST, FakeCore

ISO = dict(id="iso", label="@t4.iso_row", value="@missing", ok=False, kind="file", exts=[".iso"], dirs=[],
           hint="@iso.hint")
FOLDER = dict(id="folder", label="@t4.folder_row", value="C:\\Games\\T4", ok=True, kind="file_or_folder", exts=[".zip"],
              dirs=[], hint="@t4.folder_change_hint")


class BuildCoreFake(FakeCore):
    source_only = False

    def __init__(self, iso=""):
        super().__init__()
        self.iso = iso

    def effective_iso(self, settings):
        return self.iso

    def bundled_toolchain(self):
        return True


class Order(unittest.TestCase):
    def test_a_good_folder_puts_the_iso_card_first_and_numbers_follow(self):
        nav = page(Page(sources=[dict(ISO), dict(FOLDER)]))
        v = nav.view()
        self.assertEqual([c["id"] for c in v["build"]["cards"]], ["files", "game", "tools"])
        self.assertEqual([c["num"] for c in v["build"]["cards"]], [1, 2, 3])
        first = v["build"]["cards"][0]["actions"][0]
        self.assertEqual(first["label"], "Choose your Tekken 4 ISO file")
        self.assertTrue(first["focused"], "the page starts on the ISO row")
        folder = v["build"]["cards"][1]["actions"][0]
        self.assertEqual(folder["label"], "Use another Tekken 4 folder…")

    def test_a_wrong_folder_stays_first_because_it_is_the_thing_to_fix(self):
        bad = dict(FOLDER, ok=False, note="@t4.folder_incomplete")
        v = page(Page(sources=[dict(bad), dict(ISO)])).view()
        self.assertEqual([c["id"] for c in v["build"]["cards"]][:2], ["game", "files"])

    def test_the_labels_exist_in_every_language_and_the_folder_one_is_not_the_iso_one(self):
        for language in i18n.LANGUAGES:
            iso, folder = i18n.text(language, "t4.iso_row"), i18n.text(language, "t4.folder_row")
            self.assertTrue(iso and folder and iso != folder, language)
            self.assertNotIn("{", iso + folder)

    def test_the_real_adapter_lists_the_iso_row_before_the_folder_row_with_the_new_labels(self):
        adapter = T4(MANIFEST, {}, "fake-root", core=BuildCoreFake())
        with mock.patch.object(T4, "folder_problem", return_value=""):
            rows = adapter.sources()
        self.assertEqual([(r["id"], r["label"]) for r in rows], [("iso", "@t4.iso_row"), ("folder", "@t4.folder_row")])

    def test_messages_that_name_the_iso_row_use_its_new_name(self):
        for language in i18n.LANGUAGES:
            old = {"en": "Game ISO", "de": "Spiel-ISO", "es": "ISO del juego", "fr": "ISO du jeu", "ja": "ゲームISO",
                   "ko": "게임 ISO", "pt-BR": "ISO do jogo"}[language]
            for key in ("iso.refused", "iso.changed", "iso.check_failed", "t4.build_incomplete"):
                self.assertNotIn(old, i18n.catalog(language)[key], (language, key))


class AfterBuild(unittest.TestCase):
    def adapter(self, core=None):
        adapter = T4(MANIFEST, {}, "fake-root", core=core or BuildCoreFake())
        adapter.hero = lambda: ""
        return adapter

    def test_settings_are_read_again_when_a_build_finishes_and_saved_values_win(self):
        core = BuildCoreFake()
        adapter = self.adapter(core)
        adapter.s["iso"] = "old.iso"
        adapter.s["memory_only"] = 1
        core.saved = dict(iso="new.iso", runtime="built")
        adapter.refresh_after_build()
        self.assertEqual((adapter.s["iso"], adapter.s["runtime"]), ("new.iso", "built"))
        self.assertEqual(adapter.s["memory_only"], 1, "nothing is dropped")

    def test_a_core_that_cannot_read_its_settings_keeps_the_old_ones(self):
        core = BuildCoreFake()
        adapter = self.adapter(core)
        core.load_settings = mock.Mock(side_effect=OSError("locked"))
        adapter.refresh_after_build()
        self.assertIn("aa", adapter.s)

    def test_a_build_first_error_in_the_online_state_goes_away_once_built(self):
        adapter = self.adapter()
        adapter._online_phase, adapter._online_message = "error", "@online.build_required"
        adapter._online_client, adapter._online_busy = None, False
        adapter.refresh_after_build()
        self.assertEqual((adapter._online_phase, adapter._online_message), ("offline", "@online.offline"))

    def test_other_online_states_are_left_alone(self):
        adapter = self.adapter()
        adapter._online_phase, adapter._online_message = "error", "@online.something_else"
        adapter._online_client, adapter._online_busy = None, False
        adapter.refresh_after_build()
        self.assertEqual(adapter._online_phase, "error")
        adapter._online_phase, adapter._online_message = "searching", "@online.build_required"
        adapter.refresh_after_build()
        self.assertEqual(adapter._online_phase, "searching")

    def test_the_build_end_thread_calls_it_before_it_says_finished(self):
        adapter = self.adapter()
        order = []
        build = mock.Mock(running=lambda: False, cancelled=False, code=0)
        adapter.build = build
        adapter.refresh_after_build = lambda: order.append("refresh")
        with mock.patch("openrecomp.adapters.t4.clear_rebuild"), \
                mock.patch.object(T4, "ready", lambda self: order.append("ready") or True):
            adapter._build_end(build)
        self.assertEqual(order, ["refresh", "ready"])
        self.assertEqual(adapter.last_result, "@t4.build_finished")


class DisabledRows(unittest.TestCase):
    def test_pressing_a_row_that_is_off_says_why_instead_of_nothing(self):
        from test_nav import Fake, manifest
        nav = Nav([Game(manifest("a"), Fake(manifest("a")))], language="en")
        item = dict(kind="action", id="x", label="X", disabled=True, hint="@iso.choose_first", run=lambda: None)
        nav._activate(item)
        self.assertEqual(nav.toast, "@iso.choose_first")


if __name__ == "__main__":
    unittest.main()
