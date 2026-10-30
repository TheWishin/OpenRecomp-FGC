"""Session interoperability never connects a real client or runs a game."""
import json
import os
import tempfile
import unittest
from unittest import mock

from test_social_online import Social


class SessionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name).start()
        mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False).start()
        self.a = Social(self.directory.name)
        self.addCleanup(self.a.online_close)

    def action(self, action):
        self.a.online_action(action)
        self.a.online_poll()

    def test_kick_closes_once_and_poll_never_reconnects_or_relogs(self):
        self.a.set_text_value("online_password", "fake-password")
        self.action("login_account")
        client = self.a.clients[-1]
        client.events.put(dict(t="kicked", reason="logged in from another place"))
        self.a.online_poll()
        self.assertTrue(client.closed.wait(1))
        for _ in range(5):
            self.a.online_state()
            self.a.online_poll()
        self.assertEqual(len(self.a.clients), 1)
        self.assertEqual(client.calls.count("connect"), 1)
        self.assertEqual(self.a.online_state()["phase"], "kicked")
        self.assertEqual(self.a.online_state()["message"], "@online.kicked")
        self.assertEqual(client.kwargs["reconnect"], 0)

    def test_repeated_login_while_connected_does_not_create_second_session(self):
        self.action("login_guest")
        self.action("login_guest")
        self.action("login_saved")
        self.assertEqual(len(self.a.clients), 1)

    def test_stale_native_token_failure_cannot_remove_newer_native_session(self):
        path = self.a.online_cfg_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(dict(native_setting="keep", sessions={"local": dict(name="Native", token="new-fake-token")}), stream)
        self.a._online_write_session("local", None, None, expected="old-fake-token")
        with open(path, encoding="utf-8") as stream:
            cfg = json.load(stream)
        self.assertEqual(cfg["native_setting"], "keep")
        self.assertEqual(cfg["sessions"]["local"]["token"], "new-fake-token")

    def test_logout_clears_social_secrets_and_pending_actions(self):
        self.action("login_guest")
        self.a.set_text_value("online_room_password", "fake-room-password")
        self.a.set_text_value("online_room_code", "FAKE-CODE")
        self.a._online_invites = [dict(id="incoming", name="Friend")]
        self.action("logout")
        self.assertEqual(self.a.text_value("online_room_password"), "")
        self.assertEqual(self.a.text_value("online_room_code"), "")
        self.assertEqual(self.a.online_state()["invites"], [])
        self.assertEqual(self.a.online_state()["friends"], [])


if __name__ == "__main__":
    unittest.main()
