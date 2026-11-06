"""T5DR Online pages (0.1.5): rank emblems everywhere a rank shows, the player list ordered like T5DR's own launcher,
the friends page in groups with requests on top, and "provisional" only for the first 3 ranked matches."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n, nav_arcade
from openrecomp.adapters.t5dr import T5DR, RANK_BADGES
from openrecomp.nav_common import placing, provisional, ranked_count
from tools.online_shots import scene


class Provisional(unittest.TestCase):
    def test_only_the_first_three_ranked_matches_count(self):
        self.assertTrue(provisional(dict(provisional=True, placement=[0, 5])))
        self.assertTrue(provisional(dict(provisional=True, placement=[2, 5])))
        self.assertFalse(provisional(dict(provisional=True, placement=[3, 5])))
        self.assertFalse(provisional(dict(provisional=True, placement=[4, 5])))

    def test_a_profile_or_board_row_uses_its_ranked_count(self):
        self.assertTrue(provisional(dict(provisional=True, ranked_games=2)))
        self.assertFalse(provisional(dict(provisional=True, ranked_games=3)))
        self.assertTrue(provisional(dict(provisional=True, ranked_wins=1, ranked_losses=1)))
        self.assertFalse(provisional(dict(provisional=True, ranked_wins=2, ranked_losses=1)))

    def test_the_servers_flag_alone_is_not_enough(self):
        # the server's flag follows rating uncertainty and stays on long after the first matches
        self.assertIsNone(ranked_count(dict(provisional=True)))
        self.assertFalse(provisional(dict(provisional=True)))
        self.assertFalse(provisional(dict(provisional=True, ranked_games=40)))
        self.assertFalse(provisional({}))

    def test_placement_is_shown_for_the_first_three_only(self):
        self.assertEqual(placing(dict(placement=[1, 5])), (1, 5))
        self.assertIsNone(placing(dict(placement=[3, 5])))
        self.assertIsNone(placing({}))

    def test_the_lobby_label_follows_the_rule(self):
        nav = scene("t5", "lobby", "en")
        label = nav._rank_label
        self.assertIn("placement", i18n.localize(label(dict(name="a", rank="Beginner", placement=[1, 5])), "en").lower())
        self.assertEqual(i18n.localize(label(dict(name="a", rank="Beginner", placement=[4, 5], provisional=True)), "en"),
                         "Beginner")
        self.assertEqual(i18n.localize(label(dict(name="a", rank="2nd Dan", provisional=True)), "en"), "2nd Dan")

    def test_the_profile_shows_provisional_only_inside_the_first_three(self):
        from openrecomp.nav_profiles import _profile_rows
        nav = scene("t5", "lobby", "en")
        for games, shown in ((2, True), (3, False), (30, False)):
            profile = dict(name="X", rank="Beginner", provisional=True, ranked_games=games, tier=0)
            rows = _profile_rows(nav, nav.game, dict(profile=profile), None)
            values = [r["v"] for r in rows[0]["detail"]["rows"]]
            self.assertEqual("@online.provisional" in values, shown, games)


class Emblems(unittest.TestCase):
    def adapter(self, out_dir, built=True):
        a = T5DR.__new__(T5DR)
        a.m, a.problem = dict(id="t5dr"), ""
        a.s = SimpleNamespace(out_dir=out_dir)
        a.state = lambda: dict(built=built)
        return a

    def test_a_cached_plate_is_used_and_remembered(self):
        with tempfile.TemporaryDirectory() as out:
            path = os.path.join(out, "cache", "ranks", "rank_13.png")
            os.makedirs(os.path.dirname(path))
            open(path, "wb").close()
            a = self.adapter(out)
            self.assertEqual(a.rank_plate(13), path)
            os.remove(path)
            self.assertEqual(a.rank_plate(13), path, "asked for every row on every redraw: remembered")

    def test_without_plates_the_drawn_badge_stands_in_and_the_game_s_own_are_read_once(self):
        started = []
        with tempfile.TemporaryDirectory() as out:
            a = self.adapter(out)
            with mock.patch("openrecomp.adapters.t5dr.threading.Thread") as thread:
                thread.side_effect = lambda **kw: SimpleNamespace(start=lambda: started.append(kw["target"]))
                first = a.rank_plate(13)
                second = a.rank_plate(14)
        self.assertEqual(first, os.path.join(RANK_BADGES, "t4_rank_13.svg"))
        self.assertTrue(os.path.isfile(first))
        self.assertTrue(second.endswith("t4_rank_14.svg"))
        self.assertEqual(len(started), 1, "read once, not once per row")

    def test_an_unbuilt_game_reads_nothing(self):
        with tempfile.TemporaryDirectory() as out:
            a = self.adapter(out, built=False)
            with mock.patch("openrecomp.adapters.t5dr.threading.Thread") as thread:
                self.assertTrue(a.rank_plate(13).endswith(".svg"))
                thread.assert_not_called()

    def test_bad_tiers_have_no_plate(self):
        a = self.adapter(tempfile.gettempdir())
        for tier in (None, True, -1, 64, "13"):
            self.assertEqual(a.rank_plate(tier), "")

    def test_the_profile_rank_row_carries_the_emblem(self):
        from openrecomp.nav_profiles import _profile_rows
        nav = scene("t5", "lobby", "en")
        nav.game.a.rank_plate = lambda tier: "C:/plates/rank_%02d.png" % tier
        rows = _profile_rows(nav, nav.game, dict(profile=dict(name="X", rank="2nd Dan", tier=14)), None)
        rank = next(r for r in rows[0]["detail"]["rows"] if r["k"] == "@online.rank")
        self.assertTrue(rank["plate"].endswith("rank_14.png"))


class Ordering(unittest.TestCase):
    def order(self, players, mode=None):
        nav = scene("t5", "lobby", "en")
        if mode:
            nav_arcade.sort_by(nav, nav.game, mode)
        pairs = [(p, False) for p in players]
        return [p["name"] for p, _ in nav_arcade.player_order(nav, nav.game, {}, pairs)]

    def test_available_first_then_in_match_then_rating_then_name(self):
        players = [dict(name="Busy", status="playing", rating=1900), dict(name="Low", status="idle", rating=1200),
                   dict(name="High", status="idle", rating=1700), dict(name="Guest", status="idle", guest=True, rating=1500),
                   dict(name="Searcher", status="queue", rating=1800), dict(name="Zoe", status="idle", rating=1700),
                   dict(name="Talker", status="match", rating=1000)]
        self.assertEqual(self.order(players), ["High", "Zoe", "Low", "Guest", "Searcher", "Talker", "Busy"])

    def test_the_order_does_not_move_with_ping_so_the_list_stays_still_while_it_refreshes(self):
        a = [dict(name="A", status="idle", rating=1500, ping=30), dict(name="B", status="idle", rating=1500, ping=90)]
        b = [dict(name="A", status="idle", rating=1500, ping=120), dict(name="B", status="idle", rating=1500, ping=10)]
        self.assertEqual(self.order(a), self.order(b))

    def test_me_stays_on_top(self):
        nav = scene("t5", "lobby", "en")
        pairs = [(dict(name="Z", status="idle", rating=1), True), (dict(name="A", status="idle", rating=3000), False)]
        self.assertEqual([p["name"] for p, _ in nav_arcade.player_order(nav, nav.game, {}, pairs)], ["Z", "A"])


class Friends(unittest.TestCase):
    def labels(self, **state):
        nav = scene("t5", "friends", "en")
        nav.game.a.snapshot.update(state)
        return [(it.get("kind"), it.get("id") or it.get("label")) for it in nav.items()]

    def test_requests_come_first_then_online_in_match_offline_each_by_name(self):
        rows = self.labels(friends=[dict(name="Zed", status="offline"), dict(name="Rival", status="online", invite=True),
                                    dict(name="Busy", status="in_match"), dict(name="Anna", status="offline"),
                                    dict(name="Amy", status="online", invite=True)],
                           friend_incoming=[dict(name="Newcomer")], invites=[dict(id="i1", name="Rival")])
        ids = [r[1] for r in rows]
        request = ids.index("@online.friend_requests")
        online = ids.index("@online.friend_online")
        self.assertLess(request, online)
        self.assertLess(ids.index("accept_invite:i1"), online)
        self.assertLess(ids.index("accept_friend:Newcomer"), online)
        self.assertLess(online, ids.index("@online.friend_in_match"))
        self.assertLess(ids.index("@online.friend_in_match"), ids.index("@online.friend_offline"))
        self.assertLess(ids.index("invite_friend:Amy"), ids.index("invite_friend:Rival"))
        self.assertLess(ids.index("remove_friend:Anna"), ids.index("remove_friend:Zed"))
        self.assertLess(ids.index("remove_friend:Rival"), ids.index("remove_friend:Busy"))
        self.assertLess(ids.index("remove_friend:Busy"), ids.index("remove_friend:Anna"))

    def test_no_requests_no_heading_and_no_friends_says_so(self):
        rows = self.labels(friends=[], friend_incoming=[], friend_outgoing=[], invites=[])
        ids = [r[1] for r in rows]
        self.assertNotIn("@online.friend_requests", ids)
        self.assertIn("no_friends", ids)

    def test_the_sort_the_player_chose_is_not_split_into_groups(self):
        nav = scene("t5", "friends", "en")
        nav.game.a.snapshot["friends"] = [dict(name="Zed", status="offline"), dict(name="Amy", status="online", invite=True)]
        nav.__dict__.setdefault("community_sort", {}).setdefault(nav.game.id, {})["friends"] = "name"
        ids = [it.get("id") or it.get("label") for it in nav.items()]
        self.assertNotIn("@online.friend_online", ids)
        self.assertNotIn("@online.friend_offline", ids)

    def test_the_status_sort_puts_in_match_between_online_and_offline(self):
        from openrecomp import nav_list_sort
        rows = [dict(name="a", status="offline"), dict(name="b", status="in_match"), dict(name="c", status="online")]
        self.assertEqual([r["name"] for r in sorted(rows, key=lambda r: nav_list_sort.key("friends", "status", r))],
                         ["c", "b", "a"])


if __name__ == "__main__":
    unittest.main()
