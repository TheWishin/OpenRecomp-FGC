"""Second online audit: inert clients and repository-local fixtures only."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from test_online_adapter import Servers, Subject
from test_social_online import Social


class OnlineAuditTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory))

    def subject(self, factory=Subject):
        owner = factory(self.directory)
        self.addCleanup(owner.online_close)
        return owner

    def test_blank_server_never_uses_installed_default_or_leaks_loopback_session(self):
        owner = self.subject()
        with open(owner.online_cfg_path(), "w", encoding="utf-8") as stream:
            json.dump(dict(sessions={"127.0.0.1:7781": dict(token="loopback-only")}), stream)
        servers = SimpleNamespace(load=Servers.load, resolve=Servers.resolve,
                                  default_entry=mock.Mock(return_value=SimpleNamespace(name="other-server")))
        owner._online_api["servers"] = servers
        owner.online_action("login_saved")
        owner.online_poll()
        client = owner.clients[-1]
        self.assertEqual(client.kwargs["server"], "127.0.0.1:7781")
        self.assertIn(("session", "loopback-only"), client.calls)
        servers.default_entry.assert_not_called()

    def test_explicit_server_is_still_resolved(self):
        owner = self.subject()
        owner.set_online_text_value("online_server", "named-local-fixture")
        owner.online_action("login_guest")
        owner.online_poll()
        self.assertEqual(owner.clients[-1].kwargs["server"], "named-local-fixture")

    def test_invalid_installed_invite_timer_cannot_crash_poll_or_allow_invite(self):
        for timer in (mock.Mock(side_effect=ValueError("incompatible timer")),
                      mock.Mock(return_value="later"), mock.Mock(return_value=float("nan")),
                      mock.Mock(return_value=float("-inf"))):
            with self.subTest(timer=timer):
                owner = self.subject(Social)
                owner.set_online_text_value("online_password", "fake-password")
                owner.online_action("login_account")
                client = owner.clients[-1]
                client.invite_wait = timer
                owner.online_poll()
                self.assertEqual(owner.online_state()["friends"][0]["retry"], 86400)
                owner.online_action("invite_friend:Friend")
                owner.online_poll()
                self.assertFalse(any(isinstance(call, tuple) and call[0] == "invite" for call in client.calls))
                self.assertEqual(owner.online_state()["message"], "@online.invite_wait")
                owner.online_close()


if __name__ == "__main__":
    unittest.main()
