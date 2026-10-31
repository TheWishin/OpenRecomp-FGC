"""Private messages and report reasons can be composed with pad buttons alone."""
import unittest

from openrecomp.nav import Game, Nav
from test_online_nav import Lobby


class ChatKeyboardTests(unittest.TestCase):
    def setUp(self):
        self.adapter = Lobby()
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "online"

    def pad_key(self, char):
        if char == " ":
            row, col = len(self.nav._osk_keys()), 0
        else:
            while not any(char in row for row in self.nav._osk_keys()):
                self.nav.act("social", device="xbox")
            keys = self.nav._osk_keys()
            row = next(i for i, line in enumerate(keys) if char in line)
            col = keys[row].index(char)
        while self.nav.osk["row"] != row:
            self.nav.act("down" if self.nav.osk["row"] < row else "up", device="xbox")
        while self.nav.osk["col"] != col:
            self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")

    def test_private_message_pad_typing_saves_draft_without_sending(self):
        self.nav._open_osk("online_private_chat")
        self.assertEqual(self.nav.osk["title"], "@online_chat.private_compose")
        for char in "Hi @Rival!":
            self.pad_key(char)
        self.nav.act("play", device="xbox")
        self.assertIsNone(self.nav.overlay)
        self.assertEqual(self.adapter.calls, [("text", "online_private_chat", "Hi @Rival!")])

    def test_report_reason_pad_delete_and_cancel_preserves_saved_draft(self):
        field = "online_private_report_reason"
        self.adapter.texts[field] = "Saved"
        self.nav._open_osk(field)
        self.assertEqual(self.nav.osk["title"], "@online_chat.report_reason")
        self.pad_key("!")
        self.nav.act("x", device="xbox")
        self.assertEqual(self.nav.osk["text"], "Saved")
        self.pad_key("?")
        self.nav.act("back", device="xbox")
        self.assertEqual(self.adapter.texts[field], "Saved")
        self.assertEqual(self.adapter.calls, [])

    def test_private_fields_enforce_protocol_limit_for_pad_and_keyboard(self):
        for field in ("online_private_chat", "online_private_report_reason"):
            with self.subTest(field=field):
                self.adapter.texts[field] = "a" * 199
                self.nav._open_osk(field)
                self.pad_key("!")
                self.pad_key(" ")
                self.pad_key("b")
                self.nav.type_text("extra")
                self.assertEqual(self.nav.osk["text"], "a" * 199 + "!")
                self.nav.act("play", device="xbox")
                self.assertEqual(self.adapter.texts[field], "a" * 199 + "!")

    def test_existing_private_draft_is_bounded_on_open(self):
        self.adapter.texts["online_private_chat"] = "a" * 201
        self.nav._open_osk("online_private_chat")
        self.assertEqual(self.nav.osk["text"], "a" * 200)

    def test_dry_private_draft_done_does_not_write(self):
        self.nav.dry = True
        self.nav._open_osk("online_private_chat")
        self.pad_key("a")
        self.nav.act("play", device="xbox")
        self.assertEqual(self.adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
