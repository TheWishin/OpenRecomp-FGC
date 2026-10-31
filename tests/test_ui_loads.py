"""The real QML scene with a fake game: every screen must load without one QML warning."""
import os
import sys
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, Property, Signal, Slot  # noqa: E402
from PySide6.QtGui import QFontDatabase, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from openrecomp.app import UI_DIR  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402


class FakeBackend(QObject):
    viewChanged = Signal()

    def __init__(self, nav):
        super().__init__()
        self.nav = nav
        self._v = nav.view()

    @Property("QVariant", notify=viewChanged)
    def view(self):
        return self._v

    def go(self, action):
        self.nav.act(action)
        self._v = self.nav.view()
        self.viewChanged.emit()

    @Slot(int, str, bool)
    def keyDown(self, key, text, repeat):
        pass

    @Slot(int, bool)
    def keyUp(self, key, repeat):
        pass

    @Slot(str)
    def press(self, action):
        pass

    @Slot(int)
    def clickRow(self, i):
        pass

    @Slot(int)
    def clickTile(self, i):
        pass

    @Slot(str)
    def clickTab(self, s):
        pass

    @Slot()
    def clickPrimary(self):
        pass

    @Slot(int)
    def clickCell(self, i):
        pass

    @Slot(int)
    def clickEntry(self, i):
        pass

    @Slot(int, int)
    def clickKey(self, r, c):
        pass


def spin(ms=40):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class Scene(unittest.TestCase):
    def test_every_screen_without_a_warning(self):
        app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        self.assertEqual(app.platformName(), "offscreen")
        for name in os.listdir(os.path.join(UI_DIR, "fonts")):
            if name.endswith(".ttf"):
                QFontDatabase.addApplicationFont(os.path.join(UI_DIR, "fonts", name))
        a, b = Fake(manifest("a")), Fake(manifest("b", sections=("play", "build", "settings")), is_ready=False)
        nav = Nav([Game(a.m, a), Game(b.m, b)])
        nav.dry = True
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(os.path.join(UI_DIR, "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        spin()
        steps = ["right", "right", "right", "left", "left", "left", "confirm", "next", "confirm", "right", "down", "back", "down", "down", "confirm", "x", "back",
                 "next", "confirm", "back", "next", "down", "x", "next", "social", "back", "switchGame", "next", "next", "back", "back", "right", "back"]
        for s in steps:
            backend.go(s)
            spin()
        self.assertEqual(warnings, [])
        del engine
        del app


if __name__ == "__main__":
    unittest.main()
