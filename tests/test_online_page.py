"""The Online lobby page (nav_online_layout) and the grouped Settings page: driven by pad actions on fakes only."""
import unittest

from openrecomp.nav import Game, Nav
from openrecomp import nav_settings_page
from test_online_nav import Lobby
from test_t4_online_nav import T4Lobby


def lobby_snapshot():
    return dict(phase="logged_in", name="Me", account=True, message="@online.logged_in",
                capabilities=dict(lobby=True, match_flow=True, ranked=True, rooms=True, strict=True),
                me=dict(id="me", name="Me", rating=1610, rank="3rd Dan", tier=12, record=[19, 42, 0]),
                server_ping=34, secure=True,
                players=[dict(id="p1", name="Rival", rank="2nd Dan", rating=1580, record=[3, 1], status="idle", ping=51,
                              ping_measured=True),
                         dict(id="p2", name="Busy", rank="Guest", guest=True, status="playing", ping=120)],
                rooms=[dict(id="r1", name="Open room", host="Rival", status="open")],
                chat=[dict(name="Rival", text="hi"), dict(name="Me", text="hello")])


class LobbyPage(unittest.TestCase):
    def setUp(self):
        self.a = Lobby()
        self.a.snapshot.update(lobby_snapshot())
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def items(self):
        return self.nav.items()

    def focused(self):
        items = self.items()
        return items[self.nav.focus_index(items)]

    def page(self):
        return self.nav.view()["online"]

    def test_page_has_cards_chapters_table_and_chat(self):
        page = self.page()
        self.assertEqual(page["layout"], "lobby")
        self.assertEqual(page["profile"]["name"], "Me")
        self.assertEqual(page["profile"]["rank"], "3rd Dan")
        self.assertIn("19W 42L", page["profile"]["rows"])
        self.assertIn("Server ping 34 ms", page["profile"]["conn"])
        self.assertTrue(page["find"]["ranked"]["present"] and page["find"]["quick"]["present"])
        self.assertEqual([c["id"] for c in page["chapters"]][:2], ["lobby", "rooms"])
        self.assertEqual(page["chapters"][0]["badge"], "2")
        rows = [line for line in page["body"]["lines"] if line["kind"] == "trow"]
        self.assertEqual([r["cells"][1]["text"] for r in rows], ["Rival", "Busy"])
        self.assertEqual(rows[0]["cells"][-1]["text"], "51 ms")          # measured
        self.assertEqual(rows[1]["cells"][-1]["text"], "~120 ms")        # estimated
        self.assertTrue(rows[1]["dim"])                                   # playing: "Not available"
        self.assertIn("Not available", [line.get("label") for line in page["body"]["lines"]])
        self.assertEqual([line["text"] for line in page["chat"]["lines"]], ["hi", "hello"])
        self.assertTrue(page["chat"]["lines"][1]["own"])

    def test_pad_moves_by_line_and_left_right_inside_a_player_row(self):
        items = self.items()
        target = next(i for i, it in enumerate(items) if it.get("id") == "challenge:p1")
        for _ in range(40):
            if self.nav.focus_index(self.items()) == target:
                break
            self.nav.act("down", device="xbox")
        self.assertEqual(self.focused()["id"], "challenge:p1")
        row = next(line for line in self.page()["body"]["lines"] if line.get("focused"))
        self.assertGreaterEqual(len(row["buttons"]), 1)
        group = self.focused()["group"]
        self.nav.act("right", device="xbox")
        if len([it for it in self.items() if it.get("group") == group]) > 1:
            self.assertEqual(self.focused()["group"], group)
            self.assertNotEqual(self.focused()["id"], "challenge:p1")
            self.nav.act("left", device="xbox")
        self.nav.act("down", device="xbox")                    # the next line: Busy's row
        self.assertEqual(self.focused()["id"], "challenge:p2")

    def test_chapter_buttons_switch_and_remember(self):
        self.nav.act("chapterNext", device="xbox")
        self.assertEqual(self.focused()["region"], "rooms")
        self.assertEqual(self.page()["chapter"], "rooms")
        self.nav.act("down", device="xbox")
        remembered = self.focused()["id"]
        self.nav.act("chapterPrev", device="xbox")
        self.assertEqual(self.page()["chapter"], "lobby")
        self.nav.act("chapterNext", device="xbox")
        self.assertEqual(self.focused()["id"], remembered)
        self.nav.click_chapter("lobby")
        self.assertEqual(self.page()["chapter"], "lobby")

    def test_x_goes_to_the_chat_field_and_back(self):
        self.nav.act("down", device="xbox")
        before = self.focused()["id"]
        self.nav.act("x", device="xbox")
        self.assertEqual(self.focused()["id"], "online_chat")
        self.assertEqual(self.page()["focusRegion"], "chat")
        self.nav.act("x", device="xbox")
        self.assertEqual(self.focused()["id"], before)

    def test_hidden_chat_counts_new_messages(self):
        items = self.items()
        self.nav.focus[self.nav.key()] = next(i for i, it in enumerate(items) if it.get("id") == "chat_toggle")
        self.nav.act("confirm", device="xbox")
        page = self.page()
        self.assertFalse(page["chatOpen"])
        self.assertNotIn("online_chat", [it.get("id") for it in self.items()])
        self.a.snapshot["chat"] = self.a.snapshot["chat"] + [dict(name="Rival", text="new"), dict(name="Rival", text="two")]
        self.assertEqual(self.page()["chat"]["unread"], 2)
        self.nav.act("x", device="xbox")                         # X opens it again, into the text field
        self.assertTrue(self.page()["chatOpen"])
        self.assertEqual(self.focused()["id"], "online_chat")
        self.assertEqual(self.page()["chat"]["unread"], 0)

    def test_moved_row_keeps_focus_and_vanished_row_resets(self):
        items = self.items()
        self.nav.focus[self.nav.key()] = next(i for i, it in enumerate(items) if it.get("id") == "challenge:p2")
        self.items()
        self.a.snapshot["chat"] = self.a.snapshot["chat"] + [dict(name="X", text="y")]
        self.a.snapshot["players"] = [dict(id="p0", name="New")] + self.a.snapshot["players"]
        self.assertEqual(self.focused()["id"], "challenge:p2")
        self.a.snapshot["players"] = [p for p in self.a.snapshot["players"] if p["id"] != "p2"]
        self.assertEqual(self.nav.focus_index(self.items()), 0)

    def test_guest_sees_ranked_greyed_with_the_reason(self):
        self.a.snapshot.update(account=False)
        ranked = self.page()["find"]["ranked"]
        self.assertTrue(ranked["disabled"])
        self.assertEqual(ranked["value"], "Ranked needs an account (guests play casual)")
        items = self.items()
        self.nav.focus[self.nav.key()] = next(i for i, it in enumerate(items) if it.get("id") == "search_ranked")
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("online", "search_ranked"), self.a.calls)

    def test_profile_card_names_the_build_and_game_folder(self):
        self.a.snapshot.update(build_id="1a82466271e3b256", game_folder="C:/Games/T4")
        self.assertEqual(self.page()["profile"]["build"], ["Build 1a82466271e3b256", "C:/Games/T4"])

    def test_strict_ranked_option_is_a_find_card_chip(self):
        options = [o["label"] for o in self.page()["find"]["options"]]
        self.assertIn("Strict (Ranked: ±150 rating)", options)
        items = self.items()
        self.nav.focus[self.nav.key()] = next(i for i, it in enumerate(items) if it.get("id") == "ranked_strict")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("online", "ranked_strict"), self.a.calls)

    def test_login_screen_is_one_card(self):
        self.a.snapshot.update(phase="offline", message="@online.login_hint", saved_available=True)
        page = self.page()
        self.assertEqual(page["layout"], "login")
        self.assertEqual(page["page"], "main")
        self.assertEqual(page["name"]["label"], "Player or account name")
        self.assertEqual(page["login"]["label"], "Log in to account")
        self.assertEqual(page["guest"]["label"], "Log in as guest")
        self.assertTrue(page["remember"]["on"])
        self.assertEqual([f["label"] for f in page["footer"]][:1], ["Lobby address"])     # out of the card body
        self.a.snapshot.update(phase="error", message="@online.auth_failed")
        page = self.page()
        self.assertTrue(page["password"]["error"])                 # the red line sits under the password
        self.assertFalse(page["error"])
        self.a.snapshot.update(phase="error", message="@online.disconnected")
        self.assertTrue(self.page()["error"])                       # a general error: the card's own line


class LoginCard(unittest.TestCase):
    def setUp(self):
        self.a = Lobby()
        self.a.snapshot.update(phase="offline", message="@online.login_hint", saved_available=False)
        self.a.texts["online_name"] = ""
        self.saved = []
        self.nav = Nav([Game(self.a.m, self.a)], language="en", on_online_prefs=self.saved.append)
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def focused(self):
        items = self.nav.items()
        return items[self.nav.focus_index(items)].get("id")

    def go(self, iid):
        for _ in range(40):
            if self.focused() == iid:
                return
            items = self.nav.items()
            target = next(i for i, it in enumerate(items) if it.get("id") == iid)
            self.nav.act("down" if self.nav.focus_index(items) < target else "up", device="xbox")
        self.fail("not reached: " + iid)

    def test_pad_starts_on_the_name_then_on_log_in(self):
        self.assertEqual(self.focused(), "online_name")
        self.a.texts["online_name"] = "Me"
        self.nav.login_focused.discard(self.a.m["id"])
        self.assertEqual(self.focused(), "login_account")
        self.nav.act("right", device="xbox")
        self.assertEqual(self.focused(), "login_guest")
        self.nav.act("left", device="xbox")
        self.assertEqual(self.focused(), "login_account")

    def test_show_password_and_remember_me(self):
        self.a.texts["online_password"] = "secret"
        self.assertNotIn("secret", str(self.nav.view()["online"]["password"]))
        self.go("login_show_password")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.view()["online"]["password"]["value"], "secret")
        self.go("login_remember")
        self.nav.act("confirm", device="xbox")
        self.assertFalse(self.nav.view()["online"]["remember"]["on"])
        self.assertEqual(self.saved[-1][self.a.m["id"]]["auto_login"], False)
        self.go("login_account")
        self.nav.act("confirm", device="xbox")
        # Remember me off: the adapter is told before the login, so the login is not kept
        self.assertEqual([c for c in self.a.calls if c[0] == "online"][-2:],
                         [("online", "login_remember"), ("online", "login_account")])

    def test_forgot_password_is_its_own_page(self):
        self.a.snapshot["capabilities"] = dict(account_recovery=True)
        self.assertNotIn("online_recovery_code", [it.get("id") for it in self.nav.items()])
        self.go("login_forgot")
        self.nav.act("confirm", device="xbox")
        page = self.nav.view()["online"]
        self.assertEqual(page["page"], "recover")
        self.assertIn("online_recovery_code", [it.get("id") for it in self.nav.items()])
        self.assertNotIn("login_guest", [it.get("id") for it in self.nav.items()])
        self.go("login_back")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.view()["online"]["page"], "main")

    def test_remembered_login_logs_in_once_by_itself(self):
        self.a.snapshot.update(saved_available=True)
        self.nav.tick(0.016)
        self.nav.tick(0.016)
        self.assertEqual(self.a.calls.count(("online", "login_saved")), 1)

    def test_no_automatic_login_when_switched_off_or_dry(self):
        self.a.snapshot.update(saved_available=True)
        nav = Nav([Game(self.a.m, self.a)], language="en", online_prefs={self.a.m["id"]: dict(auto_login=False)})
        nav.screen = "hub"
        nav.sec[self.a.m["id"]] = "online"
        nav.tick(0.016)
        self.assertNotIn(("online", "login_saved"), self.a.calls)
        nav = Nav([Game(self.a.m, self.a)], language="en")
        nav.dry = True
        nav.screen = "hub"
        nav.sec[self.a.m["id"]] = "online"
        nav.tick(0.016)
        self.assertNotIn(("online", "login_saved"), self.a.calls)


class T4SharesThePage(unittest.TestCase):
    def test_t4_login_uses_the_same_card(self):
        a = T4Lobby()
        a.snapshot.update(phase="offline", message="@online.login_hint")
        nav = Nav([Game(a.m, a)], language="en")
        nav.screen = "hub"
        nav.sec["t4"] = "online"
        page = nav.view()["online"]
        self.assertEqual(page["layout"], "login")
        self.assertTrue(page["guest"] and page["name"])

    def test_t4_lobby_uses_the_same_page(self):
        a = T4Lobby()
        a.snapshot.update(phase="logged_in", name="Me")
        nav = Nav([Game(a.m, a)], language="en")
        nav.screen = "hub"
        nav.sec["t4"] = "online"
        page = nav.view()["online"]
        self.assertEqual(page["layout"], "lobby")
        self.assertIn("lobby", [c["id"] for c in page["chapters"]])
        self.assertNotIn("search_ranked", [it.get("id") for it in nav.items()])
        self.assertFalse(page["find"]["ranked"]["present"])


class SettingsGroups(unittest.TestCase):
    def test_settings_are_grouped_with_headings_and_update_rows(self):
        a = Lobby()
        a.settings = lambda: [
            dict(id="mute", label="@mute", options=[(False, "@off"), (True, "@on")], value=False),
            dict(id="internal_res", label="@internal_resolution", options=[("native", "@resolution.native")], value="native"),
            dict(id="mystery", label="@mute", options=[(1, "1")], value=1)]
        nav = Nav([Game(a.m, a)], language="en", on_update_check=lambda: None)
        nav.screen = "hub"
        nav.sec[a.m["id"]] = "settings"
        items = nav.items()
        order = [(it.get("kind"), it.get("settingsGroup"), it.get("id")) for it in items]
        groups = [g for kind, g, _ in order if kind == "heading"]
        self.assertEqual(groups, ["display", "audio", "updates", "advanced"])
        self.assertLess(order.index(("cycler", "display", "internal_res")), order.index(("cycler", "audio", "mute")))
        self.assertIn(("action", "updates", "launcher_update"), order)
        page = nav.view()["settingsPage"]
        self.assertEqual(page["layout"], "groups")
        self.assertEqual(page["lines"][0]["kind"], "group")
        self.assertEqual([o["current"] for o in page["detail"]["options"]], [True])
        self.assertEqual(set(nav_settings_page.GROUPS), set(nav_settings_page.GROUP_LABELS))


if __name__ == "__main__":
    unittest.main()
