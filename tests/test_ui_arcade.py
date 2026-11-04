"""Render the arcade through the inert adapter boundary, including reduced motion."""
import os
from pathlib import Path
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QRectF, QUrl, Slot
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from openrecomp import i18n
from openrecomp.app import UI_DIR
from test_ui_loads import FakeBackend, spin, wait_pages
from test_ui_secondary_polish import scene_items
from tools import online_shots, package_release


class InteractiveBackend(FakeBackend):
    @Slot(int)
    def clickRow(self, index):
        self.nav.click_row(index)
        self.refresh()


class ArcadeRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def setUp(self):
        self.backend = InteractiveBackend(online_shots.scene("t5", "arcade_floor", "en"))
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties(dict(backend=self.backend, wantFull=False))
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
        items = [item for item in scene_items(self.win.contentItem()) if item.objectName() == name]
        self.assertTrue(items, name)
        return items

    def publish(self, game, scene, language="en", **kwargs):
        self.backend.nav = online_shots.scene(game, scene, language, **kwargs)
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.backend.viewChanged.emit()
        wait_pages(self.win)
        spin(20)

    def rect(self, item):
        return item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))

    def test_floor_selected_cabinet_and_drawer_render_for_both_games_and_sizes(self):
        for game in ("t5", "t4"):
            for scene in online_shots.ARCADE_SCENES:
                for width, height in online_shots.SIZES:
                    with self.subTest(game=game, scene=scene, size=(width, height)):
                        self.publish(game, scene)
                        self.win.setWidth(width)
                        self.win.setHeight(height)
                        self.assertTrue(self.named("arcadeFloor")[0].isVisible())
                        self.assertEqual(len(self.named("arcadePlayer")), 7)
                        self.assertTrue(self.named("lobbyPlayersPane")[0].isVisible())
                        self.assertTrue(self.named("lobbyChatPane")[0].isVisible())
                        self.assertEqual(self.named("arcadeOptionsDrawer")[0].isVisible(), scene in ("arcade_options", "arcade_cabinet"))
                        self.assertTrue(self.named("onlineProfile")[0].isVisible())
                        self.assertTrue(self.named("onlineFind")[0].isVisible())
                        for card in self.named("arcadePlayer"):
                            self.assertGreater(card.width(), 300)
                            self.assertLessEqual(card.x() + card.width(), card.parentItem().width() + 1)
                        self.assertEqual(self.backend.nav.game.a.calls, [])

    def test_all_catalogs_fit_options_with_large_text_and_high_contrast(self):
        for language in i18n.LANGUAGES:
            self.publish("t4", "arcade_options", language, text_size=130, high_contrast=True)
            overflow, _ = online_shots.geometry(self.win)
            self.assertEqual(overflow, [], (language, overflow))

    def test_selected_card_motion_stops_when_reduced_motion_is_enabled(self):
        self.publish("t5", "arcade_selected")
        cards = self.named("arcadePlayer")
        self.assertTrue(all(card.scale() == 1 for card in cards))
        self.backend.nav.reduced_motion = False
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.backend.viewChanged.emit()
        spin(180)
        self.assertTrue(all(card.scale() == 1 for card in cards))
        self.backend.nav.reduced_motion = True
        self.backend._v = online_shots.snapshot(self.backend.nav)
        self.backend.viewChanged.emit()
        spin(20)
        self.assertTrue(all(card.scale() == 1 for card in cards))

    def test_wide_controller_and_keyboard_glyphs_leave_room_for_labels(self):
        for device in ("xbox", "kb"):
            self.publish("t5", "arcade_selected")
            self.backend.nav.device = device
            self.backend._v = online_shots.snapshot(self.backend.nav)
            self.backend.viewChanged.emit()
            spin(20)
            for name in ("arcadeActionLabel",):
                for label in self.named(name):
                    if not label.isVisible():
                        continue
                    glyphs = [child for child in label.parentItem().childItems()
                              if child.objectName() in ("arcadeShortcutGlyph", "arcadeActionGlyph") and child.isVisible()]
                    for glyph in glyphs:
                        self.assertGreaterEqual(label.x(), glyph.x() + glyph.width() + 4)
    def test_compact_table_has_eighteen_rows_at_1080_and_ten_at_720(self):
        for game in ("t5", "t4"):
            for language in ("en", "de"):
                self.publish(game, "lobby_dense", language)
                for width, height, minimum in ((1920, 1080, 18), (1280, 720, 10)):
                    with self.subTest(game=game, language=language, size=(width, height)):
                        self.win.setWidth(width); self.win.setHeight(height); spin(30)
                        viewport = self.named("arcadePlayersViewport")[0]
                        cards = self.named("arcadePlayer")
                        complete = [card for card in cards if card.y() >= viewport.property("contentY")
                                    and card.y() + card.height() <= viewport.property("contentY") + viewport.height() + .5]
                        self.assertGreaterEqual(len(complete), minimum,
                                                (viewport.height(), [(c.y(), c.height()) for c in cards]))
                        if width == 1920:
                            for card in cards:
                                self.assertGreaterEqual(self.rect(card).height(), 32)
                                self.assertLessEqual(self.rect(card).height(), 36)
                            for portrait in self.named("arcadePlayerPortrait"):
                                self.assertAlmostEqual(self.rect(portrait).width(), 24, delta=.5)
                                self.assertAlmostEqual(self.rect(portrait).height(), 24, delta=.5)
                        for name in ("arcadePlayerName", "arcadePlayerStatus"):
                            for label in self.named(name):
                                self.assertGreaterEqual(label.property("font").pixelSize() * width / 1920, 14 - .4)
                        self.assertTrue(self.named("lobbyChatPane")[0].isVisible())
                        self.assertTrue(self.named("lobbyLivePane")[0].isVisible())
                        self.assertTrue(self.named("lobbyRoomsPane")[0].isVisible())

    def test_profile_find_and_community_panels_follow_the_owner_layout(self):
        for language in ("en", "de"):
            self.publish("t5", "lobby_dense", language)
            for width, height in online_shots.SIZES:
                self.win.setWidth(width); self.win.setHeight(height); spin(30)
                profile, find, players, live, rooms, chat = [self.rect(self.named(name)[0]) for name in (
                    "onlineProfile", "onlineFind", "lobbyPlayersPane", "lobbyLivePane", "lobbyRoomsPane", "lobbyChatPane")]
                self.assertAlmostEqual(profile.top(), find.top(), delta=1)
                self.assertEqual(self.named("profileMainFighter")[0].property("text"), "F3")
                self.assertLessEqual(profile.right(), find.left())
                self.assertLessEqual(find.bottom(), players.top())
                self.assertLessEqual(players.right(), live.left())
                self.assertLessEqual(players.right(), rooms.left())
                self.assertLessEqual(max(find.right(), live.right(), rooms.right()), chat.left())

    def test_ranked_and_casual_remain_prominent_and_guest_reason_is_visible(self):
        for account in (True, False):
            self.publish("t5", "arcade_floor")
            nav = self.backend.nav
            nav.game.a.snapshot["account"] = account
            self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(30)
            actions = {}
            for item in scene_items(self.named("onlineFind")[0]):
                b = item.property("b")
                if b and item.isVisible():
                    value = b.toVariant() if hasattr(b, "toVariant") else b
                    if value.get("id") in ("search_ranked", "search_casual"):
                        actions[value["id"]] = item
            self.assertEqual(set(actions), {"search_ranked", "search_casual"})
            ranked, casual = (actions[key] for key in ("search_ranked", "search_casual"))
            self.assertLess(self.rect(ranked).left(), self.rect(casual).left())
            for action in (ranked, casual):
                self.assertGreaterEqual(self.rect(action).height(), 56)
            self.assertNotEqual(ranked.property("color"), casual.property("color"))
            projected = nav.view()["online"]["find"]["ranked"]
            self.assertEqual(bool(projected["disabled"]), not account)
            if not account:
                self.assertTrue(projected["value"])

    def test_table_headers_select_their_sort_without_a_service_request(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.publish("t5", "lobby_dense")
        nav = self.backend.nav; nav.dry = False
        for mode in ("name", "rank", "rating", "main", "status", "ping"):
            with self.subTest(mode=mode):
                headers = [item for item in self.named("lobbyPlayerHeader") if item.isVisible()]
                header = next(item for item in headers
                              if item.property("b").toVariant().get("id") == "arcade_sort:" + mode)
                point = self.rect(header).center().toPoint()
                QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, point); spin(30)
                self.assertEqual(nav.__dict__["arcade_sort"][nav.game.id], mode)
                self.assertEqual(nav.game.a.calls, [])

    def test_enlarged_profile_headers_and_room_actions_fit_at_720(self):
        self.win.setWidth(1280); self.win.setHeight(720)
        for game in ("t5", "t4"):
            for language in ("en", "de"):
                self.publish(game, "lobby_dense", language, text_size=130, high_contrast=True)
                with self.subTest(game=game, language=language):
                    overflow, elided = online_shots.geometry(self.win)
                    self.assertEqual(overflow, [])
                    self.assertEqual(elided, [])
                    for flow in self.named("lobbyRoomActions"):
                        for action in flow.childItems():
                            if action.isVisible() and action.width() > 0:
                                self.assertLessEqual(action.x() + action.width(), flow.width() + .5)

    def test_guest_fixture_keeps_full_match_buttons_and_readable_account_reason(self):
        for language in ("en", "de"):
            self.publish("t5", "lobby_guest", language)
            for width, height in online_shots.SIZES:
                self.win.setWidth(width); self.win.setHeight(height); spin(20)
                ranked = self.named("onlineRankedAction")[0]
                self.assertTrue(ranked.isVisible())
                self.assertTrue(ranked.property("b").toVariant()["disabled"])
                self.assertGreaterEqual(ranked.height(), 64)
                labels = [item for item in scene_items(ranked) if item.property("text")]
                self.assertTrue(any(item.property("text") == i18n.text(language, "online_density.needs_account") for item in labels))
                self.assertTrue(all(not item.property("truncated") for item in labels))

    def test_lobby_drawer_opener_is_only_offered_where_its_drawer_is_rendered(self):
        for chapter, expected in (("rooms", False), ("arcade_floor", True)):
            self.publish("t5", chapter)
            openers = []
            for item in scene_items(self.named("onlineFind")[0]):
                button = item.property("b")
                if button and button.toVariant().get("id") == "arcade_options":
                    openers.append(item)
            self.assertTrue(openers)
            self.assertEqual(any(item.isVisible() for item in openers), expected)

    def test_started_ranked_action_becomes_elapsed_and_cancel_in_place(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from openrecomp import nav_feedback
        self.publish("t5", "arcade_floor")
        nav = self.backend.nav; nav.dry = False
        before = self.rect(self.named("onlineRankedAction")[0])
        nav._online_action(nav.game, "search_ranked")
        nav_feedback.tick(nav, 42)
        self.backend.refresh(); spin(30)
        action = self.named("onlineRankedAction")[0]
        self.assertEqual(self.rect(action), before)
        self.assertTrue(action.property("searching"))
        self.assertEqual(action.property("b").toVariant()["id"], "cancel")
        self.assertFalse(self.named("onlineCasualAction")[0].property("searching"))
        labels = [item.property("text") for item in scene_items(action) if item.isVisible() and item.property("text")]
        self.assertTrue(any("0:42" in text and "Cancel" in text for text in labels), labels)
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, self.rect(action).center().toPoint()); spin(30)
        self.assertEqual(nav.game.a.calls, [("online", "search_ranked"), ("online", "cancel")])

    def test_notice_is_in_flow_and_selection_does_not_reflow_rows(self):
        self.publish("t5", "arcade_selected")
        before = [(c.y(), c.height()) for c in self.named("arcadePlayer")]
        nav = self.backend.nav
        nav.focus_online_row(next(i for i, it in enumerate(nav.items()) if it.get("id") == "challenge:p6"))
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(30)
        self.assertEqual(before, [(c.y(), c.height()) for c in self.named("arcadePlayer")])
        self.publish("t5", "challenge_incoming")
        notice = self.named("lobbyNotice")[0]
        self.assertTrue(notice.isVisible())
        self.assertGreaterEqual(self.rect(self.named("lobbyPlayersPane")[0]).top(), self.rect(notice).bottom())
        self.assertFalse(self.rect(notice).intersects(self.rect(self.named("lobbyChatPane")[0])))

    def test_profile_chip_cannot_become_logout_when_profiles_are_unsupported(self):
        self.publish("t4", "arcade_floor")
        nav = self.backend.nav; nav.dry = False
        nav.game.a.snapshot["capabilities"]["profiles"] = False
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(30)
        profile = nav.view()["online"]["profile"]
        self.assertFalse(any(button["id"] == "logout" and button["index"] == profile["index"]
                             for button in profile["buttons"]))
        nav.click_row(profile["index"])
        self.assertEqual(nav.game.a.calls, [])

    def test_pad_focus_reveals_far_private_conversation_tab(self):
        self.publish("t5", "private_chat")
        nav = self.backend.nav
        nav.game.a.snapshot["private_chat"]["threads"] += [dict(id="thread" + str(n), name="Conversation " + str(n), unread=0, messages=[]) for n in range(12)]
        items = nav.items()
        nav.focus_online_row(next(n for n, it in enumerate(items) if it.get("id") == "private_open:thread11"))
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(40)
        viewport = self.named("chatTabsViewport")[0]
        tab = next(tab for tab in self.named("chatConversationTab") if tab.property("modelData").toVariant()["id"] == "private_open:thread11")
        self.assertGreater(viewport.property("contentX"), 0)
        self.assertGreaterEqual(tab.x(), viewport.property("contentX"))
        self.assertLessEqual(tab.x() + tab.width(), viewport.property("contentX") + viewport.width() + .5)

    def test_match_found_has_one_heading_and_pinned_primary(self):
        self.publish("t5", "matched")
        nav = self.backend.nav
        for width, height in ((1920, 1080), (1280, 720)):
            self.win.setWidth(width); self.win.setHeight(height); spin(30)
            titles = [item for item in scene_items(self.win.contentItem()) if item.isVisible()
                      and item.property("text") == i18n.text("en", "online.match_found")]
            self.assertEqual(len(titles), 2)  # page heading and existing footer status only
            primary = self.named("onlinePhasePrimary")[0]
            self.assertTrue(primary.isVisible())
            card = self.named("onlineCard")[0]
            self.assertEqual(primary.y() + primary.height(), card.height() - 24)
        self.assertEqual(nav.game.a.calls, [])

    def test_lobby_feedback_uses_footer_without_floating_over_panes(self):
        self.publish("t5", "arcade_selected")
        nav = self.backend.nav
        nav.say("@online.challenge_sent", 3)
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(30)
        self.assertFalse(self.named("resultToast")[0].isVisible())
        self.assertEqual(self.named("focusHint")[0].property("text"), i18n.text("en", "online.challenge_sent"))

    def test_private_tab_close_has_a_named_accessible_button(self):
        self.publish("t5", "private_chat")
        from PySide6.QtGui import QAccessible
        names = []
        for target in self.named("accessibleTarget"):
            if target.isVisible():
                interface = QAccessible.queryAccessibleInterface(target)
                if interface: names.append(interface.text(QAccessible.Text.Name))
        self.assertTrue(any("Rival" in name and "Close" in name for name in names), names)

    def test_native_tab_completes_known_mention_without_navigation_or_send(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        self.publish("t5", "native_composer")
        nav = self.backend.nav; nav.dry = False
        editor = next(item for item in self.named("nativeTextInput") if item.isVisible() and item.hasActiveFocus())
        QTest.keyClick(self.win, Qt.Key_A, Qt.ControlModifier)
        QGuiApplication.clipboard().setText("@Ri")
        QTest.keyClick(self.win, Qt.Key_V, Qt.ControlModifier)
        QTest.keyClick(self.win, Qt.Key_Tab); spin(30)
        self.assertEqual(editor.property("text"), "@Rival ")
        self.assertEqual(nav.game.a.text_value("online_chat"), "@Rival ")
        self.assertEqual(nav.native_edit, "online_chat")
        self.assertFalse(any(call[0] == "online" for call in nav.game.a.calls))

    def test_semantic_primary_fill_does_not_follow_focus(self):
        self.publish("t5", "arcade_selected")
        nav = self.backend.nav
        def button(iid):
            return next(label.parentItem() for label in self.named("arcadeActionLabel")
                        if label.parentItem().property("b").toVariant().get("id") == iid)
        challenge = button("challenge:p1")
        colour = challenge.property("color")
        nav.focus_online_row(next(n for n, it in enumerate(nav.items()) if it.get("id") == "profile_player:p1"))
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(30)
        self.assertEqual(button("challenge:p1").property("color"), colour)
        self.assertNotEqual(button("profile_player:p1").property("color"), colour)

    def test_history_does_not_follow_new_messages_until_pad_latest_action(self):
        self.publish("t5", "chat_history")
        pane = self.named("lobbyChatPane")[0]
        history = self.named("lobbyChatHistory")[0]
        nav = self.backend.nav
        nav.focus_online_row(nav.view()["online"]["chat"]["lines"][4]["index"])
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(40)
        self.assertFalse(pane.property("following"))
        review_y = history.property("contentY")
        nav.game.a.snapshot["chat"].append(dict(id="new", name="Rival", text="new message"))
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(40)
        self.assertEqual(history.property("contentY"), review_y)
        self.assertGreater(pane.property("newCount"), 0)
        latest = next(it for it in nav.items() if it.get("id") == "chat_latest")
        latest["run"]()
        self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(40)
        self.assertGreater(history.property("contentY"), 0)
        self.assertEqual(pane.property("newCount"), 0)

    def test_private_chat_with_incoming_offer_keeps_history_and_composer_visible(self):
        self.win.setWidth(1280); self.win.setHeight(720)
        for game, state, language in (("t4", "challenge_incoming", "en"), ("t5", "challenge_waiting", "fr")):
            self.publish(game, state, language, text_size=130, high_contrast=True)
            nav = self.backend.nav
            private = online_shots.scene(game, "private_chat", language).game.a.snapshot["private_chat"]
            nav.game.a.snapshot["private_chat"] = private
            nav.game.a.snapshot["capabilities"]["private_reports"] = True
            self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(40)
            history = self.named("lobbyChatHistory")[0]
            self.assertGreater(history.height() * 1280 / 1920, 40, (game, state, self.named("lobbyChatPane")[0].height(), history.y(), self.named("lobbyChatComposer")[0].y()))
            self.assertTrue(any(field.isVisible() for field in self.named("editableField")))

    def test_selected_native_form_caption_has_contrast_against_its_actual_fill(self):
        from test_accessibility import contrast
        for high_contrast in (False, True):
            self.publish("t4", "rooms", "ko", text_size=130, high_contrast=high_contrast)
            nav = self.backend.nav
            nav.focus_online_row(next(n for n, item in enumerate(nav.items()) if item.get("id") == "online_room_name"))
            self.backend._v = online_shots.snapshot(nav); self.backend.viewChanged.emit(); spin(30)
            fields = [field for field in self.named("editableField") if field.isVisible()
                      and field.property("showLabel") and field.property("field").toVariant().get("focused")]
            self.assertTrue(fields)
            for field in fields:
                caption = next(item for item in field.childItems()
                               if item.property("text") == field.property("field").toVariant()["label"])
                self.assertGreaterEqual(contrast(caption.property("color").name(),
                                                field.parentItem().property("color").name()), 4.5)

    def test_short_challenge_chat_keeps_heading_history_and_native_composer_separate(self):
        from PySide6.QtCore import QRectF
        self.win.setWidth(1280); self.win.setHeight(720)
        for language in ("de", "fr", "pt-BR"):
            for state in ("challenge_incoming", "challenge_waiting"):
                self.publish("t5", state, language, text_size=130, high_contrast=True)
                pane = self.named("lobbyChatPane")[0]
                history = self.named("lobbyChatHistory")[0]
                children = scene_items(pane)
                title_text = self.backend.nav.view()["online"]["chat"]["title"]
                title = next(item for item in children if item.isVisible() and item.property("text") == title_text)
                latest = next(item for item in children if item.isVisible() and item.property("b")
                              and item.property("b").toVariant().get("id") == "chat_latest")
                def rect(item):
                    return item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))
                self.assertFalse(rect(title).intersects(rect(latest)), (language, state))
                self.assertGreaterEqual(rect(history).height(), 40, (language, state))
                field = next(item for item in children if item.isVisible() and item.objectName() == "editableField")
                self.assertGreaterEqual(rect(field).height(), 44 - .5)
                self.assertLessEqual(rect(history).bottom(), rect(field).top() + .5)
                self.assertEqual(self.backend.nav.game.a.calls, [])

    def test_double_click_challenges_once_and_single_click_only_selects(self):
        from PySide6.QtCore import QPoint, QPointF, Qt
        from PySide6.QtTest import QTest
        self.publish("t5", "arcade_selected")
        nav = self.backend.nav; nav.dry = False
        card = next(c for c in self.named("arcadePlayer") if c.property("player").toVariant()["id"] == "p1")
        point = card.mapToScene(QPointF(100, card.height() / 2)).toPoint()
        QTest.mouseClick(self.win, Qt.LeftButton, Qt.NoModifier, point); spin(450)
        self.assertEqual(nav.game.a.calls, [])
        QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, point); spin(450)
        self.assertEqual(nav.game.a.calls.count(("online", "challenge:p1")), 1)
        QTest.mouseDClick(self.win, Qt.LeftButton, Qt.NoModifier, point); spin(450)
        self.assertEqual(nav.game.a.calls.count(("online", "challenge:p1")), 1)

    def test_release_manifest_includes_the_floor_and_projection(self):
        for filename in ("ArcadeFloor.qml", "ArcadePlayer.qml", "ArcadeAction.qml", "ArcadeIcon.qml"):
            self.assertIn("openrecomp/ui/" + filename, package_release.SOURCE_FILES)
        self.assertIn("openrecomp/nav_arcade.py", package_release.SOURCE_FILES)
        self.assertIn("openrecomp/adapters/arcade_metadata.py", package_release.SOURCE_FILES)

    def test_more_drawer_scrolls_to_a_controller_selected_destination(self):
        self.publish("t5", "arcade_selected")
        nav = self.backend.nav
        nav.act("play", device="xbox")
        destinations = nav.view()["online"]["arcade"]["destinations"]
        self.assertTrue(destinations)
        nav.focus_online_row(destinations[-1]["index"])
        self.backend._v = online_shots.snapshot(nav)
        self.backend.viewChanged.emit()
        spin(40)
        choices = [item for item in scene_items(self.win.contentItem()) if item.isVisible()
                   and item.objectName() == "arcadeActionLabel" and item.property("text") == destinations[-1]["label"]]
        self.assertEqual(len(choices), 1)
        from PySide6.QtCore import QPointF
        drawer = self.named("arcadeOptionsDrawer")[0]
        point = choices[0].mapToItem(drawer, QPointF(0, 0))
        self.assertGreaterEqual(point.y(), 76)
        self.assertLessEqual(point.y() + choices[0].height(), drawer.height())


if __name__ == "__main__":
    unittest.main()
