"""The DR theme uses red actions with AA white labels and fiery selection."""
import unittest

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

from test_accessibility import ROOT, contrast
import test_ui_arcade
from test_ui_loads import spin
from test_ui_secondary_polish import scene_items


class CrimsonTokens(unittest.TestCase):
    def test_dr_is_crimson_with_white_primary_ink_and_t4_stays_blue(self):
        app = QGuiApplication.instance() or QGuiApplication([])
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        component.setData(b'import QtQuick\nimport "."\nQtObject { property var theme: Theme }',
                          QUrl.fromLocalFile(str(ROOT / "openrecomp/ui/ThemeProbe.qml")))
        probe = component.create()
        self.assertIsNotNone(probe, [error.toString() for error in component.errors()])
        theme = probe.property("theme")
        theme.setProperty("gameKind", "t5dr")
        for high_contrast in (False, True):
            theme.setProperty("highContrast", high_contrast)
            self.assertGreaterEqual(contrast(theme.property("primaryFill").name(),
                                            theme.property("primaryText").name()), 4.5)
        theme.setProperty("highContrast", False)
        self.assertEqual(theme.property("primaryText").name(), "#ffffff")
        for token in ("gameAccent", "primaryFill", "focus", "highlightStart", "highlightEnd"):
            colour = theme.property(token)
            self.assertGreater(colour.redF(), colour.greenF() * 2, token)
            self.assertGreater(colour.redF(), colour.blueF() * 1.8, token)
        for token in ("ground", "card", "raised"):
            colour = theme.property(token)
            self.assertGreater(colour.red(), colour.green(), token)
            self.assertLess(colour.lightness(), 45, token)
        for surface in ("highlightStart", "highlightEnd"):
            self.assertGreaterEqual(contrast(theme.property("text").name(), theme.property(surface).name()), 4.5)
            self.assertGreaterEqual(contrast(theme.property("rankGold").name(), theme.property(surface).name()), 4.5)
        theme.setProperty("gameKind", "t4")
        self.assertEqual(theme.property("gameAccent").name(), "#71cbe5")
        self.assertEqual(theme.property("ground").name(), "#0d141d")
        self.assertEqual(theme.property("card").name(), "#172330")
        self.assertNotEqual(theme.property("primaryText").name(), "#ffffff")
        del probe
        del engine


class CrimsonRendering(unittest.TestCase):
    setUpClass = classmethod(test_ui_arcade.ArcadeRendering.setUpClass.__func__)
    setUp = test_ui_arcade.ArcadeRendering.setUp
    tearDown = test_ui_arcade.ArcadeRendering.tearDown
    named = test_ui_arcade.ArcadeRendering.named
    publish = test_ui_arcade.ArcadeRendering.publish

    def assert_primary(self, button, labels):
        fill = button.property("color")
        self.assertGreater(fill.red(), fill.green() * 2)
        self.assertTrue(labels)
        for label in labels:
            self.assertEqual(label.property("color").name(), "#ffffff")
            self.assertGreaterEqual(contrast(label.property("color").name(), fill.name()), 4.5)

    def test_actual_lobby_and_home_primary_labels_are_white_on_red_with_focus(self):
        self.publish("t5", "arcade_selected")
        nav = self.backend.nav
        for iid in ("search_ranked", "challenge:p1"):
            nav.focus_online_row(next(n for n, item in enumerate(nav.items()) if item.get("id") == iid))
            self.backend.refresh(); spin(20)
            if iid == "search_ranked":
                button = self.named("onlineRankedAction")[0]
            else:
                button = next(label.parentItem() for label in self.named("arcadeActionLabel")
                              if label.parentItem().property("b").toVariant().get("id") == iid)
            labels = [item for item in scene_items(button) if item.isVisible() and item.property("text")
                      and item.objectName() in ("onlineMatchActionCaption", "arcadeActionLabel")]
            self.assert_primary(button, labels)
        self.publish("t5", "home")
        button = next(item for item in self.named("mainMenuEntry")
                      if item.property("modelData").toVariant().get("id") == "ranked")
        labels = [item for item in scene_items(button) if item.isVisible() and item.property("text")
                  and item.objectName() in ("mainMenuEntryLabel", "mainMenuEntrySubtitle")]
        self.assert_primary(button, labels)

    def test_only_dr_player_selection_has_a_fiery_gradient(self):
        for game, expected in (("t5", True), ("t4", False)):
            self.publish(game, "arcade_selected")
            selections = self.named("arcadePlayerSelection")
            self.assertEqual(any(item.isVisible() for item in selections), expected)


if __name__ == "__main__":
    unittest.main()
