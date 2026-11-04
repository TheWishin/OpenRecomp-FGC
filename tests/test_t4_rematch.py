"""T4 result-screen rematches use a new authorized process; no server or game is started."""
import os
import tempfile
import unittest
from unittest import mock

from test_t4_online import Subject, ticket


class T4RematchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory.name))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.a = Subject(self.directory.name)
        self.addCleanup(self.a.online_close)
        self.a.set_text_value("online_name", "FakePlayer")
        self.a.online_action("login_guest")
        self.a.online_poll()
        self.client = self.a.clients[-1]
        self.client.rematch = mock.Mock()
        self.client.events.put(dict(t="match_found", match="fake-match"))
        self.a.online_poll()
        self.a.online_action("start_match")
        self.a.online_poll()
        self.client.events.put(dict(t="match_start", ticket=ticket()))
        self.a.online_poll()
        self.a.online_poll()
        self.client.events.put(dict(t="match_result", match="fake-match", status="confirmed", rematch_window=20))
        self.a.online_poll()

    def found_next(self):
        self.client.events.put(dict(t="match_found", match="next-match", origin="rematch", ready_check=False,
                                    rematch_of="fake-match"))
        self.a.online_poll()

    def test_result_offers_rematch_and_waits_for_new_authorized_ticket(self):
        self.assertTrue(self.a.online_state()["capabilities"].get("rematch"))
        self.a.online_action("rematch")
        self.a.online_poll()
        self.client.rematch.assert_called_once_with("fake-match", True, keep=False)
        self.assertEqual(len(self.a.starts), 1)
        self.assertEqual(self.a.online_state()["message"], "@online.rematch_wait")
        self.found_next()
        self.assertEqual(self.a.online_state()["phase"], "starting")
        self.assertEqual(len(self.a.starts), 1)
        self.client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match", path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertEqual(len(self.a.starts), 2)
        self.assertEqual(len(self.a.stops), 1)
        self.assertEqual(self.a._online_match_id, "next-match")
        self.assertFalse(self.client.closed.is_set())

    def test_unsolicited_rematch_cannot_replace_result_or_start_game(self):
        self.found_next()
        self.client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        self.assertEqual(self.a._online_match_id, "fake-match")
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.assertEqual(len(self.a.starts), 1)

    def test_unrelated_rematch_cannot_consume_authorization_for_current_result(self):
        self.a.online_action("rematch")
        self.a.online_poll()
        self.client.events.put(dict(t="match_found", match="unrelated-match", origin="rematch", ready_check=False,
                                    rematch_of="other-result"))
        self.a.online_poll()
        self.assertEqual(self.a._online_match_id, "fake-match")
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.assertEqual(len(self.a.starts), 1)
        self.found_next()
        self.assertEqual(self.a._online_match_id, "next-match")
        self.assertEqual(self.a.online_state()["phase"], "starting")

    def test_offer_and_expiry_belong_to_current_result_and_revoke_authorization(self):
        self.client.events.put(dict(t="rematch", match="other-match", state="offered"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.result_confirmed")
        self.client.events.put(dict(t="rematch", match="fake-match", state="offered"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.rematch_offer")
        self.a.online_action("rematch")
        self.a.online_poll()
        self.client.events.put(dict(t="rematch", match="fake-match", state="expired"))
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["capabilities"].get("rematch"))
        self.found_next()
        self.assertEqual(self.a._online_match_id, "fake-match")
        self.assertEqual(len(self.a.starts), 1)

    def test_return_to_lobby_declines_offer_and_revokes_pending_rematch(self):
        self.a.online_action("rematch")
        self.a.online_poll()
        self.a.online_action("return_lobby")
        self.a.online_poll()
        self.client.rematch.assert_any_call("fake-match", False, keep=False)
        self.client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(len(self.a.starts), 1)
        self.assertFalse(self.a.online_state()["capabilities"].get("rematch"))
        self.assertFalse(self.client.closed.is_set())

    def test_request_error_keeps_result_and_cannot_authorize_new_game(self):
        self.client.rematch.side_effect = RuntimeError("@online.refused")
        self.a.online_action("rematch")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.assertEqual(self.a.online_state()["message"], "@online.refused")
        self.found_next()
        self.assertEqual(self.a._online_match_id, "fake-match")
        self.assertEqual(len(self.a.starts), 1)

    def test_authoritative_next_match_survives_lost_rematch_acknowledgement(self):
        submit = self.a._online_submit

        def delayed_reply(action, work):
            if action == "t4_rematch":
                self.a._online_busy = True
                work()
            else:
                submit(action, work)

        self.a._online_submit = delayed_reply
        self.a.online_action("rematch")
        self.found_next()
        self.client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        self.assertEqual(self.a._online_match_id, "next-match")
        self.assertEqual(len(self.a.starts), 1)
        self.assertIsNotNone(self.a._online_pending_start)
        self.a._online_results.put((self.a._online_generation, "t4_rematch", None, RuntimeError("lost reply")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(len(self.a.starts), 2)
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertTrue(self.a._online_authorized)

    def test_expired_decline_error_keeps_returned_lobby_session(self):
        self.client.rematch.side_effect = RuntimeError("@online.refused")
        self.a.online_action("return_lobby")
        self.a.online_poll()
        self.client.rematch.assert_called_once_with("fake-match", False, keep=False)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.logged_in")
        self.assertIs(self.a._online_client, self.client)
        self.assertFalse(self.client.closed.is_set())


if __name__ == "__main__":
    unittest.main()
