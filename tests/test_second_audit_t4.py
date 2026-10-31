"""T4 network boundaries use fake cores and processes only."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t4 import T4
from openrecomp.adapters.t4_online import T4Online
from test_t4 import FakeCore, MANIFEST


class T4NetworkBoundaries(unittest.TestCase):
    def setUp(self):
        self.core = FakeCore()
        self.adapter = T4(MANIFEST, {}, "fake-root", core=self.core)
        self.enterContext(mock.patch("openrecomp.adapters.t4.threading.Thread"))

    def test_offline_play_discards_inherited_network_session(self):
        inherited = dict(TEKKEN4_NET="join:192.0.2.8:7400", TEKKEN4_NET_PEER="192.0.2.9:7400",
                         TEKKEN4_NET_KEY="fixture", TEKKEN4_NET_SEED="42", TEKKEN4_NET_PORT="7400",
                         TEKKEN4_NET_BUILD="fixture", TEKKEN4_NET_BIND="0.0.0.0:7400",
                         tekken4_net="host:7400", SOUND_SETTING="preserved")
        with mock.patch.object(self.core, "game_env", return_value=inherited):
            self.adapter._start()
        env = self.core.started[-1]
        for name in inherited:
            if name.upper() == "TEKKEN4_NET" or name.upper().startswith("TEKKEN4_NET_"):
                self.assertNotIn(name, env)
        self.assertEqual(env["SOUND_SETTING"], "preserved")

    def test_online_play_receives_only_explicit_network_session(self):
        inherited = dict(TEKKEN4_NET="host:7400", TEKKEN4_NET_KEY="old-session",
                         TEKKEN4_NET_PEER="192.0.2.8:7400")
        explicit = dict(TEKKEN4_NET="join:192.0.2.9:7400", TEKKEN4_NET_KEY="new-session")
        with mock.patch.object(self.core, "game_env", return_value=inherited):
            self.adapter._start(explicit)
        env = self.core.started[-1]
        self.assertEqual(env["TEKKEN4_NET"], explicit["TEKKEN4_NET"])
        self.assertEqual(env["TEKKEN4_NET_KEY"], "new-session")
        self.assertNotIn("TEKKEN4_NET_PEER", env)

    def test_cancelled_preflight_never_spawns_a_tool(self):
        cancel = threading.Event()
        cancel.set()
        with mock.patch("openrecomp.adapters.t4_online.subprocess.Popen") as process:
            with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
                T4Online._direct_process(self.adapter, ["fake-tool"], cancel)
        process.assert_not_called()

    def test_post_start_lock_failure_keeps_child_reachable_and_reserved(self):
        proc = SimpleNamespace(pid=123, returncode=None)
        proc.poll = lambda: proc.returncode
        run = SimpleNamespace(start=mock.Mock(), stop=mock.Mock(), proc=proc)
        self.core.GameRun = lambda settings: run
        self.core.take_run_lock = mock.Mock(side_effect=OSError("synthetic lock failure"))
        self.core.release_run_lock = mock.Mock()
        with mock.patch("openrecomp.adapters.t4.LaunchGuard") as guard_type, mock.patch(
                "openrecomp.adapters.t4.game_process_running", return_value=False):
            with self.assertRaisesRegex(OSError, "synthetic lock failure"):
                self.adapter.start()
        self.assertIs(self.adapter.run, run)
        run.stop.assert_called_once_with()
        guard = guard_type.return_value.acquire.return_value
        guard.release.assert_not_called()
        guard.watch.assert_called_once()
        proc.returncode = 0
        self.assertFalse(guard.watch.call_args.args[0]())
        self.core.release_run_lock.assert_not_called()

    def test_failed_waiter_releases_owned_native_lock_only_after_confirmed_exit(self):
        for stop_finishes in (True, False):
            with self.subTest(stop_finishes=stop_finishes):
                proc = SimpleNamespace(pid=123, returncode=None)
                proc.poll = lambda: proc.returncode
                stop = mock.Mock(side_effect=lambda: setattr(proc, "returncode", 0)
                                 if stop_finishes else None)
                run = SimpleNamespace(start=mock.Mock(), stop=stop, proc=proc)
                self.adapter.run = None
                self.core.GameRun = lambda settings: run
                self.core.release_run_lock = mock.Mock()
                with mock.patch("openrecomp.adapters.t4.threading.Thread") as thread, mock.patch(
                        "openrecomp.adapters.t4.LaunchGuard") as guard_type, mock.patch(
                            "openrecomp.adapters.t4.game_process_running", return_value=False):
                    thread.return_value.start.side_effect = RuntimeError("synthetic waiter failure")
                    with self.assertRaisesRegex(RuntimeError, "synthetic waiter failure"):
                        self.adapter.start()
                guard = guard_type.return_value.acquire.return_value
                stop.assert_called_once_with()
                if stop_finishes:
                    self.core.release_run_lock.assert_called_once_with()
                    guard.release.assert_called_once_with()
                else:
                    self.core.release_run_lock.assert_not_called()
                    guard.release.assert_not_called()
                    active = guard.watch.call_args.args[0]
                    self.assertTrue(active())
                    proc.returncode = 0
                    self.assertFalse(active())
                    self.assertFalse(active())
                    self.core.release_run_lock.assert_called_once_with()

    def test_direct_start_failure_keeps_new_child_owned_for_disconnect(self):
        self.adapter._direct_init()
        verified = dict(stamps=(), paths=(), checked_at=time.monotonic(), build="fixture")
        self.adapter._direct_phase = "checked"
        self.adapter._direct_verified = verified
        run = SimpleNamespace(proc=SimpleNamespace(poll=lambda: None))

        def fail_start(extra_env):
            self.adapter.run = run
            raise OSError("synthetic post-start failure")

        pending = []
        with mock.patch.object(self.adapter, "start", side_effect=fail_start), mock.patch.object(
                self.adapter, "_online_game_check", return_value=""), mock.patch.object(
                    self.adapter, "_direct_log_stamps", return_value={}), mock.patch.object(
                        self.adapter, "_direct_submit", side_effect=lambda action, work: pending.append(work)):
            self.adapter._direct_action("start_match")
            with self.assertRaisesRegex(OSError, "synthetic post-start failure"):
                pending.pop()()
        self.assertIs(self.adapter._online_owned_run, run)

    def test_failed_reservation_watcher_stops_child_and_keeps_guard(self):
        run = SimpleNamespace(proc=SimpleNamespace(poll=lambda: None), stop=mock.Mock())

        def start(extra_env):
            self.adapter.run = run
            return 123

        with mock.patch.object(self.adapter, "_start", side_effect=start), mock.patch(
                "openrecomp.adapters.t4.LaunchGuard") as guard_type, mock.patch(
                    "openrecomp.adapters.t4.game_process_running", return_value=False):
            guard = guard_type.return_value.acquire.return_value
            guard.watch.side_effect = RuntimeError("synthetic watcher failure")
            with self.assertRaisesRegex(RuntimeError, "synthetic watcher failure"):
                self.adapter.start()
        run.stop.assert_called_once_with()
        self.assertIs(self.adapter._launch_guard, guard)
        guard.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
