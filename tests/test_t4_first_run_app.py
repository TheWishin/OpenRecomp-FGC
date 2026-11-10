"""T4 first-run bridge with fake adapters, pads and window; no launcher is started."""
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import app
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav


class FirstRunBridge(unittest.TestCase):
    def game(self, kind="t4", running=False):
        adapter = Adapter(dict(id=kind, short=kind))
        adapter.running = lambda: running
        return Game(dict(id=kind, short=kind, accent="#ffffff", adapter=kind), adapter)

    def backend(self, game):
        nav = SimpleNamespace(games=[game], act=mock.Mock(), release=mock.Mock(),
                              tick=lambda dt: False, binding_active=lambda: False,
                              poll_tools=lambda **kwargs: False, pad_kind="xbox")
        pads = mock.Mock(kind="xbox")
        pads.return_requested.return_value = True
        pads.poll.return_value = []
        return SimpleNamespace(nav=nav, pads=pads, _slow=0.0, _in_front=lambda: False,
                               _poll_updates=lambda: False, refresh=mock.Mock())

    def test_t4_exit_chord_is_read_while_game_is_in_front_without_navigation_input(self):
        backend = self.backend(self.game(running=True))
        app.Backend._tick(backend)
        backend.pads.return_requested.assert_called_once_with(app.TICK_MS / 1000.0)
        backend.nav.act.assert_called_once_with("returnGame", device="xbox")
        backend.pads.poll.assert_not_called()

    def test_exit_chord_does_not_change_t5dr_play_and_resets_when_game_stops(self):
        for game in (self.game("t5dr", running=True), self.game(running=False)):
            with self.subTest(game=game.id):
                backend = self.backend(game)
                app.Backend._tick(backend)
                backend.pads.return_requested.assert_not_called()
                backend.pads.reset_return.assert_called_once_with()
                backend.nav.act.assert_not_called()

    def test_source_work_refreshes_until_finished_even_before_game_is_found(self):
        game = self.game()
        state = dict(running=True)
        game.a.source_state = lambda: state
        backend = SimpleNamespace(nav=SimpleNamespace(games=[game]), window=None,
                                  _was_running=False, _was_building=False,
                                  _was_sourcing=False, _last_hero={game.id: ""})
        app.Backend._slow_changes(backend, False)
        self.assertTrue(app.Backend._slow_changes(backend, False))
        self.assertTrue(app.Backend._slow_changes(backend, False))
        state["running"] = False
        self.assertTrue(app.Backend._slow_changes(backend, False))
        self.assertFalse(app.Backend._slow_changes(backend, False))

    def test_source_work_blocks_update_restart(self):
        game = self.game()
        game.a.source_state = lambda: dict(running=True)
        backend = SimpleNamespace(nav=SimpleNamespace(games=[game], binding_active=lambda: False))
        self.assertTrue(app.Backend._update_busy(backend))

    def test_native_sony_reader_is_available_with_no_game_install(self):
        backend = SimpleNamespace(pads=None, _pad_root=None)
        sony = mock.Mock()
        sony.read.return_value = set()
        with mock.patch.object(app, "XInputReader") as xbox, \
                mock.patch.object(app, "WinMMPlayStationReader", return_value=sony) as factory,                 mock.patch.object(app, "HidPlayStationReader") as hid:
            app.Backend._load_pads(backend, [])
        factory.assert_called_once_with()
        self.assertEqual(backend.pads.readers, [xbox.return_value, sony, hid.return_value])

    def test_window_close_uses_navigation_quit_guard(self):
        backend = SimpleNamespace(nav=SimpleNamespace(request_quit=mock.Mock()), refresh=mock.Mock())
        app.Backend.requestQuit(backend)
        backend.nav.request_quit.assert_called_once_with()
        backend.refresh.assert_called_once_with()

    def test_approved_quit_allows_native_close_after_confirmation(self):
        backend = SimpleNamespace(window=mock.Mock())
        with mock.patch.object(app.QGuiApplication, "quit") as quit_app:
            app.Backend._quit(backend)
        backend.window.setProperty.assert_called_once_with("allowClose", True)
        quit_app.assert_called_once_with()

    def test_short_run_failure_and_late_build_result_redraw_without_running_transition(self):
        game = self.game()
        status = game.a.status()
        build = game.a.build_state()
        game.a.status = lambda: dict(status)
        game.a.build_state = lambda: dict(build)
        backend = SimpleNamespace(nav=SimpleNamespace(games=[game]), window=None,
                                  _was_running=False, _was_building=False, _was_sourcing=False,
                                  _last_hero={game.id: ""})
        app.Backend._slow_changes(backend, False)
        self.assertFalse(app.Backend._slow_changes(backend, False))
        status["detail"] = "Synthetic short run failed; retry Play."
        self.assertTrue(app.Backend._slow_changes(backend, False))
        build["result"] = "Synthetic build failed; retry Build."
        self.assertTrue(app.Backend._slow_changes(backend, False))
        self.assertFalse(app.Backend._slow_changes(backend, False))


if __name__ == "__main__":
    unittest.main()
