"""Local-art review fixtures use only explicitly supplied synthetic PNGs."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PySide6.QtGui import QImage

from tools import t4_art_shots


class T4ArtShots(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name).resolve()

    def picture(self, key, width=8, height=8):
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(0xffabcdef)
        path = self.cache / (key + ".png")
        self.assertTrue(image.save(str(path)))
        return str(path)

    def test_loads_only_known_square_pngs(self):
        expected = {key: self.picture(key) for key in ("jin", "kazuya")}
        (self.cache / "unknown.png").write_bytes(b"not an image")
        self.assertEqual(t4_art_shots.load_cache(self.cache, expected), expected)
        self.picture("jin", 8, 16)
        with self.assertRaises(ValueError):
            t4_art_shots.load_cache(self.cache, expected)

    def test_requires_two_known_pictures(self):
        self.picture("jin")
        self.picture("unknown")
        with self.assertRaises(ValueError):
            t4_art_shots.load_cache(self.cache, ("jin", "kazuya"))

    def test_review_includes_incoming_challenge_with_no_invented_deadline(self):
        self.assertIn("challenge", t4_art_shots.SCENES)
        pictures = {key: self.picture(key) for key in ("jin", "kazuya")}
        nav = t4_art_shots.scene("challenge", pictures)
        offer, = nav.view()["globalOffers"]
        self.assertEqual(offer["countdown"], "")
        self.assertEqual(nav.game.a.calls, [])

    def test_review_can_supply_native_renders_separately_from_list_faces(self):
        pictures = {key: self.picture(key) for key in ("jin", "kazuya")}
        renders = {key: {False: str(self.cache / (key + "-p1.png")),
                         True: str(self.cache / (key + "-p2.png"))} for key in pictures}
        nav = t4_art_shots.scene("vs", pictures, renders)
        adapter = nav.game.a
        self.assertEqual(adapter.fighter_image("jin"), pictures["jin"])
        self.assertEqual(adapter.fighter_render("jin"), renders["jin"][False])
        self.assertEqual(adapter.fighter_render("kazuya", True), renders["kazuya"][True])

    def test_review_scenes_project_supplied_art_without_real_adapters_or_network(self):
        pictures = {key: self.picture(key) for key in ("jin", "kazuya", "king")}
        with mock.patch("openrecomp.app.Backend", side_effect=AssertionError("Real backend")), \
                mock.patch("socket.socket", side_effect=AssertionError("Network")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("External process")):
            for name in t4_art_shots.SCENES:
                nav = t4_art_shots.scene(name, pictures)
                view = nav.view()
                self.assertTrue(nav.dry)
                self.assertEqual(nav.game.a.calls, [])
                self.assertIn("jin.png", str(view))
                if name == "vs":
                    self.assertIn("kazuya.png", view["matchVersus"]["right"]["art"])
                    self.assertFalse(view["matchVersus"]["left"]["picked"])
                elif name == "profile":
                    self.assertEqual(nav.game.a.snapshot["profile"]["main"], "jin")


if __name__ == "__main__":
    unittest.main()
