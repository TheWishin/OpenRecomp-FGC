"""The shared adapter and controller view keep chat state local to one session."""
import json
import os
import tempfile
import unittest
from unittest import mock

from openrecomp.nav import Game, Nav
from test_online_adapter import Client
from test_t5_features import FeatureSubject


class ChatClient(Client):
    def __init__(self):
        super().__init__()
        self.welcome = dict(caps=["mutes", "private_chat"], features=["mutes", "private_chat", "blocks"])
        self.me = dict(id="me", name="Tester", guest=True)
        self.players = [dict(id="other", name="Rival", guest=True)]
        self.mute_rows = []

    def private_chat_ok(self):
        return "private_chat" in self.welcome["caps"] and "private_chat" in self.welcome["features"]

    def mutes_ok(self):
        return "mutes" in self.welcome["caps"] and "mutes" in self.welcome["features"]

    def is_muted(self, name):
        return any(row["name"].casefold() == name.casefold() for row in self.mute_rows)

    def block(self, name):
        self.calls.append(("block", name))

    def unblock(self, name):
        self.calls.append(("unblock", name))

    def blocks(self):
        self.calls.append(("blocks",))
        return []

    def private_report(self, name, lines, reason=""):
        self.calls.append(("private_report", name, lines, reason))
        return dict(t="private_reported", id="test-report", lines=len(lines))


class ChatIntegrationContractTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))
        directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=directory))
        self.adapter = FeatureSubject(directory)
        self.adapter.m.update(accent="#112233", sections=["online"])
        self.adapter._online_init()
        self.client = ChatClient()
        self.adapter._online_client = self.client
        self.adapter._online_phase = "logged_in"
        self.adapter._online_name = "Tester"
        self.adapter._online_players = [dict(id="other", name="Rival")]
        self.addCleanup(self.adapter.online_close)

    def receive(self, mid="message"):
        self.client.events.put(dict(t="private_message", id=mid,
            **{"from": dict(id="other", name="Rival", guest=True),
               "to": dict(id="me", name="Tester", guest=True)},
            text="A local test message", time=100, receipt="test-only-signed-receipt"))
        self.adapter.online_poll()

    def test_event_read_and_logout_pass_through_shared_adapter(self):
        self.receive()
        state = self.adapter.online_state()
        self.assertEqual(state["private_chat"]["unread"], 1)
        self.assertNotIn("receipt", json.dumps(state))
        self.assertNotIn("test-only-signed-receipt", json.dumps(state))
        self.adapter.online_action("private_open:other")
        self.assertEqual(self.adapter.online_state()["private_chat"]["selected"], "rival")
        self.assertEqual(self.adapter.online_state()["private_chat"]["unread"], 0)
        self.receive("next-message")
        self.assertEqual(self.adapter.online_state()["private_chat"]["unread"], 1)
        self.adapter.online_action("private_read")
        self.assertEqual(self.adapter.online_state()["private_chat"]["unread"], 0)
        self.adapter.set_text_value("online_private_chat", "unfinished draft")
        self.adapter.set_text_value("online_private_report_reason", "unfinished reason")
        self.adapter.online_close()
        self.assertEqual(self.adapter.online_state()["private_chat"]["threads"], [])
        self.assertEqual(self.adapter.text_value("online_private_chat"), "")
        self.assertEqual(self.adapter.text_value("online_private_report_reason"), "")

    def test_dry_controller_feature_actions_and_keyboard_do_not_write(self):
        self.receive()
        self.adapter.online_action("private_open:other")
        nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        nav.screen = "hub"
        nav.sec[self.adapter.m["id"]] = "online"
        nav.dry = True
        original = self.adapter.online_state()
        with mock.patch.object(self.adapter, "online_action") as action, \
                mock.patch.object(self.adapter, "set_text_value") as write:
            rows = nav.items()
            chat_rows = [row for row in rows if row.get("id", "").startswith(("private_", "moderation_"))]
            self.assertTrue(chat_rows)
            for row in chat_rows:
                if row.get("run"):
                    row["run"]()
            composer = next(row for row in rows if row.get("id") == "online_private_chat")
            composer["run"]()
            nav.type_text("dry input")
            nav.act("play", device="xbox")
            action.assert_not_called()
            write.assert_not_called()
        self.assertEqual(self.adapter.online_state(), original)

    def test_method_presence_does_not_enable_server_unsupported_rows(self):
        self.client.welcome = dict(caps=[], features=[])
        nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        nav.screen = "hub"
        nav.sec[self.adapter.m["id"]] = "online"
        ids = {row.get("id", "") for row in nav.items()}
        self.assertFalse(any(iid.startswith(("private_", "moderation_", "account_unblock:")) for iid in ids))
        self.assertNotIn("account_block", ids)
        self.assertNotIn("accounts_refresh_blocks", ids)
        self.assertEqual(self.client.calls, [])


if __name__ == "__main__":
    unittest.main()
