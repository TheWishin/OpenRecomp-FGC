"""Timer and controller regressions without a window, installed game, or network."""
from types import SimpleNamespace
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

from openrecomp import app, pad
from openrecomp.pad import Pads, PlayStationReader


class TimerSafety(unittest.TestCase):
    def test_busy_install_callback_never_writes_or_reloads_adapters(self):
        backend = SimpleNamespace(nav=SimpleNamespace(can_reload_games=lambda: False))
        with mock.patch.object(app.mf, "install") as install, \
                mock.patch.object(app.mf, "save_config") as save, \
                mock.patch.object(app, "load_games") as load:
            for path in (None, "synthetic-manifest.json"):
                self.assertEqual(app.Backend._install(backend, path), "@library.busy")
            install.assert_not_called()
            save.assert_not_called()
            load.assert_not_called()

    def backend(self, *, running=False, active=True, changed=True):
        events = []
        nav = SimpleNamespace(
            games=[SimpleNamespace(m={}, a=SimpleNamespace(running=lambda: running))],
            release=lambda action: events.append(("release", action)),
            tick=lambda dt: events.append(("tick", dt)) or changed,
            binding_active=lambda: False,
            poll_tools=lambda **kw: events.append(("tools", kw["active"])) or False,
            act=lambda *args, **kw: events.append(("act", args)),
        )
        pads = SimpleNamespace(
            poll=lambda: events.append(("poll",)) or [],
            forget=lambda: events.append(("forget",)),
            suppress=lambda: events.append(("suppress",)),
            reset_return=lambda: None,
        )
        backend = SimpleNamespace(
            nav=nav, pads=pads, _in_front=lambda: active,
            _poll_updates=lambda: False, _slow=0.49,
            _slow_changes=lambda value: events.append(("slow", value)) or False,
            refresh=lambda: events.append(("refresh",)),
        )
        return backend, events

    def test_game_running_suppresses_pad_and_control_readers_even_when_focused(self):
        backend, events = self.backend(running=True)
        app.Backend._tick(backend)
        self.assertIn(("forget",), events)
        self.assertIn(("tools", False), events)
        self.assertNotIn(("poll",), events)

    def test_inactive_hold_is_released_before_time_advances(self):
        backend, events = self.backend(active=False)
        app.Backend._tick(backend)
        self.assertEqual(events[0], ("release", "confirm"))
        self.assertEqual(events[1][0], "tick")

    def test_slow_reconciliation_runs_even_during_other_changes(self):
        backend, events = self.backend(changed=True)
        app.Backend._tick(backend)
        self.assertIn(("slow", False), events)

    def test_game_started_during_model_tick_suppresses_same_tick_pad(self):
        backend, events = self.backend()
        adapter = backend.nav.games[0].a

        def tick(dt):
            adapter.running = lambda: True
            return True

        backend.nav.tick = tick
        app.Backend._tick(backend)
        self.assertIn(("forget",), events)
        self.assertNotIn(("poll",), events)


class FocusSafety(unittest.TestCase):
    def test_selecting_first_t5_install_adds_reader_without_restarting(self):
        root = str(Path(__file__).parent / "synthetic-install")
        backend = SimpleNamespace(pads=Pads([]), _pad_root="")
        game = SimpleNamespace(id="t5dr", a=SimpleNamespace(root=root, found=lambda: True))
        ps = SimpleNamespace(kind="ps", read=lambda: {"A"})
        with mock.patch.object(app, "XInputReader", return_value=SimpleNamespace(kind="xbox", read=set)), \
                mock.patch.object(app, "PlayStationReader", return_value=ps) as factory:
            app.Backend._load_pads(backend, [game])
        factory.assert_called_once_with(root)
        self.assertIn(ps, backend.pads.readers)
        self.assertNotIn(("confirm", "down"), backend.pads.poll())

    def test_install_change_pauses_and_removes_previous_reader(self):
        paused = []
        old = SimpleNamespace(kind="ps", read=set, pause=lambda: paused.append(True))
        backend = SimpleNamespace(pads=Pads([old]), _pad_root="synthetic-old")
        with mock.patch.object(app, "XInputReader", return_value=SimpleNamespace(kind="xbox", read=set)):
            app.Backend._load_pads(backend, [])
        self.assertEqual(paused, [True])
        self.assertNotIn(old, backend.pads.readers)

    def test_pad_reader_refuses_cached_module_from_another_install(self):
        root = str(Path(__file__).parent / "synthetic-install")
        origin = os.path.join(root, "lobby", "t5lobby", "__init__.py")
        other = SimpleNamespace(__file__=str(Path(__file__).parent / "synthetic-other" / "__init__.py"))
        with mock.patch.object(pad.PathFinder, "find_spec", return_value=SimpleNamespace(origin=origin)), \
                mock.patch.dict(sys.modules, {"t5lobby": other}), \
                mock.patch.object(pad.importlib, "import_module") as imported:
            reader = PlayStationReader(root)
        self.assertIsNone(reader.source)
        imported.assert_not_called()

    def test_unplugged_hid_reader_does_not_abort_focus_loss(self):
        def unplugged():
            raise OSError("reader disconnected")

        reader = PlayStationReader.__new__(PlayStationReader)
        reader.source = SimpleNamespace(pause=unplugged)
        reader.next_scan = 10
        Pads([reader]).forget()
        self.assertEqual(reader.next_scan, 0)

    def test_button_first_pressed_while_away_requires_release_on_return(self):
        reader = SimpleNamespace(kind="xbox", read=lambda: {"A"})
        pads = Pads([reader])
        pads.forget()
        self.assertNotIn(("confirm", "down"), pads.poll())
        reader.read = lambda: set()
        pads.poll()
        reader.read = lambda: {"A"}
        self.assertIn(("confirm", "down"), pads.poll())


if __name__ == "__main__":
    unittest.main()
