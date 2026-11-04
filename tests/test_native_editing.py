"""Native text input owns physical keys; adapter drafts stay bounded and submission is guarded."""
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QInputMethodEvent, QKeyEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from openrecomp.app import Backend, UI_DIR
from openrecomp.nav import Game, Nav
from test_online_nav import Lobby
from test_online_page import lobby_snapshot
from test_ui_loads import FakeBackend, spin, wait_pages
from test_ui_secondary_polish import scene_items


def native_nav():
    adapter = Lobby()
    adapter.snapshot.update(lobby_snapshot())
    nav = Nav([Game(adapter.m, adapter)], language="en")
    nav.screen = "hub"
    nav.sec[nav.game.id] = "online"
    return nav, adapter


class NativeDrafts(unittest.TestCase):
    def setUp(self):
        self.nav, self.adapter = native_nav()

    def test_keyboard_field_activation_and_pointer_after_pad_are_native(self):
        self.nav.device = "kb"
        self.nav._edit_field("online_chat")
        self.assertEqual(self.nav.native_edit, "online_chat")
        self.assertIsNone(self.nav.overlay)
        self.nav.finish_edit("online_chat")
        self.nav.device = "ps"
        self.assertTrue(self.nav.begin_edit("online_chat"))
        self.assertEqual(self.nav.device, "kb")
        self.assertIsNone(self.nav.overlay)

    def test_only_pad_activation_opens_osk_and_done_submits_chat(self):
        self.nav._edit_field("online_chat")
        self.assertEqual(self.nav.overlay, "osk")
        self.nav.osk["text"] = "draft"
        self.nav._osk_done()
        self.assertEqual(self.adapter.texts["online_chat"], "draft")
        self.assertEqual(self.adapter.calls.count(("online", "send_chat")), 1)

    def test_osk_done_key_closes_keyboard_and_submits_lobby_and_private_chat_once(self):
        from test_private_chat_nav import PrivateLobby
        for tid, action in (("online_chat", "send_chat"), ("online_private_chat", "private_send")):
            with self.subTest(field=tid):
                adapter = PrivateLobby()
                adapter.snapshot.update(lobby_snapshot())
                adapter.snapshot["capabilities"]["private_chat"] = True
                adapter.snapshot["private_chat"] = dict(selected="peer" if tid == "online_private_chat" else "",
                                                        threads=[dict(id="peer", name="Peer", messages=[])])
                nav = Nav([Game(adapter.m, adapter)], language="en")
                nav.screen = "hub"
                nav.sec[nav.game.id] = "online"
                nav._open_osk(tid)
                nav.osk["text"] = "hello"
                nav.click_key(len(nav._osk_keys()), 2)
                self.assertIsNone(nav.overlay)
                self.assertIsNone(nav.osk)
                self.assertEqual(adapter.texts[tid], "hello")
                self.assertEqual(adapter.calls.count(("online", action)), 1)

    def test_osk_physical_enter_submits_chat_once_without_literal_enter(self):
        self.nav._open_osk("online_chat")
        self.nav.osk["text"] = "hello"
        backend = SimpleNamespace(nav=self.nav, refresh=mock.Mock())
        Backend.keyPress(backend, int(Qt.Key_Return), "Enter", False, 0, 0)
        Backend.keyPress(backend, int(Qt.Key_Return), "Enter", True, 0, 0)
        self.assertEqual(self.adapter.texts["online_chat"], "hello")
        self.assertEqual(self.adapter.calls.count(("online", "send_chat")), 1)
        self.assertIsNone(self.nav.osk)

    def test_empty_osk_chat_done_never_sends(self):
        self.nav._open_osk("online_chat")
        self.nav.osk["text"] = " "
        self.nav._osk_done()
        self.assertIsNone(self.nav.overlay)
        self.assertNotIn(("online", "send_chat"), self.adapter.calls)

    def test_duplicate_osk_done_is_inert_and_keypad_enter_submits_once(self):
        self.nav._open_osk("online_chat")
        self.nav.osk["text"] = "keypad draft"
        backend = SimpleNamespace(nav=self.nav, refresh=mock.Mock())
        Backend.keyPress(backend, int(Qt.Key_Enter), "Enter", False, 0, 0)
        Backend.keyPress(backend, int(Qt.Key_Enter), "Enter", True, 0, 0)
        self.assertFalse(self.nav._osk_done())
        self.assertEqual(self.adapter.texts["online_chat"], "keypad draft")
        self.assertEqual(self.adapter.calls.count(("online", "send_chat")), 1)

    def test_direct_edits_are_bounded_committed_and_stale_fields_are_rejected(self):
        self.nav.begin_edit("online_chat")
        self.assertTrue(self.nav.edit_text("online_chat", "a" * 299 + "界\nextra"))
        self.assertEqual(self.adapter.texts["online_chat"], "a" * 299 + "界")
        self.assertFalse(self.nav.edit_text("online_name", "other"))
        self.nav.finish_edit("online_chat")
        self.assertFalse(self.nav.edit_text("online_chat", "stale"))

    def test_submit_exactly_once_and_escape_saves_draft_without_leaving(self):
        self.nav.begin_edit("online_chat")
        self.nav.edit_text("online_chat", "hi")
        self.assertTrue(self.nav.finish_edit("online_chat", True))
        self.assertFalse(self.nav.finish_edit("online_chat", True))
        self.assertEqual(self.adapter.calls.count(("online", "send_chat")), 1)
        self.nav.begin_edit("online_chat")
        self.nav.act("back", device="xbox")
        self.assertEqual(self.nav.native_edit, "")
        self.assertEqual(self.nav.section(), "online")
        self.assertEqual(self.adapter.texts["online_chat"], "hi")

    def test_hidden_disabled_and_unknown_fields_cannot_be_edited(self):
        self.assertFalse(self.nav.begin_edit("online_password"))
        self.assertFalse(self.nav.begin_edit("invented"))
        self.assertEqual(self.adapter.calls, [])

    def test_physical_keys_cannot_trigger_global_navigation_during_native_edit(self):
        self.nav.begin_edit("online_chat")
        backend = SimpleNamespace(nav=self.nav, refresh=mock.Mock())
        with mock.patch.object(self.nav, "act") as act:
            for key in (Qt.Key_X, Qt.Key_F, Qt.Key_Q, Qt.Key_E, Qt.Key_G, Qt.Key_Space,
                        Qt.Key_Left, Qt.Key_Return):
                Backend.keyPress(backend, int(key), "x", False, Qt.ControlModifier.value, 0)
            act.assert_not_called()

    def test_private_drafts_survive_switching_conversations_that_clear_adapter_drafts(self):
        from test_private_chat_nav import PrivateLobby
        adapter = PrivateLobby()
        adapter.snapshot["private_chat"]["threads"].append(dict(id="other", name="Other", unread=0, messages=[]))
        original_action = adapter.online_action
        def clearing_action(action):
            original_action(action)
            if action.startswith("private_open:") or action == "private_close":
                adapter.texts["online_private_chat"] = ""
        adapter.online_action = clearing_action
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec[nav.game.id] = "online"
        nav._online_action(nav.game, "private_open:peer")
        nav.begin_edit("online_private_chat")
        nav.edit_text("online_private_chat", "draft for Peer")
        nav.finish_edit("online_private_chat")
        nav._online_action(nav.game, "private_open:other")
        nav.begin_edit("online_private_chat")
        nav.edit_text("online_private_chat", "draft for Other")
        nav.finish_edit("online_private_chat")
        nav._online_action(nav.game, "private_open:peer")
        self.assertEqual(adapter.texts["online_private_chat"], "draft for Peer")
        nav._online_action(nav.game, "private_close")
        nav._online_action(nav.game, "private_open:other")
        self.assertEqual(adapter.texts["online_private_chat"], "draft for Other")

    def test_closing_private_chat_exits_native_editor_and_keeps_committed_draft(self):
        from test_private_chat_nav import PrivateLobby
        for field in ("online_private_chat", "online_private_report_reason"):
            with self.subTest(field=field):
                adapter = PrivateLobby()
                nav = Nav([Game(adapter.m, adapter)], language="en")
                nav.screen = "hub"
                nav.sec[nav.game.id] = "online"
                nav._online_action(nav.game, "private_open:peer")
                self.assertTrue(nav.begin_edit(field))
                nav.edit_text(field, "committed draft")
                nav.close_chat_tab("peer")
                self.assertEqual(nav.native_edit, "")
                self.assertEqual(nav.view()["nativeEdit"], "")
                if field == "online_private_chat":
                    self.assertEqual(nav.private_drafts[nav.game.id]["peer"], "committed draft")
                before = nav.focus_index(nav.items())
                nav.act("down", device="kb")
                self.assertNotEqual(nav.focus_index(nav.items()), before)

    def test_actual_match_phase_keeps_docked_chat_editor_without_sending_draft(self):
        self.nav.begin_edit("online_chat")
        self.nav.edit_text("online_chat", "keep this draft")
        self.adapter.calls.clear()
        self.adapter.snapshot.update(phase="matched", match=dict(opponent="Rival"))
        view = self.nav.view()
        self.assertEqual(self.nav.native_edit, "online_chat")
        self.assertEqual(view["nativeEdit"], "online_chat")
        self.assertTrue(view["online"]["chatDocked"])
        self.assertEqual(view["online"]["chat"]["compose"]["fieldId"], "online_chat")
        self.assertEqual(self.adapter.texts["online_chat"], "keep this draft")
        self.assertEqual(self.adapter.calls, [])

    def test_keyboard_library_repository_is_native_and_preview_submits_once(self):
        preview = mock.Mock(return_value="@library.loading")
        nav = Nav([], on_game_preview=preview, language="en")
        nav.act("confirm", device="kb")
        nav.act("confirm", device="kb")
        self.assertEqual(nav.overlay, "native")
        self.assertEqual(nav.native_edit, "library_repository")
        self.assertIsNone(nav.osk)
        self.assertEqual(nav.view()["nativeField"]["limit"], 140)
        nav.edit_text("library_repository", "sample/project")
        preview.assert_not_called()
        nav.finish_edit("library_repository", True)
        nav.finish_edit("library_repository", True)
        preview.assert_called_once_with("sample/project")

    def test_native_library_cancel_and_pad_handoff_keep_draft_without_preview(self):
        preview = mock.Mock()
        nav = Nav([], on_game_preview=preview, language="en")
        nav.act("confirm", device="kb")
        nav.act("confirm", device="kb")
        nav.edit_text("library_repository", "sample/project")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.overlay, "osk")
        self.assertEqual(nav.osk["text"], "sample/project")
        nav.act("back", device="xbox")
        preview.assert_not_called()

    def test_generic_nickname_uses_native_modal_and_adapter_setter(self):
        from test_nav import Fake, manifest
        adapter = Fake(manifest())
        adapter.online_items = lambda: [dict(kind="action", id="nickname", label="Name", opens="text:nickname")]
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec[nav.game.id] = "online"
        nav.device = "kb"
        nav._edit_field("nickname")
        self.assertEqual(nav.overlay, "native")
        self.assertEqual(nav.native_edit, "nickname")
        nav.edit_text("nickname", "Player")
        self.assertIn(("text", "nickname", "Player"), adapter.calls)
        nav.finish_edit("nickname", True)
        self.assertIsNone(nav.overlay)


class NativeEditorRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def setUp(self):
        self.nav, self.adapter = native_nav()
        self.nav.view = lambda: dict(nativeEdit=getattr(self.nav, "native_edit", ""),
                                     inputMode=self.nav.device, overlay=self.nav.overlay or "",
                                     testDraft=self.adapter.text_value("online_chat"))
        self.backend = FakeBackend(self.nav)
        self.engine = QQmlApplicationEngine()
        self.warnings = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties(dict(backend=self.backend))
        self.engine.loadData(b'''import QtQuick
import QtQuick.Window
Window {
    id: host; width: 800; height: 240; visible: true
    required property var backend
    property var v: backend.view
    property bool secret: false
    function focusStage() { sentinel.forceActiveFocus() }
    Item { id: sentinel; focus: true }
    EditableField {
        objectName: "testField"; x: 20; y: 20; width: 760; root: host
        field: ({fieldId: "online_chat", label: "Chat", limit: 300, secret: host.secret, draft: backend.view.testDraft || "", submitId: "send_chat"})
    }
}''', QUrl.fromLocalFile(str(Path(UI_DIR) / "NativeEditingTest.qml")))
        self.assertTrue(self.engine.rootObjects(), self.warnings)
        self.window = self.engine.rootObjects()[0]
        self.editor = self.window.findChild(QObject, "nativeTextInput")
        self.backend.beginEdit("online_chat")
        spin()
        self.editor.forceActiveFocus()
        spin()

    def tearDown(self):
        self.window.close()
        del self.editor
        del self.window
        del self.engine
        self.assertEqual(self.warnings, [])

    def type_keys(self, text):
        for char in text:
            modifiers = Qt.ShiftModifier if char.isupper() else Qt.NoModifier
            QCoreApplication.sendEvent(self.window, QKeyEvent(QEvent.KeyPress, ord(char.upper()), modifiers, char))
            QCoreApplication.sendEvent(self.window, QKeyEvent(QEvent.KeyRelease, ord(char.upper()), modifiers, char))

    def test_native_selection_replacement_and_navigation_letters(self):
        self.type_keys("XFQEG space")
        self.assertEqual(self.editor.property("text"), "XFQEG space")
        QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
        self.type_keys("replacement")
        self.assertEqual(self.editor.property("text"), "replacement")
        self.assertEqual(self.adapter.texts["online_chat"], "replacement")
        self.assertIsNone(self.nav.overlay)

    def test_altgr_text_is_inserted_without_global_shortcuts(self):
        QCoreApplication.sendEvent(self.window, QKeyEvent(QEvent.KeyPress, Qt.Key_Q,
                                   Qt.ControlModifier | Qt.AltModifier, "@"))
        self.assertEqual(self.editor.property("text"), "@")
        self.assertEqual(self.adapter.texts["online_chat"], "@")
        self.assertIsNone(self.nav.overlay)

    def test_return_keypad_enter_and_shift_enter_submit_without_newlines(self):
        for key, modifiers in ((Qt.Key_Return, Qt.NoModifier), (Qt.Key_Enter, Qt.NoModifier),
                               (Qt.Key_Return, Qt.ShiftModifier)):
            with self.subTest(key=key, modifiers=modifiers):
                self.backend.beginEdit("online_chat")
                spin()
                self.editor.forceActiveFocus()
                QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
                self.type_keys("hello")
                before = self.adapter.calls.count(("online", "send_chat"))
                QTest.keyClick(self.window, key, modifiers)
                self.assertEqual(self.adapter.texts["online_chat"], "hello")
                self.assertEqual(self.adapter.calls.count(("online", "send_chat")), before + 1)
                self.assertEqual(self.nav.native_edit, "")
                self.assertFalse(self.editor.hasActiveFocus())

    def test_ime_preedit_is_not_a_draft_or_a_submit_and_commit_is_unicode(self):
        QCoreApplication.sendEvent(self.editor, QInputMethodEvent("日本", []))
        self.assertTrue(self.editor.property("inputMethodComposing"))
        self.assertEqual(self.adapter.calls, [])
        QTest.keyClick(self.window, Qt.Key_Return)
        self.assertNotIn(("online", "send_chat"), self.adapter.calls)
        commit = QInputMethodEvent()
        commit.setCommitString("日本語")
        QCoreApplication.sendEvent(self.editor, commit)
        self.assertEqual(self.adapter.texts["online_chat"], "日本語")
        QTest.keyClick(self.window, Qt.Key_Return)
        self.assertEqual(self.adapter.calls.count(("online", "send_chat")), 1)


    def test_native_clipboard_and_escape_preserve_draft(self):
        QGuiApplication.clipboard().setText("hello @Rival")
        QTest.keyClick(self.window, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(self.editor.property("text"), "hello @Rival")
        QTest.keyClick(self.window, Qt.Key_Escape)
        self.assertEqual(self.nav.native_edit, "")
        self.assertEqual(self.adapter.texts["online_chat"], "hello @Rival")
        self.assertNotIn(("online", "send_chat"), self.adapter.calls)

    def test_password_copy_and_cut_do_not_disclose_to_clipboard(self):
        self.window.setProperty("secret", True)
        self.type_keys("secret")
        QGuiApplication.clipboard().setText("untouched")
        QTest.keyClick(self.window, Qt.Key_A, Qt.ControlModifier)
        QTest.keyClick(self.window, Qt.Key_C, Qt.ControlModifier)
        self.assertEqual(QGuiApplication.clipboard().text(), "untouched")
        QTest.keyClick(self.window, Qt.Key_X, Qt.ControlModifier)
        self.assertEqual(QGuiApplication.clipboard().text(), "untouched")

    def test_pointer_after_pad_enters_native_and_limit_applies_to_paste(self):
        self.backend.finishEdit("online_chat", False)
        self.nav.device = "ps"
        self.backend.refresh()
        spin()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, QPoint(100, 70))
        self.assertEqual(self.nav.device, "kb")
        self.assertEqual(self.nav.native_edit, "online_chat")
        self.assertIsNone(self.nav.overlay)
        QGuiApplication.clipboard().setText("界" * 320)
        QTest.keyClick(self.window, Qt.Key_V, Qt.ControlModifier)
        self.assertEqual(self.editor.property("text"), "界" * 300)
        self.assertEqual(self.adapter.texts["online_chat"], "界" * 300)

    def test_clicking_an_action_exits_native_edit_before_invoking_its_action(self):
        self.type_keys("saved")
        target = next(n for n, row in enumerate(self.nav.items()) if row.get("id") == "send_chat")
        backend = SimpleNamespace(nav=self.nav, refresh=mock.Mock())
        Backend.clickRow(backend, target)
        self.assertEqual(self.nav.native_edit, "")
        self.assertEqual(self.adapter.calls.count(("online", "send_chat")), 1)


class NativeModalRendering(unittest.TestCase):
    def test_library_native_modal_loads_focuses_and_enters_preview_without_osk(self):
        app = QGuiApplication.instance() or QGuiApplication([])
        preview = mock.Mock(return_value="@library.loading")
        nav = Nav([], on_game_preview=preview, language="de")
        nav.act("confirm", device="kb")
        nav.act("confirm", device="kb")
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(Path(UI_DIR) / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.show()
        wait_pages(window)
        spin()
        editors = [item for item in scene_items(window.contentItem())
                   if item.objectName() == "nativeTextInput" and item.isVisible()]
        self.assertEqual(len(editors), 1)
        self.assertTrue(editors[0].hasActiveFocus())
        QGuiApplication.clipboard().setText("sample/project")
        QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier)
        preview.assert_not_called()
        self.assertEqual(nav.native_repository, "sample/project")
        QTest.keyClick(window, Qt.Key_Return)
        preview.assert_called_once_with("sample/project")
        self.assertIsNone(nav.osk)
        window.setProperty("allowClose", True)
        window.close()
        self.assertEqual(warnings, [])

