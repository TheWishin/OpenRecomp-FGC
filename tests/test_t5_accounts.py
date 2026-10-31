"""Account actions use inert clients only; no server or game is contacted."""
import json
import threading
import unittest
from unittest import mock

from openrecomp.adapters import t5_accounts
from openrecomp import nav_accounts


class Client:
    def __init__(self):
        self.calls = []
        self.session = "previous-local-session"
        self.rows = [dict(name="Rival", guest=False, token="never-expose", address="never-expose")]

    def connect(self):
        self.calls.append(("connect",))

    def close(self):
        self.calls.append(("close",))

    def recover(self, name, code, password):
        self.calls.append(("recover", name, code, password))
        return dict(name=name, session="never-expose")

    def change_password(self, old, new, remember=False):
        self.calls.append(("password", old, new, remember))
        self.session = "new-local-session"
        return dict(session=self.session)

    def new_recovery_codes(self, password):
        self.calls.append(("codes", password))
        return ["TEST-CODE"]

    def blocks(self):
        self.calls.append(("blocks",))
        return self.rows

    def block(self, name):
        self.calls.append(("block", name))

    def unblock(self, name):
        self.calls.append(("unblock", name))


class Owner:
    def __init__(self):
        self._online_fields = dict(online_name="Tester", online_server="local-only", online_password="")
        self._online_account = True
        self._online_client = Client()
        self._online_phase = "logged_in"
        self._online_generation = 1
        self._online_busy = False
        self._online_name = "Tester"
        self._online_name_prefill = True
        self._online_lock = threading.RLock()
        self._online_recovery_codes = []
        self._online_message = ""
        self.saved = []
        self.pending = None
        self.recovery_client = Client()
        t5_accounts.init(self)

    def _online_config(self):
        return dict(fingerprint="configured-pin")

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("@online.cancelled")

    def _online_submit(self, operation, work):
        self._online_busy = True
        self.pending = operation, work

    def finish(self):
        operation, work = self.pending
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        self._online_busy = False
        t5_accounts.completion(self, operation, value, error)

    def _online_write_session(self, *args, **kwargs):
        self.saved.append((args, kwargs))

    def _online_new_client(self, server):
        return self.recovery_client, server

    def _online_error(self, error):
        return "@online.failure"


class AccountTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))
        self.owner = Owner()

    def password(self, current="current-secret", new=" new-secret ", repeat=" new-secret "):
        self.owner._online_fields.update(online_current_password=current, online_new_password=new,
                                         online_repeat_password=repeat)

    def test_password_change_clears_fields_and_replaces_only_saved_session(self):
        self.password()
        self.assertTrue(t5_accounts.action(self.owner, "account_change_password", self.owner._online_client))
        self.assertEqual(self.owner._online_fields["online_current_password"], "")
        self.assertEqual(self.owner._online_fields["online_new_password"], "")
        self.owner.finish()
        self.assertIn(("password", "current-secret", " new-secret ", True), self.owner._online_client.calls)
        self.assertEqual(self.owner.saved, [(("local-only", "Tester", "new-local-session"),
                                             dict(expected="previous-local-session"))])
        self.assertEqual(self.owner._online_message, "@online120.password_changed")
        self.assertNotIn("secret", json.dumps(t5_accounts.state(self.owner)))
        self.assertNotIn("session", json.dumps(t5_accounts.state(self.owner)))

    def test_password_confirmation_and_length_refuse_before_request(self):
        for password, repeat in (("short", "short"), ("long-enough", "different"), ("x" * 129, "x" * 129)):
            with self.subTest(length=len(password)):
                self.password(new=password, repeat=repeat)
                self.assertTrue(t5_accounts.action(self.owner, "account_change_password", self.owner._online_client))
                self.assertIsNone(self.owner.pending)
                self.assertEqual(self.owner._online_client.calls, [])
                self.assertEqual(self.owner._online_fields["online_repeat_password"], "")

    def test_regenerated_codes_use_existing_once_only_display(self):
        self.password()
        t5_accounts.action(self.owner, "account_new_codes", self.owner._online_client)
        self.owner.finish()
        self.assertEqual(self.owner._online_recovery_codes, ["TEST-CODE"])
        self.assertNotIn("TEST-CODE", json.dumps(t5_accounts.state(self.owner)))

    def test_guest_can_block_but_cannot_change_password(self):
        self.owner._online_account = False
        self.owner._online_fields["online_block_name"] = "Rival"
        t5_accounts.action(self.owner, "account_change_password", self.owner._online_client)
        self.assertIsNone(self.owner.pending)
        t5_accounts.action(self.owner, "account_block", self.owner._online_client)
        self.owner.finish()
        self.assertIn(("block", "Rival"), self.owner._online_client.calls)
        self.assertEqual(t5_accounts.state(self.owner)["blocks"], [dict(name="Rival", guest=False)])
        self.assertNotIn("never-expose", json.dumps(t5_accounts.state(self.owner)))

    def test_unblock_requires_current_snapshot_target_and_checks_generation(self):
        t5_accounts.action(self.owner, "account_unblock:Replaced", self.owner._online_client)
        self.assertIsNone(self.owner.pending)
        self.owner._account_blocks = [dict(name="Rival", guest=False)]
        t5_accounts.action(self.owner, "account_unblock:Rival", self.owner._online_client)
        self.owner._online_generation += 1
        self.owner.finish()
        self.assertEqual(self.owner._online_client.calls, [])

    def test_recovery_is_explicit_uses_transient_client_and_closes_it(self):
        self.owner._online_client = None
        self.owner._online_phase = "offline"
        self.password()
        self.owner._online_fields["online_recovery_code"] = " TEST-CODE "
        self.assertEqual(self.owner.recovery_client.calls, [])
        self.assertTrue(t5_accounts.offline_action(self.owner, "recover_account"))
        self.assertEqual(self.owner._online_fields["online_recovery_code"], "")
        self.assertEqual(self.owner._online_phase, "connecting")
        self.owner.finish()
        self.assertEqual(self.owner.recovery_client.calls,
                         [("connect",), ("recover", "Tester", "TEST-CODE", " new-secret "), ("close",)])
        self.assertIsNone(self.owner._online_client)
        self.assertEqual(self.owner._online_phase, "offline")
        self.assertEqual(self.owner.saved, [])

    def test_cancelled_recovery_never_connects_and_closes_transient_client(self):
        self.owner._online_client = None
        self.owner._online_phase = "offline"
        self.password()
        self.owner._online_fields["online_recovery_code"] = "TEST-CODE"
        t5_accounts.offline_action(self.owner, "recover_account")
        self.owner._online_generation += 1
        self.owner.finish()
        self.assertEqual(self.owner.recovery_client.calls, [("close",)])

    def test_recovery_failure_still_closes_client(self):
        self.owner._online_client = None
        self.owner._online_phase = "offline"
        self.password()
        self.owner._online_fields["online_recovery_code"] = "TEST-CODE"
        self.owner.recovery_client.recover = mock.Mock(side_effect=RuntimeError("secret server detail"))
        t5_accounts.offline_action(self.owner, "recover_account")
        self.owner.finish()
        self.assertEqual(self.owner.recovery_client.calls, [("connect",), ("close",)])
        self.assertEqual(self.owner._online_message, "@online.failure")

    def test_logout_reset_erases_passwords_and_previous_block_list(self):
        self.password()
        self.owner._account_blocks = [dict(name="Rival", guest=False)]
        t5_accounts.reset(self.owner)
        self.assertEqual(self.owner._account_blocks, [])
        self.assertEqual(self.owner._online_fields["online_current_password"], "")


class AccountRowsTests(unittest.TestCase):
    def test_recovery_rows_hide_secrets_and_offer_controller_editing(self):
        values = dict(online_fingerprint="certificate-hash", online_recovery_code="secret-code",
                      online_new_password="secret-password", online_repeat_password="secret-password")

        class Adapter:
            def text_value(self, field):
                return values[field]

        class Game:
            a = Adapter()

        class Nav:
            def _online_text_item(self, game, field, label, hint):
                return dict(id=field, value=values[field], run=lambda: field)

        def action(iid, label, hint):
            return dict(id=iid, label=label, hint=hint, run=lambda: iid)

        rows = nav_accounts.rows(Nav(), Game(), dict(phase="offline", capabilities=dict(account_recovery=True)), action)
        self.assertIn("recover_account", [row.get("id") for row in rows])
        for row in rows:
            if row.get("id") in values:
                self.assertEqual(row["run"](), row["id"])
                self.assertNotIn("secret", str(row["value"]))


if __name__ == "__main__":
    unittest.main()
