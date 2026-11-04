"""A single art-free chat dock survives Online pages and the logged-in main menu."""
import unittest

from tools.online_shots import scene, snapshot


class PersistentChat(unittest.TestCase):
    def test_all_online_chapters_and_match_phases_project_the_same_conversation(self):
        nav = scene("t5", "private_chat", "en")
        selected = nav.game.a.snapshot["private_chat"]["selected"]
        for chapter in ("lobby", "rooms", "friends", "leaderboard", "profile", "stats", "tournaments", "spectating", "account"):
            with self.subTest(chapter=chapter):
                nav.click_chapter(chapter)
                page = nav.view()["online"]
                self.assertTrue(page["chatDocked"])
                self.assertTrue(page["chat"]["open"])
                self.assertEqual(page["chat"]["conversation"], selected)
                self.assertTrue(page["chat"]["compose"])
        for phase in ("matched", "starting", "playing", "result", "result_sent"):
            with self.subTest(phase=phase):
                nav.game.a.snapshot["phase"] = phase
                page = nav.view()["online"]
                self.assertTrue(page["chatDocked"])
                self.assertEqual(page["chat"]["conversation"], selected)
                self.assertTrue(page["chat"]["compose"])
                self.assertFalse(any(row.get("id") == "online_private_chat" for row in page["lines"]))

    def test_lobby_collapse_persists_to_chapters_and_main_menu(self):
        nav = scene("t5", "mentions", "en")
        nav._chat_set_open(nav.game, False)
        self.assertFalse(nav.view()["online"]["chat"]["open"])
        self.assertEqual([nav.items()[n]["id"] for n in nav._visible_chat_rows(nav.items(), 0)], ["chat_toggle"])
        nav.click_chapter("rooms")
        self.assertFalse(nav.view()["online"]["chat"]["open"])
        nav.open_main_menu()
        self.assertFalse(nav.view()["online"]["chat"]["open"])
        nav.act("x", device="xbox")
        self.assertTrue(nav.view()["online"]["chat"]["open"])
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "online_chat")
        nav.act("back", device="xbox")
        self.assertTrue(nav.view()["mainMenu"]["show"])
        nav.act("back", device="xbox")
        self.assertEqual(nav.screen, "start")

    def test_main_menu_chat_supports_native_edit_and_send_without_leaving_menu(self):
        nav = scene("t5", "home", "en")
        nav.dry = False
        self.assertTrue(nav.view()["online"]["chatDocked"])
        self.assertTrue(nav.begin_edit("online_chat"))
        self.assertTrue(nav.edit_text("online_chat", "hello"))
        self.assertTrue(nav.finish_edit("online_chat", True))
        self.assertTrue(nav.view()["mainMenu"]["show"])
        self.assertEqual(nav.game.a.calls.count(("online", "send_chat")), 1)

    def test_match_card_pad_exits_chat_and_reaches_ready_without_starting_match(self):
        from pad_step import pad_step
        nav = scene("t4", "mentions", "en")
        nav.act("x", device="xbox")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["region"], "chat")
        nav.game.a.snapshot["phase"] = "matched"
        for _ in range(12):
            rows = nav.items()
            target = next(n for n, row in enumerate(rows) if row.get("id") == "start_match")
            if nav.focus_index(rows) == target:
                break
            pad_step(nav, target)
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "start_match")
        nav.act("x", device="xbox")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["region"], "chat")
        nav.act("x", device="xbox")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "start_match")
        self.assertEqual(nav.game.a.calls, [])


class PersistentChatScene(unittest.TestCase):
    from test_ui_polish import ScenePolish
    setUpClass = classmethod(ScenePolish.setUpClass.__func__)
    setUp = ScenePolish.setUp
    tearDown = ScenePolish.tearDown
    named = ScenePolish.named
    wait_pages = ScenePolish.wait_pages

    def test_secondary_fields_and_tables_are_dense_with_scaled_readable_hierarchy(self):
        from pathlib import Path
        from PySide6.QtCore import QUrl
        from PySide6.QtQml import QQmlComponent
        from openrecomp.app import UI_DIR
        from test_ui_loads import spin
        from test_ui_polish import items
        component = QQmlComponent(self.engine)
        component.setData(b'''import QtQuick
Item {
    width: 640; height: 400
    OnlineStyle.PageTitle { objectName: "densityTitle"; text: "Title" }
    OnlineStyle.SectionHeader { objectName: "densitySection"; text: "Section" }
    OnlineStyle.FieldRow { objectName: "densityField"; width: 600; b: ({label: "Name", value: "Value"}) }
    OnlineStyle.Table { objectName: "densityTable"; width: 600; columns: [{w: 1}]; line: ({kind: "row", cells: [{text: "Player"}]}) }
}''', QUrl.fromLocalFile(str(Path(UI_DIR) / "DensityProbe.qml")))
        self.assertFalse(component.isError(), component.errorString())
        probe = component.create()
        self.assertIsNotNone(probe, component.errorString())
        try:
            for width, height in ((1920, 1080), (1280, 720)):
                self.win.setWidth(width)
                self.win.setHeight(height)
                for percent in (100, 115, 130):
                    self.nav.text_size = percent
                    self.backend.refresh()
                    spin(10)
                    visible = [item for item in items(probe) if item.isVisible()]
                    named = {item.objectName(): item for item in visible if item.objectName()}
                    title = named["densityTitle"].property("font").pixelSize()
                    section = named["densitySection"].property("font").pixelSize()
                    label = next(item for item in visible if item.objectName() == "onlineFieldLabel")
                    self.assertGreater(title, section)
                    self.assertGreater(section, label.property("font").pixelSize())
                    for item in visible:
                        if item.property("text") and item.property("font") is not None:
                            self.assertGreaterEqual(item.property("font").pixelSize() * width / 1920,
                                                    14 * percent / 100 - .5)
                    if width == 1920 and percent == 100:
                        self.assertGreaterEqual(named["densityField"].height(), 48)
                        self.assertLess(named["densityField"].height(), 64)
                        self.assertGreaterEqual(named["densityTable"].height(), 44)
                        self.assertLess(named["densityTable"].height(), 64)
        finally:
            probe.deleteLater()
            spin(1)

    def test_chat_instance_and_history_position_survive_page_switches(self):
        from test_ui_loads import spin
        self.nav = scene("t5", "chat_history", "en")
        self.backend.nav = self.nav
        def publish():
            self.backend._v = snapshot(self.nav)
            self.backend.viewChanged.emit()
            self.wait_pages()
            spin(30)
        publish()
        dock = next(item for item in self.named("lobbyChatPane") if item.y() == 8)
        history = next(item for item in self.named("lobbyChatHistory") if item.parentItem() == dock)
        dock.setProperty("following", False)
        history.setProperty("contentY", 40)
        for chapter in ("rooms", "friends", "profile", "stats", "account"):
            self.nav.click_chapter(chapter)
            publish()
            self.assertIs(next(item for item in self.named("lobbyChatPane") if item.y() == 8), dock)
            self.assertTrue(dock.isVisible())
            self.assertEqual(history.property("contentY"), 40)
            self.assertGreater(dock.height(), 700)
            hub = self.named("onlineHub")[0]
            self.assertEqual(hub.y(), 0)
            self.assertEqual(hub.height(), hub.parentItem().parentItem().height())
        self.nav.open_main_menu()
        publish()
        self.assertIs(next(item for item in self.named("lobbyChatPane") if item.y() == 8), dock)
        self.assertTrue(dock.isVisible())
        self.assertEqual(history.property("contentY"), 40)


if __name__ == "__main__":
    unittest.main()
