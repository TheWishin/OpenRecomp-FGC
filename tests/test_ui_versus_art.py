"""VS renders use their own large images while list portraits stay compact."""
import os
from pathlib import Path
import tempfile
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp.app import UI_DIR
from openrecomp.nav_feedback import match_view
from test_ui_loads import FakeBackend, spin, wait_pages
from test_ui_secondary_polish import scene_items
from tools import online_shots


class VersusArt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.nav = online_shots.scene("t5", "matched", "en")
        self.backend = FakeBackend(self.nav)
        self.backend._v = online_shots.snapshot(self.nav)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties(dict(backend=self.backend, wantFull=False))
        self.engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.win = self.engine.rootObjects()[0]
        self.win.show()
        wait_pages(self.win)

    def tearDown(self):
        self.win.setProperty("allowClose", True)
        self.win.close()
        del self.win
        del self.engine
        self.assertEqual(self.warnings, [])

    def named(self, name, parent=None):
        return [item for item in scene_items(parent or self.win.contentItem())
                if item.objectName() == name]

    def publish(self):
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(40)

    def test_projection_requests_large_render_for_each_side_and_keeps_small_art(self):
        requests = []
        self.nav.game.a.fighter_render = lambda key, mirrored=False: requests.append((key, mirrored)) or ""
        view = match_view(self.nav, self.nav.game)
        self.assertEqual(requests, [("f3", False), ("f1", True)])
        self.assertIn("render", view["left"])
        self.assertIn("art", view["left"])
        self.assertIn("render", view["right"])

    def test_no_art_outline_is_small_and_names_and_ranks_have_more_weight(self):
        for width, height in online_shots.SIZES:
            self.win.setWidth(width); self.win.setHeight(height); spin(30)
            portraits = self.named("versusPortrait")
            self.assertEqual(len(portraits), 2)
            for portrait in portraits:
                fallback = self.named("fighterFallback", portrait)[0]
                self.assertLessEqual(fallback.width(), 108)
                self.assertLessEqual(fallback.width(), portrait.width() * .4)
                self.assertLessEqual(fallback.opacity(), .5)
            for name in self.named("versusPlayerName"):
                self.assertGreaterEqual(name.property("font").pixelSize(), 40)
            for rank in self.named("versusPlayerRank"):
                self.assertGreaterEqual(rank.property("font").pixelSize(), 30)

    def test_large_render_fills_portrait_and_is_not_mirrored_twice(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / "build") as temporary:
            path = Path(temporary) / "synthetic.png"
            image = QImage(512, 512, QImage.Format_RGBA8888)
            image.fill(QColor("#4e8d92"))
            self.assertTrue(image.save(str(path)))
            for side in ("left", "right"):
                self.backend._v["matchVersus"][side]["render"] = QUrl.fromLocalFile(str(path)).toString()
            self.publish()
            for portrait in self.named("versusPortrait"):
                picture = self.named("fighterPicture", portrait)[0]
                self.assertEqual(Path(picture.property("source").toLocalFile()), path)
                self.assertAlmostEqual(picture.width(), portrait.width())
                self.assertAlmostEqual(picture.height(), portrait.height())
                self.assertFalse(picture.property("mirror"))
                self.assertFalse(self.named("fighterFallback", portrait)[0].isVisible())


if __name__ == "__main__":
    unittest.main()
