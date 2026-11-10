"""`--offline [game]`: a shortcut or Steam launch option that starts the game offline in fullscreen at once, and the
same way by controller alone through the launcher (game -> Offline -> Play), with an Xbox or a PlayStation pad."""
from pathlib import Path
import unittest
from unittest import mock

from openrecomp import i18n, updater
from openrecomp.adapters import t4, t5dr
from openrecomp.nav import Game, Nav
from tools.online_shots import SyntheticOnline


def make(*games, ready=True):
    adapters = []
    for game in games:
        adapter = SyntheticOnline(game)
        adapter.is_ready = ready
        adapter.fullscreen_env = lambda game=game: {"FULL_" + game.upper(): "1"}
        adapters.append(adapter)
    nav = Nav([Game(a.m, a) for a in adapters], language="en", launch_env={"MUTE": "1"})
    return adapters, nav


class DirectOffline(unittest.TestCase):
    def test_starts_the_last_game_in_fullscreen_without_any_menu_or_online_step(self):
        (t5, four), nav = make("t5", "t4")
        self.assertTrue(nav.direct_offline())
        self.assertEqual(t5.calls, [("start", {"MUTE": "1", "FULL_T5": "1"})])
        self.assertEqual(four.calls, [])
        self.assertFalse(nav.view()["mainMenu"]["show"])
        self.assertEqual(nav.launch_env, {"MUTE": "1"})             # only this start is forced to fullscreen

    def test_a_named_game_by_id_or_short_name_in_any_case(self):
        for name in ("t4", "T4", " t4 "):
            with self.subTest(name=name):
                (t5, four), nav = make("t5", "t4")
                self.assertTrue(nav.direct_offline(name))
                self.assertEqual(four.calls, [("start", {"MUTE": "1", "FULL_T4": "1"})])
                self.assertEqual(t5.calls, [])
                self.assertEqual(nav.game.id, "t4")
        (t5, four), nav = make("t5", "t4")
        self.assertTrue(nav.direct_offline("t5dr"))                 # the short name of the fixture game
        self.assertEqual(len(t5.calls), 1)

    def test_an_unknown_name_starts_nothing_and_says_so_on_the_games_page(self):
        (t5, four), nav = make("t5", "t4")
        self.assertFalse(nav.direct_offline("tekken9"))
        self.assertEqual(t5.calls + four.calls, [])
        self.assertEqual(nav.screen, "start")
        self.assertIn("tekken9", nav.view()["toast"])
        for language in ("en", "de", "es", "fr", "ja", "ko", "pt-BR"):
            self.assertIn("tekken9", i18n.text(language, "direct.unknown_game", name="tekken9"))
            if language != "en":
                self.assertNotEqual(i18n.text(language, "direct.unknown_game", name="x"),
                                    i18n.text("en", "direct.unknown_game", name="x"))

    def test_a_game_that_is_not_built_lands_on_its_build_page_with_the_reason(self):
        (t5,), nav = make("t5", ready=False)
        self.assertFalse(nav.direct_offline("t5"))
        self.assertEqual(t5.calls, [])
        self.assertEqual((nav.screen, nav.section()), ("hub", "build"))
        self.assertTrue(nav.view()["toast"])

    def test_a_running_game_is_not_started_twice(self):
        (t5,), nav = make("t5")
        t5.is_running = True
        nav.direct_offline()
        self.assertEqual(t5.calls, [])

    def test_the_games_get_their_own_fullscreen_switch(self):
        self.assertEqual(t5dr.T5DR.fullscreen_env(None), {"PS3_FULLSCREEN": "1"})
        self.assertEqual(t4.T4.fullscreen_env(None), {"TEKKEN4_FULLSCREEN": "1"})


class CommandLine(unittest.TestCase):
    def run_main(self, argv):
        from openrecomp import app
        backend = mock.Mock()
        backend.updates.root = Path("fake-install")
        backend.nav.fullscreen = False
        later = []
        with mock.patch.object(app, "QGuiApplication"), mock.patch.object(app, "Backend", return_value=backend), \
                mock.patch.object(app, "make_engine"), mock.patch.object(app, "QIcon"), \
                mock.patch.object(app.QTimer, "singleShot", side_effect=lambda delay, fn: later.append((delay, fn))), \
                mock.patch.object(app.updater, "confirm_startup"), mock.patch.object(app.other_launchers, "enable"), \
                mock.patch.object(app.ctypes, "windll", create=True):
            app.main(argv)
        for delay, fn in later:
            if delay == 0:
                fn()
        return backend

    def test_offline_with_and_without_a_game_name(self):
        self.run_main(["--offline", "t4"]).direct_offline.assert_called_once_with("t4")
        self.run_main(["--offline"]).direct_offline.assert_called_once_with("")
        self.run_main(["--windowed", "--offline", "t5dr"]).direct_offline.assert_called_once_with("t5dr")

    def test_a_plain_start_starts_no_game(self):
        self.run_main([]).direct_offline.assert_not_called()
        self.run_main(["--windowed"]).direct_offline.assert_not_called()

    def test_the_launcher_restarted_by_its_update_does_not_start_a_game(self):
        self.assertEqual(updater.launcher_args(["--windowed", "--offline", "t4"]), ["--windowed"])


class ControllerOnly(unittest.TestCase):
    """Choose the game, choose Offline or Online, press Play: every step with pad actions only."""

    def walk_to(self, nav, entry, device):
        nav.act("confirm", device=device)                            # the game on the shelf -> its main menu
        self.assertTrue(nav.view()["mainMenu"]["show"])
        ids = [e["id"] for e in nav.view()["mainMenu"]["entries"]]
        for _ in range(len(ids)):
            if ids[nav.view()["mainMenu"]["selected"]] == entry:
                break
            nav.act("down", device=device)
        self.assertEqual(ids[nav.view()["mainMenu"]["selected"]], entry)
        nav.act("confirm", device=device)

    def test_offline_then_play_with_either_pad(self):
        for device in ("xbox", "ps"):
            with self.subTest(device=device):
                (t5,), nav = make("t5")
                self.walk_to(nav, "offline", device)
                self.assertEqual((nav.screen, nav.section()), ("hub", "play"))
                self.assertEqual(t5.calls, [])                        # choosing Offline starts nothing by itself
                nav.act("confirm", device=device)
                self.assertEqual([call[0] for call in t5.calls], ["start"])

    def test_online_pages_with_either_pad_and_no_search_starts_by_itself(self):
        for device in ("xbox", "ps"):
            with self.subTest(device=device):
                (t5,), nav = make("t5")
                self.walk_to(nav, "lobby", device)
                self.assertEqual((nav.screen, nav.section()), ("hub", "online"))
                self.assertFalse(any(call[0] in ("start", "search_ranked", "search_casual") for call in t5.calls))
                nav.act("back", device=device)
                self.assertTrue(nav.view()["mainMenu"]["show"])

    def test_build_page_with_either_pad(self):
        for device in ("xbox", "ps"):
            with self.subTest(device=device):
                (t5,), nav = make("t5")
                self.walk_to(nav, "build", device)
                self.assertEqual((nav.screen, nav.section()), ("hub", "build"))


if __name__ == "__main__":
    unittest.main()
