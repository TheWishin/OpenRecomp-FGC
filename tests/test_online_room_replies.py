"""Room replies retain member metadata without authorizing a game start."""
import json
import os
import tempfile
import unittest
from unittest import mock

from test_social_online import Social


class RoomReplies(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.env = mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.probe = mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False)
        self.probe.start()
        self.addCleanup(self.probe.stop)
        self.a = Social(self.directory.name)
        self.addCleanup(self.a.online_close)
        self.action("login_guest")
        self.client = self.a.clients[-1]

    def action(self, action):
        self.a.online_action(action)
        self.a.online_poll()

    def test_tuple_room_reply_uses_only_the_public_member_snapshot(self):
        room = dict(id="mine", name="Private room", lock="code", password="fake-native-room-secret")
        self.client.room_code = "ABCD-EFGH-JKLM"
        self.client.create_room = mock.Mock(return_value=(room, "fake-room-reply-secret"))
        self.action("create_code_room")
        state = self.a.online_state()
        self.assertEqual(state["room"]["id"], "mine")
        self.assertEqual(state["room"]["lock"], "code")
        self.assertEqual(state["room"]["code"], "ABCD-EFGH-JKLM")
        self.assertNotIn("password", state["room"])
        self.assertNotIn("fake-native-room-secret", json.dumps(state))
        self.assertNotIn("fake-room-reply-secret", json.dumps(state))

    def test_match_before_join_reply_keeps_member_room_and_invite_code(self):
        code = "ABCD-EFGH-JKLM"
        message = self.a.online_state()["message"]
        self.a.set_text_value("online_room_code", code)

        def join(**kwargs):
            self.client.room_code = kwargs["code"]
            self.client.events.put(dict(t="match_found"))
            return dict(id="joined", lock="code", password="fake-native-room-secret")

        self.client.join_room = join
        self.action("join_room_code")
        state = self.a.online_state()
        self.assertEqual(state["phase"], "matched")
        self.assertEqual(state["message"], message)
        self.assertEqual(state["room"]["id"], "joined")
        self.assertEqual(state["room"]["code"], code)
        self.assertNotIn("password", state["room"])
        self.assertNotIn("fake-native-room-secret", json.dumps(state))

    def test_room_and_tournament_drafts_survive_a_pending_lobby_reply(self):
        calls = list(self.client.calls)
        self.a._online_busy = True
        for tid in ("online_room_name", "online_room_password", "online_room_code",
                    "online_tour_name", "online_tour_clock", "online_tour_dq"):
            with self.subTest(tid=tid):
                self.a.set_text_value(tid, " draft text ")
                self.assertEqual(self.a.text_value(tid), " draft text ")
        for tid in ("online_name", "online_password", "online_server", "online_chat", "online_friend_name"):
            with self.subTest(tid=tid):
                previous = self.a.text_value(tid)
                self.a.set_text_value(tid, "replacement")
                self.assertEqual(self.a.text_value(tid), previous)
        self.assertEqual(self.client.calls, calls)

    def test_empty_join_acknowledgement_does_not_erase_the_native_room_event(self):
        self.a.set_text_value("online_room_code", "ABCD-EFGH-JKLM")

        def join(**kwargs):
            self.client.room_code = kwargs["code"]
            self.client.events.put(dict(t="room", room=dict(id="joined", lock="code")))
            self.client.events.put(dict(t="match_found"))

        self.client.join_room = join
        self.action("join_room_code")
        state = self.a.online_state()
        self.assertEqual(state["phase"], "matched")
        self.assertEqual(state["room"]["id"], "joined")

    def test_room_drafts_remain_locked_during_login(self):
        self.a._online_phase = "connecting"
        self.a._online_busy = True
        self.a.set_text_value("online_room_password", "replacement")
        self.assertEqual(self.a.text_value("online_room_password"), "")


if __name__ == "__main__":
    unittest.main()
