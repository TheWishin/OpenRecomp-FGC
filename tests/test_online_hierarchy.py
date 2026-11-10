"""Online hierarchy and controller reachability use synthetic adapters only."""
import re
from pathlib import Path
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from openrecomp.nav_online_layout import CHAPTERS, MERGED_INTO
from pad_step import pad_step
from test_online_nav import Lobby
from test_online_page import lobby_snapshot


UI = Path(__file__).resolve().parents[1] / "openrecomp" / "ui"
COMPONENTS = ("PageTitle", "SectionHeader", "FieldLabel", "Value", "HelpText",
              "PrimaryButton", "SecondaryButton", "Chip", "Table")


def hierarchy_nav(language="en", t4=False):
    adapter = Lobby()
    adapter.m.update(id="t4" if t4 else "sample", adapter="t4" if t4 else "t5dr")
    adapter.snapshot.update(lobby_snapshot())
    adapter.snapshot["capabilities"].update(
        private_rooms=True, friends=True, profiles=True, leaderboard=True, community_stats=True,
        community=True, room_tables=True, tournaments=True, spectating=True,
        account_tools=True, account_blocks=True, t4_lobby=t4, ranked=not t4, strict=not t4)
    adapter.snapshot.update(
        community=dict(preferences=dict(size=4, rotation="winner", access="none", hidden=False, mode="line")),
        friends=[dict(name="Friend", status="online", invite=True)],
        tournaments=dict(rows=[dict(id="sample", name="Weekly event", state="signup")]),
        spectating=dict(targets=[dict(kind="room", id="spec_watch:sample", name="Open room")]))
    adapter.texts.update(online_room_name="Sample room", online_room_password="never-show-this",
                         online_room_code="ABC123", online_friend_name="Friend",
                         online_current_password="never-show-this")
    nav = Nav([Game(adapter.m, adapter)], language=language)
    nav.dry = True
    nav.screen = "hub"
    nav.sec[adapter.m["id"]] = "online"
    return adapter, nav


class SharedOnlineHierarchy(unittest.TestCase):
    def test_requested_components_have_one_shared_definition(self):
        definitions = {name: [] for name in COMPONENTS}
        for source in UI.glob("*.qml"):
            text = source.read_text(encoding="utf-8")
            for name in COMPONENTS:
                if re.search(r"\bcomponent\s+" + name + r"\s*:", text):
                    definitions[name].append(source.name)
        for name, files in definitions.items():
            with self.subTest(component=name):
                self.assertEqual(files, ["OnlineStyle.qml"])

    def test_online_screens_use_the_shared_scale(self):
        for name in ("OnlineBody.qml", "OnlineCard.qml"):
            source = (UI / name).read_text(encoding="utf-8")
            with self.subTest(screen=name):
                self.assertIn("OnlineStyle.PageTitle", source)
                self.assertIn("OnlineStyle.FieldLabel", source)
                self.assertIn("OnlineStyle.HelpText", source)

    def test_all_chapters_keep_pad_reachability_in_all_catalogs_for_both_games(self):
        for language in i18n.LANGUAGES:
            for t4 in (False, True):
                adapter, nav = hierarchy_nav(language, t4)
                self.assertEqual({c["id"] for c in nav.view()["online"]["chapters"]}, set(CHAPTERS) - set(MERGED_INTO))
                for chapter in CHAPTERS:
                    nav.click_chapter(chapter)
                    page = nav.view()["online"]
                    self.assertEqual(page["chapter"], MERGED_INTO.get(chapter, chapter))
                    self.assertTrue(page["body"]["title"])
                    targets = [it["id"] for it in nav.items()
                               if it.get("region") == chapter and it.get("kind") != "heading"]
                    for iid in targets:
                        with self.subTest(language=language, t4=t4, chapter=chapter, row=iid):
                            for _ in range(len(nav.items()) * 2):
                                rows = nav.items()
                                target = next(n for n, row in enumerate(rows) if row.get("id") == iid)
                                if nav.focus_index(rows) == target:
                                    break
                                pad_step(nav, target)
                            else:
                                self.fail("Controller could not reach " + iid)
                            self.assertEqual(nav.view()["online"]["chapter"], chapter)
                            self.assertNotIn("never-show-this", str(nav.view()))
                self.assertEqual(adapter.calls, [])


class OnlineHierarchyProjection(unittest.TestCase):
    def setUp(self):
        self.adapter, self.nav = hierarchy_nav()

    def page(self, chapter):
        if chapter in ("profile", "leaderboard", "stats"):
            self.nav._t5_profile_pages = {self.nav.game.id: chapter}
        self.nav.click_chapter(chapter)
        return self.nav.view()["online"]

    @staticmethod
    def indices(value):
        if isinstance(value, dict):
            if isinstance(value.get("index"), int):
                yield value["index"]
            for child in value.values():
                yield from OnlineHierarchyProjection.indices(child)
        elif isinstance(value, list):
            for child in value:
                yield from OnlineHierarchyProjection.indices(child)

    def test_sections_retain_every_account_row_beyond_the_old_page_limit(self):
        self.adapter.snapshot["blocks"] = [dict(name="Player " + str(n)) for n in range(30)]
        page = self.page("account")
        rows = self.nav.items()
        expected = {n for n, row in enumerate(rows)
                    if row.get("region") == "profile" and row.get("kind") != "heading"}
        self.assertGreater(len(expected), 13)
        self.assertEqual(set(self.indices(page["body"]["sections"])), expected)
        self.assertLess(len(page["body"]["lines"]), len(expected))
        self.assertTrue(all(section["title"] and section["lines"] for section in page["body"]["sections"]))

    def test_focused_actions_remain_in_the_card_projection_for_every_chapter(self):
        for chapter in CHAPTERS:
            self.page(chapter)
            rows = self.nav.items()
            for index, row in enumerate(rows):
                if row.get("region") != chapter or row.get("kind") == "heading":
                    continue
                with self.subTest(chapter=chapter, row=row.get("id")):
                    self.nav.focus[self.nav.key()] = index
                    page = self.nav.view()["online"]
                    projection = page["rooms"] if chapter == "rooms" else page["body"]["sections"]
                    self.assertIn(index, set(self.indices(projection)))
        self.assertEqual(self.adapter.calls, [])

    def test_fields_keep_labels_values_and_localized_help_separate(self):
        self.page("account")
        page = self.nav.view()["online"]
        rows = [line for section in page["body"]["sections"] for line in section["lines"]]
        field = next(line for line in rows if line.get("id") == "online_current_password")
        self.assertEqual(field["label"], i18n.text("en", "online120.current_password"))
        self.assertEqual(field["value"], "\u2022" * len("never-show-this"))
        self.assertTrue(field["hint"])
        self.assertNotEqual(field["hint"], field["label"])
        self.assertNotIn("never-show-this", str(page))

    def test_room_browser_columns_and_selected_join_use_existing_rows(self):
        self.adapter.snapshot["rooms"] = [
            dict(id="r1", name="Room", players=["p1", "p2"], size=4,
                 mode="tables", lock="password", ping=42, ping_measured=True)]
        self.page("rooms")
        index = next(n for n, row in enumerate(self.nav.items()) if row.get("id") == "join_room:r1")
        self.nav.focus_online_row(index)
        rooms = self.nav.view()["online"]["rooms"]
        header, row = rooms["browser"]
        self.assertEqual(len(header["cols"]), 5)
        self.assertAlmostEqual(sum(col["w"] for col in header["cols"]), 1.0)
        self.assertEqual([cell["text"] for cell in row["cells"]][:3],
                         ["Room", "2 / 4", i18n.text("en", "online.room_tables_mode")])
        self.assertTrue(row["cells"][3]["hint"])
        self.assertEqual(row["cells"][4]["text"], "42 ms")
        self.assertTrue(row["focused"])
        self.assertEqual(row["buttons"][0]["index"], index)
        self.assertEqual(row["buttons"][0]["id"], "join_room:r1")

    def test_empty_room_browser_and_invite_card_are_separate(self):
        self.adapter.snapshot["rooms"] = []
        rooms = self.page("rooms")["rooms"]
        self.assertEqual(rooms["browser"], [])
        self.assertIn("create", rooms["empty"]["label"].lower())
        self.assertEqual([field["id"] for field in rooms["invite"]], ["online_room_code", "join_room_code"])
        self.assertNotIn("online_room_code", [field["id"] for field in rooms["draft"]])

    def test_single_primary_preserves_each_existing_creation_callback(self):
        self.nav.dry = False
        for iid in ("create_room", "create_password_room", "create_code_room", "community_create"):
            self.page("rooms")
            index = next(n for n, row in enumerate(self.nav.items()) if row.get("id") == iid)
            self.nav.focus_online_row(index)
            primary = self.nav.view()["online"]["rooms"]["create"]
            self.assertEqual(primary["index"], index)
            self.assertEqual(primary["id"], iid)
            self.assertEqual(primary["label"], i18n.text("en", "online_hierarchy.create_room"))
            self.nav.act("confirm", device="xbox")
            self.assertEqual(self.adapter.calls[-1], ("online", iid))

    def test_room_pointer_selection_never_submits_and_rejects_other_regions(self):
        rows = self.nav.items()
        room = next(n for n, row in enumerate(rows) if row.get("id") == "create_password_room")
        foreign = next(n for n, row in enumerate(rows) if row.get("id") == "search_casual")
        self.nav.focus_online_row(room)
        self.assertEqual(self.nav.focus_index(self.nav.items()), room)
        for index in (-1, len(rows), foreign):
            self.nav.focus_online_row(index)
            self.assertEqual(self.nav.focus_index(self.nav.items()), room)
        self.assertEqual(self.adapter.calls, [])
        self.nav.screen = "start"
        another = next(n for n, row in enumerate(rows) if row.get("id") == "create_room")
        self.nav.focus_online_row(another)
        self.assertEqual(self.nav.focus_index(self.nav.items()), room)
        self.assertEqual(self.adapter.calls, [])

    def test_access_segments_use_existing_option_setter_and_dry_guard(self):
        next(row for row in self.nav.items() if row.get("id") == "room_advanced")["run"]()
        rows = self.nav.items()
        index = next(n for n, row in enumerate(rows) if row.get("id") == "community_option:access")
        foreign = next(n for n, row in enumerate(rows) if row.get("id") == "community_option:size")
        self.nav.select_online_option(index, 1)
        self.assertEqual(self.adapter.calls, [])
        self.nav.dry = False
        for option in (-1, 3):
            self.nav.select_online_option(index, option)
        self.nav.select_online_option(foreign, 0)
        self.assertEqual(self.adapter.calls, [])
        self.nav.select_online_option(index, 2)
        self.assertEqual(self.adapter.calls, [("online", "community_option:access:code")])
        self.nav.screen = "start"
        self.nav.select_online_option(index, 0)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_legacy_creation_mode_is_visible_and_draft_selection_restores_community_creation(self):
        self.page("rooms")
        rows = self.nav.items()
        access = next(n for n, row in enumerate(rows) if row.get("id") == "community_option:access")
        for iid, selected in (("create_room", 0), ("create_password_room", 1), ("create_code_room", 2)):
            index = next(n for n, row in enumerate(rows) if row.get("id") == iid)
            self.nav.focus_online_row(index)
            rooms = self.nav.view()["online"]["rooms"]
            segments = next(row["segments"] for row in rooms["draft"] if row["id"] == "community_option:access")
            self.assertEqual([n for n, segment in enumerate(segments) if segment["selected"]], [selected])
            self.assertEqual(rooms["create"]["id"], iid)
        self.nav.select_online_option(access, 1)
        self.assertEqual(self.nav.view()["online"]["rooms"]["create"]["id"], "community_create")
        self.assertEqual(self.adapter.calls, [])

    def test_watch_stays_on_selected_room_row_and_calls_the_existing_spectating_action(self):
        self.adapter.snapshot["spectating"]["targets"] = [
            dict(kind="room", id="spec_watch_room:r1", name="Open room")]
        self.page("rooms")
        rows = self.nav.items()
        join = next(n for n, row in enumerate(rows) if row.get("id") == "join_room:r1")
        watch = next(n for n, row in enumerate(rows) if row.get("id") == "room_watch:r1")
        self.assertIn("spec_watch_room:r1", [row.get("id") for row in rows])
        self.nav.focus_online_row(join)
        self.nav.act("right", device="xbox")
        self.assertEqual(self.nav.focus_index(self.nav.items()), watch)
        rooms = self.nav.view()["online"]["rooms"]
        table_row = next(line for line in rooms["browser"] if line["kind"] == "trow")
        self.assertTrue(table_row["focused"])
        self.assertEqual([button["id"] for button in table_row["buttons"]], ["join_room:r1", "room_watch:r1"])
        self.assertNotIn(watch, set(self.indices(rooms["other"])))
        self.nav.act("left", device="xbox")
        self.assertEqual(self.nav.focus_index(self.nav.items()), join)
        self.nav.act("right", device="xbox")
        self.nav.dry = False
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.adapter.calls[-1], ("online", "spec_watch_room:r1"))

    def test_room_pointer_helpers_ignore_modal_overlays_and_stale_row_indices(self):
        self.page("rooms")
        rows = self.nav.items()
        access = next(n for n, row in enumerate(rows) if row.get("id") == "community_option:access")
        create = next(n for n, row in enumerate(rows) if row.get("id") == "create_room")
        before = self.nav.focus_index(rows)
        self.nav.dry = False
        self.nav.overlay = "drawer"
        self.nav.focus_online_row(create)
        self.nav.select_online_option(access, 1)
        self.assertEqual(self.nav.focus_index(self.nav.items()), before)
        self.assertEqual(self.adapter.calls, [])
        self.nav.overlay = None
        self.adapter.snapshot["players"].insert(0, dict(id="new", name="New player"))
        self.nav.select_online_option(access, 2)
        self.assertEqual(self.adapter.calls, [])
        rows = self.nav.items()
        create = next(n for n, row in enumerate(rows) if row.get("id") == "create_room")
        self.adapter.snapshot["players"].insert(0, dict(id="newer", name="Another new player"))
        self.nav.focus_online_row(create)
        self.assertNotEqual(self.nav.focus_index(self.nav.items()), create)

    def test_room_order_matches_browser_then_draft_then_invite(self):
        next(row for row in self.nav.items() if row.get("id") == "room_advanced")["run"]()
        ids = [row.get("id") for row in self.nav.items() if row.get("region") == "rooms"]
        order = ["refresh_rooms", "join_room:r1", "online_room_name", "community_option:size",
                 "online_room_password", "create_room", "online_room_code", "join_room_code"]
        self.assertEqual(sorted(order, key=ids.index), order)
        self.assertEqual(len(ids), len(set(ids)))

    def test_access_pointer_errors_use_the_same_guard_as_controller_actions(self):
        from unittest.mock import Mock
        self.page("rooms")
        self.nav.dry = False
        self.adapter.online_action = Mock(side_effect=RuntimeError("@online.disconnected"))
        index = next(n for n, row in enumerate(self.nav.items()) if row.get("id") == "community_option:access")
        self.nav.select_online_option(index, 1)
        self.adapter.online_action.assert_called_once_with("community_option:access:password")
        self.assertTrue(self.nav.toast)

    def test_find_groups_keep_each_option_once_and_separate_captions(self):
        find = self.page("lobby")["find"]
        options = find["options"]
        grouped = [option for group in find["groups"] for option in group["options"]]
        self.assertEqual({option["id"] for option in grouped}, {option["id"] for option in options})
        self.assertEqual(len(grouped), len(options))
        self.assertTrue(all(group["label"] for group in find["groups"]))
        self.assertNotIn(find["ranked"]["id"], {option["id"] for option in grouped})
        self.assertNotIn(find["quick"]["id"], {option["id"] for option in grouped})


class OnlineHierarchyScene(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (UI / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def test_titles_fields_and_help_have_distinct_sizes_in_both_viewports(self):
        from PySide6.QtCore import QPointF, QUrl
        from PySide6.QtQml import QQmlApplicationEngine
        from test_ui_loads import FakeBackend, spin, wait_pages
        from test_ui_polish import items

        adapter, nav = hierarchy_nav()
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(QUrl.fromLocalFile(str(UI / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        win = engine.rootObjects()[0]
        win.show()
        try:
            wait_pages(win)
            for width, height in ((1920, 1080), (1280, 720)):
                win.setWidth(width)
                win.setHeight(height)
                for language in i18n.LANGUAGES:
                    nav.language = language
                    for chapter in CHAPTERS:
                        with self.subTest(width=width, language=language, chapter=chapter):
                            nav._t5_profile_pages = {nav.game.id: chapter}
                            nav.click_chapter(chapter)
                            backend._v = nav.view()
                            backend._v["reducedMotion"] = True
                            backend.viewChanged.emit()
                            wait_pages(win)
                            spin(10)
                            scene = [item for item in items(win.contentItem()) if item.isVisible()]
                            body = next(item for item in scene if item.objectName() == ("arcadeFloor" if chapter == "lobby" else "onlineBody"))
                            if chapter == "lobby":
                                player_pane = next(item for item in scene if item.objectName() == "lobbyPlayersPane")
                                chat_pane = next(item for item in scene if item.objectName() == "lobbyChatPane")
                                self.assertTrue(player_pane.isVisible() and chat_pane.isVisible())
                                profile = next(item for item in scene if item.objectName() == "onlineProfile")
                                find = next(item for item in scene if item.objectName() == "onlineFind")
                                live = next(item for item in scene if item.objectName() == "lobbyLivePane")
                                rooms = next(item for item in scene if item.objectName() == "lobbyRoomsPane")
                                def left(item): return item.mapToScene(QPointF(0, 0)).x()
                                def right(item): return item.mapToScene(QPointF(item.width(), 0)).x()
                                def top(item): return item.mapToScene(QPointF(0, 0)).y()
                                def bottom(item): return item.mapToScene(QPointF(0, item.height())).y()
                                self.assertLessEqual(right(profile), left(find))
                                self.assertLessEqual(right(find), left(chat_pane))
                                self.assertLessEqual(bottom(profile), top(player_pane))
                                self.assertLessEqual(right(player_pane), left(live))
                                self.assertLessEqual(right(live), left(chat_pane))
                                self.assertLessEqual(bottom(live), top(rooms))
                                self.assertLessEqual(top(chat_pane), top(profile))
                                self.assertGreaterEqual(chat_pane.width() / 1920, .28)
                                self.assertLessEqual(chat_pane.width() / 1920, .32)
                                expected = backend._v["online"]["arcade"]["labels"]["players"] + "  /  " + str(len(backend._v["online"]["arcade"]["players"]))
                                titles = [item for item in items(player_pane)
                                          if item.isVisible() and item.property("text") == expected]
                            else:
                                titles = [item for item in items(body)
                                          if item.isVisible() and item.objectName() == "onlinePageTitle"]
                            self.assertEqual(len(titles), 1)
                            title = titles[0]
                            expected_title = (backend._v["online"]["arcade"]["labels"]["players"] + "  /  " + str(len(backend._v["online"]["arcade"]["players"]))) if chapter == "lobby" else backend._v["online"]["body"]["title"]
                            self.assertEqual(title.property("text"), expected_title)
                            self.assertGreater(title.width(), 0)
                            position = title.mapToItem(body, QPointF(0, 0))
                            self.assertGreaterEqual(position.x(), 0)
                            self.assertGreaterEqual(position.y(), 0)
                            self.assertLessEqual(position.x() + title.width(), body.width() + 1)
                            self.assertLessEqual(position.y() + title.height(), body.height() + 1)
                            labels = [item for item in items(body) if item.isVisible()
                                      and item.objectName() == "onlineFieldLabel" and item.property("text")
                                      and item.parentItem().objectName() not in
                                      ("onlineChip", "onlinePrimaryButton", "onlineSecondaryButton")]
                            help_text = [item for item in items(body) if item.isVisible()
                                         and item.objectName() == "onlineHelpText" and item.property("text")]
                            for label in labels:
                                self.assertGreater(title.property("font").pixelSize(), label.property("font").pixelSize())
                            if labels and help_text:
                                self.assertGreaterEqual(min(item.property("font").pixelSize() for item in labels),
                                                   max(item.property("font").pixelSize() for item in help_text))
                            for item in titles + labels + help_text:
                                self.assertLessEqual(item.property("contentHeight"), item.height() + 2)
            self.assertEqual(warnings, [])
            self.assertEqual(adapter.calls, [])
        finally:
            win.close()
            del engine


if __name__ == "__main__":
    unittest.main()
