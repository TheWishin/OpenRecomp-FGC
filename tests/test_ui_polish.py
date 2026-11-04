"""Fake-only scene geometry: long catalogs, fixed navigation, and immediate reduced motion."""
import json
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp.app import UI_DIR
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_ui_loads import FakeBackend, spin


def items(parent):
    for child in parent.childItems():
        yield child
        yield from items(child)


class ScenePolish(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.adapter = Fake(manifest())
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.dry = True
        self.backend = FakeBackend(self.nav)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties({"backend": self.backend, "wantFull": False})
        self.engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.win = self.engine.rootObjects()[0]
        self.win.show()
        self.wait_pages()
        spin()

    def tearDown(self):
        self.assertEqual(self.warnings, [])
        self.win.close()
        del self.win
        del self.engine

    def named(self, name):
        found = [item for item in items(self.win.contentItem()) if item.objectName() == name]
        self.assertTrue(found, name)
        return found

    def wait_pages(self):
        for _ in range(200):
            spin(5)
            if all(not p.property("active") or p.property("progress") == 1
                   and p.property("item") is not None
                   for p in self.win.findChildren(QObject, "pageLoader")):
                return
        self.fail("A page did not load before geometry was checked")

    def publish(self):
        self.backend._v = self.nav.view()
        self.backend.viewChanged.emit()
        self.wait_pages()
        spin(160)

    def test_longest_catalog_texts_keep_shelf_and_prompts_in_bounds(self):
        for catalog in (Path(UI_DIR).parent / "i18n").glob("*.json"):
            with self.subTest(language=catalog.stem):
                strings = json.loads(catalog.read_text(encoding="utf-8"))
                longest = max(strings.values(), key=len)
                self.nav.language = catalog.stem
                self.adapter.m["title"] = longest
                self.adapter.m["subtitle"] = longest
                self.publish()
                focused = next(c for c in self.named("shelfContent") if c.parentItem().width() > 900)
                action = next(c for c in self.named("shelfAction") if c.parentItem() == focused.parentItem())
                self.assertLessEqual(focused.y() + focused.height(), action.y() + 1)
                for prompt in self.named("promptItem"):
                    self.assertGreater(prompt.width(), 0)
                    self.assertLessEqual(prompt.x() + prompt.width(), 1825)
                for label in self.named("promptLabel"):
                    self.assertGreater(label.width(), 0)

    def test_full_settings_list_stays_below_fixed_tabs_and_above_hint(self):
        setting = self.adapter.settings()[0]
        self.adapter.settings = lambda: [dict(setting, id=str(i), label="A long setting label " * 3) for i in range(18)]
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "settings"
        for focus in (0, 8, 17):
            self.nav.focus[self.nav.key()] = focus
            self.publish()
            tabs = self.named("sectionTabs")[0]
            area = self.named("hubList")[0]
            self.assertEqual(tabs.y(), 0)
            for row in self.named("hubRow"):
                self.assertLessEqual(row.y() + row.height() + row.parentItem().y(), area.height() + 1)
            for label in self.named("hubRowLabel"):
                self.assertGreater(label.width(), 0)
                self.assertLessEqual(label.x() + label.width(), label.parentItem().width() - 48)

    def test_overlays_leave_focused_hint_visible_and_drawer_follows_focus(self):
        # Positioners need a visible scene, even with the offscreen platform.
        self.win.show()
        spin()
        self.nav.games = [Game(manifest(f"g{i}"), Fake(manifest(f"g{i}"))) for i in range(20)]
        self.nav.overlay = "drawer"
        for focus in (0, 8, len(self.nav._drawer_items()) - 1):
            with self.subTest(focus=focus):
                self.nav.drawer_focus = focus
                self.publish()
                viewport = self.named("drawerViewport")[0]
                focused = next(row for row in self.named("drawerRow") if row.property("index") == focus)
                self.assertGreaterEqual(focused.y() + focused.parentItem().y(), 0)
                self.assertLessEqual(focused.y() + focused.height() + focused.parentItem().y(), viewport.height())
        mask = self.named("overlayMask")[0]
        panel = self.named("drawerPanel")[0]
        self.assertLessEqual(mask.y() + mask.height(), 972)
        self.assertLessEqual(panel.y() + panel.height(), 972)
        picker = self.named("pickerPanel")[0]
        self.assertLessEqual(picker.y() + picker.height(), 972)
        self.named("pickerMessage")

    def test_reduced_motion_moves_shelf_to_target_without_animation(self):
        self.backend._v["reducedMotion"] = True
        self.backend.viewChanged.emit()
        self.nav.act("right")
        self.backend._v = self.nav.view()
        self.backend._v["reducedMotion"] = True
        self.backend.viewChanged.emit()
        spin(1)
        for content in self.named("shelfContent"):
            tile = content.parentItem()
            index = tile.property("index")
            self.assertAlmostEqual(tile.width(), self.backend._v["shelf"]["tiles"][index]["w"])

    def test_long_replay_detail_stays_above_primary_action(self):
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "replays"
        self.publish()
        detail = self.backend._v["detail"]
        detail["images"] = [QUrl.fromLocalFile(str(Path(UI_DIR) / "assets" / "icon.svg")).toString()] * 2
        for catalog in (Path(UI_DIR).parent / "i18n").glob("*.json"):
            with self.subTest(language=catalog.stem):
                strings = json.loads(catalog.read_text(encoding="utf-8"))
                longest = max(strings.values(), key=len)
                detail["title"] = longest
                detail["lead"] = longest
                self.backend.viewChanged.emit()
                spin(160)
                content = self.named("detailContent")[0]
                primary = self.named("primaryAction")[0]
                self.assertLessEqual(content.y() + content.height(), primary.y() - 8)
                self.assertEqual(primary.property("color"), self.win.property("bone"))

    def test_stage_preserves_geometry_at_1080p_and_150_percent_logical_size(self):
        for width, height in ((1920, 1080), (1280, 720)):
            self.win.setWidth(width)
            self.win.setHeight(height)
            spin()
            stage = self.win.contentItem().childItems()[0]
            self.assertEqual(stage.width(), 1920)
            self.assertEqual(stage.height(), 1080)
            self.assertAlmostEqual(stage.scale(), width / 1920)


if __name__ == "__main__":
    unittest.main()
