"""T4 ready, connection messages and installed-client delegation, with fakes only."""
import json
import threading
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from test_t4_online import Subject, ticket


class T4MatchFlowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory.name))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.a = Subject(self.directory.name)
        self.addCleanup(self.a.online_close)
        self.a.set_text_value("online_name", "Player")
        self.a.online_action("login_guest")
        self.a.online_poll()
        self.client = self.a.clients[-1]

    def found(self):
        self.event(t="match_found", match="fake-match", opponent=dict(name="Peer"))

    def event(self, **event):
        self.client.events.put(event)
        self.a.online_poll()

    def playing(self):
        self.found()
        self.a.online_action("start_match")
        self.a.online_poll()
        self.event(t="match_start", ticket=ticket())
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")

    def test_ready_acknowledgement_waits_for_peer_without_starting(self):
        self.found()
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.waiting_peer_ready")
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.client.calls.count(("ready", True)), 1)

    def already_ready(self, current=None):
        self.client.events.put(dict(t="match_found", match="fake-match", ready_check=False,
                                    opponent=dict(name="Peer")))
        self.client.events.put(dict(t="match_start", ticket=current or ticket()))
        self.a.online_poll()

    def test_accepted_challenge_same_batch_ticket_waits_for_pad_then_starts_once(self):
        self.already_ready()
        self.assertEqual(self.a.online_state()["phase"], "matched")
        self.assertEqual(self.a.starts, [])
        self.assertNotIn("fake-key", json.dumps(self.a.online_state()))
        self.a.online_poll()
        self.assertEqual(self.a.starts, [])
        self.a.online_action("start_match")
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertEqual(len(self.a.starts), 1)
        self.assertNotIn(("ready", True), self.client.calls)
        self.event(t="match_start", ticket=ticket())
        self.assertEqual(len(self.a.starts), 1)

    def test_accepted_challenge_cancellation_discards_buffered_ticket(self):
        self.already_ready()
        self.a.online_action("cancel_match")
        self.a.online_poll()
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertIsNone(self.a._online_early_start)
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.a.online_state()["phase"], "logged_in")     # declined: back in the lobby

    def test_accepted_challenge_wrong_match_ticket_is_never_buffered(self):
        self.already_ready(ticket(match_id="wrong-match"))
        self.assertIsNone(self.a._online_early_start)
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertEqual(self.a.starts, [])
        self.assertNotIn(("ready", True), self.client.calls)

    def test_accepted_challenge_still_checks_other_running_game(self):
        self.already_ready()
        with mock.patch.object(self.a, "_online_game_check", return_value="@online.game_running"):
            self.a.online_action("start_match")
            self.a.online_poll()
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.a.online_state()["message"], "@online.game_running")
        self.assertIsNone(self.a._online_early_start)

    def test_buffered_ticket_from_old_generation_cannot_start(self):
        self.already_ready()
        generation, event = self.a._online_early_start
        self.a._online_early_start = (generation - 1, event)
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertEqual(self.a.starts, [])
        self.assertIsNone(self.a._online_early_start)

    def test_nat_and_relay_messages_are_catalog_keys_without_raw_addresses(self):
        self.found()
        for phase, expected in (("register", "@online.connection_direct"),
                                ("punch", "@online.connection_direct"),
                                ("relay", "@online.connection_relay")):
            self.event(t="nat_status", match="fake-match", phase=phase,
                       text="raw endpoint 192.0.2.1:9999 private detail")
            state = self.a.online_state()
            self.assertEqual(state["message"], expected)
            self.assertNotIn("192.0.2.1", json.dumps(state))
            self.assertEqual(self.a.starts, [])

    def test_stale_nat_and_reveal_cannot_change_current_match(self):
        self.found()
        state = self.a.online_state()
        self.event(t="nat_status", match="old-match", phase="relay")
        self.event(t="match_reveal", match="old-match", opponent=dict(name="Wrong peer"))
        self.assertEqual(self.a.online_state(), state)

    def test_idle_lobby_ignores_late_match_cancel_and_reveal(self):
        self.event(t="match_cancel", match="old-match")
        self.event(t="match_reveal", match="old-match", opponent=dict(name="Wrong peer"))
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["match"], {})
        self.assertFalse(self.client.closed.is_set())

    def test_peer_quit_cancellation_explains_why_and_does_not_requeue(self):
        self.found()
        self.event(t="match_cancel", match="fake-match", reason="peer_quit")
        self.assertEqual(self.a.online_state()["message"], "@online.peer_quit")
        # Still logged in; the queue the server may have put this player back into is left.
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        for _ in range(200):
            self.a.online_poll()
            if "cancel" in self.client.calls and not self.a._online_busy:
                break
            threading.Event().wait(0.01)
        self.assertIn("cancel", self.client.calls)
        self.assertFalse(self.client.closed.is_set())

    def test_nat_failure_notice_closes_without_leaking_technical_details(self):
        self.found()
        self.event(t="notice", code="nat_error", msg="private endpoint 192.0.2.1 failed")
        self.assertEqual(self.a.online_state()["message"], "@online.connection_failed")
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertNotIn("192.0.2.1", json.dumps(self.a.online_state()))

    def test_server_cancel_reasons_are_explained_in_plain_catalog_messages(self):
        for reason, message in (("opponent_left", "@online.peer_quit"),
                                ("ready_timeout", "@online.ready_expired"),
                                ("declined", "@online.peer_declined"),
                                ("relay_full", "@online.relay_full"),
                                ("udp_unreachable", "@online.connection_failed"),
                                ("no_connection", "@online.connection_failed")):
            with self.subTest(reason=reason):
                self.a._online_phase = "matched"
                self.a._online_match_id = "fake-match"
                self.a._online_event(dict(t="match_cancel", match="fake-match", reason=reason))
                self.assertEqual(self.a.online_state()["message"], message)

    def test_late_nat_status_preserves_submitted_result_message(self):
        self.playing()
        self.a.child_exit = 0
        self.a.online_poll()
        self.a.online_action("result_none")
        self.a.online_poll()
        self.event(t="nat_status", match="fake-match", phase="relay")
        self.assertEqual(self.a.online_state()["message"], "@online.result_sent")

    def test_return_lobby_clears_ticket_identity_and_ignores_late_cancel(self):
        self.playing()
        self.a.child_exit = 0
        self.a.online_poll()
        self.a.online_action("result_none")
        self.a.online_poll()
        self.a.online_action("return_lobby")
        self.assertIsNone(self.a._online_match_id)
        self.event(t="match_cancel", match="fake-match")
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_match_connection_failure_reasons_stay_visible_after_exit(self):
        for reason, message in (("peer_quit", "@online.peer_quit"),
                                ("peer_timeout", "@online.peer_timeout"),
                                ("no_peer", "@online.connection_failed"),
                                ("build_mismatch", "@online.game_build_mismatch")):
            with self.subTest(reason=reason):
                self.a._online_phase = "playing"
                self.a._online_owned_run = None
                self.a._online_evidence = dict(reason=reason)
                self.a._online_log_offsets = {}
                self.a.online_poll()
                self.assertEqual(self.a.online_state()["phase"], "result")
                self.assertEqual(self.a.online_state()["message"], message)

    def test_direct_timeout_explains_relay_fallback(self):
        self.playing()
        self.a._online_started_at -= 21
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.connection_fallback")
        self.assertEqual(self.client.calls.count(("nat_fallback", "fake-match")), 1)

    def test_bridge_path_upgrade_changes_message_without_another_game(self):
        self.playing()
        self.event(t="nat_upgrade", match="fake-match", path="relay", text="private endpoint")
        self.assertEqual(self.a.online_state()["message"], "@online.connection_relay")
        self.event(t="nat_upgrade", match="fake-match", path="direct")
        self.assertEqual(self.a.online_state()["message"], "@online.connection_direct")
        self.assertEqual(len(self.a.starts), 1)

    def test_game_environment_comes_from_installed_runtime_helper(self):
        del self.a._online_api["game_env"]
        make_env = mock.Mock(return_value=dict(TEKKEN4_NET="fake-client-env"))
        module = SimpleNamespace(__file__=os.path.join(self.directory.name, "lobby", "t4lobby", "t4game.py"),
                                 game_env=make_env)
        with mock.patch("openrecomp.adapters.t4_online.importlib.import_module", return_value=module) as load:
            self.playing()
        load.assert_called_once_with("t4lobby.t4game")
        make_env.assert_called_once_with(self.a._online_ticket)
        # The client's endpoint wins; both PCs run the same direct-IP compatibility switches.
        self.assertEqual(self.a.starts, [dict(TEKKEN4_NET="fake-client-env", TEKKEN4_NET_STRICT_HELLO="0",
                                              TEKKEN4_NET_DELAY_MATCH="0")])

    def test_ranked_ticket_is_refused_before_installed_environment_helper(self):
        helper = mock.Mock()
        self.a._online_api["game_env"] = helper
        self.found()
        self.a.online_action("start_match")
        self.a.online_poll()
        self.event(t="match_start", ticket=ticket(ranked=True))
        self.a.online_poll()
        helper.assert_not_called()
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.a.online_state()["message"], "@online.refused")

    def test_wrong_install_runtime_helper_refuses_before_start(self):
        del self.a._online_api["game_env"]
        helper = mock.Mock()
        module = SimpleNamespace(__file__=os.path.join(self.directory.name, "other", "t4game.py"), game_env=helper)
        with mock.patch("openrecomp.adapters.t4_online.importlib.import_module", return_value=module):
            self.found()
            self.a.online_action("start_match")
            self.a.online_poll()
            self.event(t="match_start", ticket=ticket())
            self.a.online_poll()
        helper.assert_not_called()
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.a.online_state()["message"], "@online.client_missing")

    def test_missing_runtime_game_helper_refuses_before_start(self):
        del self.a._online_api["game_env"]
        with mock.patch("openrecomp.adapters.t4_online.importlib.import_module", side_effect=ImportError):
            self.found()
            self.a.online_action("start_match")
            self.a.online_poll()
            self.event(t="match_start", ticket=ticket())
            self.a.online_poll()
        self.assertEqual(self.a.starts, [])
        self.assertEqual(self.a.online_state()["message"], "@online.client_missing")


if __name__ == "__main__":
    unittest.main()
