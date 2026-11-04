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
                        if not row.property("r").toVariant().get("heading"):
                            self.assertGreaterEqual(row.height(), 44)
                    viewport = self.named("sessionViewport")[0]
                    self.assertLessEqual(viewport.y() + viewport.height(), card.height())
                    for label in self.named("sessionRowLabel"):
                        self.assertGreater(label.width(), 0)
                    if section == "replays":
                        self.assertEqual(len(self.named("replayTableCell")) % 5, 0)
                        for cell in self.named("replayTableCell"):
                            self.assertGreater(cell.width(), 0)
                            self.assertLessEqual(cell.x() + cell.width(), cell.parentItem().width() + 1)

    def test_720_rows_keep_physical_targets_and_wrap_long_empty_guidance(self):
        self.win.setWidth(1280)
        self.win.setHeight(720)
        self.nav.sec[self.nav.game.id] = "controls"
        self.nav.text_size = 130
        for language in ("en", "de", "fr", "pt-BR"):
            self.nav.language = language
            self.publish()
            for row in self.named("sessionRow"):
                if not row.property("r").toVariant().get("heading"):
                    self.assertGreaterEqual(row.height() * 2 / 3, 44)
            for label in self.named("sessionRowLabel"):
                if label.isVisible():
                    self.assertFalse(label.property("truncated"), label.property("text"))
                    self.assertGreaterEqual(label.property("font").pixelSize() * 2 / 3, 18)

    def test_control_heading_height_tracks_viewport_scaled_font(self):
        self.adapter.controls = lambda: [dict(id="pad1", label="Sample controller - Player 1",
            slots=[dict(id="cross", label="Cross", value="A")])]
        self.nav.sec[self.nav.game.id] = "controls"
        self.nav.text_size = 130
        self.win.setWidth(1280)
        self.win.setHeight(720)
        self.publish()
        for label in self.named("sessionHeadingLabel"):
            if label.isVisible():
                self.assertLessEqual(label.property("contentHeight"), label.height() + 1)

    def test_login_guest_labels_wrap_and_pad_focus_reveals_lower_fields(self):
        from tools.ui_shots import scene, snapshot
        self.win.setWidth(1280)
        self.win.setHeight(720)
        for language in ("es", "fr", "pt-BR"):
            self.nav = scene("login", language)
            self.nav.text_size = 130
            self.backend.nav = self.nav
            self.backend._v = snapshot(self.nav, "login")
            self.backend.viewChanged.emit()
            wait_pages(self.win)
            spin(30)
            for label in self.named("loginButtonLabel"):
                if label.isVisible():
                    self.assertFalse(label.property("truncated"), label.property("text"))
                    self.assertLessEqual(label.property("contentWidth"), label.width() + 1)
                    self.assertLessEqual(label.property("contentHeight"), label.height() + 1)
            items = self.nav.items()
            server = next(index for index, item in enumerate(items) if item.get("id") == "online_server")
            self.nav.focus[self.nav.key()] = server
            self.backend._v = snapshot(self.nav, "login")
            self.backend.viewChanged.emit()
            spin(30)
            viewport = self.named("loginViewport")[0]
            self.assertGreater(viewport.property("contentY"), 0)

    def test_disconnect_login_links_and_guest_heading_fit_accessibility_sizes(self):
        from tools.online_shots import scene, snapshot, geometry
        self.win.setWidth(1280)
        self.win.setHeight(720)
        for language in ("de", "es", "fr", "pt-BR"):
            for text_size in (115, 130):
                self.nav = scene("t5", "disconnect_retry", language, text_size=text_size, high_contrast=True)
                self.backend.nav = self.nav
                self.backend._v = snapshot(self.nav)
                self.backend.viewChanged.emit()
                wait_pages(self.win)
                spin(20)
                with self.subTest(language=language, text_size=text_size):
                    self.assertEqual(geometry(self.win)[0], [])
                    for button in self.named("loginButton"):
                        if button.isVisible():
                            self.assertGreaterEqual(button.height() * 2 / 3, 44)
                    for label in self.named("loginLinkLabel") + self.named("loginGuestTitle"):
                        if label.isVisible():
                            self.assertFalse(label.property("truncated"))
                            self.assertLessEqual(label.property("contentWidth"), label.width() + 1)

    def test_recovery_native_fields_do_not_overlap_at_720_large_text(self):
        from PySide6.QtCore import QPointF
        from tools.online_shots import scene, snapshot
        self.nav = scene("t5", "disconnect_retry", "fr", text_size=130)
        self.nav.game.a.snapshot["capabilities"]["account_recovery"] = True
        self.nav.login_page = {"t5": "recover"}
        self.backend.nav = self.nav
        self.win.setWidth(1280)
        self.win.setHeight(720)
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(20)
        viewport = self.named("loginViewport")[0]
        fields = [field for field in self.named("editableField") if field.isVisible()
                  and field.property("field").toVariant().get("fieldId") in
                  ("online_recovery_code", "online_new_password", "online_repeat_password")]
        self.assertEqual(len(fields), 3)
        bounds = sorted((field.mapToItem(viewport, QPointF()).y(), field.height()) for field in fields)
        for (top, height), (next_top, _) in zip(bounds, bounds[1:]):
            self.assertGreaterEqual(next_top, top + height + 4)

    def test_ranking_headings_pin_at_viewport_top_when_scrolling(self):
        from tools.online_shots import scene, snapshot
        from PySide6.QtCore import QPointF
        self.nav = scene("t5", "leaderboard", "de", text_size=130)
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(30)
        header = self.named("rankingPinnedHeadings")[0]
        viewport = header.parentItem().parentItem()
        viewport.setProperty("contentY", 1000)
        spin(20)
        self.assertTrue(header.isVisible())
        self.assertAlmostEqual(header.mapToItem(viewport, QPointF()).y(), 0)
        self.assertGreater(header.height(), 0)

    def test_720_leaderboard_opens_with_headings_and_complete_records_at_every_text_size(self):
        from tools.online_shots import scene, snapshot
        from PySide6.QtCore import QPointF
        self.win.setWidth(1280)
        self.win.setHeight(720)
        for language in i18n.LANGUAGES:
            for text_size in (100, 115, 130):
                self.nav = scene("t5", "leaderboard", language, text_size=text_size)
                self.backend.nav = self.nav
                self.backend._v = snapshot(self.nav)
                self.backend.viewChanged.emit()
                wait_pages(self.win)
                spin(20)
                with self.subTest(language=language, text_size=text_size):
                    viewport = self.named("rankingPinnedHeadings")[0].parentItem().parentItem()
                    headings = self.named("rankingColumnHeadings")[0]
                    heading_top = headings.mapToItem(viewport, QPointF()).y()
                    self.assertGreaterEqual(heading_top, 0)
                    self.assertLessEqual(heading_top + headings.height(), viewport.height())
                    complete = [row for row in self.named("rankingRow") if row.isVisible()
                                and row.mapToItem(viewport, QPointF()).y() >= 0
                                and row.mapToItem(viewport, QPointF()).y() + row.height() <= viewport.height()]
                    self.assertGreaterEqual(len(complete), 1)
                    controls = self.named("rankingCompactControls")[0]
                    projected = self.nav.view()["online"]["leaderboard"]
                    expected = projected["controls"] + projected["buttons"] + projected["sorts"]
                    row = controls.childItems()[0].childItems()[0]
                    actual = [item.property("b").toVariant()["index"] for item in row.childItems()
                              if item.property("b") is not None]
                    self.assertEqual(actual, [item["index"] for item in expected])

    def test_compact_leaderboard_pad_focus_reveals_last_filter(self):
        from tools.online_shots import scene, snapshot
        from PySide6.QtCore import QPointF
        self.win.setWidth(1280)
        self.win.setHeight(720)
        self.nav = scene("t5", "leaderboard", "de", text_size=130)
        self.backend.nav = self.nav
        board = self.nav.view()["online"]["leaderboard"]
        last = (board["controls"] + board["buttons"] + board["sorts"])[-1]
        self.nav.focus[self.nav.key()] = last["index"]
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(30)
        viewport = self.named("rankingCompactControls")[0]
        row = viewport.childItems()[0].childItems()[0]
        target = next(item for item in row.childItems() if item.property("b") is not None
                      and item.property("b").toVariant()["index"] == last["index"])
        self.assertGreater(viewport.property("contentX"), 0, (last, target.property("b").toVariant(), viewport.width(), row.width(), target.x(), target.width()))
        self.assertGreaterEqual(target.mapToItem(viewport, QPointF()).x(), -1)
        self.assertLessEqual(target.mapToItem(viewport, QPointF()).x() + target.width(), viewport.width() + 1)

    def test_joined_room_shows_numbered_queue_on_entry_at_both_sizes(self):
        from tools.online_shots import scene, snapshot
        from PySide6.QtCore import QPointF
        for text_size in (100, 130):
            for width, height in ((1920, 1080), (1280, 720)):
                self.nav = scene("t5", "community_room", "de", text_size=text_size)
                self.backend.nav = self.nav
                self.backend._v = snapshot(self.nav)
                self.backend.viewChanged.emit()
                self.win.setWidth(width)
                self.win.setHeight(height)
                wait_pages(self.win)
                spin(30)
                header = self.named("communityRoomName")[0]
                self.assertEqual(header.property("text"), "Evening practice")
                self.assertTrue(header.isVisible())
                viewport = self.named("communityRoomViewport")[0]
                queue = self.named("communityQueueRow")
                self.assertEqual([(row.property("b").toVariant()["label"], row.property("b").toVariant()["value"]) for row in queue],
                                 [("Rival", "1"), ("Me", "2"), ("Player 6", "3")])
                for row in queue:
                    top = row.mapToItem(viewport, QPointF()).y()
                    self.assertGreaterEqual(top, 0)
                    self.assertLessEqual(top + row.height(), viewport.height() + 1)
                primary = next(item for item in self.named("onlinePrimaryButton") if item.isVisible())
                self.assertEqual(primary.property("b").toVariant()["id"], "community_sit_out")
                self.assertGreaterEqual(primary.height() * width / 1920, 44)

    def test_large_spanish_room_sort_reflows_above_browser_rows(self):
        from tools.online_shots import scene, snapshot
        for width, height in ((1920, 1080), (1280, 720)):
            self.nav = scene("t5", "rooms", "es", text_size=130, high_contrast=True)
            self.backend.nav = self.nav
            self.backend._v = snapshot(self.nav)
            self.backend.viewChanged.emit()
            self.win.setWidth(width)
            self.win.setHeight(height)
            wait_pages(self.win)
            spin(30)
            actions = self.named("roomBrowserActions")[0]
            browser = self.named("roomBrowserRows")[0]
            buttons = [item for item in actions.childItems() if item.property("b") is not None]
            self.assertEqual(len(buttons), 2)
            for button in buttons:
                self.assertGreater(button.width(), 0)
                self.assertGreater(button.height(), 0)
                self.assertLessEqual(button.x() + button.width(), actions.width() + 1)
                self.assertLessEqual(button.y() + button.height(), actions.height() + 1)
            self.assertGreaterEqual(browser.y(), actions.y() + actions.height() + 8)

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

