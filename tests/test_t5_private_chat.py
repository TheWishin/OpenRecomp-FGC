"""Private messaging uses installed-client calls and bounded session memory only."""
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5_private_chat as feature


def envelope(mid="pm1", sender="Peer", recipient="Owner", text="Hello"):
    return dict(id=mid, **{"from": dict(id=sender.lower(), name=sender, guest=True)},
                to=dict(id=recipient.lower(), name=recipient, guest=False), text=text, time=100.0,
                receipt="signed-receipt-" + mid)


class Owner:
    def __init__(self):
        self._online_client = SimpleNamespace(me=dict(id="owner", name="Owner"),
            players=[dict(id="peer-id", name="Peer"), dict(id="owner", name="Owner")],
            private_chat_ok=mock.Mock(return_value=True), is_muted=mock.Mock(return_value=False),
            private_message=mock.Mock(return_value=dict(message=envelope(sender="Owner", recipient="Peer"))),
            private_report=mock.Mock(return_value=dict(t="private_reported", lines=1)))
        self._online_fields = {}
        self._online_generation = 1
        self._online_phase = "logged_in"
        self._online_busy = False
        self._online_message = ""
        self.pending = None
        self.operation = ""
        feature.init(self)

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("stale request")

    def _online_submit(self, operation, work):
        self.operation, self.pending = operation, work

    def _online_error(self, error):
        return "@online.connection_failed"

    def action(self, action):
        return feature.action(self, action, self._online_client)

    def finish(self):
        work, self.pending = self.pending, None
        value = work()
        feature.completion(self, self.operation, value, None)
        return value


class PrivateChatTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client

    def snapshot(self):
        return feature.state(self.owner)["private_chat"]

    def receive(self, message=None):
        return feature.event(self.owner, dict(envelope() if message is None else message, t="private_message"))

    def test_incoming_unread_deduplicates_and_only_explicit_open_or_read_marks_read(self):
        self.receive()
        self.receive()
        self.assertEqual(self.snapshot()["unread"], 1)
        self.assertEqual(len(self.snapshot()["threads"][0]["messages"]), 1)
        self.owner.action("private_open:peer")
        self.assertEqual(self.snapshot()["selected"], "peer")
        self.assertEqual(self.snapshot()["unread"], 0)
        self.receive(envelope("pm2"))
        self.assertEqual(self.snapshot()["unread"], 1)
        self.owner.action("private_read")
        self.assertEqual(self.snapshot()["unread"], 0)
        self.owner.action("private_close")
        self.assertEqual(self.snapshot()["selected"], "")

    def test_roster_target_send_renders_only_server_accepted_envelope(self):
        self.owner.action("private_open:peer-id")
        self.owner._online_fields["online_private_chat"] = "hello"
        self.owner.action("private_send")
        self.assertEqual(self.snapshot()["threads"][0]["messages"], [])
        self.client.private_message.assert_not_called()
        self.owner.finish()
        self.client.private_message.assert_called_once_with("Peer", "hello")
        self.assertEqual(self.snapshot()["threads"][0]["messages"][0]["text"], "Hello")
        self.assertEqual(self.owner._online_fields["online_private_chat"], "")
        self.assertEqual(self.snapshot()["unread"], 0)

    def test_failed_send_keeps_draft_and_newer_draft_is_not_cleared_by_completion(self):
        self.owner.action("private_open:peer-id")
        self.owner._online_fields["online_private_chat"] = "first"
        self.owner.action("private_send")
        feature.completion(self.owner, self.owner.operation, None, RuntimeError("refused"))
        self.assertEqual(self.owner._online_fields["online_private_chat"], "first")
        self.owner._online_fields["online_private_chat"] = "newer"
        self.owner.finish()
        self.assertEqual(self.owner._online_fields["online_private_chat"], "newer")

    def test_read_only_public_snapshot_never_contains_receipts_or_raw_envelopes(self):
        self.receive()
        snapshot = feature.state(self.owner)
        rendered = json.dumps(snapshot)
        self.assertNotIn("receipt", rendered)
        self.assertNotIn("signed-receipt", rendered)
        self.assertNotIn('"time"', rendered)
        self.assertNotIn('"guest"', rendered)
        self.assertIsNone(self.owner.pending)
        self.client.private_message.assert_not_called()
        self.client.private_report.assert_not_called()

    def test_private_report_submits_only_explicit_original_selected_envelopes(self):
        original = envelope()
        self.receive(original)
        self.receive(envelope("pm2", text="Unselected"))
        self.owner.action("private_open:peer")
        self.owner.action("private_report")
        self.assertIsNone(self.owner.pending)
        self.owner.action("private_select:pm1")
        self.owner._online_fields["online_private_report_reason"] = "Review this line"
        self.owner.action("private_report")
        self.receive(envelope("pm3", text="Arrived after selection"))
        self.owner.finish()
        self.client.private_report.assert_called_once_with("Peer", [original], "Review this line")
        self.assertFalse(self.snapshot()["threads"][0]["messages"][0]["selected"])
        self.assertEqual(self.owner._online_fields["online_private_report_reason"], "")

    def test_report_rejects_missing_receipt_and_caps_selection_at_five(self):
        for index in range(7):
            message = envelope("pm" + str(index))
            if index == 0:
                message.pop("receipt")
            self.receive(message)
        self.owner.action("private_open:peer")
        self.owner.action("private_select:pm0")
        self.owner.action("private_report")
        self.assertIsNone(self.owner.pending)
        for index in range(1, 7):
            self.owner.action("private_select:pm" + str(index))
        self.assertEqual(len(self.owner._online_private_lines), 5)
        self.client.private_report.assert_not_called()

    def test_capability_absence_or_failure_hides_data_and_blocks_every_request(self):
        self.receive()
        for mode in (False, RuntimeError("old client")):
            self.client.private_chat_ok.side_effect = mode if isinstance(mode, Exception) else None
            self.client.private_chat_ok.return_value = False
            snapshot = feature.state(self.owner)
            self.assertFalse(snapshot["capabilities"]["private_chat"])
            self.assertEqual(snapshot["private_chat"]["threads"], [])
            for action in ("private_open:peer-id", "private_send", "private_report"):
                self.owner.action(action)
            self.assertIsNone(self.owner.pending)
        del self.client.private_chat_ok
        self.assertFalse(feature.state(self.owner)["capabilities"]["private_chat"])

    def test_stale_generation_wrong_client_busy_and_phase_refuse_requests(self):
        self.owner.action("private_open:peer-id")
        self.owner._online_fields["online_private_chat"] = "Hello"
        self.owner.action("private_send")
        self.owner._online_generation += 1
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.owner.pending()
        self.client.private_message.assert_not_called()
        self.owner.pending = None
        self.owner._online_busy = True
        self.owner.action("private_send")
        self.owner._online_busy = False
        self.owner._online_phase = "offline"
        self.owner.action("private_send")
        self.owner._online_phase = "logged_in"
        feature.action(self.owner, "private_send", object())
        self.assertIsNone(self.owner.pending)

    def test_worker_rechecks_capability_and_phase_before_sending(self):
        self.owner.action("private_open:peer-id")
        self.owner._online_fields["online_private_chat"] = "Hello"
        for change in (lambda: setattr(self.client.private_chat_ok, "return_value", False),
                       lambda: setattr(self.owner, "_online_phase", "offline")):
            self.client.private_chat_ok.return_value = True
            self.owner._online_phase = "logged_in"
            self.owner.action("private_send")
            change()
            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                self.owner.pending()
        self.client.private_message.assert_not_called()

    def test_self_unknown_targets_and_malformed_messages_are_rejected(self):
        for target in ("owner", "invented"):
            self.owner.action("private_open:" + target)
        self.assertEqual(self.snapshot()["threads"], [])
        for message in ({}, dict(envelope(), text=None), dict(envelope(), text="x" * 201),
                        dict(envelope(), to={"name": "SomeoneElse"}), dict(envelope(), id=None)):
            self.receive(message)
        self.assertEqual(self.snapshot()["threads"], [])

    def test_muted_incoming_is_hidden_unread_cleared_and_hidden_evidence_is_not_reported(self):
        self.receive()
        self.owner.action("private_open:peer")
        self.owner.action("private_select:pm1")
        self.receive(envelope("pm2"))
        self.client.is_muted.return_value = True
        feature.event(self.owner, dict(t="mutes"))
        self.receive(envelope("pm3"))
        self.assertEqual(self.snapshot()["unread"], 0)
        self.assertEqual(self.snapshot()["threads"][0]["messages"], [])
        self.owner.action("private_report")
        self.assertIsNone(self.owner.pending)
        self.client.is_muted.return_value = False
        self.assertEqual(len(self.snapshot()["threads"][0]["messages"]), 2)

    def test_threads_and_lines_bounded_active_conversation_survives_eviction(self):
        self.owner.action("private_open:peer-id")
        for index in range(40):
            self.receive(envelope("thread" + str(index), sender="Peer" + str(index)))
        snapshot = self.snapshot()
        self.assertEqual(len(snapshot["threads"]), feature.MAX_THREADS)
        self.assertIn("peer", [thread["id"] for thread in snapshot["threads"]])
        for index in range(110):
            self.receive(envelope("line" + str(index)))
        peer = next(thread for thread in self.snapshot()["threads"] if thread["id"] == "peer")
        self.assertEqual(len(peer["messages"]), feature.MAX_LINES)
        self.assertEqual(peer["unread"], feature.MAX_LINES)

    def test_switch_does_not_send_previous_peers_draft_and_close_erases_session(self):
        self.receive()
        self.receive(envelope("pm2", sender="Other"))
        self.owner.action("private_open:peer")
        self.owner._online_fields["online_private_chat"] = "for Peer"
        self.owner._online_fields["online_private_report_reason"] = "reason"
        self.owner.action("private_open:other")
        self.assertEqual(self.owner._online_fields["online_private_chat"], "")
        self.owner._online_fields["online_private_chat"] = "unsent"
        feature.close(self.owner)
        self.assertEqual(self.snapshot()["threads"], [])
        self.assertEqual(self.snapshot()["unread"], 0)
        self.assertEqual(self.owner._online_fields["online_private_chat"], "")
        self.assertEqual(self.owner._online_fields["online_private_report_reason"], "")

    def test_evicted_selected_lines_do_not_reserve_report_selection_slots(self):
        for index in range(5):
            self.receive(envelope("selected" + str(index)))
        self.owner.action("private_open:peer")
        for index in range(5):
            self.owner.action("private_select:selected" + str(index))
        for index in range(100):
            self.receive(envelope("new" + str(index)))
        self.assertEqual(self.owner._online_private_lines, set())
        self.owner.action("private_select:new99")
        self.assertEqual(self.owner._online_private_lines, {"new99"})


if __name__ == "__main__":
    unittest.main()
