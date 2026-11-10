"""T5DR gets from this launcher what its own launcher gives it: the same arguments to the install's GameRun.start.
The install's core is a stand-in; no game starts and no window is looked for."""
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters import t5_monitor
from openrecomp.adapters.t5dr import T5DR


class Run:
    """GameRun as the install has it: the settings' environment, the launcher's monitor, then what was asked for."""

    def __init__(self, out, settings):
        self.settings, self.env, self.proc = settings, None, None

    def start(self, extra_env=None, monitor_point=None):
        env = dict(self.settings.env_overrides())
        if monitor_point and "PS3_WINDOW_MONITOR" not in env:
            env["PS3_WINDOW_MONITOR"] = "%d,%d" % monitor_point
        env.update(extra_env or {})
        self.env = env
        return 7

    def running(self):
        return False


class OldRun(Run):
    def start(self, extra_env=None):                # an install from before the launcher's monitor was handed over
        return super().start(extra_env)


def adapter(run=Run, **core):
    a = T5DR.__new__(T5DR)
    a.m = dict(id="t5dr")
    a.game = None
    a.ready = lambda: True
    a.s = SimpleNamespace(out_dir="fake", env_overrides=lambda: dict(PS3_LAPTOP="auto", PS3_INTERNAL_RES="1080p"))
    a.core = SimpleNamespace(GameRun=run, **core)
    a._track_playtime = lambda *args, **kwargs: None
    return a


def start(a, extra_env=None, window=77):
    with mock.patch("openrecomp.adapters.t5dr.LaunchGuard"), \
         mock.patch("openrecomp.adapters.t5dr.game_process_running", return_value=False), \
         mock.patch("openrecomp.adapters.t5dr.t5_startlog"), \
         mock.patch.object(t5_monitor, "own_window", return_value=window):
        a.start(extra_env=extra_env)
    return a.game.env


class LaunchParity(unittest.TestCase):
    def own_launcher(self, a, extra_env=None, window=77):
        """What T5DR's own launcher does on PLAY: GameRun(out, settings).start(env, monitor_point=its window's centre)."""
        run = a.core.GameRun(a.s.out_dir, a.s)
        run.start(extra_env, monitor_point=a.core.window_center(window))
        return run.env

    def test_the_same_environment_as_the_games_own_launcher(self):
        for extra in (None, dict(PS3_FULLSCREEN="1"), dict(T5_NET_MODE="host", PS3_WINDOW_MONITOR="5,5")):
            with self.subTest(extra=extra):
                a = adapter(window_center=lambda hwnd: (2560 + hwnd, 700))
                self.assertEqual(start(a, extra), self.own_launcher(a, extra))
        self.assertEqual(start(adapter(window_center=lambda hwnd: (2560 + hwnd, 700)))["PS3_WINDOW_MONITOR"], "2637,700")

    def test_no_window_or_an_install_without_the_point_starts_as_before(self):
        self.assertNotIn("PS3_WINDOW_MONITOR", start(adapter(window_center=lambda hwnd: (1, 2)), window=None))
        self.assertNotIn("PS3_WINDOW_MONITOR", start(adapter(window_center=lambda hwnd: None)))
        self.assertNotIn("PS3_WINDOW_MONITOR", start(adapter()))
        self.assertNotIn("PS3_WINDOW_MONITOR", start(adapter(run=OldRun, window_center=lambda hwnd: (1, 2))))
        broken = adapter(window_center=mock.Mock(side_effect=OSError("no screen")))
        self.assertNotIn("PS3_WINDOW_MONITOR", start(broken))

    def test_own_window_answers_without_a_window(self):
        self.assertIsNone(t5_monitor.own_window())      # a test run has no visible window of its own


if __name__ == "__main__":
    unittest.main()
