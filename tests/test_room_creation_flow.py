"""Room openers reveal a draft; only its Create button sends a creation request."""
import unittest

from test_online_hierarchy import hierarchy_nav


class RoomCreationFlow(unittest.TestCase):
    def setUp(self):
        self.adapter, self.nav = hierarchy_nav()
        self.nav.dry = False
        self.adapter.snapshot["community"]["first_to"] = True

    def activate(self, iid):
        items = self.nav.items()
        self.nav.focus[self.nav.key()] = next(n for n, row in enumerate(items) if row.get("id") == iid)
        self.nav.act("confirm", device="xbox")

    def test_lobby_and_rooms_openers_reveal_every_creation_setting_without_creating(self):
        for chapter, opener in (("lobby", "arcade_create_room"), ("rooms", "room_create_open")):
            with self.subTest(chapter=chapter):
                self.nav.click_chapter(chapter)
                self.activate(opener)
                view = self.nav.view()["online"]
                self.assertEqual(view["chapter"], "rooms")
                self.assertTrue(view["rooms"]["createOpen"])
                self.assertEqual(next(p for p in self.nav.view()["prompts"] if p["action"] == "back")["label"], "Cancel")
                ids = [row["id"] for row in view["rooms"]["draft"]]
                self.assertTrue({"online_room_name", "community_option:size", "community_option:rotation",
                                 "community_option:access", "community_option:hidden", "community_option:first_to"}.issubset(ids))
                self.assertEqual(view["rooms"]["create"]["id"], "community_create")
                self.assertEqual(self.adapter.calls, [])
                self.nav.act("back", device="xbox")
                self.assertEqual(self.nav.view()["online"]["chapter"], chapter)
                self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], opener)

    def test_rooms_section_starts_with_create_then_join_code(self):
        ids = [row["id"] for row in self.nav.items() if row.get("region") == "rooms"]
        self.assertEqual(ids[:2], ["room_create_open", "room_join_code_open"])

    def test_players_and_format_offer_every_requested_value(self):
        self.activate("arcade_create_room")
        items = {row.get("id"): row for row in self.nav.items()}
        self.assertEqual([value for value, _ in items["community_option:size"]["options"]], list(range(2, 9)))
        self.assertEqual([value for value, _ in items["community_option:first_to"]["options"]], list(range(1, 11)))

    def test_missing_adapter_preferences_are_not_replaced_with_fixture_defaults(self):
        self.assertNotIn("first_to", self.adapter.snapshot["community"]["preferences"])
        self.activate("arcade_create_room")
        items = {row.get("id"): row for row in self.nav.items()}
        self.assertIsNone(items["community_option:first_to"]["current"])
        self.assertNotIn("first_to", self.adapter.snapshot["community"]["preferences"])
        self.adapter.snapshot["community"].pop("first_to")
        self.assertNotIn("community_option:first_to", {row.get("id") for row in self.nav.items()})
        self.assertEqual(self.adapter.calls, [])

    def test_join_code_openers_focus_code_and_b_returns_to_opener(self):
        for chapter, opener in (("lobby", "arcade_join_code"), ("rooms", "room_join_code_open")):
            with self.subTest(chapter=chapter):
                self.nav.click_chapter(chapter)
                self.activate(opener)
                view = self.nav.view()["online"]
                self.assertEqual(view["chapter"], "rooms")
                self.assertTrue(view["rooms"]["joinOpen"])
                self.assertEqual(next(p for p in self.nav.view()["prompts"] if p["action"] == "back")["label"], "Cancel")
                self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "online_room_code")
                self.assertEqual(self.adapter.calls, [])
                self.nav.act("back", device="xbox")
                self.assertEqual(self.nav.view()["online"]["chapter"], chapter)
                self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], opener)

    def test_only_explicit_create_submits_once_and_name_enter_only_finishes_editing(self):
        self.activate("arcade_create_room")
        self.assertTrue(self.nav.begin_edit("online_room_name"))
        self.nav.edit_text("online_room_name", "Practice")
        self.nav.finish_edit("online_room_name", True)
        self.assertFalse(any(call == ("online", "community_create") for call in self.adapter.calls))
        self.activate("community_create")
        self.assertEqual(self.adapter.calls.count(("online", "community_create")), 1)

    def test_create_card_renders_without_warnings_at_both_sizes_and_languages(self):
        import os
        from pathlib import Path
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        from PySide6.QtCore import QPointF, QUrl
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from test_ui_loads import FakeBackend, spin, wait_pages
        from test_ui_secondary_polish import scene_items

        app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(__file__).resolve().parents[1] / "openrecomp/ui/fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))
        self.activate("arcade_create_room")
        backend = FakeBackend(self.nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "openrecomp/ui/Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        win = engine.rootObjects()[0]
        win.show()
        try:
            for language in ("en", "de"):
                self.nav.language = language
                backend.refresh()
                for width, height in ((1920, 1080), (1280, 720)):
                    with self.subTest(language=language, size=(width, height)):
                        win.setWidth(width)
                        win.setHeight(height)
                        wait_pages(win)
                        spin()
                        rows = list(scene_items(win.contentItem()))
                        draft = next(item for item in rows if item.objectName() == "roomDraftViewport" and item.isVisible())
                        self.assertGreater(draft.width(), 0)
                        self.assertGreater(draft.height(), 0)
                        self.assertEqual(draft.x(), 0)
                        self.assertTrue(any(item.objectName() == "roomsCreateOpen" and item.isVisible() for item in rows))
                        for iid in ("online_room_name", "community_option:size", "community_option:rotation",
                                    "community_option:access", "community_option:hidden", "community_option:first_to"):
                            matches = []
                            for item in rows:
                                data = item.property("b")
                                data = data.toVariant() if hasattr(data, "toVariant") else data
                                if isinstance(data, dict) and data.get("id") == iid and item.isVisible():
                                    matches.append(item)
                            self.assertTrue(matches, iid)
                            pos = matches[0].mapToItem(draft, QPointF(0, 0))
                            self.assertGreaterEqual(pos.y(), 0, iid)
                            self.assertLessEqual(pos.y() + matches[0].height(), draft.height() + 1, iid)
            self.assertEqual(warnings, [])
        finally:
            win.close()


if __name__ == "__main__":
    unittest.main()
