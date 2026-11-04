"""Online is driven by pad actions and fake snapshots, never a real lobby."""
import string
import types
import unittest
from unittest import mock

from openrecomp.nav import Game, Nav
from openrecomp.nav_keyboard import ONLINE_KEYS
from test_nav import Fake, manifest
from pad_step import pad_step


class Lobby(Fake):
    def __init__(self):
        super().__init__(manifest("lobby"))
        self.snapshot = dict(phase="offline", message="@online.login_hint", name="", account=False,
                             queue="", match={}, saved_available=True)
        self.texts = dict(online_name="", online_password="", online_server="localhost:1234")
        self.pending = None
        self.polls = 0

    def online_supported(self):
        return True

    def online_state(self):
        return dict(self.snapshot)

    def online_action(self, action):
        self.calls.append(("online", action))
        if action.startswith("login_"):
            self.snapshot.update(phase="logged_in", name=self.texts["online_name"], account=action != "login_guest")
        elif action.startswith("search_"):
            self.snapshot.update(phase="searching", queue=action[7:])
        elif action == "cancel":
            self.snapshot.update(phase="logged_in", queue="")
        elif action == "logout":
            self.snapshot.update(phase="offline")

    def online_poll(self):
        self.polls += 1
        if self.pending:
            self.snapshot.update(self.pending)
            self.pending = None
            return True
        return False

    def online_close(self):
        self.calls.append(("close",))

    def text_value(self, tid):
        return self.texts.get(tid, "")

    def set_text_value(self, tid, value):
        self.calls.append(("text", tid, value))
        self.texts[tid] = value


class OnlineNavigation(unittest.TestCase):
    def setUp(self):
        self.a = Lobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def choose(self, iid):
        items = self.nav.items()
        target = next(i for i, it in enumerate(items) if it.get("id") == iid)
        while self.nav.focus_index(items) != target:
            pad_step(self.nav, target)
        self.nav.act("confirm", device="xbox")

    def pad_key(self, char):
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

    def test_pad_account_keyboard_search_cancel_and_match_stop(self):
        self.choose("online_name")
        for char in "Player":
            self.pad_key(char)
        self.nav.act("play", device="xbox")
        self.choose("online_password")
        for char in "pA@!":
            self.pad_key(char)
        self.assertNotIn("pA@!", str(self.nav.view()))
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.texts["online_password"], "pA@!")
        self.choose("login_account")
        self.choose("search_casual")
        self.choose("cancel")
        self.choose("search_ranked")
        self.a.pending = dict(phase="matched", message="@online.match_found", match=dict(opponent="Rival", ping=42))
        self.assertTrue(self.nav.tick(.016))
        view = self.nav.view()
        self.assertEqual(view["detail"]["title"], "Match found")
        self.assertIn("Rival", str(view))
        self.assertEqual([it["id"] for it in self.nav.items()], ["online_status", "logout", "native"])
        self.nav.act("play", device="xbox")
        self.assertFalse(any(call[0] == "start" for call in self.a.calls))
        self.assertFalse(any(prompt["action"] == "play" for prompt in self.nav.view()["prompts"]))

    def test_guest_and_saved_login_and_native_still_available(self):
        self.choose("login_guest")
        self.assertFalse(self.a.snapshot["account"])
        self.choose("logout")
        self.choose("login_saved")
        self.assertTrue(self.a.snapshot["account"])
        self.choose("native")
        self.assertIn(("native",), self.a.calls)

    def test_kick_focuses_persistent_message_and_never_relogs(self):
        self.choose("login_saved")
        self.choose("search_ranked")
        self.a.pending = dict(phase="kicked", message="Logged in from another place. Log in again only when you choose.")
        self.nav.tick(.016)
        self.nav.tick(30)
        view = self.nav.view()
        self.assertIn("Logged in from another place", view["detail"]["lead"])
        self.assertEqual(self.a.calls.count(("online", "login_saved")), 1)
        self.assertEqual(self.nav.focus_index(self.nav.items()), 0)

    def test_errors_are_persistent_and_recoverable(self):
        self.a.pending = dict(phase="error", message="The connection was lost. Log in again.")
        self.nav.tick(.016)
        self.assertEqual(self.nav.view()["detail"]["lead"], self.a.snapshot["message"])
        self.choose("login_guest")
        self.assertEqual(self.a.snapshot["phase"], "logged_in")

    def test_dry_suppresses_login_search_cancel_poll_text_and_close(self):
        self.nav.dry = True
        self.choose("login_saved")
        self.choose("login_guest")
        self.choose("login_account")
        self.choose("online_password")
        self.nav.type_text("secret")
        self.nav.act("play")
        for phase, action in (("logged_in", "search_ranked"), ("logged_in", "search_casual"), ("searching", "cancel"), ("matched", "logout")):
            self.a.snapshot["phase"] = phase
            self.choose(action)
        self.nav.tick(.016)
        self.nav.close_online()
        self.assertEqual(self.a.polls, 0)
        self.assertEqual(self.a.calls, [])

    def test_password_exact_case_spaces_and_symbols_hidden(self):
        self.choose("online_password")
        self.nav.type_text(" aB @^ ")
        self.assertEqual(self.nav.view()["osk"]["text"], "•••••••_")
        self.nav.act("play")
        self.assertEqual(self.a.texts["online_password"], " aB @^ ")
        self.assertNotIn(" aB @^ ", str(self.nav.view()))

    def test_pad_can_enter_every_ascii_password_character(self):
        self.choose("online_password")
        available = "".join("".join(page) for page in ONLINE_KEYS)
        self.assertTrue(set(string.ascii_letters + string.digits + string.punctuation) <= set(available))
        self.nav.osk["row"] = 4
        self.nav.osk["col"] = 0
        self.nav.act("confirm")
        self.nav.act("play")
        self.assertEqual(self.a.texts["online_password"], " ")

    def test_close_disconnects_through_adapter(self):
        self.nav.close_online()
        self.assertEqual(self.a.calls, [("close",)])
        with mock.patch.object(self.a, "online_close", side_effect=RuntimeError("closed")):
            self.nav.close_online()

    def test_physical_keyboard_does_not_uppercase_password(self):
        from PySide6.QtCore import Qt
        from openrecomp.app import Backend

        self.choose("online_password")
        backend = types.SimpleNamespace(nav=self.nav, refresh=lambda: None)
        Backend.keyDown(backend, Qt.Key_A, "a", False)
        self.nav.act("play")
        self.assertEqual(self.a.texts["online_password"], "a")


if __name__ == "__main__":
    unittest.main()
