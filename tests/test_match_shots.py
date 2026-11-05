"""Private review fixtures keep each game's art and launch boundary separate."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PySide6.QtGui import QImage

from tools import match_shots


class MatchShots(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)

    def picture(self, name, size=(32, 48)):
        image = QImage(*size, QImage.Format_RGBA8888)
        image.fill(0xff345678)
        path = self.cache / (name + ".png")
        self.assertTrue(image.save(str(path)))
        return str(path)

    def test_separate_large_native_sides_and_small_face_cache(self):
        self.picture("face_09", (32, 32))
        self.picture("face_00", (32, 32))
        left = self.picture("render_09_p1", (512, 512))
        right = self.picture("render_00_p2", (512, 512))
        faces, renders = match_shots.pictures("t5", self.cache)
        self.assertNotEqual(faces["f9"], left)
        self.assertEqual(renders["f9"][False], left)
        self.assertEqual(renders["f0"][True], right)
        self.assertEqual(renders["f0"][False], "")

    def test_t4_accepts_full_height_art_and_rejects_invalid_png(self):
        self.picture("jin", (248, 307))
        self.picture("kazuya", (248, 307))
        faces, _ = match_shots.pictures("t4", self.cache)
        self.assertTrue(faces["jin"])
        self.picture("king", (2049, 2))
        with self.assertRaises(ValueError):
            match_shots.pictures("t4", self.cache)

    def test_both_games_and_languages_use_only_fake_adapters(self):
        with mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("Game launch")), \
                mock.patch("openrecomp.app.Backend", side_effect=AssertionError("Backend")):
            for game, left, right in (("t4", "jin", "kazuya"), ("t5", "f9", "f0")):
                faces = {left: self.picture(left), right: self.picture(right)}
                for language in ("en", "de"):
                    for chapter in match_shots.SCENES:
                        nav = match_shots.scene(game, chapter, language, faces, {})
                        view = nav.view()
                        self.assertEqual(nav.game.a.calls, [])
                        self.assertTrue(nav.dry)
                        if chapter in ("matched", "starting"):
                            self.assertIn(left + ".png", view["matchVersus"]["left"]["art"])
                            self.assertIn(right + ".png", view["matchVersus"]["right"]["art"])

    def test_starting_review_retains_found_match_terms(self):
        for game in ("t4", "t5"):
            before = match_shots.scene(game, "matched", "de", {}, {}).view()["matchVersus"]
            after = match_shots.scene(game, "starting", "de", {}, {}).view()["matchVersus"]
            self.assertEqual(after["infoLine"], before["infoLine"])
            self.assertTrue(after["starting"])


if __name__ == "__main__":
    unittest.main()
