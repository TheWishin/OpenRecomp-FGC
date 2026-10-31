"""Second social audit: inert clients only, without files, sockets or game processes."""
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5_challenges as challenges
from openrecomp.adapters import t5_community as community
from openrecomp.adapters import t5_profiles as profiles
from openrecomp.adapters import t5_spectating as spectating
from openrecomp.adapters import t5_tournaments as tournaments


class Owner:
    def __init__(self):
        self._online_client = SimpleNamespace()
        self._online_generation = 1
        self._online_phase = "logged_in"
        self._online_busy = False
        self._online_fields = dict(online_room_name="Test", online_room_password="")
        self._online_players = []
        self._online_message = ""
        self._online_account = True
        self._online_game_check = mock.Mock(return_value="")
        self._online_submit = mock.Mock()
        self.s = {}

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("@online.cancelled")

    def queued(self):
        return self._online_submit.call_args.args[1]


class CommunitySafetyTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client
        self.client.private_rooms_ok = lambda: True
        self.client.my_room = dict(id="room", owner_id="me")
        self.client.me = dict(id="me")
        self.client.room_line = mock.Mock()
        self.client.create_room = mock.Mock()

    def test_back_in_line_checks_for_running_game_before_reserving_turn(self):
        self.owner._online_game_check.return_value = "@online.game_running"
        community.action(self.owner, "community_back_in_line", self.client)
        with self.assertRaisesRegex(RuntimeError, "game_running"):
            self.owner.queued()()
        self.client.room_line.assert_not_called()

    def test_logout_during_game_check_cancels_room_creation(self):
        def close():
            self.owner._online_generation += 1
            return ""
        self.owner._online_game_check.side_effect = close
        community.action(self.owner, "community_create", self.client)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.owner.queued()()
        self.client.create_room.assert_not_called()

    def test_same_session_match_during_game_check_cancels_room_creation(self):
        def matched():
            self.owner._online_phase = "matched"
            return ""
        self.owner._online_game_check.side_effect = matched
        community.action(self.owner, "community_create", self.client)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.owner.queued()()
        self.client.create_room.assert_not_called()

    def test_malformed_nested_room_metadata_does_not_break_snapshot(self):
        for field, value in (("welcome", dict(room_limits="bad")),
                             ("players", [dict(id=[]), "bad"]),
                             ("my_room", dict(id="room", players={}, line={}, guesses="bad",
                                              tables=[dict(id="table", set="bad", players=[{}]), "bad"]))):
            with self.subTest(field=field):
                self.setUp()
                setattr(self.client, field, value)
                snapshot = community.state(self.owner)
                self.assertEqual(snapshot["community"]["room"]["members"], [])
                self.client.create_room.assert_not_called()


class TournamentSafetyTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client
        self.client.welcome = dict(features=["tournaments"], caps=["tournaments"])
        self.client.tournaments = True
        self.client.tour_list = mock.Mock()
        self.client.tour_get = mock.Mock()
        self.client.tour_accept = mock.Mock()
        self.client.tour_join = mock.Mock()
        self.client.tour_admin = mock.Mock()
        tournaments.init(self.owner)
        self.data = self.owner._online_tours
        self.data.update(selected="cup", selected_set="one", detail=dict(
            id="cup", state="running", can_manage=True, rev=1,
            bracket=dict(sets=[dict(id="one", p=["One", "Two"])])))

    def call(self):
        tournaments.event(self.owner, dict(t="tour_call", tournament=dict(id="cup"),
            set=dict(id="one"), deadline=60))
        tournaments.action(self.owner, "tour_accept:cup:one", self.client)
        return self.owner.queued()

    def test_expired_call_is_rechecked_in_worker(self):
        worker = self.call()
        self.data["call"]["expires"] = time.monotonic() - 1
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker()
        self.client.tour_accept.assert_not_called()

    def test_ended_call_is_rechecked_in_worker(self):
        worker = self.call()
        tournaments.event(self.owner, dict(t="tour_call_end", tournament="cup", set="one"))
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker()
        self.client.tour_accept.assert_not_called()

    def test_game_start_after_pad_press_refuses_tournament_acceptance(self):
        worker = self.call()
        self.owner._online_game_check.return_value = "@online.game_running"
        with self.assertRaisesRegex(RuntimeError, "game_running"):
            worker()
        self.client.tour_accept.assert_not_called()

    def test_same_session_match_cancels_queued_tournament_acceptance(self):
        worker = self.call()
        self.owner._online_phase = "matched"
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker()
        self.client.tour_accept.assert_not_called()

    def test_call_ending_during_game_check_cancels_tournament_acceptance(self):
        worker = self.call()
        def end():
            self.data["call"] = {}
            return ""
        self.owner._online_game_check.side_effect = end
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker()
        self.client.tour_accept.assert_not_called()

    def test_stale_detail_cannot_create_a_new_organizer_confirmation(self):
        tournaments.event(self.owner, dict(t="tour_changed", id="cup", rev=2))
        tournaments.action(self.owner, "tour_cancel:cup", self.client)
        self.assertEqual(self.data["pending"], "")
        self.owner._online_submit.assert_not_called()

    def test_change_after_confirmation_cancels_queued_organizer_action(self):
        tournaments.action(self.owner, "tour_cancel:cup", self.client)
        tournaments.action(self.owner, "tour_confirm:tour_cancel:cup", self.client)
        worker = self.owner.queued()
        tournaments.event(self.owner, dict(t="tour_changed", id="cup", rev=2))
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker()
        self.client.tour_admin.assert_not_called()

    def test_non_finite_deadline_is_treated_as_expired(self):
        for deadline in (float("inf"), float("nan"), 10 ** 1000, True):
            with self.subTest(deadline=type(deadline)):
                tournaments.event(self.owner, dict(t="tour_call", tournament=dict(id="cup"),
                    set=dict(id="one"), deadline=deadline))
                self.assertEqual(tournaments.state(self.owner)["tournaments"]["call"]["seconds"], 0)

    def test_incomplete_bracket_pair_refuses_missing_winner(self):
        self.data["detail"]["bracket"]["sets"][0]["p"] = ["One"]
        tournaments.action(self.owner, "tour_win1:cup:one", self.client)
        self.assertEqual(self.data["pending"], "")
        self.owner._online_submit.assert_not_called()


class SpectatorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client
        self.client.has_spectate = lambda: True
        self.client.watch = mock.Mock()
        self.client.friend_list = dict(friends=[dict(name="Friend", watch=True)])
        self.client.rooms = []

    def test_game_start_after_pad_press_refuses_spectator_request(self):
        spectating.action(self.owner, "spec_watch_friend:Friend", self.client)
        self.owner._online_game_check.return_value = "@online.game_running"
        with self.assertRaisesRegex(RuntimeError, "game_running"):
            self.owner.queued()()
        self.client.watch.assert_not_called()

    def test_malformed_target_metadata_does_not_break_snapshot(self):
        for friends, rooms, mine in (([], [], None), (dict(friends=[None, "bad", {}]), [], None),
                                    ({}, [None, "bad"], None), ({}, [], "bad"),
                                    ({}, [dict(id="room", mode="tables", tables=[None, "bad"])], None)):
            with self.subTest(friends=friends, rooms=rooms, mine=mine):
                self.client.friend_list, self.client.rooms, self.client.my_room = friends, rooms, mine
                self.assertEqual(spectating.state(self.owner)["spectating"]["targets"], [])
                self.client.watch.assert_not_called()

    def test_match_preemption_during_game_check_does_not_send_watch(self):
        spectating.action(self.owner, "spec_watch_friend:Friend", self.client)
        def preempt():
            self.owner._spec_pending = None
            return ""
        self.owner._online_game_check.side_effect = preempt
        self.assertIsNone(self.owner.queued()())
        self.client.watch.assert_not_called()


class ProfileSafetyTests(unittest.TestCase):
    def test_oversized_server_number_is_ignored_without_crashing_profile(self):
        self.assertEqual(profiles._profile(dict(name="Peer", rating=10 ** 1000)),
                         dict(name="Peer", history=[]))


class ChallengeSafetyTests(unittest.TestCase):
    def test_same_session_match_during_game_check_cancels_outgoing_challenge(self):
        owner = Owner()
        owner._online_config = mock.Mock(return_value={})
        owner._online_players = [dict(id="peer", name="Peer")]
        client = owner._online_client
        client.send_challenge = mock.Mock()
        def matched():
            owner._online_phase = "matched"
            return ""
        owner._online_game_check.side_effect = matched
        challenges.action(owner, "challenge:peer", client)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            owner.queued()()
        client.send_challenge.assert_not_called()


if __name__ == "__main__":
    unittest.main()
