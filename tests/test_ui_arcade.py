"""Render the arcade through the inert adapter boundary, including reduced motion."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import i18n
from openrecomp.app import UI_DIR
from test_ui_loads import FakeBackend, spin, wait_pages
from test_ui_secondary_polish import scene_items
from tools import online_shots, package_release


class ArcadeRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.backend = FakeBackend(online_shots.scene("t5", "arcade_floor", "en"))
        self.backend._v = online_shots.snapshot(self.backend.nav)
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

    def named(self, name):
        items = [item for item in scene_items(self.win.contentItem()) if item.objectName() == name]
        self.assertTrue(items, name)
        return items

    def publish(self, game, scene, language="en", **kwargs):
        self.backend.nav = online_shots.scene(game, scene, language, **kwargs)
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(20)

    def test_floor_selected_cabinet_and_drawer_render_for_both_games_and_sizes(self):
        for game in ("t5", "t4"):
            for scene in online_shots.ARCADE_SCENES:
                for width, height in online_shots.SIZES:
                    with self.subTest(game=game, scene=scene, size=(width, height)):
                        self.publish(game, scene)
                        self.win.setWidth(width)
                        self.win.setHeight(height)
                        self.assertTrue(self.named("arcadeFloor")[0].isVisible())
                        self.assertEqual(len(self.named("arcadePlayer")), 7)
                        self.assertEqual(self.named("arcadeCabinet")[0].isVisible(), scene != "arcade_options")
                        self.assertEqual(self.named("arcadeOptionsDrawer")[0].isVisible(), scene == "arcade_options")
                        self.assertFalse(self.named("onlineProfile")[0].isVisible())
                        self.assertFalse(self.named("onlineFind")[0].isVisible())
                        for card in self.named("arcadePlayer"):
                            self.assertGreater(card.width(), 300)
                            self.assertLessEqual(card.x() + card.width(), card.parentItem().width() + 1)
                        self.assertEqual(self.backend.nav.game.a.calls, [])

    def test_all_catalogs_fit_options_with_large_text_and_high_contrast(self):
        for language in i18n.LANGUAGES:
            self.publish("t4", "arcade_options", language, text_size=130, high_contrast=True)
            overflow, _ = online_shots.geometry(self.win)
            self.assertEqual(overflow, [], (language, overflow))

    def test_selected_card_motion_stops_when_reduced_motion_is_enabled(self):
        self.publish("t5", "arcade_selected")
        cards = self.named("arcadePlayer")
        self.assertTrue(all(card.scale() == 1 for card in cards))
        self.backend.nav.reduced_motion = False
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.backend.viewChanged.emit()
        spin(180)
        self.assertTrue(any(card.scale() > 1 for card in cards))
        self.backend.nav.reduced_motion = True
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.backend.viewChanged.emit()
        spin(20)
        self.assertTrue(all(card.scale() == 1 for card in cards))

    def test_wide_controller_and_keyboard_glyphs_leave_room_for_labels(self):
        for device in ("xbox", "kb"):
            self.publish("t5", "arcade_selected")
            self.backend.nav.device = device
            self.backend._v = online_shots.snapshot(self.backend.nav)
            self.backend.viewChanged.emit()
            spin(20)
            for name in ("arcadeShortcutLabel", "arcadeActionLabel"):
                for label in self.named(name):
                    if not label.isVisible():
                        continue
                    glyphs = [child for child in label.parentItem().childItems()
                              if child.objectName() in ("arcadeShortcutGlyph", "arcadeActionGlyph") and child.isVisible()]
                    for glyph in glyphs:
                        self.assertGreaterEqual(label.x(), glyph.x() + glyph.width() + 4)
    def test_release_manifest_includes_the_floor_and_projection(self):
        for filename in ("ArcadeFloor.qml", "ArcadePlayer.qml", "ArcadeAction.qml", "ArcadeIcon.qml"):
            self.assertIn("openrecomp/ui/" + filename, package_release.SOURCE_FILES)
        self.assertIn("openrecomp/nav_arcade.py", package_release.SOURCE_FILES)
        self.assertIn("openrecomp/adapters/arcade_metadata.py", package_release.SOURCE_FILES)

    def test_more_drawer_scrolls_to_a_controller_selected_destination(self):
        self.publish("t5", "arcade_selected")
        nav = self.backend.nav
        nav.act("play", device="xbox")
        destinations = nav.view()["online"]["arcade"]["destinations"]
        self.assertTrue(destinations)
        nav.focus_online_row(destinations[-1]["index"])
        self.backend._v = online_shots.snapshot(nav)
        self.backend.viewChanged.emit()
        spin(40)
        choices = [item for item in scene_items(self.win.contentItem()) if item.isVisible()
                   and item.objectName() == "arcadeActionLabel" and item.property("text") == destinations[-1]["label"]]
        self.assertEqual(len(choices), 1)
        from PySide6.QtCore import QPointF
        drawer = self.named("arcadeOptionsDrawer")[0]
        point = choices[0].mapToItem(drawer, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 76)
        self.assertLessEqual(point.y() + choices[0].height(), drawer.height())


if __name__ == "__main__":
    unittest.main()
