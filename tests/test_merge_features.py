"""Release features remain reachable through the polished menus, with fake adapters."""
import unittest

from openrecomp.nav import Game, Nav
from openrecomp.nav_challenges import _details
from openrecomp.nav_online_layout import region_of
from test_controls_nav import ControlsFake
from test_t4_lobby_entry import LobbyModes


class MergedFeatures(unittest.TestCase):
    def test_controller_bindings_open_from_main_menu(self):
        adapter = ControlsFake()
        adapter.m["adapter"] = "t4"
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.act("confirm", "xbox")
        self.assertTrue(nav.view()["mainMenu"]["show"])
        entries = nav._main_entries(nav.game)
        target = next(n for n, entry in enumerate(entries) if entry["id"] == "controls")
        for _ in range(target):
            nav.act("down", "xbox")
        nav.act("confirm", "xbox")
        self.assertEqual(nav.section(), "controls")
        self.assertEqual(nav.view()["bindingsPage"]["layout"], "bindings")
        nav.act("confirm", "xbox")
        self.assertTrue(nav.binding_active())
        self.assertIn(("bind", "pad1", "cross"), adapter.calls)

    def test_advanced_direct_and_accessibility_survive_menu_navigation(self):
        adapter = LobbyModes()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.act("confirm", "xbox")
        entries = nav._main_entries(nav.game)
        nav._open_main_entry(next(entry for entry in entries if entry["id"] == "settings"))
        rows = nav.items()
        ids = {row.get("id") for row in rows}
        self.assertTrue({"text_size", "high_contrast", "reduced_motion", "mode_direct"} <= ids)
        nav.focus[nav.key()] = next(n for n, row in enumerate(rows) if row.get("id") == "mode_direct")
        nav.act("confirm", "xbox")
        self.assertIn("host", {row.get("id") for row in nav.items()})
        nav.act("back", "xbox")
        self.assertEqual(nav.section(), "settings")
        self.assertFalse(nav.view()["mainMenu"]["show"])
        self.assertEqual(adapter.calls[-2:], [("online", "disconnect"), ("online", "mode_lobby")])

    def test_challenge_rounds_and_integer_delay_are_both_visible(self):
        rows = _details(dict(rounds=3, delay=0, first_to=2))
        values = {row["k"]: row["v"] for row in rows}
        self.assertEqual(values["@online.challenge_rounds"], "3")
        self.assertEqual(values["@online.challenge_delay"], "0")
        self.assertIn("@online.challenge_first_to", values)

    def test_room_start_and_watch_actions_share_the_room_page(self):
        for action in ("start_match", "room_watch:sample"):
            with self.subTest(action=action):
                self.assertEqual(region_of(action), "rooms")


if __name__ == "__main__":
    unittest.main()
