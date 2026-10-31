"""Challenge options use inert client doubles; no network or game is reachable."""
import unittest
from unittest import mock

from openrecomp.adapters import t5_challenges as challenges
from openrecomp.adapters.t5_online import SearchRefused
from openrecomp import nav_challenges


class Client:
    def __init__(self):
        self.calls = []
        self.extended = True
        self.casual = True
        self.sets = True

    def challenge_delay_max(self, target=None):
        return 8 if self.extended and target != "legacy" else 2

    def multi_challenge_ok(self):
        return True

    def casual_ok(self):
        return self.casual

    def casual_sets_ok(self):
        return self.sets

    def auto_skip_ok(self):
        return self.casual

    def casual_stages(self):
        return ["test-stage"]

    def set_casual_prefs(self, side, stage):
        self.calls.append(("prefs", side, stage))

    def set_auto_skip_after_round(self, enabled):
        self.calls.append(("skip", enabled))

    def send_challenge(self, target, delay=None, first_to=1):
        self.calls.append(("challenge", target, delay, first_to))
        return dict(challenge="sent", delay=dict(frames=delay if delay is not None else 1, auto=delay is None),
                    token="must-not-leak")

    def cancel_challenge(self, target):
        self.calls.append(("cancel", target))


class Owner:
    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self._online_client = Client()
        self._online_generation = 1
        self._online_phase = "logged_in"
        self._online_busy = False
        self._online_players = [dict(id="peer", name="Peer"), dict(id="legacy", name="Legacy")]
        self._online_message = ""
        self.result = None
        self.saved = []
        self.problem = ""
        self.closed = False

    def _online_config(self):
        return self.cfg

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise SearchRefused("@online.cancelled")

    def _online_events(self):
        return False, False

    def online_close(self):
        self.closed = True
        self._online_generation += 1
        self._online_phase = "offline"
        challenges.reset(self)

    def _online_write_preferences(self, values):
        self.saved.append(values)

    def _online_game_check(self):
        return self.problem

    def _online_error(self, error):
        return str(error)

    def _online_submit(self, operation, work):
        self.result = operation, work

    def finish(self):
        operation, work = self.result
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        challenges.completion(self, operation, value, error)


class ChallengePreferencesTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))
        self.owner = Owner()
        challenges.init(self.owner)

    def action(self, action):
        self.assertTrue(challenges.action(self.owner, action, self.owner._online_client))
        self.owner.finish()

    def test_delay_eight_and_first_to_reach_installed_client(self):
        self.action("challenge_option:delay:8")
        self.action("challenge_option:first_to:5")
        self.action("challenge:peer")
        self.assertIn(("challenge", "peer", 8, 5), self.owner._online_client.calls)
        self.assertEqual(self.owner.saved[-1]["casual_first_to"], 5)
        self.assertEqual(self.owner.saved[-1]["challenge_delay"], "8")
        snapshot = challenges.state(self.owner)
        self.assertEqual(snapshot["open_challenges"][0]["delay"]["frames"], 8)
        self.assertNotIn("token", repr(snapshot))

    def test_legacy_peer_uses_auto_without_losing_remembered_delay(self):
        self.action("challenge_option:delay:8")
        self.action("challenge:legacy")
        self.assertIn(("challenge", "legacy", None, 1), self.owner._online_client.calls)
        self.assertEqual(challenges.state(self.owner)["challenge_preferences"]["delay"], "8")

    def test_side_stage_and_agreed_skip_apply_to_native_client(self):
        self.action("challenge_option:side:1")
        self.action("challenge_option:stage:test-stage")
        self.action("challenge_option:auto_skip:on")
        self.assertIn(("prefs", 1, "test-stage"), self.owner._online_client.calls)
        self.assertIn(("skip", True), self.owner._online_client.calls)
        self.assertTrue(self.owner.saved[-1]["auto_skip_after_round"])

    def test_pad_delay_and_first_to_cycle_do_not_resend_unrelated_native_preferences(self):
        challenges.client_created(self.owner, self.owner._online_client)
        self.owner._online_client.calls.clear()
        for frames in range(9):
            self.action("challenge_option:delay:" + str(frames))
        for first_to in (2, 3):
            self.action("challenge_option:first_to:" + str(first_to))
        self.assertEqual(self.owner._online_client.calls, [])
        self.assertEqual(self.owner._online_client.casual_first_to, 3)
        for side in (0, 1):
            self.action("challenge_option:side:" + str(side))
        self.action("challenge:peer")
        self.assertEqual(self.owner._online_client.calls,
                         [("prefs", 0, "random"), ("prefs", 1, "random"), ("challenge", "peer", 8, 3)])

    def test_unchanged_preferences_do_not_repeat_native_setters(self):
        challenges.client_created(self.owner, self.owner._online_client)
        self.owner._online_client.calls.clear()
        for choice in ("delay:auto", "first_to:1", "side:any", "stage:random", "auto_skip:off"):
            self.action("challenge_option:" + choice)
        self.assertEqual(self.owner._online_client.calls, [])

    def test_client_created_applies_preferences_before_login(self):
        owner = Owner(dict(casual_side=0, casual_stage="test-stage", casual_first_to=3, auto_skip_after_round=True))
        challenges.client_created(owner, owner._online_client)
        self.assertEqual(owner._online_client.calls, [("prefs", 0, "test-stage"), ("skip", True)])
        self.assertEqual(owner._online_client.casual_first_to, 3)

    def test_obsolete_stage_preference_falls_back_to_random(self):
        owner = Owner(dict(casual_stage="unavailable-stage"))
        challenges.client_created(owner, owner._online_client)
        self.assertIn(("prefs", None, "random"), owner._online_client.calls)

    def test_snapshot_never_sends_or_saves(self):
        for _ in range(3):
            challenges.state(self.owner)
        self.assertEqual(self.owner._online_client.calls, [])
        self.assertEqual(self.owner.saved, [])
        self.assertIsNone(self.owner.result)

    def test_invalid_unnegotiated_and_busy_choices_do_nothing(self):
        self.owner._online_client.extended = False
        self.owner._online_client.sets = False
        self.owner._online_client.casual = False
        for action in ("challenge_option:delay:8", "challenge_option:first_to:3", "challenge_option:side:0",
                       "challenge_option:stage:unknown", "challenge_option:auto_skip:on"):
            self.assertTrue(challenges.action(self.owner, action, self.owner._online_client))
            self.assertIsNone(self.owner.result)
        self.owner._online_busy = True
        challenges.action(self.owner, "challenge:peer", self.owner._online_client)
        self.assertIsNone(self.owner.result)

    def test_stale_generation_and_running_game_refuse_send(self):
        challenges.action(self.owner, "challenge:peer", self.owner._online_client)
        self.owner._online_generation += 1
        self.owner.finish()
        self.assertEqual(self.owner._online_client.calls, [])
        self.assertFalse(self.owner.closed)
        self.owner.problem = "@online.game_running"
        self.action("challenge:peer")
        self.assertEqual(self.owner._online_client.calls, [])
        self.assertFalse(self.owner.closed)

    def test_lost_send_acknowledgement_disconnects_and_invalidates_late_work(self):
        client = self.owner._online_client
        client.send_challenge = mock.Mock(side_effect=TimeoutError("lost acknowledgement"))
        self.action("challenge:peer")
        self.assertTrue(self.owner.closed)
        self.assertEqual(self.owner._online_phase, "offline")
        self.assertEqual(challenges.state(self.owner)["open_challenges"], [])
        challenges.event(self.owner, dict(t="match_found", match="late"))
        self.assertEqual(self.owner._online_phase, "offline")
        self.assertEqual(client.calls, [])

    def test_match_offer_already_confirms_request_despite_lost_acknowledgement(self):
        self.owner._online_phase = "matched"
        self.assertTrue(challenges.completion(self.owner, challenges.PREFIX + "send", None, TimeoutError()))
        self.assertFalse(self.owner.closed)

    def test_duplicate_and_unknown_targets_do_not_send(self):
        self.action("challenge:peer")
        self.owner.result = None
        challenges.action(self.owner, "challenge:peer", self.owner._online_client)
        challenges.action(self.owner, "challenge:unknown", self.owner._online_client)
        self.assertIsNone(self.owner.result)
        self.assertEqual(sum(call[0] == "challenge" for call in self.owner._online_client.calls), 1)

    def test_outgoing_cancel_and_reply_race_are_safe(self):
        self.action("challenge:peer")
        self.action("cancel_challenge:sent")
        self.assertEqual(challenges.state(self.owner)["open_challenges"], [])
        challenges.event(self.owner, dict(t="challenge_update", challenge="sent", state="accepted"))
        self.action("challenge:legacy")
        self.assertEqual(challenges.state(self.owner)["open_challenges"], [])

    def test_send_reply_after_match_offer_does_not_restore_outgoing_challenge(self):
        challenges.action(self.owner, "challenge:peer", self.owner._online_client)
        challenges.event(self.owner, dict(t="match_found", match="accepted"))
        self.owner._online_phase = "matched"
        self.owner.finish()
        self.assertEqual(challenges.state(self.owner)["open_challenges"], [])

    def test_incoming_ft_delay_and_wishes_are_allowlisted(self):
        challenges.event(self.owner, dict(t="challenged", challenge="incoming", first_to=5,
            delay=dict(frames=8, auto=False, token="secret"), wish=dict(side=1, stage="test-stage", ticket="secret")))
        info = challenges.state(self.owner)["challenge_preferences"]["incoming"]
        self.assertEqual(info, dict(id="incoming", first_to=5, delay=dict(frames=8, auto=False),
                                   wish=dict(side=1, stage="test-stage")))
        shared = []
        rows = [dict(id="accept_challenge", detail=dict(rows=shared)),
                dict(id="decline_challenge", detail=dict(rows=shared))]
        nav_challenges.enhance_rows(rows, dict(challenge=dict(id="incoming"), challenge_preferences=dict(incoming=info)))
        self.assertEqual(len(rows[0]["detail"]["rows"]), 4)
        self.assertEqual(len(rows[1]["detail"]["rows"]), 4)
        challenges.reset(self.owner)
        self.assertEqual(challenges.state(self.owner)["challenge_preferences"]["incoming"], {})

    def test_controller_cycler_dispatches_and_unsupported_rows_hide(self):
        nav = mock.Mock()
        game = object()
        state = challenges.state(self.owner)
        rows = nav_challenges.rows(nav, game, state, mock.Mock())
        delay = next(row for row in rows if row.get("id") == "challenge_delay")
        self.assertEqual(delay["options"][-1], ("8", "8"))
        delay["set"]("8")
        nav._online_action.assert_called_once_with(game, "challenge_option:delay:8")
        self.assertEqual(nav_challenges.rows(nav, game, dict(capabilities={}), mock.Mock()), [])

    def test_opponent_card_shows_effective_fallback_delay(self):
        self.action("challenge_option:delay:8")
        state = challenges.state(self.owner)
        rows = [dict(id="challenge:peer", detail=dict(rows=[])),
                dict(id="challenge:legacy", detail=dict(rows=[]))]
        nav_challenges.enhance_rows(rows, state)
        self.assertEqual(rows[0]["detail"]["rows"][0]["v"], "8")
        self.assertEqual(rows[1]["detail"]["rows"][0]["v"], "@auto")


if __name__ == "__main__":
    unittest.main()
