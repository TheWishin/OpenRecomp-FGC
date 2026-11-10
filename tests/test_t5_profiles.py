"""Installed-client doubles only: profile views never connect, search or start a game."""
import copy
import json
import types
import unittest
from unittest import mock

from openrecomp.adapters import t5_profiles
from openrecomp.nav import Game, Nav
from test_online_nav import Lobby, OnlineNavigation


class RecordsClient:
    def __init__(self):
        self.calls = []
        self.result = dict(name="Player", self=True, account=True, rank="Beginner", rating=1200,
                           stats=dict(ranked=dict(games=50, wins=30, losses=18, draws=2, win_rate=60)),
                           ranked_chars=[dict(char="fixture", games=40, wins=22, losses=17, draws=1, win_rate=55.25)],
                           history=[], token="never-expose", password="never-expose")
        self.has_stats = True

    def profile(self, name=None, history=10):
        self.calls.append(("profile", name, history))
        return copy.deepcopy(self.result)

    def history(self, name=None, limit=20, offset=0):
        self.calls.append(("history", name, limit, offset))
        return [dict(opponent="Rival", time=offset + index, result="win") for index in range(limit)]

    def leaderboard(self, limit=20, offset=0):
        self.calls.append(("leaderboard", limit, offset))
        return [dict(name="Player" + str(index + offset), place=index + offset + 1, rating=1200,
                     ranked_wins=12, ranked_losses=7, casual_wins=9, casual_losses=3, session="never-expose")
                for index in range(limit)]

    def stats(self):
        self.calls.append(("stats",))
        return dict(accounts=12, players=4, matches=100, ranked=40, matches_24h=10, players_24h=3,
                    fighters=[dict(char="fixture", ranked=[40, 21, 1], casual=[60, 29, 1])], secret="never-expose")


class Owner:
    def __init__(self, client=None):
        self._online_client = client or RecordsClient()
        self._online_fields = {}
        self._online_phase = "logged_in"
        self._online_busy = False
        self._online_generation = 0
        self._online_name = "Player"
        self._online_players = [dict(id="peer", name="Rival")]
        self._online_message = ""
        self.work = None
        t5_profiles.init(self)

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("stale session")

    def _online_submit(self, operation, work):
        self.work = operation, work
        self._online_busy = True

    def finish(self):
        operation, work = self.work
        self._online_busy = False
        t5_profiles.completion(self, operation, work(), None)

    def _online_error(self, error):
        return "@online.failure"

    def action(self, request):
        result = t5_profiles.action(self, request, self._online_client)
        if self._online_busy:
            self.finish()
        return result


class ProfileAdapterTests(unittest.TestCase):
    def test_snapshot_never_requests_and_hides_unsupported_stats(self):
        owner = Owner()
        self.assertTrue(t5_profiles.state(owner)["capabilities"]["profiles"])
        self.assertEqual(owner._online_client.calls, [])
        owner._online_client.has_stats = False
        self.assertFalse(t5_profiles.state(owner)["capabilities"]["community_stats"])
        owner.action("stats_refresh")
        self.assertEqual(owner._online_client.calls, [])

    def test_profile_preserves_server_character_records_and_drops_private_fields(self):
        owner = Owner()
        owner.action("profile_self")
        state = t5_profiles.state(owner)
        self.assertEqual(owner._online_client.calls, [("profile", None, 20)])
        self.assertEqual(state["profile"]["ranked_chars"][0]["games"], 40)
        self.assertEqual(state["profile"]["ranked_chars"][0]["win_rate"], 55.25)
        self.assertEqual(state["profile"]["stats"]["ranked"]["games"], 50)
        self.assertNotIn("never-expose", json.dumps(state))
        state["profile"]["ranked_chars"][0]["wins"] = 0
        self.assertEqual(t5_profiles.state(owner)["profile"]["ranked_chars"][0]["wins"], 22)

    def test_profile_target_lookup_and_history_paging_are_explicit(self):
        owner = Owner()
        owner._online_fields["online_profile_name"] = "  Rival  "
        owner.action("profile_load")
        owner._t5_profile["history"] = [dict(opponent="Rival")] * 20
        owner.action("profile_history_next")
        self.assertEqual(owner._online_client.calls[-1], ("history", "Rival", 20, 20))
        self.assertEqual(t5_profiles.state(owner)["profile_history_offset"], 20)
        owner.action("profile_history_previous")
        self.assertEqual(owner._online_client.calls[-1], ("history", "Rival", 20, 0))
        owner.action("profile_player:peer")
        self.assertEqual(owner._online_client.calls[-1], ("profile", "Rival", 20))
        before = list(owner._online_client.calls)
        owner.action("profile_player:gone")
        owner.action("profile_board:never-loaded")
        self.assertEqual(owner._online_client.calls, before)

    def test_leaderboard_pagination_split_records_and_sort_are_safe(self):
        owner = Owner()
        owner.action("leaderboard_refresh")
        owner.action("leaderboard_next")
        state = t5_profiles.state(owner)
        self.assertEqual(state["leaderboard"]["offset"], 20)
        self.assertEqual(state["leaderboard"]["rows"][0]["casual_wins"], 9)
        self.assertNotIn("never-expose", json.dumps(state))
        owner.action("leaderboard_previous")
        self.assertEqual(owner._online_client.calls[-1], ("leaderboard", 20, 0))
        before = list(owner._online_client.calls)
        owner.action("leaderboard_sort:ranked_wins")
        owner.action("leaderboard_sort:ranked_wins")
        self.assertEqual(owner._online_client.calls, before)
        self.assertFalse(t5_profiles.state(owner)["leaderboard"]["descending"])

    def test_stats_modes_sorting_and_missing_fields_do_not_trigger_extra_requests(self):
        owner = Owner()
        owner.action("stats_refresh")
        owner.action("stats_mode:ranked")
        owner.action("stats_sort:winrate")
        stats = t5_profiles.state(owner)["community_stats"]
        self.assertEqual(stats["accounts"], 12)
        self.assertEqual(stats["fighters"][0]["ranked"], [40, 21, 1])
        self.assertEqual((stats["mode"], stats["sort"]), ("ranked", "winrate"))
        self.assertEqual(owner._online_client.calls, [("stats",)])
        self.assertNotIn("never-expose", json.dumps(stats))
        self.assertEqual(t5_profiles._profile(None), {})
        self.assertEqual(t5_profiles._stats(None), dict(fighters=[]))

    def test_stale_generation_guard_runs_before_client_request(self):
        owner = Owner()
        t5_profiles.action(owner, "profile_self", owner._online_client)
        owner._online_generation += 1
        with self.assertRaisesRegex(RuntimeError, "stale session"):
            owner.work[1]()
        self.assertEqual(owner._online_client.calls, [])

    def test_no_requests_while_busy_or_outside_lobby_and_close_clears_records(self):
        owner = Owner()
        for phase in ("offline", "connecting", "searching", "matched", "playing", "result"):
            owner._online_phase = phase
            self.assertTrue(t5_profiles.action(owner, "profile_self", owner._online_client))
            self.assertIsNone(owner.work)
        owner._online_phase = "logged_in"
        owner._online_busy = True
        self.assertTrue(t5_profiles.action(owner, "leaderboard_refresh", owner._online_client))
        self.assertIsNone(owner.work)
        owner._online_busy = False
        owner.action("profile_self")
        t5_profiles.close(owner)
        self.assertEqual(t5_profiles.state(owner)["profile"], {})
        self.assertEqual(owner._online_fields["online_profile_name"], "")

    def test_history_replay_link_uses_installed_matcher_only_for_self(self):
        owner = Owner()
        entry = object()
        owner.replay_entries = lambda: [entry]
        owner._fighter_table = lambda: [dict(key="fixture", id=3)]
        owner.rp = types.SimpleNamespace(for_history=mock.Mock(return_value=entry))
        owner._online_client.result["history"] = [dict(time=100, opponent="Rival", you_char="fixture", opp_char="fixture", score=[3, 1])]
        owner.action("profile_self")
        self.assertEqual(t5_profiles.state(owner)["profile"]["history"][0]["replay_id"], "0")
        owner.rp.for_history.assert_called_once_with([entry], 100, mine=3, theirs=3, opponent="Rival", score=[3, 1])
        owner._online_client.result.update(name="Rival", self=False)
        owner.rp.for_history.reset_mock()
        owner.action("profile_load")
        self.assertNotIn("replay_id", t5_profiles.state(owner)["profile"]["history"][0])
        owner.rp.for_history.assert_not_called()

    def test_history_status_and_reason_are_bounded_catalog_codes(self):
        owner = Owner()
        owner._online_client.result["history"] = [dict(opponent="Rival", time=100, status="forfeit", reason="crash_repeat"),
                                                  dict(opponent="Rival", time=200, status="@online.logout", reason="private-address")]
        owner.action("profile_self")
        history = t5_profiles.state(owner)["profile"]["history"]
        self.assertEqual((history[0]["status"], history[0]["reason"]), ("forfeit", "crash_repeat"))
        self.assertNotIn("status", history[1])
        self.assertNotIn("reason", history[1])

    def test_malformed_records_do_not_enter_snapshot(self):
        owner = Owner()
        owner._online_client.result.update(rating=float("nan"), ranked_chars=[None, dict(char="fixture", wins=float("inf"), games=10)])
        owner.action("profile_self")
        profile = t5_profiles.state(owner)["profile"]
        self.assertNotIn("rating", profile)
        self.assertEqual(profile["ranked_chars"], [dict(char="fixture", games=10)])


class ProfileLobby(Lobby):
    def __init__(self):
        super().__init__()
        self.texts["online_profile_name"] = ""
        self.snapshot.update(phase="logged_in", name="Player", capabilities=dict(lobby=True, profiles=True, leaderboard=True, community_stats=True),
                             players=[dict(id="peer", name="@online.logout")],
                             profile=dict(name="Player", self=True, ranked_chars=[dict(char="fixture", games=40, wins=22, losses=17, draws=1, win_rate=55.25)],
                                          history=[dict(opponent="Rival", time=123, result="win", replay_id="0")]),
                             leaderboard=dict(rows=[dict(name="@online.logout", place=1, ranked_wins=40, casual_wins=9)], sort="place", offset=20, has_next=True),
                             community_stats=dict(accounts=10, fighters=[dict(char="fixture", ranked=[40, 22, 1], casual=[60, 29, 1])], mode="all", sort="matches"))


class ProfileNavigationTests(unittest.TestCase):
    choose = OnlineNavigation.choose
    pad_key = OnlineNavigation.pad_key

    def setUp(self):
        self.a = ProfileLobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def test_profile_character_records_and_lookup_are_pad_reachable(self):
        self.choose("profile_self")
        self.choose("profile_ranked_char:fixture")
        self.assertIn("55.25 %", str(self.nav.view()["detail"]))
        self.choose("online_profile_name")
        self.pad_key("a")
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.texts["online_profile_name"], "a")
        self.choose("profile_load")
        self.choose("profile_player:peer")
        self.assertIn(("online", "profile_player:peer"), self.a.calls)

    def test_leaderboard_stats_and_history_replay_are_pad_reachable(self):
        self.choose("leaderboard_refresh")
        for iid in ("leaderboard_sort:ranked_wins", "leaderboard_next", "leaderboard_previous"):
            self.choose(iid)
            self.assertIn(("online", iid), self.a.calls)
        self.choose("profile_board:@online.logout")
        self.assertIn(("online", "profile_board:@online.logout"), self.a.calls)
        with mock.patch.object(self.nav, "_play_replay") as playback:
            self.choose("profile_history_replay:0")
        playback.assert_called_once_with(self.nav.game, "0")
        self.choose("stats_refresh")
        self.choose("stats_mode:ranked")
        self.choose("stats_sort:winrate")
        self.choose("community_fighter:fixture")
        self.assertIn("100", str(self.nav.view()["detail"]))
        # On the lobby page the pages are chapters: no Back row, the statistics stay in their chapter.
        ids = [item.get("id") for item in self.nav.items()]
        self.assertNotIn("close_profile", ids)
        # 0.1.7: Statistics opens on the Leaderboard & stats page (its rows keep origin "stats")
        self.assertEqual(self.nav.view()["online"]["chapter"], "leaderboard")
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())].get("origin"), "stats")

    def test_dry_profile_navigation_never_requests_or_plays(self):
        self.nav.dry = True
        for iid in ("profile_self", "leaderboard_refresh", "stats_refresh", "profile_self", "profile_history_replay:0"):
            self.choose(iid)
        self.assertEqual(self.a.calls, [])


if __name__ == "__main__":
    unittest.main()

