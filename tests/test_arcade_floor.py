"""Arcade presentation uses existing adapter actions and controller input only."""
from pathlib import Path
import unittest
from unittest import mock
from types import SimpleNamespace

from openrecomp import nav_arcade
from tools.online_shots import scene


class ArcadeFloor(unittest.TestCase):
    def floor(self, nav):
        return nav.view()["online"]["arcade"]

    def focus(self, nav, iid):
        items = nav.items()
        nav.focus[nav.key()] = next(n for n, item in enumerate(items) if item.get("id") == iid)

    def focused(self, nav):
        items = nav.items()
        return items[nav.focus_index(items)]["id"]

    def test_both_games_start_with_collapsed_drawers_and_own_highlighted_card(self):
        for game in ("t5", "t4"):
            nav = scene(game, "arcade_floor", "en")
            floor = self.floor(nav)
            self.assertFalse(floor["optionsOpen"])
            self.assertFalse(floor["moreOpen"])
            self.assertEqual(sum(p["own"] for p in floor["players"]), 1)
            self.assertEqual(floor["players"][0]["name"], "Me")
            self.assertTrue(all(len(p["buttons"]) <= 3 for p in floor["players"]))
            self.assertEqual(nav.game.a.calls, [])

    def test_runtime_portraits_and_rank_plates_use_only_the_adapter_interface(self):
        nav = scene("t5", "arcade_selected", "en")
        nav.game.a.snapshot["players"][0].update(main="sample", tier=3)
        with mock.patch.object(nav.game.a, "fighter_image", return_value=Path("build/sample-portrait.png").resolve()) as portrait, \
                mock.patch.object(nav.game.a, "rank_plate", return_value=Path("build/sample-plate.png").resolve()) as plate:
            player = next(p for p in self.floor(nav)["players"] if p["id"] == "p1")
            self.assertTrue(player["face"].endswith("sample-portrait.png"))
            self.assertTrue(player["plate"].endswith("sample-plate.png"))
            portrait.assert_any_call("sample")
            plate.assert_any_call(3)

    def test_grid_dpad_moves_across_columns_and_down_rows(self):
        nav = scene("t5", "arcade_selected", "en")
        floor = self.floor(nav)
        own, first, second, third = floor["players"][:4]
        self.focus(nav, "online_status")
        nav.act("right", device="xbox")
        self.assertEqual(self.focused(nav), "challenge:p1")
        nav.act("right", device="xbox")
        self.assertEqual(self.focused(nav), "challenge:p2")
        nav.act("left", device="xbox")
        nav.act("down", device="xbox")
        self.assertEqual(self.focused(nav), "challenge:p4")
        nav.act("up", device="xbox")
        self.assertEqual(self.focused(nav), "challenge:p1")

    def test_options_toggle_is_local_reachable_and_back_closes_it(self):
        nav = scene("t5", "arcade_floor", "en")
        self.focus(nav, "search_ranked")
        nav.act("right", device="xbox")
        self.assertEqual(self.focused(nav), "arcade_options")
        nav.act("confirm", device="xbox")
        self.assertTrue(self.floor(nav)["optionsOpen"])
        nav.act("down", device="xbox")
        self.assertIn(self.focused(nav), [b["id"] for b in self.floor(nav)["options"]])
        nav.act("back", device="xbox")
        self.assertFalse(self.floor(nav)["optionsOpen"])
        self.assertEqual(nav.overlay, None)
        self.assertEqual(nav.game.a.calls, [])

    def test_cabinets_only_reuse_advertised_watch_actions_and_actual_scores(self):
        nav = scene("t5", "arcade_cabinet", "en")
        floor = self.floor(nav)
        cabinet = floor["cabinets"][0]
        self.assertEqual(cabinet["score"], "2 : 1")
        self.assertEqual(len(cabinet["players"]), 2)
        items = nav.items()
        proxy = items[cabinet["watch"]["index"]]
        original = next(it for it in items if it.get("id") == "spec_watch_room:r1")
        self.assertIs(proxy["run"], original["run"])
        self.assertEqual(proxy["region"], "lobby")
        nav.game.a.snapshot["spectating"]["targets"] = []
        self.assertEqual(self.floor(nav)["cabinets"], [])
        self.assertEqual(nav.game.a.calls, [])

    def test_y_profile_and_x_watch_reuse_existing_rows(self):
        nav = scene("t5", "arcade_selected", "en")
        self.focus(nav, "challenge:p1")
        with mock.patch.object(nav, "_activate") as activate:
            nav.act("social", device="xbox")
        self.assertEqual(activate.call_args.args[0]["id"], "profile_player:p1")
        self.assertIsNone(nav.overlay)
        nav.game.a.snapshot["spectating"]["targets"].append(
            dict(kind="friend", id="spec_watch_friend:p1", name="Rival"))
        self.focus(nav, "challenge:p1")
        with mock.patch.object(nav, "_activate") as activate:
            nav.act("x", device="xbox")
        self.assertEqual(activate.call_args.args[0]["id"], "arcade_watch:spec_watch_friend:p1")

    def test_hidden_options_never_receive_grid_focus_while_collapsed(self):
        nav = scene("t5", "arcade_floor", "en")
        items = nav.items()
        rows, floor = nav_arcade.routes(nav, items, nav.focus_index(items))
        visible = {n for row in rows for n in row}
        self.assertFalse(visible.intersection(b["index"] for b in floor["options"]))

    def test_drawer_sounds_and_pointer_card_selection_use_existing_cues(self):
        nav = scene("t5", "arcade_floor", "en")
        self.focus(nav, "arcade_options")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.take_sound(), "open")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.take_sound(), "close")
        nav.act("confirm", device="xbox")
        nav.take_sound()
        nav.act("back", device="xbox")
        self.assertEqual(nav.take_sound(), "back")
        items = nav.items()
        nav.focus_online_row(next(n for n, it in enumerate(items) if it.get("id") == "challenge:p1"))
        self.assertEqual(nav.take_sound(), "move")

    def test_help_retains_context_and_blocks_hidden_drawer_controls(self):
        nav = scene("t5", "arcade_options", "en")
        self.focus(nav, "ranked_strict")
        context = self.floor(nav)["help"]
        self.focus(nav, "arcade_help")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.floor(nav)["help"], context)
        nav.act("down", device="xbox")
        self.assertEqual(self.focused(nav), "arcade_help")
        nav.act("back", device="xbox")
        self.assertFalse(self.floor(nav)["helpOpen"])
        self.assertTrue(self.floor(nav)["optionsOpen"])

    def test_more_destinations_are_pad_rows_and_drawers_are_exclusive(self):
        nav = scene("t5", "arcade_options", "en")
        self.focus(nav, "arcade_more")
        nav.act("confirm", device="xbox")
        floor = self.floor(nav)
        self.assertTrue(floor["moreOpen"])
        self.assertFalse(floor["optionsOpen"])
        rows, _ = nav_arcade.routes(nav, nav.items(), nav.focus_index(nav.items()))
        visible = {n for row in rows for n in row}
        self.assertTrue(all(b["index"] in visible for b in floor["destinations"]))
        self.assertEqual(nav.game.a.calls, [])

    def test_footer_prompts_match_card_shortcuts_and_drawer_back(self):
        nav = scene("t5", "arcade_selected", "en")
        nav.game.a.snapshot["spectating"]["targets"].append(
            dict(kind="friend", id="spec_watch_friend:Rival", name="Rival"))
        prompts = {p["action"]: p["label"] for p in nav.view()["prompts"]}
        self.assertEqual(prompts["x"], "Watch")
        self.assertEqual(prompts["social"], "Profile")
        self.assertEqual(prompts["play"], "More")
        self.focus(nav, "online_status")
        prompts = {p["action"]: p["label"] for p in nav.view()["prompts"]}
        self.assertEqual(prompts["confirm"], "Profile")
        self.assertEqual(prompts["social"], "Profile")
        for drawer in ("options", "more", "help"):
            nav.__dict__.setdefault("arcade_" + drawer, {})[nav.game.id] = True
            self.focus(nav, "arcade_" + drawer)
            prompts = {p["action"]: p["label"] for p in nav.view()["prompts"]}
            self.assertEqual(prompts["back"], "Close")

    def test_actual_room_table_metadata_passes_only_public_fields_without_requests(self):
        from openrecomp.adapters import t5_spectating
        from openrecomp.adapters.t5_online import Online
        from openrecomp.adapters.t4_online import T4Online

        known = [dict(id="a", name="One", main="sample-a", private="secret"),
                 dict(id="b", name="Two", main="sample-b")]
        room = dict(id="room", name="Arcade", players=known, size=4, mode="tables", secret="hidden",
                    tables=[dict(id=1, watch=True, players=["a", "b"], set=dict(wins=[2, 1]), path="private")])
        client = SimpleNamespace(players=known, rooms=[room], my_room=None, friend_list={},
                                 has_spectate=lambda: True, watch=mock.Mock())
        owner = SimpleNamespace(_online_client=client, _online_social_cap=lambda capability: True)
        target = t5_spectating._targets(owner)[0]
        self.assertEqual(target["score"], [2, 1])
        self.assertEqual([p["main"] for p in target["players"]], ["sample-a", "sample-b"])
        self.assertNotIn("secret", str(target))
        self.assertNotIn("private", str(target))
        public = Online._online_room_view(owner, room)
        self.assertEqual((public["players"], public["size"], public["mode"]), (2, 4, "tables"))
        self.assertNotIn("secret", str(public))
        self.assertIs(T4Online._online_room_view, Online._online_room_view)
        client.watch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
