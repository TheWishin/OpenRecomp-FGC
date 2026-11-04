"""Online review images are synthetic and cannot load player art or contact services."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import online_shots


class SyntheticOnlineScreenshots(unittest.TestCase):
    def test_every_online_chapter_in_both_games_and_all_catalogs_is_safe(self):
        with mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for language in online_shots.i18n.LANGUAGES:
                for game in ("t5", "t4"):
                    for chapter in online_shots.SCENES:
                        with self.subTest(language=language, game=game, chapter=chapter):
                            nav = online_shots.scene(game, chapter, language)
                            view = online_shots.snapshot(nav)
                            self.assertTrue(nav.dry)
                            if chapter == "home":
                                self.assertTrue(view["mainMenu"]["show"])
                            elif chapter == "settings":
                                self.assertEqual(view["settingsPage"]["layout"], "groups")
                            else:
                                expected = "lobby" if chapter == "feedback" or chapter in online_shots.ARCADE_SCENES else chapter.removesuffix("_empty")
                                self.assertEqual(view["online"]["chapter"], expected)
                            self.assertEqual(nav.game.a.calls, [])
                            self.assertFalse(view["online"].get("profile", {}).get("face"))
                            self.assertFalse(view["online"].get("profile", {}).get("plate"))

    def test_sanitizer_removes_profile_art_and_nested_art(self):
        view = dict(profile=dict(face="private.png", plate="private.png"),
                    nested=[dict(image="private.png", images=["private.png"], portrait="private.png")])
        online_shots.strip_art(view)
        self.assertNotIn("private", str(view))

    def test_empty_room_scene_really_has_no_open_rooms(self):
        nav = online_shots.scene("t5", "rooms_empty", "en")
        self.assertEqual(nav.game.a.snapshot["rooms"], [])
        self.assertIn("no_rooms", [row.get("id") for row in nav.items()])

    def test_baseline_mixin_precedes_current_navigation_without_replacing_it(self):
        with tempfile.TemporaryDirectory(dir=online_shots.ROOT) as directory:
            source = Path(directory) / "baseline.py"
            source.write_text('class OnlineLayout:\n    baseline_marker = "preserved"\n', encoding="utf-8")
            nav_type = online_shots.baseline_nav(source)
            nav = online_shots.scene("t5", "rooms", "en", nav_type=nav_type)
            self.assertEqual(nav.baseline_marker, "preserved")
            self.assertTrue(issubclass(nav_type, online_shots.Nav))
            self.assertFalse(hasattr(online_shots.Nav, "baseline_marker"))

    def test_vertical_scrolling_does_not_hide_horizontal_clipping(self):
        self.assertEqual(online_shots.clip_reason(0, -60, 300, 40, 300, 200, True), "")
        self.assertEqual(online_shots.clip_reason(0, 180, 300, 240, 300, 200, True), "")
        self.assertEqual(online_shots.clip_reason(0, 180, 320, 240, 300, 200, True), "horizontal-clip")
        self.assertEqual(online_shots.clip_reason(0, 180, 300, 240, 300, 200), "vertical-clip")

    def test_accessibility_and_feedback_scenes_stay_inert(self):
        for game in ("t5", "t4"):
            nav = online_shots.scene(game, "feedback", "en", text_size=130, high_contrast=True)
            view = online_shots.snapshot(nav)
            self.assertEqual(view["textScale"], 1.3)
            self.assertTrue(view["highContrast"])
            self.assertIn("0:27 remaining", str(view["online"]["body"]))
            self.assertEqual(nav.game.a.calls, [])
            home = online_shots.snapshot(online_shots.scene(game, "home", "en"))
            self.assertEqual(any(row["id"] == "ranked" for row in home["mainMenu"]["entries"]), game != "t4")

    def test_arcade_review_scenes_cover_cards_cabinet_and_options_without_actions(self):
        with mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for game in ("t5", "t4"):
                for name in online_shots.ARCADE_SCENES:
                    with self.subTest(game=game, scene=name):
                        nav = online_shots.scene(game, name, "en")
                        arcade = online_shots.snapshot(nav)["online"]["arcade"]
                        self.assertGreaterEqual(len(arcade["players"]), 7)
                        self.assertEqual(sum(p["own"] for p in arcade["players"]), 1)
                        self.assertTrue(arcade["cabinets"])
                        self.assertEqual(arcade["cabinets"][0]["score"], "2 : 1")
                        self.assertEqual(arcade["optionsOpen"], name == "arcade_options")
                        if name == "arcade_selected":
                            self.assertTrue(next(p for p in arcade["players"] if p["id"] == "p1")["focused"])
                        elif name == "arcade_cabinet":
                            self.assertTrue(arcade["cabinets"][0]["focused"])
                        self.assertFalse(any(p["face"] or p["plate"] for p in arcade["players"]))
                        self.assertFalse(any(p["face"] for cabinet in arcade["cabinets"] for p in cabinet["players"]))
                        self.assertEqual(nav.game.a.calls, [])


if __name__ == "__main__":
    unittest.main()
