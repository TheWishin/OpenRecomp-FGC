"""T5 match-driver integration with inert clients and game handles only."""
import unittest
import os
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t5_match import T5Match
from openrecomp.adapters.t5dr import T5DR
import test_online_adapter as online_fakes


class Driver:
    def __init__(self):
        self.events = []
        self.notes = []
        self.ticket = None
        self.started = 0
        self.closed = False
        self.answers = []
        self.rematches = []

    def on_event(self, event):
        self.events.append(event)
        if event["t"] == "match_start":
            self.ticket = event.get("ticket") or SimpleNamespace(match_id=event["match"])
            self.started += 1

    def poll(self):
        notes, self.notes = self.notes, []
        return notes

    def game_running(self):
        return self.ticket is not None

    def close(self):
        self.closed = True

    def answer(self, answer):
        self.answers.append(answer)

    def rematch(self, mid, accept):
        self.rematches.append((mid, accept))


class MatchSubject(T5Match, online_fakes.Subject):
    def _online_make_driver(self, client, generation):
        return self.fake_driver

    def _online_driver_submit(self, work):
        self._online_driver_busy = True
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        self._online_driver_results.put((self._online_generation, value, error))


class PendingResultDriver(Driver):
    def __init__(self):
        super().__init__()
        self.last = None

    def on_event(self, event):
        super().on_event(event)
        if event["t"] == "match_result":
            self.last = event

    def rematch(self, mid, accept):
        # The native driver learns its default match only after consuming the result.
        mid = mid or (self.last or {}).get("match")
        if mid:
            super().rematch(mid, accept)


class T5MatchTests(unittest.TestCase):
    login = online_fakes.OnlineAdapterTests.login

    def setUp(self):
        online_fakes.OnlineAdapterTests.setUp(self)
        self.a = MatchSubject(self.directory.name)
        self.a.fake_driver = Driver()
        self.addCleanup(self.a.online_close)

    def match(self):
        client = self.login()
        client.ready = mock.Mock(return_value={})
        client.leave_set = mock.Mock(return_value={})
        client.events.put(dict(t="match_found", match="one", opponent=dict(name="Peer")))
        self.a.online_poll()
        self.a.online_poll()
        return client

    def start(self, client, ticket=None):
        self.a.online_action("start_match")
        self.a.online_poll()
        ticket = ticket or SimpleNamespace(match_id="one", path="direct")
        client.events.put(dict(t="match_start", match="one", ticket=ticket))
        self.a.online_poll()
        self.a.online_poll()
        return ticket

    def test_ready_is_explicit_and_duplicate_start_is_ignored(self):
        client = self.match()
        self.assertEqual(self.a.online_state()["phase"], "matched")
        client.ready.assert_not_called()
        ticket = self.start(client)
        client.ready.assert_called_once_with(True)
        self.assertEqual(self.a.online_state()["phase"], "playing")
        client.events.put(dict(t="match_start", match="one", ticket=ticket))
        client.events.put(dict(t="match_start", match="one", ticket=SimpleNamespace(path="direct")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 1)

    def test_driver_polling_keeps_pad_actions_available(self):
        client = self.match()
        for _ in range(4):
            self.a.online_poll()
            self.assertFalse(self.a._online_busy)
        self.a.online_action("start_match")
        client.ready.assert_called_once_with(True)

    def test_unsolicited_start_has_no_authority(self):
        client = self.match()
        client.events.put(dict(t="match_start", match="one", ticket=SimpleNamespace(path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 0)

    def test_already_ready_challenge_buffers_ticket_until_pad_confirmation(self):
        client = self.login()
        client.ready = mock.Mock()
        client.events.put(dict(t="match_found", match="one", ready_check=False, origin="challenge"))
        client.events.put(dict(t="match_start", match="one", ticket=SimpleNamespace(match_id="one", path="direct")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 0)
        self.assertEqual(self.a.online_state()["phase"], "matched")
        self.a.online_action("start_match")
        self.a.online_poll()
        self.a.online_poll()
        client.ready.assert_not_called()
        self.assertEqual(self.a.fake_driver.started, 1)
        self.assertEqual(self.a.online_state()["phase"], "playing")

    def test_requested_rematch_accepts_immediate_continuation(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        self.a.online_poll()
        self.a.online_poll()
        self.a.online_action("rematch")
        self.a.online_poll()
        client.events.put(dict(t="match_found", match="two", ready_check=False, origin="rematch", keep=True))
        client.events.put(dict(t="match_start", match="two", **{"continue": True}))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 2)
        self.assertEqual(self.a.online_state()["phase"], "playing")
        client.ready.assert_called_once_with(True)

    def test_rematch_before_driver_consumes_result_uses_current_match(self):
        self.a.fake_driver = PendingResultDriver()
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        pending = []
        with mock.patch.object(self.a, "_online_driver_submit", side_effect=pending.append):
            self.a.online_poll()
            self.assertEqual(self.a.online_state()["phase"], "result_sent")
            self.assertIsNone(self.a.fake_driver.last)
            self.a.online_action("rematch")
            self.assertEqual(self.a.fake_driver.rematches, [("one", True)])
        self.assertTrue(pending)

    def test_native_connection_notice_ends_pending_match_without_raw_message(self):
        client = self.match()
        client.events.put(dict(t="notice", code="nat_error", msg="private endpoint"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")      # the match ends, the login stays
        self.assertEqual(self.a.online_state()["message"], "@online.connection_failed")
        self.assertNotIn("private endpoint", str(self.a.online_state()))

    def test_relay_fallback_replaces_only_direct_start(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_start", match="one", ticket=SimpleNamespace(path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 2)
        client.events.put(dict(t="match_start", match="one", ticket=SimpleNamespace(path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 2)

    def test_manual_result_and_rematch_delegate_to_driver(self):
        client = self.match()
        self.start(client)
        self.a.fake_driver.notes.append(dict(kind="ask_result", match="one"))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result")
        self.a.online_action("result_win")
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.answers, ["won"])
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        self.a.online_poll()
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])
        self.a.online_action("rematch")
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.rematches, [("one", True)])

    def test_return_lobby_declines_rematch(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        self.a.online_poll()
        self.a.online_poll()
        self.a.online_action("return_lobby")
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.rematches, [("one", False)])
        client.leave_set.assert_called_once_with()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_return_lobby_after_a_decided_set_stays_logged_in(self):
        # 1.2.0: every casual game is an FT1 set; once it is decided there is no set to leave
        # (the real server answers bad_state "you are not in a set"). Seen in a real local-lobby pair.
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20,
                               set=dict(id="s1", casual=True, first_to=1, state="active")))
        client.events.put(dict(t="set_end", set="s1", reason="decided", result="win"))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.set_won")
        self.a.online_action("return_lobby")
        self.a.online_poll()
        client.leave_set.assert_not_called()
        self.assertEqual(self.a.fake_driver.rematches, [("one", False)])
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_return_lobby_when_the_server_has_no_set_to_leave(self):
        client = self.match()
        self.start(client)
        client.leave_set.side_effect = type("Refused", (Exception,), {"code": "bad_state"})()
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        self.a.online_poll()
        self.a.online_poll()
        self.a.online_action("return_lobby")
        self.a.online_poll()
        client.leave_set.assert_called_once_with()
        self.assertEqual(self.a.fake_driver.rematches, [("one", False)])
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_return_lobby_refused_keeps_the_result_screen(self):
        client = self.match()
        self.start(client)
        client.leave_set.side_effect = type("Refused", (Exception,), {"code": "busy"})()
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        self.a.online_poll()
        self.a.online_poll()
        self.a.online_action("return_lobby")
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.rematches, [])
        # The set was not left: the result screen stays (Return can be pressed again), logged in.
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.assertFalse(client.closed.is_set())

    def test_game_back_at_its_select_screen_keeps_the_result_message(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.result_confirmed")
        self.a.fake_driver.notes.append(dict(kind="game_state", state="select"))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.result_confirmed")
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])

    def test_finished_match_cannot_restart_on_late_relay_ticket(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed", rematch_window=20))
        client.events.put(dict(t="match_start", match="one", ticket=SimpleNamespace(match_id="one", path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 1)
        self.assertEqual(self.a.online_state()["phase"], "result_sent")

    def test_peer_quit_and_nat_messages_do_not_expose_server_text(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="nat_upgrade", match="one", path="relay", text="private endpoint"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.connection_relay")
        client.events.put(dict(t="match_result", match="one", reason="peer_quit"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.peer_quit")
        self.assertNotIn("private endpoint", str(self.a.online_state()))

    def test_native_nat_status_and_fallback_use_catalogs(self):
        client = self.match()
        for event, message in (
                (dict(t="nat_status", phase="relay"), "@online.connection_relay"),
                (dict(t="nat_status", phase="punch", udp_blocked=True), "@online.connection_failed"),
                (dict(t="nat_fallback", ok=True), "@online.connection_fallback"),
                (dict(t="nat_fallback", ok=False), "@online.connection_failed")):
            with self.subTest(event=event):
                client.events.put(dict(event, match="one", text="private endpoint"))
                self.a.online_poll()
                self.assertEqual(self.a.online_state()["message"], message)

    def test_stale_match_events_cannot_replace_idle_lobby(self):
        client = self.login()
        for kind in ("match_start", "match_result", "rematch", "nat_status"):
            client.events.put(dict(t=kind, match="stale", state="offered"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])

    def test_installed_driver_launch_callback_requires_current_ready_authority(self):
        client = self.match()
        module = SimpleNamespace(
            __file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
            MatchDriver=mock.Mock(), game_files=mock.Mock(return_value=[]))
        with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module):
            T5Match._online_make_driver(self.a, client, self.a._online_generation)
        call = module.MatchDriver.call_args
        self.assertEqual(call.kwargs["mode"], "auto")
        self.assertTrue(call.kwargs["async_calls"])
        launch = call.args[1]
        self.a.start = mock.Mock()
        self.a.game = object()
        with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
            launch({"TEST": "fake"})
        self.a._online_authorized = True
        with mock.patch.object(self.a, "_online_game_check", return_value=""):
            self.assertIs(launch({"TEST": "fake"}), self.a.game)
        self.a.start.assert_called_once_with(extra_env=dict(TEST="fake", T5_RB_NET_FEEL="balanced", T5_NET_LINE="0",
            T5_RB_COST_FILE=os.path.join(self.a._online_out_dir(), "rb_cost.txt")))
        self.a.online_close()
        with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
            launch({"TEST": "stale"})
        self.a.start.assert_called_once()

    def test_driver_from_other_install_is_refused(self):
        client = self.match()
        module = SimpleNamespace(__file__=self.directory.name + "/elsewhere/match_driver.py")
        with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module):
            with self.assertRaisesRegex(RuntimeError, "@online.client_missing"):
                T5Match._online_make_driver(self.a, client, self.a._online_generation)

    def test_kick_closes_driver_without_relogin(self):
        client = self.match()
        self.start(client)
        driver = self.a.fake_driver
        client.events.put(dict(t="kicked", reason="logged in from another place"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "kicked")
        for _ in range(3):
            self.a.online_poll()
        self.assertEqual(len(self.a.clients), 1)
        self.assertIsNone(self.a._online_driver)

    def test_game_start_refuses_another_launcher_and_unknown_process_state(self):
        adapter = T5DR.__new__(T5DR)
        adapter.ready = lambda: True
        adapter.game = None
        adapter.s = SimpleNamespace(out_dir="fake")
        adapter.core = SimpleNamespace(GameRun=mock.Mock())
        for running, message in ((True, "@online.game_running"), (None, "@online.process_unknown")):
            with self.subTest(running=running), mock.patch("openrecomp.adapters.t5dr.LaunchGuard") as guard, mock.patch(
                    "openrecomp.adapters.t5dr.game_process_running", return_value=running):
                with self.assertRaisesRegex(RuntimeError, message):
                    adapter.start()
                guard.return_value.release.assert_called_once()
                adapter.core.GameRun.assert_not_called()

    def test_successful_start_keeps_reservation_until_game_exit(self):
        adapter = T5DR.__new__(T5DR)
        adapter.ready = lambda: True
        adapter.game = None
        adapter.s = SimpleNamespace(out_dir="fake")
        game = mock.Mock()
        game.start.return_value = 73
        adapter.core = SimpleNamespace(GameRun=mock.Mock(return_value=game))
        with mock.patch("openrecomp.adapters.t5dr.LaunchGuard") as guard, mock.patch(
                "openrecomp.adapters.t5dr.game_process_running", return_value=False):
            self.assertEqual(adapter.start(extra_env={"TEST": "fake"}), 73)
            guard.return_value.acquire.assert_called_once()
            game.start.assert_called_once_with(extra_env={"TEST": "fake"})
            guard.return_value.watch.assert_called_once_with(game.running)
            guard.return_value.release.assert_not_called()

    def test_failed_start_releases_reservation(self):
        adapter = T5DR.__new__(T5DR)
        adapter.ready = lambda: True
        adapter.game = None
        adapter.s = SimpleNamespace(out_dir="fake")
        adapter.core = SimpleNamespace(GameRun=mock.Mock(side_effect=RuntimeError("fake failure")))
        with mock.patch("openrecomp.adapters.t5dr.LaunchGuard") as guard, mock.patch(
                "openrecomp.adapters.t5dr.game_process_running", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "fake failure"):
                adapter.start()
            guard.return_value.release.assert_called_once()

    def test_restart_releases_exited_games_guard_before_acquire(self):
        adapter = T5DR.__new__(T5DR)
        adapter.ready = lambda: True
        old_game = mock.Mock()
        old_game.running.return_value = False
        adapter.game = old_game
        adapter._game_guard = mock.Mock()
        adapter.s = SimpleNamespace(out_dir="fake")
        adapter.core = SimpleNamespace(GameRun=mock.Mock())
        with mock.patch("openrecomp.adapters.t5dr.LaunchGuard") as guard, mock.patch(
                "openrecomp.adapters.t5dr.game_process_running", return_value=False):
            guard.return_value.acquire.side_effect = lambda: adapter._game_guard.release.assert_called_once()
            adapter.start()


if __name__ == "__main__":
    unittest.main()
