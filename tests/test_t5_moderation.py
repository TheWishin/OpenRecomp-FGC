"""Installed lobby moderation contracts without sockets, game data or a window."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5_moderation as feature


class Owner:
    def __init__(self):
        self._online_client = SimpleNamespace(
            me=dict(id="me", name="Local"), players=[dict(id="peer", name="Remote")],
            welcome=dict(features=["blocks"]), mute_rows=[dict(name="OldPeer", guest=True, secret="hidden")],
            chat_moderation={}, mutes_ok=lambda: True,
            mute=mock.Mock(return_value=dict(rows=[dict(name="Remote", guest=False)])),
            mutes=mock.Mock(return_value=dict(rows=[dict(name="OldPeer", guest=True)])),
            block=mock.Mock(), blocks=mock.Mock(return_value=[dict(name="Remote", guest=False)]))
        self._online_busy = False
        self._online_phase = "logged_in"
        self._online_generation = 1
        self._online_message = ""
        self._account_blocks = []
        self.operation = ""
        self.pending = None

    def _online_submit(self, operation, work):
        self.operation, self.pending = operation, work

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("@online.cancelled")

    def _online_error(self, error):
        return "@online.refused"


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client
        feature.logged_in(self.owner, self.client)

    def perform(self, action):
        self.assertTrue(feature.action(self.owner, action, self.client))
        value = self.owner.pending()
        feature.completion(self.owner, self.owner.operation, value, None)

    def test_snapshot_is_allowlisted_and_does_not_request(self):
        snapshot = feature.state(self.owner)
        self.assertEqual(snapshot["moderation"]["mutes"], [dict(name="OldPeer", guest=True)])
        self.assertTrue(snapshot["capabilities"]["mutes"])
        self.assertTrue(snapshot["capabilities"]["blocks"])
        self.assertNotIn("hidden", json.dumps(snapshot))
        self.client.mutes.assert_not_called()
        self.client.blocks.assert_not_called()

    def test_mute_maps_roster_id_to_native_name_and_accepts_only_reply(self):
        self.assertTrue(feature.action(self.owner, "moderation_mute:peer", self.client))
        self.assertEqual(feature.state(self.owner)["moderation"]["mutes"][0]["name"], "OldPeer")
        value = self.owner.pending()
        self.client.mute.assert_called_once_with("Remote", True)
        feature.completion(self.owner, self.owner.operation, value, None)
        self.assertEqual(feature.state(self.owner)["moderation"]["mutes"], [dict(name="Remote", guest=False)])

    def test_list_refresh_and_unmute_work_for_offline_muted_player(self):
        self.perform("moderation_refresh_mutes")
        self.client.mutes.assert_called_once_with()
        self.client.mute.return_value = dict(rows=[])
        self.perform("moderation_unmute:OldPeer")
        self.client.mute.assert_called_once_with("OldPeer", False)
        self.assertEqual(feature.state(self.owner)["moderation"]["mutes"], [])

    def test_block_uses_negotiated_feature_and_updates_existing_list(self):
        self.perform("moderation_block:peer")
        self.client.block.assert_called_once_with("Remote")
        self.assertEqual(self.owner._account_blocks, [dict(name="Remote", guest=False)])

    def test_absent_caps_hide_state_and_refuse_actions_without_requests(self):
        self.client.mutes_ok = lambda: False
        self.client.welcome = dict(features=[])
        snapshot = feature.state(self.owner)
        self.assertEqual(snapshot["capabilities"], dict(mutes=False, blocks=False))
        self.assertEqual(snapshot["moderation"]["mutes"], [])
        for action in ("moderation_refresh_mutes", "moderation_mute:peer", "moderation_unmute:OldPeer", "moderation_block:peer"):
            self.assertTrue(feature.action(self.owner, action, self.client))
            self.assertIsNone(self.owner.pending)

    def test_invalid_target_self_busy_and_stale_client_do_not_submit(self):
        self.client.players.append(dict(id="me", name="Local"))
        for action in ("moderation_mute:unknown", "moderation_mute:me", "moderation_unmute:unknown", "moderation_block:me"):
            feature.action(self.owner, action, self.client)
            self.assertIsNone(self.owner.pending)
        self.owner._online_busy = True
        feature.action(self.owner, "moderation_mute:peer", self.client)
        self.assertIsNone(self.owner.pending)
        self.owner._online_busy = False
        feature.action(self.owner, "moderation_mute:peer", SimpleNamespace())
        self.assertIsNone(self.owner.pending)

    def test_worker_rechecks_session_cap_phase_and_roster(self):
        changes = (
            lambda: setattr(self.owner, "_online_generation", 2),
            lambda: setattr(self.owner, "_online_phase", "offline"),
            lambda: setattr(self.client, "mutes_ok", lambda: False),
            lambda: self.client.players.clear(),
            lambda: self.client.players[0].update(name="Changed"),
        )
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                feature.action(self.owner, "moderation_mute:peer", self.client)
                change()
                with self.assertRaisesRegex(RuntimeError, "cancelled"):
                    self.owner.pending()
                self.client.mute.assert_not_called()

    def test_failure_preserves_mute_list(self):
        feature.completion(self.owner, feature.PREFIX + "mutes", None, OSError())
        self.assertEqual(self.owner._online_mutes, [dict(name="OldPeer", guest=True)])
        self.assertEqual(self.owner._online_message, "@online.refused")

    def test_known_filter_error_is_translated_without_exposing_arbitrary_server_text(self):
        event = dict(t="error", code="not_allowed", msg="Message blocked: hate terms are not allowed.")
        self.assertTrue(feature.event(self.owner, event))
        self.assertEqual(self.owner._online_message, "@online_chat.filter_blocked")
        self.assertEqual(feature.state(self.owner)["moderation"]["notice"], "@online_chat.filter_blocked")
        self.assertFalse(feature.event(self.owner, dict(t="error", code="not_allowed", msg="arbitrary text")))
        self.assertFalse(feature.event(self.owner, dict(event, code="other")))
        error = SimpleNamespace(code="not_allowed", msg="This room name is not allowed.")
        self.assertEqual(feature.refusal(self.owner, error), "@online_chat.room_name_blocked")

    def test_account_mute_notice_is_negotiated_and_deadline_is_validated(self):
        future = time.time() + 3600
        self.client.chat_moderation = dict(muted_until=future)
        feature.logged_in(self.owner, self.client)
        self.assertEqual(feature.state(self.owner)["moderation"]["notice"], "@online_chat.chat_muted")
        for deadline in (None, False, float("nan"), float("inf"), 0, time.time() - 10):
            self.assertTrue(feature.event(self.owner, dict(t="chat_moderation", muted_until=deadline)))
            self.assertEqual(feature.state(self.owner)["moderation"]["notice"], "")
        self.client.mutes_ok = lambda: False
        self.assertFalse(feature.event(self.owner, dict(t="chat_moderation", muted_until=future)))

    def test_mute_event_sanitizes_and_reset_clears_session(self):
        self.assertTrue(feature.event(self.owner, dict(t="mutes", rows=[
            dict(name="Remote", guest=True, token="private"), dict(name="remote"), None, dict(name=42)])))
        self.assertEqual(self.owner._online_mutes, [dict(name="Remote", guest=True)])
        feature.reset(self.owner)
        self.assertEqual(feature.state(self.owner)["moderation"], dict(mutes=[], notice=""))


if __name__ == "__main__":
    unittest.main()
