"""Community presentation and gestures use received snapshots and fake adapters only."""
import unittest
from unittest import mock

from openrecomp import nav_arcade, nav_feedback
from openrecomp.nav_lobby_chat import segments
from tools.online_shots import scene


class CommunityLobby(unittest.TestCase):
    def setUp(self):
        self.nav = scene("t5", "arcade_selected", "en")
        self.nav.dry = False

    def page(self):
        return self.nav.view()["online"]

    def test_sorts_are_visible_bounded_and_keep_own_player_first(self):
        nav = self.nav
        players = nav.game.a.snapshot["players"]
        players[0].update(name="Zed", tier=20, rating=2000)
        players[5].update(name="Amy", tier=10, rating=1800)
        state = nav.game.a.snapshot
        state["friends"] = [dict(name="Zed", status="online")]
        floor = self.page()["arcade"]
        self.assertEqual([p["id"] for p in floor["players"]][:2], ["me", "p1"])
        item = next(it for it in nav.items() if it.get("id") == "arcade_sort")
        self.assertEqual({key for key, _ in item["options"]}, {"recommended", "name", "rank", "rating", "main", "ping", "status"})
        for mode, first in (("name", "p6"), ("rank", "p1"), ("rating", "p1"), ("ping", "p6")):
            item["set"](mode)
            floor = self.page()["arcade"]
            self.assertEqual(floor["players"][0]["id"], "me")
            self.assertEqual(floor["players"][1]["id"], first)
            self.assertTrue(floor["sort"]["value"])
        item["set"]("unknown")
        self.assertTrue(self.page()["arcade"]["sort"]["value"])
        self.assertEqual(nav.game.a.calls, [])

    def test_challenge_uses_identity_and_rejects_busy_self_and_duplicate(self):
        nav = self.nav
        for target in ("me", "p2", "gone"):
            nav.challenge_player(target)
        self.assertEqual(nav.game.a.calls, [])
        nav.challenge_player("p1")
        self.assertEqual(nav.take_sound(), "confirm")
        nav.challenge_player("p1")
        self.assertIsNone(nav.take_sound())
        self.assertEqual(nav.game.a.calls.count(("online", "challenge:p1")), 1)
        nav.game.a.snapshot["busy"] = False
        nav_feedback.records(nav, nav.game.id)["challenge:p1"].update(kind="waiting")
        nav.challenge_player("p1")
        self.assertEqual(nav.game.a.calls.count(("online", "challenge:p1")), 1)

    def test_main_sort_and_table_data_keep_the_supplied_player_values(self):
        nav = self.nav
        players = nav.game.a.snapshot["players"]
        players[0].update(main="z-fighter", rating=1987)
        players[5].update(main="a-fighter", rating=1423)
        item = next(it for it in nav.items() if it.get("id") == "arcade_sort:main")
        item["run"]()
        floor = self.page()["arcade"]
        self.assertEqual(floor["players"][0]["id"], "me")
        self.assertEqual(floor["players"][1]["id"], "p6")
        supplied = next(player for player in floor["players"] if player["id"] == "p1")
        self.assertEqual(str(supplied["rating"]), "1987")
        self.assertEqual(supplied["main"], nav.game.a.fighter_label("z-fighter"))
        self.assertEqual(nav.game.a.calls, [])

    def test_missing_table_values_do_not_claim_idle_rank_rating_or_fighter(self):
        self.nav.game.a.snapshot["players"] = [dict(id="unknown", name="Unknown data")]
        player = next(p for p in self.page()["arcade"]["players"] if p["id"] == "unknown")
        self.assertEqual(player["status"], "unknown")
        self.assertEqual((player["rank"], player["rating"], player["main"]), ("\u2014", "\u2014", "\u2014"))
        self.assertEqual(player["connection"]["bars"], 0)
        self.assertEqual(self.nav.game.a.calls, [])

    def test_repeated_header_sort_reverses_peers_and_keeps_own_player_first(self):
        nav = self.nav
        def order():
            return [player["id"] for player in self.page()["arcade"]["players"]]
        def header():
            return next(it for it in nav.items() if it.get("id") == "arcade_sort:name")
        header()["run"]()
        ascending = order()
        first_header = next(h for h in self.page()["arcade"]["headers"] if h["key"] == "name")
        self.assertFalse(first_header["descending"])
        header()["run"]()
        self.assertEqual(order(), [ascending[0]] + list(reversed(ascending[1:])))
        reverse_header = next(h for h in self.page()["arcade"]["headers"] if h["key"] == "name")
        self.assertTrue(reverse_header["descending"])
        header()["run"]()
        self.assertEqual(order(), ascending)
        self.assertEqual(ascending[0], "me")
        self.assertEqual(nav.game.a.calls, [])

    def test_ranked_search_elapsed_and_cancel_come_from_the_started_action(self):
        nav = self.nav
        nav._online_action(nav.game, "search_ranked")
        nav_feedback.tick(nav, 42)
        search = self.page()["arcade"]["search"]
        self.assertTrue(search["ranked"])
        self.assertEqual(search["elapsed"], "0:42")
        self.assertEqual([button["id"] for button in search["buttons"]], ["cancel"])
        self.assertEqual(nav.game.a.calls, [("online", "search_ranked")])

    def test_cancelling_search_keeps_origin_and_disables_repeated_cancel(self):
        nav = self.nav
        nav._online_action(nav.game, "search_ranked")
        nav.game.a.snapshot["phase"] = "cancelling"
        search = self.page()["arcade"]["search"]
        self.assertTrue(search["ranked"])
        self.assertEqual(search["phase"], "cancelling")
        self.assertEqual(search["text"], "Stopping the search\u2026")
        self.assertTrue(search["buttons"][0]["disabled"])
        self.assertNotIn("window", search)
        self.assertEqual(nav.game.a.calls, [("online", "search_ranked")])

    def test_challenge_role_survives_profile_focus(self):
        nav = self.nav
        items = nav.items()
        nav.focus[nav.key()] = next(n for n, it in enumerate(items) if it.get("id") == "profile_player:p1")
        card = next(p for p in self.page()["arcade"]["players"] if p["id"] == "p1")
        primary = [b for b in card["buttons"] if b.get("semantic") == "challenge"]
        self.assertEqual(len(primary), 1)
        self.assertFalse(primary[0]["focused"])
        self.assertTrue(next(b for b in card["buttons"] if b.get("semantic") == "profile")["focused"])

    def test_chat_returns_to_safe_visible_player_when_original_player_leaves(self):
        nav = self.nav
        nav.focus_online_row(next(n for n, it in enumerate(nav.items()) if it.get("id") == "challenge:p1"))
        nav.act("x", device="xbox")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "online_chat")
        nav.game.a.snapshot["players"] = [p for p in nav.game.a.snapshot["players"] if p["id"] != "p1"]
        nav.act("x", device="xbox")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "online_status")
        self.assertEqual(nav.game.a.calls, [])

    def test_drawer_contains_shortcuts_and_returns_to_player_opener(self):
        nav = self.nav
        before = nav.items()[nav.focus_index(nav.items())]["id"]
        nav.act("play", device="xbox")
        self.assertTrue(self.page()["arcade"]["moreOpen"])
        for action in ("x", "social", "play"):
            nav.act(action, device="xbox")
            self.assertTrue(self.page()["arcade"]["moreOpen"])
            self.assertNotEqual(self.page()["focusRegion"], "chat")
        nav.act("back", device="xbox")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], before)

    def test_received_history_is_complete_and_mentions_are_plain_segments(self):
        state = self.nav.game.a.snapshot
        state["chat"] = [dict(name="Rival", text=f"line {n}") for n in range(90)]
        state["chat"].append(dict(name="Rival", text="<b>@Me</b> @MeToo & @me!"))
        chat = self.page()["chat"]
        self.assertEqual(len(chat["lines"]), 91)
        self.assertEqual(chat["mentions"], 1)
        parts = segments("<b>@Me</b> @MeToo & @me!", "Me")
        self.assertEqual([p["text"]["_literal"] for p in parts if p["mention"]], ["@Me", "@me"])
        self.assertEqual("".join(p["text"]["_literal"] for p in parts), "<b>@Me</b> @MeToo & @me!")
        self.assertTrue(chat["latest"]["index"] >= 0)

    def test_search_keeps_chat_and_cancel_without_starting_another_search(self):
        nav = self.nav
        nav.game.a.set_text_value("online_chat", "draft")
        nav.game.a.calls.clear()
        for phase in ("searching", "cancelling"):
            nav.game.a.snapshot.update(phase=phase, message="@online.searching_casual")
            page = self.page()
            self.assertEqual(page["layout"], "lobby")
            self.assertEqual(page["chat"]["compose"]["draft"], "draft")
            self.assertTrue(page["find"]["quick"]["disabled"])
            self.assertEqual(page["arcade"]["search"]["buttons"][0]["id"], "cancel")
            self.assertEqual(page["arcade"]["search"]["buttons"][0]["disabled"], phase == "cancelling")
        self.assertEqual(nav.game.a.calls, [])

    def test_chat_focus_follows_received_message_when_history_prefix_is_trimmed(self):
        nav = self.nav
        state = nav.game.a.snapshot
        state["chat"] = [dict(id=str(n), name="Rival", text=f"line {n}") for n in range(20)]
        line = self.page()["chat"]["lines"][10]
        nav.focus_online_row(line["index"])
        state["chat"] = state["chat"][5:] + [dict(id="new", name="Rival", text="new")]
        focused = next(line for line in self.page()["chat"]["lines"] if line["focused"])
        self.assertEqual(focused["text"], "line 10")
        self.assertEqual(focused["id"], line["id"])

    def test_secondary_collapsed_chat_has_only_its_visible_toggle_target(self):
        nav = self.nav
        nav.dry = True
        nav.click_chapter("rooms")
        nav._chat_set_open(nav.game, False)
        items = nav.items()
        visible = nav._visible_chat_rows(items, nav.focus_index(items))
        self.assertEqual([items[n]["id"] for n in visible], ["chat_toggle"])
        for step in (-1, 1):
            self.assertEqual(nav._online_move(items, visible[0], step), visible[0])

    def test_actual_match_phases_and_existing_actions_are_preserved(self):
        nav = self.nav
        state = nav.game.a.snapshot
        state["match"] = dict(opponent="Rival", ping=42, ping_measured=True)
        for phase, action in (("matched", "start_match"), ("starting", "cancel_match"),
                              ("playing", "stop_match"), ("result", "result_win"),
                              ("result_sent", "return_lobby")):
            state["phase"] = phase
            page = self.page()
            self.assertEqual(page["phase"], phase)
            self.assertIn(action, [row.get("id") for row in page["lines"]])
            self.assertEqual(page["connection"]["text"], "42 ms")
            if phase in ("matched", "result_sent"):
                self.assertEqual(page["primary"]["id"], action)
            metadata = page["detail"]["rows"]
            self.assertEqual(len(metadata), len([row for n, row in enumerate(metadata) if row not in metadata[:n]]))
        self.assertEqual(nav.game.a.calls, [])

    def test_failure_remains_recoverable_after_transient_receipt_expires(self):
        nav = self.nav
        row = dict(kind="pending", text="@feedback.sending", age=0, name="Rival", action="challenge:p1")
        nav_feedback.records(nav, nav.game.id)["challenge:p1"] = row
        nav_feedback.finish(nav, row, "error", "@online.failure")
        nav_feedback.tick(nav, 6)
        self.assertEqual(nav_feedback.view(nav, nav.game.id, "challenge:p1"), {})
        self.assertTrue(self.page()["arcade"]["result"]["error"])


if __name__ == "__main__":
    unittest.main()
