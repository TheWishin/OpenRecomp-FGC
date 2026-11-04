"""Player identity pictures use usage summaries; only the VS card can show both picks."""
from pathlib import Path
import unittest

from openrecomp import nav_arcade
from openrecomp.nav_common import uri
from tools.online_shots import scene, snapshot


class SessionPortraits(unittest.TestCase):
    def nav(self, game="t5", phase="matched"):
        nav = scene(game, phase, "en")
        nav.game.a.fighter_image = lambda key: str(Path.cwd() / (key + ".png"))
        nav.game.a.snapshot["me"].update(main="f3", fighter="f5")
        nav.game.a.snapshot["players"][0].update(main="f1", fighter="f6")
        return nav

    def test_vs_uses_each_players_main_until_both_picks_are_supplied(self):
        for game in ("t4", "t5"):
            nav = self.nav(game)
            for partial in ({}, dict(you_char="f4"), dict(you_char="f4", opp_char="random")):
                nav.game.a.snapshot["match"].update(partial)
                vs = nav.view()["matchVersus"]
                self.assertEqual(vs["left"]["art"], uri(nav.game.a.fighter_image("f3")))
                self.assertEqual(vs["right"]["art"], uri(nav.game.a.fighter_image("f1")))
                self.assertFalse(vs["left"]["picked"])

    def test_both_picks_override_vs_and_keep_separately_labelled_mains(self):
        for game in ("t4", "t5"):
            nav = self.nav(game)
            nav.game.a.snapshot["match"].update(you_char="f4", opp_char="f2")
            vs = nav.view()["matchVersus"]
            self.assertEqual(vs["left"]["art"], uri(nav.game.a.fighter_image("f4")))
            self.assertEqual(vs["right"]["art"], uri(nav.game.a.fighter_image("f2")))
            self.assertEqual(vs["left"]["main"], nav.game.a.fighter_label("f3"))
            self.assertEqual(vs["left"]["mainLabel"], "Main")
            self.assertTrue(vs["left"]["picked"])
            nav.game.a.snapshot["phase"] = "result"
            self.assertEqual(nav.view()["matchVersus"]["left"]["art"], uri(nav.game.a.fighter_image("f3")))

    def test_no_usage_does_not_fall_back_to_current_or_configured_character(self):
        nav = self.nav()
        nav.game.a.snapshot["me"].pop("main")
        nav.game.a.snapshot["players"][0].pop("main")
        vs = nav.view()["matchVersus"]
        self.assertEqual(vs["left"]["art"], "")
        self.assertEqual(vs["right"]["art"], "")
        self.assertEqual(nav_arcade._face(nav.game, dict(char="f4"))["face"], "")
        nav = self.nav(phase="lobby_dense")
        nav.game.a.snapshot["me"].pop("main")
        nav.game.a.main_fighter = lambda: "f4"
        nav.game.a.chosen_fighter = lambda: "f4"
        own = next(p for p in nav.view()["online"]["arcade"]["players"] if p["own"])
        self.assertEqual(own["face"], "")

    def test_challenge_popup_uses_challengers_main_and_capture_strips_all_art(self):
        nav = self.nav(phase="challenge_incoming")
        offer = nav.view()["globalOffers"][0]
        self.assertEqual(offer["art"], uri(nav.game.a.fighter_image("f1")))
        self.assertEqual(offer["selfArt"], uri(nav.game.a.fighter_image("f3")))
        self.assertEqual(snapshot(nav)["globalOffers"][0]["selfArt"], "")
        nav.game.a.snapshot["players"][0].pop("main")
        self.assertEqual(nav.view()["globalOffers"][0]["art"], "")

    def test_portrait_review_batch_has_each_surface_and_both_pick_labels_without_art(self):
        from tools.online_shots import PORTRAIT_SCENES, SCENES
        self.assertTrue(set(PORTRAIT_SCENES).issubset(SCENES))
        for game in ("t5", "t4"):
            for language in ("en", "de"):
                nav = scene(game, "matched_picks", language)
                vs = snapshot(nav)["matchVersus"]
                self.assertTrue(vs["left"]["picked"])
                self.assertTrue(vs["right"]["picked"])
                self.assertTrue(vs["left"]["main"])
                self.assertEqual(vs["left"]["art"], "")
                self.assertEqual(nav.game.a.calls, [])


if __name__ == "__main__":
    unittest.main()
