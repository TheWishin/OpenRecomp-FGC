"""Copy and paste in the launcher's text fields (the on-screen keyboard), with a fake clipboard.

The fields are not QML TextFields: every key goes through Backend.keyPress into Nav. Paste used to be lost there: Ctrl+V
types "\x16" (not printable, dropped) and Ctrl+X was the X action (delete a letter). Passwords take a paste but never
give their text to the clipboard.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPointF, Qt  # noqa: E402

from openrecomp import app, i18n  # noqa: E402
from openrecomp.app import ALT, CTRL, SHIFT, Backend, edit_shortcut  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402

V, C, X, A = (int(k) for k in (Qt.Key_V, Qt.Key_C, Qt.Key_X, Qt.Key_A))
CYRILLIC_EM = 0x41C        # the key at V on a Russian layout
GREEK_OMEGA = 0x3C9        # the key at V on a Greek layout


class Shortcuts(unittest.TestCase):
    def test_latin_layouts(self):
        self.assertEqual(edit_shortcut(V, "\x16", CTRL, 0x2F), "paste")
        self.assertEqual(edit_shortcut(C, "\x03", CTRL, 0x2E), "copy")
        self.assertEqual(edit_shortcut(X, "\x18", CTRL, 0x2D), "cut")
        self.assertEqual(edit_shortcut(A, "\x01", CTRL, 0x1E), "select_all")
        self.assertEqual(edit_shortcut(V, "\x16", CTRL | SHIFT, 0x2F), "paste")

    def test_non_latin_layouts_by_control_character_or_key_position(self):
        for key in (CYRILLIC_EM, GREEK_OMEGA):
            with self.subTest(key=hex(key)):
                self.assertEqual(edit_shortcut(key, "\x16", CTRL, 0x2F), "paste")
                self.assertEqual(edit_shortcut(key, "", CTRL, 0x2F), "paste", "no text: the key's position")
                self.assertEqual(edit_shortcut(key, "", CTRL, 0x2E), "copy", "the C position copies")
        self.assertEqual(edit_shortcut(0x441, "", CTRL, 0x2E), "copy")      # Cyrillic ES at C

    def test_azerty_follows_the_letters_not_the_positions(self):
        self.assertEqual(edit_shortcut(A, "\x01", CTRL, 0x10), "select_all")   # A sits where Q is on QWERTY
        self.assertIsNone(edit_shortcut(int(Qt.Key_Q), "\x11", CTRL, 0x1E))    # Q sits where A is

    def test_insert_and_delete_keys(self):
        self.assertEqual(edit_shortcut(int(Qt.Key_Insert), "", SHIFT, 0x152), "paste")
        self.assertEqual(edit_shortcut(int(Qt.Key_Insert), "", CTRL, 0x152), "copy")
        self.assertEqual(edit_shortcut(int(Qt.Key_Delete), "", SHIFT, 0x153), "cut")

    def test_typed_characters_are_no_shortcut(self):
        self.assertIsNone(edit_shortcut(V, "v", 0, 0x2F))
        self.assertIsNone(edit_shortcut(int(Qt.Key_Q), "@", CTRL | ALT, 0x10), "AltGr+Q = @ on a German keyboard")
        self.assertIsNone(edit_shortcut(int(Qt.Key_Insert), "", 0, 0x152))


class Clipboard:
    def __init__(self, text=""):
        self.value = text

    def text(self):
        return self.value

    def setText(self, text):
        self.value = text


class Fields(unittest.TestCase):
    def setUp(self):
        self.a = Fake(manifest())
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.clipboard = Clipboard()
        patcher = mock.patch.object(app.QGuiApplication, "clipboard", return_value=self.clipboard)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.backend = SimpleNamespace(nav=self.nav, refresh=lambda: Backend._copy_pending(self.backend))

    def field(self, tid, text=""):
        self.nav._open_osk(tid)
        self.nav.osk["text"] = text

    def key(self, key, text="", modifiers=0, scan=0, repeat=False):
        Backend.keyPress(self.backend, int(key), text, repeat, modifiers, scan)

    def done(self):
        self.nav.act("play", device="kb")
        return self.a.calls[-1]

    def test_ctrl_v_pastes_into_a_password(self):
        self.clipboard.value = "Pass word!7\r\n"
        self.field("online_password")
        self.key(V, "\x16", CTRL, 0x2F)
        self.assertEqual(self.nav.osk["text"], "Pass word!7", "a copied line's end is not part of it")
        self.assertEqual(self.nav.view()["osk"]["text"], "•" * 11 + "_")
        self.assertEqual(self.done(), ("text", "online_password", "Pass word!7"))

    def test_ctrl_v_on_a_russian_layout_pastes(self):
        self.clipboard.value = "secret"
        self.field("online_password")
        self.key(CYRILLIC_EM, "\x16", CTRL, 0x2F)
        self.assertEqual(self.nav.osk["text"], "secret")

    def test_shift_insert_and_the_right_click_menu_paste(self):
        self.clipboard.value = "abc"
        self.field("online_name", "x")
        self.key(Qt.Key_Insert, "", SHIFT, 0x152)
        Backend.oskEdit(self.backend, "paste")
        self.assertEqual(self.nav.osk["text"], "xabcabc")

    def test_a_password_is_never_copied_or_cut_out(self):
        self.clipboard.value = "before"
        self.field("online_password", "hunter2")
        for key, text, scan in ((C, "\x03", 0x2E), (X, "\x18", 0x2D)):
            self.key(key, text, CTRL, scan)
        self.key(Qt.Key_Insert, "", CTRL, 0x152)
        self.assertEqual(self.clipboard.value, "before")
        self.assertIsNone(self.nav.pending_clipboard)
        self.assertEqual(self.nav.osk["text"], "hunter2")
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "osk.copy_password_blocked"))
        self.assertFalse(self.nav.view()["osk"]["canCopy"])

    def test_copy_and_cut_a_name(self):
        self.field("online_name", "Wishin")
        self.key(C, "\x03", CTRL, 0x2E)
        self.assertEqual((self.clipboard.value, self.nav.osk["text"]), ("Wishin", "Wishin"))
        self.clipboard.value = ""
        self.key(X, "\x18", CTRL, 0x2D)
        self.assertEqual((self.clipboard.value, self.nav.osk["text"]), ("Wishin", ""))
        self.assertTrue(self.nav.view()["osk"]["canCopy"])

    def test_ctrl_a_then_typing_paste_or_backspace_replaces_everything(self):
        self.field("online_name", "old")
        self.key(A, "\x01", CTRL, 0x1E)
        self.assertTrue(self.nav.view()["osk"]["selected"])
        self.key(Qt.Key_N, "n")
        self.assertEqual(self.nav.osk["text"], "n")
        self.key(A, "\x01", CTRL, 0x1E)
        self.clipboard.value = "new"
        self.key(V, "\x16", CTRL, 0x2F)
        self.assertEqual(self.nav.osk["text"], "new")
        self.key(A, "\x01", CTRL, 0x1E)
        self.key(Qt.Key_Backspace)
        self.assertEqual(self.nav.osk["text"], "")
        self.field("online_name", "keep")
        self.key(A, "\x01", CTRL, 0x1E)
        self.nav.act("left", device="kb")
        self.key(Qt.Key_S, "s")
        self.assertEqual(self.nav.osk["text"], "keeps", "moving on the keys drops the mark")

    def test_ctrl_keys_are_no_letters_and_no_launcher_actions(self):
        self.field("online_name", "ab")
        self.key(X, "\x18", CTRL, 0x2D)          # Ctrl+X used to be X = delete one letter
        self.assertEqual(self.nav.overlay, "osk")
        self.field("online_name", "ab")
        page = self.nav.osk["page"]
        self.key(Qt.Key_F, "\x06", CTRL, 0x21)   # F alone switches the key page
        self.key(Qt.Key_B, "\x02", CTRL, 0x30)
        self.assertEqual((self.nav.osk["text"], self.nav.osk["page"]), ("ab", page))

    def test_altgr_still_types(self):
        self.field("online_password")
        self.key(Qt.Key_Q, "@", CTRL | ALT, 0x10)
        self.assertEqual(self.nav.osk["text"], "@")

    def test_held_ctrl_c_copies_once_but_held_ctrl_v_repeats(self):
        self.field("online_name", "a")
        self.clipboard.value = "b"
        self.key(V, "\x16", CTRL, 0x2F)
        self.key(V, "\x16", CTRL, 0x2F, repeat=True)
        self.assertEqual(self.nav.osk["text"], "abb")
        with mock.patch.object(self.nav, "copy_text") as copy:
            self.key(C, "\x03", CTRL, 0x2E, repeat=True)
        copy.assert_not_called()

    def test_pasted_text_is_one_line_and_bounded(self):
        self.field("online_chat")
        self.nav.paste_text("one\ntwo\tthree\x07\r\n")
        self.assertEqual(self.nav.osk["text"], "one two three")
        self.field("online_server")
        self.nav.paste_text("x" * 5000)
        self.assertEqual(len(self.nav.osk["text"]), 256)
        self.field("online_private_chat")
        self.nav.paste_text("y" * 5000)
        self.assertEqual(len(self.nav.osk["text"]), 200, "the chat's own limit still holds")

    def test_player_name_field_pastes_upper_case_like_typing(self):
        self.field("player_name")
        self.nav.paste_text("kazuya")
        self.assertEqual(self.nav.osk["text"], "KAZUYA")

    def test_empty_clipboard_and_no_field_change_nothing(self):
        self.field("online_name", "a")
        self.key(V, "\x16", CTRL, 0x2F)
        self.assertEqual(self.nav.osk["text"], "a")
        self.nav.act("back", device="kb")
        self.clipboard.value = "z"
        Backend.oskEdit(self.backend, "paste")
        self.key(V, "\x16", CTRL, 0x2F)
        self.assertIsNone(self.nav.osk)

    def test_every_language_has_the_menu_texts(self):
        self.field("online_name", "a")
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                self.nav.language = code
                osk = self.nav.view()["osk"]
                self.assertEqual((osk["paste"], osk["copy"]), (i18n.text(code, "osk.paste"), i18n.text(code, "osk.copy")))
                self.assertNotEqual(i18n.text(code, "osk.copy_password_blocked"), "osk.copy_password_blocked")


class Scene(unittest.TestCase):
    """The real QML: a right click on the text opens Paste (and Copy, not for a password); keys carry modifiers."""

    def test_right_click_menu_and_key_modifiers(self):
        from PySide6.QtCore import QObject, Property, Signal, Slot
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtTest import QTest
        from test_ui_loads import FakeBackend, spin

        qt = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        a = Fake(manifest())
        nav = Nav([Game(a.m, a)], language="en")
        nav._open_osk("online_password")

        class Recording(FakeBackend):
            def __init__(self, nav):
                super().__init__(nav)
                self.calls = []

            @Slot(int, str, bool, int, int)
            def keyPress(self, key, text, repeat, modifiers, scan):
                self.calls.append(("key", key, int(modifiers)))

            @Slot(str)
            def oskEdit(self, what):
                self.calls.append(("edit", what))

        backend = Recording(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties({"backend": backend, "wantFull": False})
        engine.load(app.QUrl.fromLocalFile(os.path.join(app.UI_DIR, "Main.qml")))
        window = engine.rootObjects()[0]
        window.show()
        spin(80)
        def item(name, under=None):
            """Repeater delegates have no QObject parent: walk the visual tree."""
            for child in (under or window.contentItem()).childItems():
                if child.objectName() == name:
                    return child
                found = item(name, child)
                if found is not None:
                    return found
            return None

        field = item("oskField")
        menu = item("oskMenu")
        self.assertFalse(menu.isVisible())
        centre = field.mapToScene(QPointF(field.width() / 2, field.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.RightButton, Qt.NoModifier, centre)
        spin()
        self.assertTrue(menu.isVisible())
        self.assertIsNone(item("oskMenu_copy", menu), "no Copy for a password")
        paste = item("oskMenu_paste", menu)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, paste.mapToScene(QPointF(20, 20)).toPoint())
        spin()
        self.assertIn(("edit", "paste"), backend.calls)
        self.assertFalse(menu.isVisible())
        QTest.keyClick(window, Qt.Key_V, Qt.ControlModifier)
        spin()
        self.assertIn(("key", V, CTRL), backend.calls)
        nav.osk["tid"] = "online_name"
        backend.go("left")
        spin()
        QTest.mouseClick(window, Qt.RightButton, Qt.NoModifier, centre)
        spin()
        self.assertIsNotNone(item("oskMenu_copy", menu))
        self.assertEqual(warnings, [])
        window.close()
        del engine
        del qt


if __name__ == "__main__":
    unittest.main()
