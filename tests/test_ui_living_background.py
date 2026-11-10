"""Inspect original fallback geometry and motion gates without capturing a launcher."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem

from test_ui_loads import spin

ROOT = Path(__file__).resolve().parent.parent


class LivingBackgroundScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.engine = QQmlEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda warnings: self.warnings.extend(w.toString() for w in warnings))
        self.component = QQmlComponent(self.engine, QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/LivingBackground.qml")))
        self.assertEqual(self.component.status(), QQmlComponent.Ready,
                         "\n".join(error.toString() for error in self.component.errors()))
        self.item = self.component.createWithInitialProperties(dict(width=1280, height=720,
                                                                    scene=dict(theme="t4", source="")))
        self.assertIsInstance(self.item, QQuickItem)

    def tearDown(self):
        self.item.setProperty("motionActive", False)
        self.item.deleteLater()
        spin(5)
        del self.component
        del self.engine
        self.assertEqual(self.warnings, [])

    def test_reduce_motion_stops_timer_and_freezes_on_static_composition(self):
        timer = self.item.findChild(QObject, "backgroundDriftTimer")
        self.assertTrue(timer.property("running"))
        spin(560)
        self.assertGreater(self.item.property("drift"), 0)
        self.item.setProperty("reducedMotion", True)
        self.assertFalse(timer.property("running"))
        self.assertEqual(self.item.property("drift"), 0)
        spin(140)
        self.assertEqual(self.item.property("drift"), 0)

    def test_hidden_and_inactive_windows_stop_ambient_work(self):
        from PySide6.QtQuick import QQuickWindow
        window = QQuickWindow()
        window.resize(1280, 720)
        self.item.setParentItem(window.contentItem())
        self.addCleanup(lambda window=window: window.hide())
        window.show()
        spin(60)
        timer = self.item.findChild(QObject, "backgroundDriftTimer")
        self.item.setProperty("motionActive", False)
        self.assertFalse(timer.property("running"))
        self.item.setProperty("motionActive", True)
        self.assertTrue(timer.property("running"))
        self.item.setVisible(False)
        self.assertFalse(timer.property("running"))
        self.assertTrue(self.item.property("softwareRenderer"))
        self.assertEqual(timer.property("interval"), 500)

    def theme(self):
        component = QQmlComponent(self.engine)
        component.setData(b'import QtQuick\nimport "."\nQtObject { property var theme: Theme }',
                          QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/ThemeProbe.qml")))
        self.probe = component.create()
        return self.probe.property("theme")

    def test_calm_default_keeps_one_grey_atmosphere_and_faint_art(self):
        theme = self.theme()
        self.assertTrue(theme.property("calm"))
        first = self.item.property("atmosphere")
        self.item.setProperty("scene", dict(theme="t5dr", source=""))
        self.assertEqual(first, self.item.property("atmosphere"))
        self.assertLess(theme.property("artStrength"), .58)

    def test_per_game_atmosphere_and_bounded_async_art(self):
        self.theme().setProperty("calm", False)       # the vivid palette keeps a colour per game
        self.assertTrue(self.item.property("blue"))
        first = self.item.property("atmosphere")
        self.item.setProperty("scene", dict(theme="t5dr", source=""))
        self.assertFalse(self.item.property("blue"))
        self.assertNotEqual(first, self.item.property("atmosphere"))
        art = self.item.findChild(QObject, "backgroundRuntimeArt")
        self.assertTrue(art.property("asynchronous"))
        self.assertLessEqual(art.property("sourceSize").width(), 1100)
        self.assertLessEqual(art.property("sourceSize").height(), 900)
        self.assertEqual(art.property("opacity"), 0)
        self.assertIsNotNone(self.item.findChild(QObject, "backgroundReadabilityVeil"))


if __name__ == "__main__":
    unittest.main()
