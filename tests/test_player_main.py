"""Public character-usage fixtures only; no game client or art is opened."""
from datetime import datetime
from types import SimpleNamespace
import unittest

from openrecomp.player_main import choose_main, local_main
from openrecomp.adapters import t5_profiles
from openrecomp.adapters.t5_online import Online
from openrecomp.adapters.t4_online import T4Online
from openrecomp.adapters.t5dr import T5DR


class PlayerMainTests(unittest.TestCase):
    def test_games_then_wins_then_recency_choose_main(self):
        rows = [dict(char="a", games=12, wins=10, last_played=100),
                dict(char="b", games=13, wins=0, last_played=1)]
        self.assertEqual(choose_main(dict(char_usage=rows)), "b")
        rows[0]["games"] = 13
        self.assertEqual(choose_main(dict(char_usage=rows)), "a")
        rows[1].update(wins=10, last_played=101)
        self.assertEqual(choose_main(dict(char_usage=rows)), "b")
        self.assertEqual(choose_main(dict(char_usage=list(reversed(rows)))), "b")

    def test_all_modes_beat_ranked_subset_and_stale_summary(self):
        source = dict(main="stale", chars=[dict(char="casual", games=30, wins=10),
                                           dict(char="ranked", games=20, wins=20)],
                      ranked_chars=[dict(char="ranked", games=20, wins=20)])
        self.assertEqual(choose_main(source), "casual")
        self.assertEqual(choose_main(dict(ranked_chars=[dict(char="a", games=2, wins=2)],
                                         casual_chars=[dict(char="b", games=3, wins=0)])), "b")

    def test_usage_maps_and_mode_counts(self):
        self.assertEqual(choose_main(dict(char_usage={"a": dict(games=2, wins=2), "b": [3, 1, 10]})), "b")
        self.assertEqual(choose_main(dict(chars=[dict(char="a", ranked=[3, 1, 0], casual=[3, 2, 0]),
                                                 dict(char="b", ranked=[5, 5, 0], casual=[0, 0, 0])])), "a")

    def test_iso_recency_and_deterministic_complete_tie(self):
        rows = [dict(char="b", games=1, wins=1, last_played_at="2026-11-03T21:00:00Z"),
                dict(char="a", games=1, wins=1, last_played_at="2026-11-04T21:00:00Z")]
        self.assertEqual(choose_main(dict(chars=rows)), "a")
        rows[0]["last_played_at"] = rows[1]["last_played_at"]
        self.assertEqual(choose_main(dict(chars=rows)), choose_main(dict(chars=list(reversed(rows)))))

    def test_missing_zero_and_invalid_usage_stay_silhouettes(self):
        for source in ({}, dict(fighter="selected"), dict(main="random"), dict(main="control\n"),
                       dict(main="stale", chars=[]), dict(chars=[dict(char="a", games=0, wins=4)]),
                       dict(chars=[dict(char="a", games=float("nan")), dict(char="b", games=10 ** 1000)])):
            with self.subTest(source=source):
                self.assertEqual(choose_main(source), "")
        self.assertEqual(choose_main(dict(main="server-summary")), "server-summary")
        self.assertEqual(choose_main(dict(main="stale", record=[0, 0, 0])), "")
        self.assertEqual(choose_main(dict(main="stale", games=0)), "")

    def test_local_history_is_only_a_fallback_with_wins_and_recent_ties(self):
        history = [dict(you_char="b", result="win", time=30), dict(you_char="a", result="loss", time=40)]
        self.assertEqual(choose_main({}, history), "b")
        history[1]["result"] = "win"
        self.assertEqual(choose_main({}, history), "a")
        self.assertEqual(choose_main(dict(main="server"), history), "server")
        self.assertEqual(choose_main({}, [dict(you_char="a", status="void")] * 5), "")

    def test_other_profile_never_supplies_local_main(self):
        owner = SimpleNamespace(_online_name="Me", _t5_profile=dict(name="Rival", self=True,
                                chars=[dict(char="rival", games=30)], history=[dict(you_char="rival")]))
        self.assertEqual(local_main(owner), "")
        owner._t5_profile.update(name="me", main="server", chars=[dict(char="a", games=1)])
        self.assertEqual(local_main(owner), "server")

    def test_local_replay_slot_wins_and_recency(self):
        owner = SimpleNamespace(_fighter_table=lambda: [dict(id=1, key="a"), dict(id=2, key="b")],
            replay_entries=lambda: [SimpleNamespace(p1=1, p2=2, slot=0, complete=True, won=True, when=datetime(2026, 11, 3)),
                                    SimpleNamespace(p1=1, p2=2, slot=1, complete=True, won=True, when=datetime(2026, 11, 4))])
        self.assertEqual(local_main(owner), "b")

    def test_local_main_id_prefers_server_usage_over_current_pick(self):
        owner = SimpleNamespace(_online_me=dict(main="b"),
                                _fighter_table=lambda: [dict(id=1, key="a"), dict(id=2, key="b")],
                                chosen_fighter=lambda: "a")
        self.assertEqual(T5DR.main_id(owner), 2)

    def test_complete_local_history_precedes_profile_history_page(self):
        owner = SimpleNamespace(_online_name="Me", _t5_profile=dict(name="Me", self=True,
            history=[dict(you_char="b", result="win")] * 20),
            _fighter_table=lambda: [dict(id=1, key="a"), dict(id=2, key="b")],
            replay_entries=lambda: [SimpleNamespace(p1=1, p2=2, slot=0, complete=True, won=True, when=None)] * 100
                + [SimpleNamespace(p1=1, p2=2, slot=1, complete=True, won=True, when=None)] * 20)
        self.assertEqual(local_main(owner), "a")
        owner.replay_entries = lambda: []
        self.assertEqual(local_main(owner), "b")


class PublicUsageAdapterTests(unittest.TestCase):
    def setUp(self):
        self.owner = Online()
        self.owner._online_client = None
        self.owner._online_players = []
        self.usage = [dict(char="a", games=9, wins=9), dict(char="b", games=10, wins=0)]

    def test_player_and_match_views_normalize_usage_and_keep_picks_separate(self):
        row = dict(id="peer", name="Rival", main="stale", char_usage=self.usage)
        self.assertEqual(self.owner._online_player(row)["main"], "b")
        match = self.owner._online_match_view(dict(opponent=dict(row, fighter="picked-b"),
                                                  you=dict(fighter="picked-a")))
        self.assertEqual(match["opponent_info"]["main"], "b")
        self.assertEqual((match["you_char"], match["opp_char"]), ("picked-a", "picked-b"))
        self.assertNotIn("char_usage", str(match))
        self.assertEqual(self.owner._online_player(dict(id="old", name="Old"))["main"], "")

    def test_profile_and_leaderboard_use_their_own_usage(self):
        source = dict(name="Rival", main="stale", chars=self.usage, token="private")
        self.assertEqual(t5_profiles._profile(source)["main"], "b")
        self.assertEqual(t5_profiles._board([source])[0]["main"], "b")
        self.assertNotIn("private", str(t5_profiles._profile(source)))
        self.assertEqual(t5_profiles._profile(dict(name="Old"))["main"], "")

    def test_known_match_fighter_pair_respects_the_local_slot(self):
        for slot in (0, 1):
            match = self.owner._online_match_view(dict(slot=slot, fight=dict(chars=["a", "b"])))
            self.assertEqual(match["you_char"], ("a", "b")[slot])
            self.assertEqual(match["opp_char"], ("a", "b")[1 - slot])
        for slot in (None, True, 4):
            match = self.owner._online_match_view(dict(slot=slot, fight=dict(chars=["a", "b"])))
            self.assertNotIn("you_char", match)
        self.assertNotIn("opp_char", self.owner._online_match_view(dict(opp_char="random")))

    def test_t4_uses_the_same_per_player_choice(self):
        owner = T4Online()
        owner._online_client = None
        self.assertEqual(owner._online_player(dict(id="peer", name="Rival", char_usage=self.usage))["main"], "b")
        self.assertEqual(owner._online_player(dict(id="old", name="Old"))["main"], "")

    def test_friend_usage_is_preserved_without_exposing_counts(self):
        self.owner._online_social_cap = lambda capability: True
        self.owner._online_invite_wait = lambda name, retry: retry
        self.owner._online_friends_snapshot(dict(friends=[dict(name="Rival", char_usage=self.usage)],
            incoming=[dict(name="New", char_usage=self.usage)]))
        self.assertEqual(self.owner._online_friends[0]["main"], "b")
        self.assertEqual(self.owner._online_friend_incoming[0]["main"], "b")
        self.assertNotIn("char_usage", str(self.owner._online_friends))


if __name__ == "__main__":
    unittest.main()
