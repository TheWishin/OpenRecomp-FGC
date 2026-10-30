"""T4 final launch checks and reservation lifetime use fake core objects only."""
import unittest
from unittest import mock

from openrecomp.adapters.t4 import T4
from test_t4 import FakeCore, MANIFEST


class T4LaunchReservationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = T4(MANIFEST, {}, "fake-root", core=FakeCore())
        self.guard_type = self.enterContext(mock.patch("openrecomp.adapters.t4.LaunchGuard"))
        self.guard = self.guard_type.return_value.acquire.return_value
        self.scan = self.enterContext(mock.patch("openrecomp.adapters.t4.game_process_running", return_value=False))
        self.start = self.enterContext(mock.patch.object(self.adapter, "_start", return_value=123))
        self.adapter.run = mock.Mock()

    def test_start_checks_existing_process_after_atomic_reservation(self):
        calls = []
        self.guard_type.return_value.acquire.side_effect = lambda: calls.append("reserve") or self.guard
        self.scan.side_effect = lambda _image: calls.append("scan") or False
        self.start.side_effect = lambda _env: calls.append("start") or 123
        self.assertEqual(self.adapter.start(), 123)
        self.assertEqual(calls, ["reserve", "scan", "start"])
        self.guard.release.assert_not_called()
        self.guard.watch.assert_called_once()
        running = self.guard.watch.call_args.args[0]
        self.adapter.run.proc.poll.return_value = None
        self.assertTrue(running())
        self.adapter.run.proc.poll.return_value = 0
        self.assertFalse(running())

    def test_running_native_game_and_unknown_scan_refuse_before_start(self):
        for active, message in ((True, "@online.game_running"), (None, "@online.process_unknown")):
            with self.subTest(active=active):
                self.scan.return_value = active
                with self.assertRaisesRegex(RuntimeError, message):
                    self.adapter.start()
                self.start.assert_not_called()
        self.assertEqual(self.guard.release.call_count, 2)

    def test_failed_start_releases_reservation(self):
        self.start.side_effect = RuntimeError("fake start failure")
        with self.assertRaisesRegex(RuntimeError, "fake start failure"):
            self.adapter.start()
        self.guard.release.assert_called_once()
        self.guard.watch.assert_not_called()

    def test_busy_reservation_never_scans_or_starts(self):
        self.guard_type.return_value.acquire.side_effect = RuntimeError("@online.game_running")
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            self.adapter.start()
        self.scan.assert_not_called()
        self.start.assert_not_called()

    def test_confirmed_exit_releases_old_reservation_before_immediate_restart(self):
        old = mock.Mock()
        self.adapter._launch_guard = old
        self.adapter.run.proc.poll.return_value = 0
        calls = []
        old.release.side_effect = lambda: calls.append("release")
        self.guard_type.return_value.acquire.side_effect = lambda: calls.append("reserve") or self.guard
        self.adapter.start()
        self.assertEqual(calls, ["release", "reserve"])


if __name__ == "__main__":
    unittest.main()
