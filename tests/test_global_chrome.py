"""Global header and prompts reflow at output text floors without covering page controls."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QRectF, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from openrecomp import i18n
from openrecomp.app import UI_DIR
from test_ui_loads import FakeBackend, spin, wait_pages
from test_ui_secondary_polish import scene_items
from tools import online_shots


class GlobalChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def test_global_labels_and_targets_fit_all_catalogs_at_three_viewports(self):
        backend = FakeBackend(online_shots.scene("t5", "arcade_floor", "en"))
        backend._v = online_shots.snapshot(backend.nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.show()
        wait_pages(window)
        for width, height in ((1920, 1080), (1280, 720), (960, 540)):
            window.setWidth(width)
            window.setHeight(height)
            for language in i18n.LANGUAGES:
                for percent in (100, 130):
                    with self.subTest(size=(width, height), language=language, text=percent):
                        backend.nav.language = language
                        backend.nav.text_size = percent
                        backend._v = online_shots.snapshot(backend.nav)
                        backend.viewChanged.emit()
                        spin(5)
                        items = [item for item in scene_items(window.contentItem()) if item.isVisible()]
                        named = {item.objectName(): item for item in items if item.objectName()}
                        identity, actions = named["topIdentity"], named["topActions"]
                        self.assertLessEqual(identity.x() + identity.width() + 16, actions.x())
                        for item in items:
                            if item.objectName() in ("promptLabel", "quickAccessLabel", "discordLabel", "focusHint"):
                                self.assertLessEqual(item.property("contentWidth"), item.width() + 1, item.objectName())
                                self.assertLessEqual(item.property("contentHeight"), item.height() + 1, item.objectName())
                            if item.objectName() in ("promptItem", "quickAccessButton", "discordButton"):
                                self.assertGreaterEqual(item.mapRectToScene(QRectF(0, 0, item.width(), item.height())).height(), 44 - .1)
        window.setProperty("allowClose", True)
        window.close()
        self.assertEqual(warnings, [])
