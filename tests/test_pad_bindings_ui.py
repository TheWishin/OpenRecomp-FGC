"""The Pad bindings page drawn offscreen with fake controllers, in every language, without a QML warning."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem

from openrecomp import i18n
from openrecomp.app import UI_DIR
from openrecomp.nav import Game, Nav
from pad_fakes import PadsFake
from test_ui_loads import FakeBackend, wait_pages


class BindingsScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def test_page_capture_presets_and_input_test_in_every_language(self):
        adapter = PadsFake()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec[nav.game.id] = "controls"
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        root = engine.rootObjects()[0]

        def show():
            backend._v = nav.view()
            backend.viewChanged.emit()
            wait_pages(root)

        def visible(name):
            item = root.findChild(QQuickItem, name)
            return item is not None and item.isVisible()

        try:
            for language in i18n.LANGUAGES:
                with self.subTest(language=language):
                    nav.language = language
                    nav.overlay = None
                    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("slot") == "1")
                    adapter.held["xinput:0"] = {"A", "DDOWN"}
                    show()
                    self.assertTrue(visible("bindingsPage"))
                    self.assertFalse(visible("hubList"))
                    nav.act("confirm", device="xbox")
                    show()
                    self.assertTrue(visible("bindCapture"))
                    nav.act("back", device="kb")
                    nav.focus[nav.key()] = next(i for i, it in enumerate(nav.items()) if it.get("id") == "ctl:preset")
                    nav.act("confirm", device="xbox")
                    show()
                    self.assertTrue(visible("ctlPreset"))
                    nav.act("back", device="xbox")
                    for pad in range(3):          # every controller type: Xbox, PlayStation, keyboard
                        nav.act("chapterNext", device="xbox")
                        show()
            self.assertEqual(warnings, [])
        finally:
            del engine


if __name__ == "__main__":
    unittest.main()
