"""Clickable menu and modal controls retain 44 output-pixel targets and reveal pad selection."""
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QPointF, QRectF, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from openrecomp.app import UI_DIR
from test_ui_loads import FakeBackend, spin, wait_pages
from test_ui_secondary_polish import scene_items
from tools import online_shots


class ClickTargetFloors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.nav = online_shots.scene("t5", "home", "de")
        self.backend = FakeBackend(self.nav)
        self.backend._v = online_shots.snapshot(self.nav)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties(dict(backend=self.backend, wantFull=False))
        self.engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.window.show()
        wait_pages(self.window)

    def tearDown(self):
        self.window.setProperty("allowClose", True)
        self.window.close()
        self.assertEqual(self.warnings, [])

    def publish(self):
        self.backend._v = online_shots.snapshot(self.nav)
        self.backend.viewChanged.emit()
        wait_pages(self.window)
        spin(20)

    def named(self, name):
        return [item for item in scene_items(self.window.contentItem()) if item.objectName() == name and item.isVisible()]

    def assert_targets(self, name):
        targets = self.named(name)
        self.assertTrue(targets, name)
        for target in targets:
            output = target.mapRectToScene(QRectF(0, 0, target.width(), target.height()))
            self.assertGreaterEqual(output.height(), 44 - .1, name)
        return targets

    def assert_selected_visible(self, targets, viewport):
        selected = next(target for target in targets
                        if target.findChild(QObject, "interactionFeedback").property("selected"))
        position = selected.mapToItem(viewport, QPointF(0, 0))
        self.assertGreaterEqual(position.y(), -.1)
        self.assertLessEqual(position.y() + selected.height(), viewport.height() + .1)

    def test_main_menu_targets_and_last_entry_are_reachable_at_small_viewports(self):
        for width, height in ((1280, 720), (960, 540)):
            self.window.setWidth(width)
            self.window.setHeight(height)
            for percent in (100, 130):
                self.nav.text_size = percent
                self.nav.main_menu_focus = len(self.nav._main_entries(self.nav.game)) - 1
                self.publish()
                targets = self.assert_targets("mainMenuEntry")
                self.assert_selected_visible(targets, self.named("mainMenuList")[0])

    def test_dialog_and_drawer_targets_keep_pad_selection_inside_the_viewport(self):
        for width, height in ((1280, 720), (960, 540)):
            self.window.setWidth(width)
            self.window.setHeight(height)
            for percent in (100, 130):
                self.nav.text_size = percent
                self.nav._ask("exit")
                self.publish()
                self.assert_targets("dialogOption")
                self.nav.overlay = "drawer"
                self.nav.drawer_focus = len(self.nav._drawer_items()) - 1
                self.publish()
                targets = self.assert_targets("drawerRow")
                self.assert_selected_visible(targets, self.named("drawerViewport")[0])

    def test_picker_targets_scroll_the_current_window_without_reading_any_directory(self):
        entries = [dict(kind="dir", name=f"Sample folder {n}", path="") for n in range(20)]
        self.nav._picker_entries = lambda: entries
        self.nav._open_list_picker("synthetic", "@library.local", [], "folder", "")
        for width, height in ((1280, 720), (960, 540)):
            self.window.setWidth(width)
            self.window.setHeight(height)
            for percent in (100, 130):
                self.nav.text_size = percent
                for selected in (0, len(entries) - 1, 5):
                    self.nav.picker["focus"] = selected
                    self.publish()
                    targets = self.assert_targets("pickerRow")
                    self.assert_selected_visible(targets, self.named("pickerViewport")[0])
