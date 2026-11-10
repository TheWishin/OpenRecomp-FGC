"""A game started from this launcher inherits the player's environment, not variables this launcher set for itself."""
import os
import sys
import unittest
from unittest import mock

from openrecomp import app


class ControlsStyle(unittest.TestCase):
    def test_the_style_is_set_in_qt_and_not_in_the_environment(self):
        with mock.patch.dict(os.environ), mock.patch("PySide6.QtQuickControls2.QQuickStyle.setStyle") as style:
            os.environ.pop("QT_QUICK_CONTROLS_STYLE", None)
            self.assertIs(app.controls_style(), False)
            self.assertNotIn("QT_QUICK_CONTROLS_STYLE", os.environ)
        style.assert_called_once_with("Basic")

    def test_a_style_of_the_players_own_stays(self):
        with mock.patch.dict(os.environ, QT_QUICK_CONTROLS_STYLE="Fusion"), \
             mock.patch("PySide6.QtQuickControls2.QQuickStyle.setStyle") as style:
            app.controls_style()
            self.assertEqual(os.environ["QT_QUICK_CONTROLS_STYLE"], "Fusion")
        style.assert_not_called()

    def test_without_the_module_the_variable_as_before(self):
        with mock.patch.dict(os.environ), mock.patch.dict(sys.modules, {"PySide6.QtQuickControls2": None}):
            os.environ.pop("QT_QUICK_CONTROLS_STYLE", None)
            self.assertIs(app.controls_style(), True)      # main takes it out again once the window is loaded
            self.assertEqual(os.environ["QT_QUICK_CONTROLS_STYLE"], "Basic")

    def test_main_sets_no_variable_of_its_own(self):
        with open(app.__file__, encoding="utf-8") as source:
            text = source.read()
        self.assertNotIn("os.environ.setdefault(", text)
        self.assertIn('os.environ.pop("QT_QUICK_CONTROLS_STYLE", None)', text)


if __name__ == "__main__":
    unittest.main()
