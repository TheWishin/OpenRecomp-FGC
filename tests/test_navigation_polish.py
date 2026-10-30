"""Controller preferences and safe navigation, using only fake adapters."""
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.app import Backend
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class NavigationPolish(unittest.TestCase):
    def setUp(self):
        self.adapters = [Fake(manifest(gid)) for gid in ("a", "b")]
        self.games = [Game(a.m, a) for a in self.adapters]
        self.saved = []
        self.nav = Nav(self.games, language="en", on_game=self.saved.append)

    def press(self, *actions):
        for action in actions:
            self.nav.act(action)

    def test_saved_game_restores_shelf_selection_and_missing_id_falls_back(self):
        restored = Nav(self.games, last_game="b")
        self.assertEqual((restored.game.id, restored.start_focus), ("b", 1))
        self.assertTrue(restored.view()["shelf"]["tiles"][1]["focused"])
        self.assertEqual(Nav(self.games, last_game="removed").game.id, "a")
        self.assertIsNone(Nav([], last_game="removed").game)

    def test_selection_and_view_switch_notify_persistence_and_keep_focus(self):
        self.press("right", "confirm", "down", "switchGame", "switchGame")
        self.assertEqual(self.saved, ["b", "a", "b"])
        self.assertEqual(self.nav.focus_index(self.nav.items()), 1)
        self.press("back", "confirm")
        self.assertEqual(self.nav.focus_index(self.nav.items()), 1)

    def test_view_switch_on_shelf_wraps_games_without_entering_free_slots(self):
        self.press("switchGame", "switchGame")
        self.assertEqual(self.nav.start_focus, 0)
        self.assertEqual(self.saved, ["b", "a"])
        self.assertIn("switchGame", [p["action"] for p in self.nav.view()["prompts"]])

    def test_mouse_selects_keyboard_prompts_for_click_targets(self):
        backend = SimpleNamespace(nav=mock.Mock(), refresh=mock.Mock())
        for name, args in (("clickRow", (0,)), ("clickTile", (0,)), ("clickTab", ("play",)),
                           ("clickPrimary", ()), ("clickCell", (0,)), ("clickEntry", (0,)), ("clickKey", (0, 0))):
            with self.subTest(slot=name):
                backend.nav.device = "ps"
                getattr(Backend, name)(backend, *args)
                self.assertEqual(backend.nav.device, "kb")

    def test_last_pad_device_changes_glyphs_without_qt(self):
        self.nav.act("social", device="ps")
        self.assertEqual(self.nav.pad_kind, "ps")
        self.assertEqual(self.nav.view()["prompts"][0]["g"]["text"], "✕")
        self.nav.act("down", device="kb")
        self.assertTrue(self.nav.view()["prompts"][0]["g"]["key"])
        self.nav.act("up", device="xbox")
        self.assertEqual(self.nav.view()["prompts"][0]["g"]["text"], "A")

    def test_display_and_motion_cycle_by_pad_and_notify(self):
        changed = []
        self.nav.on_preferences = lambda full, reduced: changed.append((full, reduced))
        self.press("social", "down", "left")
        self.assertFalse(self.nav.view()["fullscreen"])
        display_hint = self.nav.view()["hint"]
        self.press("down", "confirm")
        self.assertTrue(self.nav.view()["reducedMotion"])
        self.assertNotEqual(self.nav.view()["hint"], display_hint)
        self.assertEqual(changed, [(False, False), (False, True)])
        self.assertEqual(self.nav.view()["prompts"][0]["action"], "confirm")
        self.press("back", "social")
        self.assertEqual(self.nav.drawer_focus, 2)

    def test_dry_preferences_do_not_write_or_change_window(self):
        self.nav.dry = True
        self.nav.on_preferences = mock.Mock()
        self.press("social", "down", "confirm", "down", "right")
        self.assertTrue(self.nav.fullscreen)
        self.assertFalse(self.nav.reduced_motion)
        self.nav.on_preferences.assert_not_called()

    def test_moving_away_or_opening_drawer_cancels_destructive_hold(self):
        self.press("confirm", "next", "next", "down", "down", "confirm")
        self.assertIsNotNone(self.nav.holding)
        self.nav.tick(1)
        self.press("social")
        self.nav.tick(2)
        self.assertIsNone(self.nav.holding)
        self.assertEqual(self.adapters[0].calls, [])
        self.press("back", "confirm", "up")
        self.nav.tick(2)
        self.assertEqual(self.adapters[0].calls, [])

    def test_stop_and_rebuild_default_no_then_require_explicit_yes(self):
        for kind, expected in (("stop_game", ("stop",)), ("rebuild", ("build", True))):
            with self.subTest(kind=kind):
                self.adapters[0].calls.clear()
                self.nav._ask(kind)
                self.assertTrue(self.nav.view()["dialog"]["options"][0]["focused"])
                self.press("confirm")
                self.assertEqual(self.adapters[0].calls, [])
                self.nav._ask(kind)
                self.press("right", "confirm")
                self.assertEqual(self.adapters[0].calls, [expected])

    def test_backend_restores_preferences_without_reading_installs(self):
        config = dict(last_game="b", fullscreen=False, reduced_motion=True)
        with mock.patch("openrecomp.app.mf.load_config", return_value=config), \
                mock.patch("openrecomp.app.load_games", return_value=(self.games, [])), \
                mock.patch("openrecomp.app.XInputReader"), mock.patch("openrecomp.app.Pads"), \
                mock.patch("openrecomp.app.QTimer"):
            backend = Backend()
            self.assertEqual(backend.nav.game.id, "b")
            self.assertFalse(backend.nav.fullscreen)
            self.assertTrue(backend.nav.reduced_motion)

    def test_backend_defaults_to_fullscreen_and_windowed_option_overrides(self):
        with mock.patch("openrecomp.app.mf.load_config", return_value={}), \
                mock.patch("openrecomp.app.load_games", return_value=(self.games, [])), \
                mock.patch("openrecomp.app.XInputReader"), mock.patch("openrecomp.app.Pads"), \
                mock.patch("openrecomp.app.QTimer"):
            self.assertTrue(Backend().nav.fullscreen)
            self.assertFalse(Backend(windowed=True).nav.fullscreen)

    def test_backend_saves_preference_and_applies_window_mode(self):
        backend = SimpleNamespace(config={}, window=mock.Mock())
        backend.window.isMinimized.return_value = False
        with mock.patch("openrecomp.app.mf.save_config") as save:
            Backend._save_game(backend, "b")
            self.assertEqual(backend.config["last_game"], "b")
            Backend._save_preferences(backend, False, True)
            save.assert_called_with(backend.config)
        backend.window.setProperty.assert_called_once_with("wantFull", False)
        backend.window.showNormal.assert_called_once_with()
        self.assertTrue(backend.config["reduced_motion"])

    def test_pad_can_reach_stop_when_launcher_is_active_while_game_runs(self):
        self.adapters[0].is_running = True
        self.nav.screen = "hub"
        backend = SimpleNamespace(nav=self.nav, pads=mock.Mock(kind="xbox"), _slow=0,
                                  _in_front=lambda: True, refresh=mock.Mock())
        backend.pads.poll.return_value = [("confirm", "down")]
        Backend._tick(backend)
        self.assertEqual(self.nav.overlay, "dialog")
        self.assertEqual(self.nav.confirm_kind, "stop_game")
        self.assertEqual(self.adapters[0].calls, [])
        backend.refresh.assert_called_once()
        backend.pads.forget.assert_not_called()

    def test_pad_stays_with_game_when_launcher_is_not_active(self):
        self.adapters[0].is_running = True
        backend = SimpleNamespace(nav=self.nav, pads=mock.Mock(), _slow=0,
                                  _in_front=lambda: False, refresh=mock.Mock())
        Backend._tick(backend)
        backend.pads.poll.assert_not_called()
        backend.pads.forget.assert_called_once()


if __name__ == "__main__":
    unittest.main()
