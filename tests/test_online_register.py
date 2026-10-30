"""Registration uses the installed client's account creation contract."""
import json
import os
import tempfile
import unittest
from unittest import mock

from test_online_adapter import Client, Subject


class RegisterClient(Client):
    def register(self, name, password, remember=False):
        self.calls.append(("register", name, password, remember))
        self.recovery_codes = ["FAKE-CODE-ONE", "FAKE-CODE-TWO"]
        return dict(name=name, guest=False)


class RegisterSubject(Subject):
    def make_client(self, **kwargs):
        client = RegisterClient(**kwargs)
        self.clients.append(client)
        return client


class OnlineRegisterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        patch = mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name)
        patch.start()
        self.addCleanup(patch.stop)
        self.a = RegisterSubject(self.directory.name)
        self.addCleanup(self.a.online_close)

    def test_registration_creates_account_and_saves_session_without_password(self):
        self.a.set_text_value("online_name", "NewAccount")
        self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_register")
        self.assertEqual(self.a.online_state()["phase"], "connecting")
        self.assertEqual(self.a.text_value("online_password"), "")
        self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["phase"], "logged_in")
        self.assertTrue(state["account"])
        self.assertEqual(state["recovery_codes"], ["FAKE-CODE-ONE", "FAKE-CODE-TWO"])
        self.assertEqual(self.a.clients[0].calls,
                         ["connect", ("register", "NewAccount", "fake-password", True)])
        with open(self.a.online_cfg_path(), encoding="utf-8") as stream:
            cfg = json.load(stream)
        self.assertEqual(cfg["sessions"]["127.0.0.1:7781"]["token"], "fake-remembered-session")
        self.assertNotIn("fake-password", json.dumps(cfg))
        self.assertNotIn("FAKE-CODE", json.dumps(cfg))

    def register(self):
        self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_register")
        self.a.online_poll()

    def test_recovery_codes_are_transient_and_clear_after_acknowledgment(self):
        self.register()
        self.assertIsNone(self.a.clients[0].recovery_codes)
        state = self.a.online_state()
        state["recovery_codes"].clear()
        self.assertEqual(len(self.a.online_state()["recovery_codes"]), 2)
        self.a.online_action("acknowledge_recovery")
        self.assertEqual(self.a.online_state()["recovery_codes"], [])
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["recovery_codes"], [])

    def test_recovery_codes_clear_on_logout(self):
        self.register()
        self.a.online_action("logout")
        self.assertEqual(self.a.online_state()["recovery_codes"], [])

    def test_native_recovery_codes_are_bounded_strings(self):
        self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_register")
        self.a.clients[0].recovery_codes = [None, "x" * 100] + ["code"] * 50
        self.a.online_poll()
        codes = self.a.online_state()["recovery_codes"]
        self.assertEqual(len(codes), 31)
        self.assertEqual(codes[0], "x" * 64)
        self.assertTrue(all(isinstance(code, str) for code in codes))

    def test_registration_is_only_offered_for_t5_client(self):
        self.assertTrue(self.a.online_state()["capabilities"]["registration"])
        self.a.online_package = "t4lobby"
        self.assertFalse(self.a.online_state()["capabilities"].get("registration", False))
        self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_register")
        self.assertEqual(self.a.clients, [])

    def test_registration_requires_password_before_connecting(self):
        self.a.online_action("login_register")
        self.assertEqual(self.a.clients, [])
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertEqual(self.a.online_state()["message"], "@online.password_required")


if __name__ == "__main__":
    unittest.main()
