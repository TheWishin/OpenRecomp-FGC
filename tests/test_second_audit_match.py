"""Second-audit match lifecycle checks with inert clients and drivers only."""
import unittest
from types import SimpleNamespace
from unittest import mock

import test_t5_match_flow as flow
from openrecomp.adapters.t5dr import T5DR


class MatchSafetyTests(unittest.TestCase):
    setUp = flow.T5MatchTests.setUp
    login = flow.T5MatchTests.login
    match = flow.T5MatchTests.match

    def test_close_owns_driver_before_worker_completion_is_adopted(self):
        client = self.login()
        client.events.put(dict(t="match_found", match="one"))
        self.a.online_poll()
        self.assertFalse(self.a._online_driver_results.empty())
        with mock.patch("openrecomp.adapters.t5_match.threading.Thread") as worker:
            self.a.online_close()
        closers = [call.kwargs["target"] for call in worker.call_args_list
                   if call.kwargs.get("name") == "openrecomp-t5-match-close"]
        self.assertEqual(len(closers), 1)
        closers[0]()
        self.assertTrue(self.a.fake_driver.closed)

    def test_close_during_driver_creation_closes_unpublished_driver(self):
        client = self.login()
        def make_driver(*_args):
            self.a.online_close()
            return self.a.fake_driver
        self.a._online_make_driver = make_driver
        client.events.put(dict(t="match_found", match="one"))
        self.a.online_poll()
        self.assertTrue(self.a.fake_driver.closed)
        self.assertEqual(self.a.fake_driver.events, [])

    def test_ticket_from_other_match_cannot_reach_native_driver(self):
        client = self.match()
        self.a.online_action("start_match")
        self.a.online_poll()
        client.events.put(dict(t="match_start", match="one",
                               ticket=SimpleNamespace(match_id="previous", path="direct")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 0)
        self.assertEqual(self.a.online_state()["phase"], "starting")


class PartialStartTests(unittest.TestCase):
    def setUp(self):
        self.a = T5DR.__new__(T5DR)
        self.a.ready = lambda: True
        self.a.game = None
        self.a.s = SimpleNamespace(out_dir="inert-output")
        self.game = mock.Mock()
        self.game.running.return_value = True
        self.a.core = SimpleNamespace(GameRun=mock.Mock(return_value=self.game))
        self.guard = self.enterContext(mock.patch("openrecomp.adapters.t5dr.LaunchGuard")).return_value
        self.enterContext(mock.patch("openrecomp.adapters.t5dr.game_process_running", return_value=False))

    def test_partial_start_keeps_live_child_and_reservation_until_exit(self):
        original = RuntimeError("inert start failure")
        self.game.start.side_effect = original
        with self.assertRaises(RuntimeError) as raised:
            self.a.start()
        self.assertIs(raised.exception, original)
        self.assertIs(self.a.game, self.game)
        self.assertIs(self.a._game_guard, self.guard)
        self.game.stop.assert_called_once_with()
        self.guard.watch.assert_called_once_with(self.game.running)
        self.guard.release.assert_not_called()

    def test_partial_start_retains_reservation_when_child_state_is_unknown(self):
        original = RuntimeError("inert start failure")
        self.game.start.side_effect = original
        self.game.stop.side_effect = OSError("inert stop failure")
        self.game.running.side_effect = OSError("inert process failure")
        with self.assertRaises(RuntimeError) as raised:
            self.a.start()
        self.assertIs(raised.exception, original)
        self.assertIs(self.a._game_guard, self.guard)
        self.guard.release.assert_not_called()

    def test_partial_start_releases_only_after_confirmed_stop(self):
        self.game.start.side_effect = RuntimeError("inert start failure")
        self.game.running.return_value = False
        with self.assertRaisesRegex(RuntimeError, "inert start failure"):
            self.a.start()
        self.game.stop.assert_called_once_with()
        self.guard.release.assert_called_once_with()

    def test_failed_monitor_stops_child_and_keeps_live_reservation(self):
        original = RuntimeError("inert monitor failure")
        self.guard.watch.side_effect = original
        with self.assertRaises(RuntimeError) as raised:
            self.a.start()
        self.assertIs(raised.exception, original)
        self.assertIs(self.a.game, self.game)
        self.assertIs(self.a._game_guard, self.guard)
        self.game.stop.assert_called_once_with()
        self.guard.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
