"""The shared invitation flow preserves the visible, cancellable search lobby."""
import unittest

from openrecomp.nav import Game, Nav
from test_t4_lobby_entry import LobbyModes


class LobbyFlowMerge(unittest.TestCase):
    def test_invitation_waits_for_search_to_end_in_both_games(self):
        for game in ("t4", "t5dr"):
            with self.subTest(game=game):
                adapter = LobbyModes(game)
                adapter.snapshot.update(phase="searching", queue="casual",
                                        challenge=dict(id="offer", name="Rival"))
                nav = Nav([Game(adapter.m, adapter)], language="en")
                nav.screen, nav.sec[game] = "hub", "online"
                nav.tick(0)
                self.assertIsNone(nav.overlay)
                rows = {row.get("id"): row for row in nav.items()}
                self.assertIn("refresh_players", rows)
                self.assertTrue(rows["search_casual"]["disabled"])
                self.assertIsNone(rows["search_casual"]["run"])
                self.assertTrue(rows["cancel"]["run"])
                self.assertNotIn("mode_direct", rows)

                adapter.snapshot["phase"] = "cancelling"
                cancel = next(row for row in nav.items() if row.get("id") == "cancel")
                self.assertTrue(cancel["disabled"])
                self.assertIsNone(cancel["run"])
                nav.tick(0)
                self.assertIsNone(nav.overlay)

                adapter.snapshot["phase"] = "logged_in"
                nav.tick(0)
                self.assertEqual(nav.overlay, "dialog")
                nav.act("right", device="xbox")
                nav.act("confirm", device="xbox")
                self.assertEqual(adapter.calls[-1], ("online", "accept_challenge"))


if __name__ == "__main__":
    unittest.main()
