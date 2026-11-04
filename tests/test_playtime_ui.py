"""Local play time stays visible through the adapter boundary and controller routes."""
import unittest

from openrecomp import i18n, nav_profiles, playtime_format
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_online_hierarchy import hierarchy_nav
import test_ui_polish


SAMPLE = dict(offline_seconds=42 * 3600, online_seconds=30 * 60,
              last_played="2026-10-28", sessions=5)


class PlaytimeViews(unittest.TestCase):
    def setUp(self):
        self.adapter = Fake(manifest("t5dr", short="T5DR"))
        self.adapter.playtime = lambda: dict(SAMPLE)
        self.game = Game(self.adapter.m, self.adapter)
        second = Fake(manifest("t4", short="T4"))
        second.playtime = lambda: dict(SAMPLE, offline_seconds=6 * 3600, online_seconds=0)
        self.nav = Nav([self.game, Game(second.m, second)], language="en")

    def test_shelf_and_controller_game_page_share_local_summary(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                self.nav.language = language
                self.nav.screen = "start"
                tiles = self.nav.view()["shelf"]["tiles"]
                self.assertEqual(tiles[0]["playtime"], playtime_format.summary(SAMPLE, language))
                self.assertEqual(tiles[1]["playtime"], playtime_format.summary(
                    dict(SAMPLE, offline_seconds=6 * 3600, online_seconds=0), language))
                self.nav.act("confirm", device="xbox")
                page = self.nav.view()["sessionPage"]
                self.assertEqual(page["playtime"], tiles[0]["playtime"])
                self.assertEqual(self.adapter.calls, [])

    def test_main_menu_shows_game_time_without_starting_game(self):
        self.game.m["adapter"] = "t5dr"
        self.nav.open_main_menu()
        self.assertEqual(self.nav.view()["mainMenu"]["playtime"], playtime_format.summary(SAMPLE, "en"))
        self.assertEqual(self.adapter.calls, [])

    def test_profile_lists_each_games_local_total_only_on_own_profile(self):
        state = dict(name="Me", profile=dict(name="Me", self=True))
        rows = nav_profiles._profile_rows(self.nav, self.game, state, None)
        row = next(row for row in rows if row["id"] == "profile_playtime")
        localized = i18n.localize(row, "en")
        self.assertIn("T5DR 42 h 30 min", localized["label"])
        self.assertIn("T4 6 h", localized["label"])
        self.assertEqual([r["v"] for r in localized["detail"]["rows"]], ["42 h", "30 min", "5"])
        for profile in (dict(name="Rival", self=False), dict(name="Me")):
            rows = nav_profiles._profile_rows(self.nav, self.game, dict(state, profile=profile), None)
            self.assertNotIn("profile_playtime", [row.get("id") for row in rows])

    def test_lobby_identity_card_has_local_totals_without_server_profile(self):
        adapter, nav = hierarchy_nav()
        adapter.playtime = lambda: dict(SAMPLE)
        self.assertEqual(nav.view()["online"]["profile"]["playtime"], playtime_format.profile(nav.games, "en"))
        self.assertEqual(adapter.calls, [])


class PlaytimeGeometry(unittest.TestCase):
    setUpClass = classmethod(test_ui_polish.ScenePolish.setUpClass.__func__)
    setUp = test_ui_polish.ScenePolish.setUp
    tearDown = test_ui_polish.ScenePolish.tearDown
    named = test_ui_polish.ScenePolish.named
    wait_pages = test_ui_polish.ScenePolish.wait_pages
    publish = test_ui_polish.ScenePolish.publish

    def test_playtime_labels_wrap_and_leave_controller_rows_reachable(self):
        self.adapter.playtime = lambda: dict(SAMPLE)
        for language in i18n.LANGUAGES:
            self.nav.language = language
            for size in ((1920, 1080), (1280, 720)):
                self.win.setWidth(size[0])
                self.win.setHeight(size[1])
                self.nav.screen = "start"
                self.publish()
                label = next(label for label in self.named("shelfPlaytime") if label.isVisible())
                self.assertFalse(label.property("truncated"))
                self.assertLessEqual(label.property("contentWidth"), label.width() + 1)
                self.nav.act("confirm", device="xbox")
                self.publish()
                label = self.named("sessionPlaytime")[0]
                viewport = self.named("sessionViewport")[0]
                self.assertTrue(label.isVisible())
                self.assertLessEqual(label.property("contentWidth"), label.width() + 1)
                self.assertGreater(viewport.height(), 0)
                self.assertGreater(viewport.y(), label.parentItem().y() + label.y() + label.height())

    def test_own_profile_totals_fit_in_all_languages_at_large_text_size(self):
        adapter, self.nav = hierarchy_nav()
        adapter.playtime = lambda: dict(SAMPLE)
        second = Fake(manifest("t4", short="T4"))
        second.playtime = lambda: dict(SAMPLE, offline_seconds=6 * 3600, online_seconds=0)
        self.nav.games.append(Game(second.m, second))
        self.nav.text_size = 130
        self.backend.nav = self.nav
        for language in i18n.LANGUAGES:
            self.nav.language = language
            for size in ((1920, 1080), (1280, 720)):
                self.win.setWidth(size[0])
                self.win.setHeight(size[1])
                self.publish()
                labels = self.named("profilePlaytime") + self.named("profilePlaytimeWide")
                label = next(label for label in labels if label.isVisible())
                card = self.named("onlineProfile")[0]
                self.assertFalse(label.property("truncated"))
                self.assertLessEqual(label.property("contentWidth"), label.width() + 1)
                self.assertLessEqual(label.parentItem().y() + label.y() + label.height(), card.height() - 44)


if __name__ == "__main__":
    unittest.main()
