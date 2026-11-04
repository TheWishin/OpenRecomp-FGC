"""Synthetic section cards keep focused rows and translated table cells in bounds."""
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
from openrecomp.nav import Game, Nav
from test_controls_nav import ControlsFake
from test_support_nav import SupportFake
from test_ui_loads import FakeBackend, spin, wait_pages


def scene_items(parent):
    for child in parent.childItems():
        yield child
        yield from scene_items(child)


class SecondaryCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.adapter = ControlsFake()
        support = SupportFake()
        self.support = support
        self.adapter.support_available = support.support_available
        self.adapter.support_state = support.support_state
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.dry = True
        self.nav.screen = "hub"
        self.backend = FakeBackend(self.nav)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties({"backend": self.backend, "wantFull": False})
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
        found = [item for item in scene_items(self.win.contentItem()) if item.objectName() == name]
        self.assertTrue(found, name)
        return found

    def publish(self):
        self.backend._v = self.nav.view()
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(30)

    def test_all_catalogs_fit_compact_sections_and_table(self):
        for language in i18n.LANGUAGES:
            for section in ("play", "replays", "controls", "support"):
                with self.subTest(language=language, section=section):
                    self.nav.language = language
                    self.nav.sec[self.nav.game.id] = section
                    self.publish()
                    card = self.named("sessionCard")[0]
                    rows = self.named("sessionRows")[0]
                    for row in self.named("sessionRow"):
                        self.assertGreater(row.height(), 0)
                        self.assertLessEqual(rows.y() + row.y() + row.height(), card.height())
                    for label in self.named("sessionRowLabel"):
                        self.assertGreater(label.width(), 0)
                    if section == "replays":
                        self.assertEqual(len(self.named("replayTableCell")) % 5, 0)
                        for cell in self.named("replayTableCell"):
                            self.assertGreater(cell.width(), 0)
                            self.assertLessEqual(cell.x() + cell.width(), cell.parentItem().width() + 1)

    def test_report_error_and_loading_remain_visible_inside_the_card(self):
        self.nav.sec[self.nav.game.id] = "support"
        self.support.state.update(error="Synthetic connection failed", running=True, operation="report")
        self.publish()
        error = self.named("sessionError")[0]
        self.assertEqual(error.property("text"), "Synthetic connection failed")
        self.assertTrue(error.isVisible())
        busy = self.named("sessionBusy")[0]
        self.assertTrue(busy.isVisible())
        self.assertFalse(self.named("primaryAction")[0].isVisible())

    def test_dialog_is_a_bounded_card_with_focused_safe_answer(self):
        self.nav.act("back")
        self.nav.act("back")
        self.publish()
        card = self.named("dialogCard")[0]
        self.assertLessEqual(card.y() + card.height(), 972)
        options = self.named("dialogOption")
        self.assertTrue(options[0].property("o").toVariant()["focused"])
        for option in options:
            self.assertLessEqual(option.x() + option.width(), option.parentItem().parentItem().width())
        self.assertLess(card.height(), 700)


if __name__ == "__main__":
    unittest.main()

