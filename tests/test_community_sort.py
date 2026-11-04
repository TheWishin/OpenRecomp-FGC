"""Presentation ordering never mutates an adapter or invokes a request."""
import copy
import unittest

from openrecomp import nav_list_sort
from tools.online_shots import SyntheticOnline
from openrecomp.nav import Game, Nav


class CommunityOrdering(unittest.TestCase):
    def make(self):
        adapter = SyntheticOnline("t5")
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec[nav.game.id] = "online"
        return adapter, nav

    def ids(self, nav, prefix):
        return [row["id"] for row in nav.items() if str(row.get("id") or "").startswith(prefix)]

    def test_rooms_default_free_seats_then_ping_and_user_sort(self):
        adapter, nav = self.make()
        adapter.snapshot["rooms"] = [dict(id="full", name="A", status="open", size=2, players=2, ping=1),
                                     dict(id="slow", name="Z", status="open", size=4, players=1, ping=80),
                                     dict(id="fast", name="M", status="open", size=4, players=1, ping=20)]
        before = copy.deepcopy(adapter.snapshot)
        self.assertEqual(self.ids(nav, "join_room:"), ["join_room:fast", "join_room:slow", "join_room:full"])
        sort = next(row for row in nav.items() if row.get("id") == "community_sort:rooms")
        sort["set"]("name")
        self.assertEqual(self.ids(nav, "join_room:"), ["join_room:full", "join_room:fast", "join_room:slow"])
        self.assertEqual(adapter.snapshot, before)
        self.assertEqual(adapter.calls, [])

    def test_friends_and_tournaments_sort_complete_action_groups(self):
        adapter, nav = self.make()
        adapter.snapshot["friends"] = [dict(name="A", status="offline", invite=True),
                                       dict(name="Z", status="in_match", invite=True),
                                       dict(name="M", status="online", invite=True)]
        self.assertEqual(self.ids(nav, "remove_friend:"), ["remove_friend:M", "remove_friend:Z", "remove_friend:A"])
        adapter.snapshot["tournaments"]["rows"] = [dict(id="end", name="A", state="finished"),
                                                  dict(id="run", name="Z", state="running"),
                                                  dict(id="open", name="M", state="signup")]
        self.assertEqual(self.ids(nav, "tour_select:"), ["tour_select:open", "tour_select:run", "tour_select:end"])
        self.assertEqual(adapter.calls, [])

    def test_unknown_metrics_remain_after_known_without_mutating_values(self):
        rows = [dict(name="Unknown"), dict(name="Known", ping=50, tier=2)]
        self.assertEqual([row["name"] for row in sorted(rows, key=lambda r: nav_list_sort.key("spectating", "rank", r))],
                         ["Known", "Unknown"])
        self.assertNotIn("tier", rows[0])

    def test_collapsed_room_advanced_has_no_hidden_nav_targets_and_restores_opener(self):
        adapter, nav = self.make()
        adapter.snapshot["capabilities"]["community"] = True
        nav.click_chapter("rooms")
        ids = self.ids(nav, "community_option:")
        self.assertEqual(ids, ["community_option:access"])
        toggle = next(row for row in nav.items() if row.get("id") == "room_advanced")
        toggle["run"]()
        self.assertGreater(len(self.ids(nav, "community_option:")), 1)
        self.assertTrue(nav.close_room_advanced())
        rows = nav.items()
        self.assertEqual(rows[nav.focus_index(rows)]["id"], "room_advanced")
        self.assertEqual(adapter.calls, [])

    def test_settings_help_is_selected_only_and_values_are_informational(self):
        _, nav = self.make()
        nav.sec[nav.game.id] = "settings"
        page = nav.view()["settingsPage"]
        hints = [row for row in page["tabLines"] if row.get("hint")]
        self.assertLessEqual(len(hints), 1)
        self.assertTrue(all(row["focused"] for row in hints))
        self.assertTrue(page["optionLabel"])

    def test_replays_newest_first_and_local_opponent_filter_keep_ids(self):
        _, nav = self.make()
        adapter = nav.game.a
        adapter.replays = lambda: [dict(id="old", label="Old", date="03.01.2026, 10:00", group="Local", opponent="A", result="", netcode="", when="10:00"),
                                   dict(id="new", label="New", date="04.01.2026, 10:00", group="Local", opponent="B", result="", netcode="", when="10:00")]
        nav.sec[nav.game.id] = "replays"
        self.assertEqual([row["replay"] for row in nav.items() if row.get("replay")], ["new", "old"])
        next(row for row in nav.items() if row.get("id") == "replay_sort")["set"]("oldest")
        self.assertEqual([row["replay"] for row in nav.items() if row.get("replay")], ["old", "new"])
        next(row for row in nav.items() if row.get("id") == "replay_opponent")["set"]("B")
        self.assertEqual([row["replay"] for row in nav.items() if row.get("replay")], ["new"])
        self.assertEqual(adapter.calls, [])

    def test_populated_replay_filters_never_present_the_empty_library_hint(self):
        _, nav = self.make()
        adapter = nav.game.a
        adapter.replays = lambda: [dict(id="saved", label="Saved", date="2026-01-03", group="Local",
                                       opponent="A", result="", netcode="", when="10:00")]
        nav.sec[nav.game.id] = "replays"
        populated = nav.items()
        controls = [row for row in populated if row.get("kind") == "cycler"]
        self.assertEqual(len(controls), 2)
        self.assertTrue(any(row.get("replay") == "saved" for row in populated))
        adapter.replays = lambda: []
        empty = nav.items()[0]
        for control in controls:
            self.assertNotEqual(control["hint"], empty["hint"])
            self.assertNotEqual(control["detail"]["lead"], empty["hint"])
        self.assertEqual(adapter.calls, [])

    def test_joined_room_projects_actual_queue_order_and_preserves_every_pad_action(self):
        from tools.online_shots import scene
        from pad_step import pad_step
        nav = scene("t5", "community_room", "en")
        room = nav.game.a.snapshot["community"]["room"]
        room["line"] = ["p6", "p1", "me"]
        page = nav.view()["online"]["rooms"]["joined"]
        self.assertEqual(page["name"], room["name"])
        self.assertEqual([(row["label"], row["value"]) for row in page["queue"]],
                         [("Player 6", "1"), ("Rival", "2"), ("Me", "3")])
        self.assertTrue(page["mode"] and page["rotation"])
        represented = {row["index"] for row in page["queue"] + page["members"] + page["tables"] + page["controls"]}
        represented.add(page["primary"]["index"])
        targets = {n for n, row in enumerate(nav.items()) if row.get("region") == "rooms" and row.get("kind") != "heading"}
        self.assertEqual(represented, targets)
        for target in targets:
            for _ in range(len(nav.items()) * 3):
                if nav.focus_index(nav.items()) == target:
                    break
                pad_step(nav, target)
            else:
                self.fail("Pad could not reach joined-room action " + str(target))
        self.assertEqual(nav.game.a.calls, [])


if __name__ == "__main__":
    unittest.main()
