"""Use the pinned Qt objects without creating a visible launcher or loading games."""
import os
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QFont, QGuiApplication, QWindow

from openrecomp import app


class QuietWindow(QWindow):
    def __init__(self):
        super().__init__()
        self.shown = []

    def showFullScreen(self):
        self.shown.append("full")

    def showNormal(self):
        self.shown.append("normal")


class QtApiCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gui = QGuiApplication.instance() or QGuiApplication([])

    def test_make_engine_registers_cjk_substitutions_using_real_qfont(self):
        families = ("Big Shoulders", "IBM Plex Sans")
        previous = {family: QFont.substitutes(family) for family in families}
        backend = SimpleNamespace(window=None)
        root = QObject()
        engine = mock.Mock()
        engine.rootObjects.return_value = [root]
        try:
            for family in families:
                QFont.removeSubstitutions(family)
            with mock.patch.object(app, "QQmlApplicationEngine", return_value=engine), \
                    mock.patch.object(app.os, "listdir", return_value=[]):
                self.assertIs(app.make_engine(backend, full=False), engine)
            for family in families:
                self.assertEqual([name.casefold() for name in QFont.substitutes(family)],
                                 ["yu gothic ui", "malgun gothic"])
            self.assertIs(backend.window, root)
        finally:
            for family, substitutions in previous.items():
                QFont.removeSubstitutions(family)
                QFont.insertSubstitutions(family, substitutions)

    def test_display_preferences_use_qwindow_state_and_preserve_minimization(self):
        window = QuietWindow()
        backend = SimpleNamespace(window=window, config={})
        backend._save_config = lambda: app.Backend._save_config(backend)
        with mock.patch.object(app.mf, "save_config") as save:
            window.setProperty("wantFull", False)
            app.Backend._save_preferences(backend, True, False)
            self.assertEqual(window.shown, ["full"])
            app.Backend._save_preferences(backend, False, True)
            self.assertEqual(window.shown, ["full", "normal"])
            window.setWindowState(Qt.WindowMinimized)
            app.Backend._save_preferences(backend, True, True)
            self.assertEqual(window.shown, ["full", "normal"])
            self.assertTrue(window.property("wantFull"))
            self.assertEqual(backend.config, dict(fullscreen=True, reduced_motion=True))
            self.assertEqual(save.call_count, 3)


if __name__ == "__main__":
    unittest.main()
