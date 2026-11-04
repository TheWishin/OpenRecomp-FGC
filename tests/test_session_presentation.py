"""Compact page snapshots preserve action indices, values and spoiler preferences."""
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class SessionPresentation(unittest.TestCase):
    def setUp(self):
        self.adapter = Fake(manifest())
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.screen = "hub"

    def page(self, section):
        self.nav.sec[self.nav.game.id] = section
        return self.nav.view()["sessionPage"]

    def test_session_keeps_focused_current_setting_and_action_indices(self):
        self.nav.sec[self.nav.game.id] = "play"
        self.nav.focus[self.nav.key()] = 1
        page = self.page("play")
        focused = next(row for row in page["rows"] if row["focused"])
        self.assertEqual((focused["index"], focused["id"], focused["value"]), (1, "res", "A"))
        self.assertTrue(page["rows"][0]["primary"])
        self.nav.act("right")
        self.assertEqual(self.adapter.calls, [("set", "res", "b")])

    def test_replay_table_preserves_spoilers_and_original_indices(self):
        page = self.page("replays")
        self.assertEqual(len(page["replayColumns"]), 5)
        self.assertTrue(all(not row["heading"] for row in page["rows"]))
        self.assertTrue(all(row["cells"][3] == i18n.text("en", "hidden") for row in page["rows"]))
        self.assertEqual(page["rows"][0]["index"], 1)
        self.assertEqual(page["rows"][0]["cells"][4], "—")
        self.nav.act("x")
        self.assertEqual(self.page("replays")["rows"][0]["cells"][3], "Sieg 3:1")
        self.nav.act("confirm")
        self.assertEqual(self.adapter.calls, [("replay", "0")])

    def test_replay_window_tracks_focus_without_group_rows(self):
        self.page("replays")
        for _ in range(11):
            self.nav.act("down")
        page = self.page("replays")
        self.assertEqual(len(page["rows"]), 10)
        self.assertTrue(page["up"])
        self.assertFalse(page["down"])
        self.assertEqual(next(row for row in page["rows"] if row["focused"])["id"], "11")

    def test_replay_table_uses_optional_fighters_and_length_metadata(self):
        replay = dict(self.adapter.replays()[0], fighters="F1 / F2", length="02:14")
        self.adapter.replays = lambda: [replay]
        cells = self.page("replays")["rows"][0]["cells"]
        self.assertEqual(cells[2], "F1 / F2")
        self.assertEqual(cells[4], "02:14")

    def test_empty_replays_have_guidance_and_no_watch_action(self):
        self.adapter.replays = lambda: []
        page = self.page("replays")
        self.assertTrue(page["empty"])
        self.assertEqual(page["rows"][0]["label"], i18n.text("en", "no_replays"))
        self.assertFalse(page["rows"][0]["verb"])
        self.assertTrue(page["lead"])

    def test_shelf_status_and_play_glyph_are_localized_without_changing_open(self):
        self.nav.screen = "start"
        tile = self.nav.view()["shelf"]["tiles"][0]
        self.assertTrue(tile["ready"])
        self.assertEqual(tile["status"], i18n.text("en", "ready"))
        self.assertEqual(tile["bar"], i18n.text("en", "open"))
        self.assertTrue(tile["playG"])
        self.adapter.is_ready = False
        tile = self.nav.view()["shelf"]["tiles"][0]
        self.assertEqual(tile["statusKind"], "build")
        self.assertFalse(tile["ready"])

    def test_new_copy_has_catalog_parity_and_localizes(self):
        keys = {key for key in i18n.catalog("en") if key.startswith("ui.")}
        self.assertGreaterEqual(len(keys), 11)
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual({key for key in i18n.catalog(language) if key.startswith("ui.")}, keys)
                for key in keys:
                    self.assertEqual(i18n.localize("@" + key, language), i18n.catalog(language)[key])

    def test_compact_page_is_in_the_explicit_release_inventory(self):
        from tools.package_release import SOURCE_FILES
        self.assertIn("openrecomp/ui/SessionPage.qml", SOURCE_FILES)


if __name__ == "__main__":
    unittest.main()
