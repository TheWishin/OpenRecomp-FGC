"""Action receipts use a fake lobby and explicit server snapshots; no external I/O."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from openrecomp import i18n, nav_feedback
from openrecomp.adapters import t5_challenges
from openrecomp.nav import Game, Nav
from test_online_adapter import Client, Subject
from test_online_nav import Lobby
from test_online_page import lobby_snapshot
from test_t5_challenges import Owner


class FeedbackLobby(Lobby):
    def __init__(self):
        super().__init__()
        self.snapshot.update(lobby_snapshot())
        self.snapshot["capabilities"].update(challenge_preferences=True, profiles=True, friends=True)
        self.snapshot["challenge_preferences"] = {}

    def online_action(self, action):
        super().online_action(action)
        if not action.startswith("search_"):
            self.snapshot["busy"] = True


class FeedbackNavigation(unittest.TestCase):
    def setUp(self):
        self.a = FeedbackLobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "online"

    def choose(self, action):
        items = self.nav.items()
        index = next(n for n, it in enumerate(items) if it.get("id") == action)
        self.nav.focus_online_row(index)
        self.nav.act("confirm", device="xbox")

    def receipt(self, action="challenge:p1"):
        return i18n.localize(nav_feedback.view(self.nav, self.nav.game.id, action), "en")

    def reply(self, **state):
        self.a.pending = dict(busy=False, **state)
        self.nav.tick(0)

    def waiting(self, seconds=None):
        self.choose("challenge:p1")
        offer = dict(id="offer-1", player="p1", name="Rival")
        if seconds is not None:
            offer["seconds"] = seconds
        self.reply(open_challenges=[offer], message="@online.challenge_sent")

    def test_selecting_is_inert_confirm_keeps_feedback_on_the_player_and_cancel_is_available(self):
        items = self.nav.items()
        index = next(n for n, it in enumerate(items) if it.get("id") == "challenge:p1")
        self.nav.focus_online_row(index)
        self.assertEqual(self.a.calls, [])
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.receipt()["kind"], "pending")
        before = list(self.a.calls)
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, before)
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "challenge:p1")
        self.reply(open_challenges=[dict(id="offer-1", player="p1", name="Rival", seconds=30)],
                   message="@online.challenge_sent")
        self.assertEqual(self.nav.view()["toast"], "Challenge sent to Rival")
        self.nav.tick(3)
        self.assertIn("0:27 remaining", self.receipt()["text"])
        row = next(r for r in self.nav.view()["online"]["body"]["lines"] if r.get("feedback"))
        self.assertIn("Y: Profile", row["actionHint"])
        cancel = next(b for b in row["buttons"] if b["label"] == "Cancel")
        self.nav.click_row(cancel["index"])
        self.reply(open_challenges=[], message="@online.challenge_cancelled")
        self.assertEqual(self.receipt()["text"], "✓ Cancelled")

    def test_server_declined_and_expired_statuses_remain_then_clear(self):
        for terminal in ("declined", "expired"):
            with self.subTest(terminal=terminal):
                self.setUp()
                self.waiting()
                self.reply(open_challenges=[], challenge_updates=[dict(id="offer-1", state=terminal)])
                self.assertEqual(self.receipt()["kind"], terminal)
                self.nav.tick(4)
                self.assertTrue(self.receipt())
                self.nav.tick(2)
                self.assertFalse(self.receipt())

    def test_legacy_waiting_uses_elapsed_time_and_never_invents_server_expiry(self):
        self.waiting()
        self.reply(open_challenges=[], outgoing_challenge=dict(id="offer-1", name="Rival"))
        self.nav.tick(61)
        self.assertEqual(self.receipt()["kind"], "waiting")
        self.assertIn("1:01 elapsed", self.receipt()["text"])
        before = list(self.a.calls)
        self.nav._online_action(self.nav.game, "challenge:p1")
        self.assertEqual(self.a.calls, before)

    def test_waiting_row_ignores_duplicate_confirm_and_named_cancel_cancels_offer(self):
        self.waiting(seconds=30)
        before = list(self.a.calls)
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, before)
        self.choose("cancel_challenge:offer-1")
        self.assertEqual(self.a.calls[-1], ("online", "cancel_challenge:offer-1"))

    def test_cancel_failure_is_shown_on_the_challenged_row(self):
        self.waiting(seconds=30)
        self.choose("cancel_challenge:offer-1")
        self.reply(message="@online.failure")
        self.assertEqual(self.receipt()["kind"], "error")

    def test_cancel_is_once_only_and_disabled_until_server_reply(self):
        for local_receipt in (True, False):
            with self.subTest(local_receipt=local_receipt):
                self.setUp()
                if local_receipt:
                    self.waiting()
                else:
                    self.a.snapshot["open_challenges"] = [dict(id="offer-1", player="p1", name="Rival")]
                action = "cancel_challenge:offer-1"
                self.nav._online_action(self.nav.game, action)
                self.nav._online_action(self.nav.game, action)
                self.assertEqual(self.a.calls.count(("online", action)), 1)
                outgoing = self.nav.view()["online"]["find"]["outgoing"]
                self.assertEqual(outgoing["status"], i18n.text("en", "feedback.cancelling"))
                self.assertTrue(outgoing["buttons"][0]["disabled"])
                self.reply(open_challenges=[], message="@online.challenge_cancelled")
                receipt = self.receipt("challenge:p1" if local_receipt else action)
                self.assertEqual(receipt["kind"], "success")

    def test_incoming_answer_guards_both_choices_by_server_identity(self):
        self.a.snapshot["challenge"] = dict(id="incoming-1", name="Rival")
        for action in ("accept_challenge", "accept_challenge", "decline_challenge"):
            self.nav._online_action(self.nav.game, action)
        answers = [call for call in self.a.calls if call[1] in ("accept_challenge", "decline_challenge")]
        self.assertEqual(answers, [("online", "accept_challenge")])
        incoming = self.nav.view()["online"]["find"]["incoming"]
        self.assertTrue(all(button["disabled"] for button in incoming["buttons"]))
        self.reply(message="@online.failure")
        incoming = self.nav.view()["online"]["find"]["incoming"]
        self.assertTrue(all(not button["disabled"] for button in incoming["buttons"]))
        self.nav._online_action(self.nav.game, "decline_challenge")
        self.assertEqual(self.a.calls[-1], ("online", "decline_challenge"))
        self.reply(challenge={}, message="@online.challenge_answered")
        self.assertEqual(self.receipt("decline_challenge")["kind"], "success")

    def test_incoming_disappearance_does_not_invent_result_and_new_identity_releases_guard(self):
        self.a.snapshot["challenge"] = dict(id="incoming-1", name="Rival")
        self.nav._online_action(self.nav.game, "accept_challenge")
        self.reply(challenge={})
        self.assertEqual(self.receipt("accept_challenge")["kind"], "pending")
        self.reply(challenge=dict(id="incoming-2", name="Another rival"))
        incoming = self.nav.view()["online"]["find"]["incoming"]
        self.assertTrue(all(not button["disabled"] for button in incoming["buttons"]))
        self.nav._online_action(self.nav.game, "accept_challenge")
        self.assertEqual(self.a.calls.count(("online", "accept_challenge")), 2)
        self.reply(phase="matched", challenge={}, match=dict(opponent="Another rival"))
        self.assertEqual(self.receipt("accept_challenge")["kind"], "success")

    def test_room_friend_invite_results_and_failure_reason_are_in_place(self):
        for action, result in (("create_room", "@online.room_joined"), ("join_room:r1", "@online.room_joined"),
                               ("add_friend", "@online.friend_requested"), ("invite_friend:Rival", "@online.invite_sent")):
            with self.subTest(action=action):
                self.nav._online_action(self.nav.game, action)
                self.assertEqual(self.receipt(action)["kind"], "pending")
                self.reply(message=result)
                self.assertEqual(self.receipt(action)["kind"], "success")
        self.nav._online_action(self.nav.game, "create_password_room")
        self.reply(message="@online.room_password_required")
        self.assertEqual(self.receipt("create_password_room")["kind"], "error")
        self.assertIn("password", self.receipt("create_password_room")["text"].lower())
        self.nav._online_action(self.nav.game, "join_room_code")
        self.reply(message=i18n.message("online_ui.ranked_account"))
        self.assertEqual(self.receipt("join_room_code")["kind"], "error")

    def test_search_is_visible_and_exception_text_is_never_copied(self):
        self.nav._online_action(self.nav.game, "search_ranked")
        self.assertEqual(self.receipt("search_ranked")["kind"], "waiting")
        with mock.patch.object(self.a, "online_action", side_effect=RuntimeError("private-secret")):
            self.nav._online_action(self.nav.game, "join_room:r1")
        self.assertEqual(self.receipt("join_room:r1")["kind"], "error")
        self.assertNotIn("private-secret", str(self.nav.view()))

    def test_one_search_receipt_tracks_cancelling_found_and_start_then_error_without_reissue(self):
        self.nav._online_action(self.nav.game, "search_casual")
        calls = list(self.a.calls)
        for phase in ("cancelling", "matched", "starting", "playing", "result"):
            self.reply(phase=phase, message="@online.status")
            receipt = self.receipt("search_casual")
            self.assertEqual(receipt["phase"], phase)
            self.assertEqual(receipt["kind"], "waiting")
        self.reply(phase="error", message="@online.failure")
        self.assertEqual(self.receipt("search_casual")["kind"], "error")
        self.assertEqual(self.a.calls, calls)

    def test_ready_and_decline_are_identity_guarded_through_late_match_replies(self):
        self.a.snapshot.update(phase="matched", busy=False, match=dict(id="same-match", opponent="Rival"))
        self.nav._online_action(self.nav.game, "start_match")
        self.nav._online_action(self.nav.game, "start_match")
        self.assertEqual(self.a.calls.count(("online", "start_match")), 1)
        self.reply(phase="starting")
        self.nav._online_action(self.nav.game, "cancel_match")
        self.nav._online_action(self.nav.game, "cancel_match")
        self.assertEqual(self.a.calls.count(("online", "cancel_match")), 1)
        self.reply(phase="logged_in", match={}, message="@online.cancelled")
        self.nav.tick(10)
        self.reply(phase="matched", match=dict(id="same-match", opponent="Rival"))
        self.nav._online_action(self.nav.game, "start_match")
        self.nav._online_action(self.nav.game, "cancel_match")
        self.assertEqual(self.a.calls.count(("online", "start_match")), 1)
        self.assertEqual(self.a.calls.count(("online", "cancel_match")), 1)

    def test_hidden_online_focus_and_notifications_remain_stable_on_other_pages(self):
        self.nav.screen = "start"
        self.nav.focus[self.nav.game.id + ":online"] = 7
        self.reply(phase="matched", match=dict(id="offer", opponent="Rival"))
        self.assertEqual(self.nav.focus[self.nav.game.id + ":online"], 7)
        self.assertEqual(self.nav.take_sound(), "notify")
        self.reply(phase="matched", match=dict(id="offer", opponent="Rival", ping=30))
        self.assertIsNone(self.nav.take_sound())

    def test_y_opens_selected_profile_and_quick_access_still_opens_elsewhere(self):
        items = self.nav.items()
        index = next(n for n, it in enumerate(items) if it.get("id") == "challenge:p1")
        self.nav.focus_online_row(index)
        self.nav.act("social", device="xbox")
        self.assertIn(("online", "profile_player:p1"), self.a.calls)
        self.assertIsNone(self.nav.overlay)
        self.nav.focus[self.nav.key()] = 0
        self.nav.act("social", device="xbox")
        self.assertEqual(self.nav.overlay, "drawer")


class AdapterFeedback(unittest.TestCase):
    def test_only_explicit_server_duration_becomes_countdown_and_private_fields_stay_out(self):
        owner = Owner()
        t5_challenges.init(owner)
        value = dict(player="peer", name="Peer", first_to=1,
                     reply=dict(challenge="offer", seconds=30, token="private"))
        with mock.patch.object(t5_challenges.time, "monotonic", return_value=10):
            t5_challenges.completion(owner, "feature_challenges:send", value, None)
        with mock.patch.object(t5_challenges.time, "monotonic", return_value=13):
            offer = t5_challenges.state(owner)["open_challenges"][0]
        self.assertEqual(offer["seconds"], 27)
        self.assertNotIn("private", str(offer))
        self.assertNotIn("_expires", offer)
        self.assertEqual(t5_challenges.offer_deadline(dict(challenge="legacy")), {})

    def test_terminal_events_are_allowlisted_bounded_and_reset_on_close(self):
        root = Path(__file__).resolve().parents[1] / "build" / "tmp-home"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            owner = Subject(directory)
            owner.online_lobby = True
            owner._online_init()
            owner._online_phase = "logged_in"
            owner._online_client = Client()
            owner._online_client.events.put(dict(t="challenge_update", challenge="offer", state="declined", token="private"))
            owner.online_poll()
            self.assertEqual(owner.online_state()["challenge_updates"], [dict(id="offer", state="declined")])
            self.assertNotIn("private", str(owner.online_state()["challenge_updates"]))
            for number in range(20):
                owner._online_client.events.put(dict(t="challenge_update", challenge=str(number), state="expired", token="private"))
            owner._online_client.events.put(dict(t="challenge_update", challenge="unknown", state="private"))
            owner.online_poll()
            updates = owner.online_state()["challenge_updates"]
            self.assertEqual(len(updates), 16)
            self.assertEqual(updates[-1], dict(id="19", state="expired"))
            self.assertTrue(all(set(row) == {"id", "state"} for row in updates))
            owner.online_close()
            self.assertEqual(owner.online_state()["challenge_updates"], [])


if __name__ == "__main__":
    unittest.main()
