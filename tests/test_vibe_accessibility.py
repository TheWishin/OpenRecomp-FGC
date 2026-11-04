"""The player summary stays visible and runtime white art preserves AA text contrast."""
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QColor, QImage
from PySide6.QtQml import QQmlComponent, QQmlEngine

from test_accessibility import contrast
from test_ui_loads import spin
import test_ui_polish
from tools.online_shots import scene


ROOT = Path(__file__).resolve().parent.parent


class VibeSummaryGeometry(unittest.TestCase):
    setUpClass = classmethod(test_ui_polish.ScenePolish.setUpClass.__func__)
    setUp = test_ui_polish.ScenePolish.setUp
    tearDown = test_ui_polish.ScenePolish.tearDown
    named = test_ui_polish.ScenePolish.named
    wait_pages = test_ui_polish.ScenePolish.wait_pages

    def test_player_summary_and_results_fit_at_720p_with_large_text(self):
        self.win.setWidth(1280)
        self.win.setHeight(720)
        for game, language in (("t5", "en"), ("t4", "es")):
            with self.subTest(game=game, language=language):
                nav = scene(game, "home", language, text_size=130)
                nav.game.a.snapshot["me"]["main"] = "f7"
                nav.game.a.recent_results = lambda: ["L", "W", "W"]
                self.backend.nav = nav
                self.backend.refresh()
                self.wait_pages()
                spin(180)
                identity = self.named("mainMenuFighters")[0].parentItem()
                self.assertLessEqual(identity.y() + identity.height(), identity.parentItem().height() + 1)
                portraits = [child for child in self.named("mainMenuFighters")[0].childItems()
                             if child.property("showcase") is not None]
                self.assertTrue(portraits[0].property("showcase"))
                results = self.named("mainMenuRecentResults")[0]
                self.assertTrue(results.isVisible())
                self.assertGreater(results.height(), 0)


class VibeBackdropContrast(unittest.TestCase):
    setUpClass = classmethod(test_ui_polish.ScenePolish.setUpClass.__func__)

    def test_t4_secondary_ink_and_focus_use_the_cool_palette(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData(b'import QtQuick\nQtObject { property var theme: Theme }',
                          QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/VibePaletteProbe.qml")))
        probe = component.create()
        self.assertIsNotNone(probe)
        try:
            theme = probe.property("theme")
            theme.setProperty("gameKind", "t4")
            for role in ("focus", "value"):
                colour = theme.property(role)
                self.assertGreater(colour.blueF(), colour.redF())
                self.assertGreaterEqual(contrast(colour.name(), theme.property("card").name()), 4.5)
        finally:
            probe.deleteLater()
            spin(5)
            del component
            del engine

    def test_white_runtime_art_keeps_muted_and_primary_text_at_aa_contrast(self):
        with tempfile.TemporaryDirectory(prefix="vibe-white-", dir=ROOT / "build") as directory:
            image = QImage(8, 8, QImage.Format_RGB32)
            image.fill(QColor("white"))
            image_path = Path(directory) / "white.png"
            self.assertTrue(image.save(str(image_path)))
            engine = QQmlEngine()
            component = QQmlComponent(engine)
            component.setData(b'import QtQuick\nItem { property var theme: Theme; property alias backdrop: bg; LivingBackground { id: bg; width: 1280; height: 720; motionActive: false } }',
                              QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/VibeContrastProbe.qml")))
            probe = component.create()
            self.assertIsNotNone(probe, [error.toString() for error in component.errors()])
            try:
                theme = probe.property("theme")
                backdrop = probe.findChild(QObject, "livingBackground")
                art = backdrop.findChild(QObject, "backgroundRuntimeArt")
                veil = backdrop.findChild(QObject, "backgroundReadabilityVeil")
                stops = [item for item in veil.findChildren(QObject)
                         if item.property("position") is not None and item.property("color") is not None]
                self.assertTrue(stops)

                def blend(front, back, alpha):
                    return tuple(front[index] * alpha + back[index] * (1 - alpha) for index in range(3))

                def rgb(colour):
                    return colour.redF(), colour.greenF(), colour.blueF()

                for game in ("t4", "t5dr"):
                    theme.setProperty("gameKind", game)
                    backdrop.setProperty("scene", dict(theme=game, source=QUrl.fromLocalFile(str(image_path)).toString()))
                    spin(220)
                    self.assertGreater(art.property("opacity"), 0)
                    ground = rgb(theme.property("ground"))
                    atmosphere = rgb(backdrop.property("atmosphere"))
                    # The brightest gradient and a streak are a conservative art underlay.
                    underlay = blend(atmosphere, ground, .58)
                    underlay = blend(rgb(theme.property("gameAccent")), underlay, .162)
                    white_art = blend((1, 1, 1), underlay, art.property("opacity"))
                    alpha = min(item.property("color").alphaF() for item in stops)
                    composite = QColor.fromRgbF(*blend(ground, white_art, alpha)).name()
                    for ink in ("text", "muted"):
                        with self.subTest(game=game, ink=ink):
                            self.assertGreaterEqual(contrast(theme.property(ink).name(), composite), 4.5)
            finally:
                probe.deleteLater()
                spin(5)
                del component
                del engine


if __name__ == "__main__":
    unittest.main()
