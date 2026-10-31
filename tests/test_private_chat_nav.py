"""Private messages and signed-line reporting stay reachable by controller alone."""
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from test_online_nav import Lobby, OnlineNavigation


class PrivateLobby(Lobby):
    def __init__(self):
        super().__init__()
        self.snapshot.update(phase="logged_in", capabilities=dict(lobby=True, private_chat=True, private_reports=True),
            players=[dict(id="peer", name="Peer")],
            private_chat=dict(selected="", unread=2, report_limit=5, threads=[dict(id="peer", name="Peer", unread=2,
                messages=[dict(id="line", name="Peer", text="Hello", selected=False)])]))
        self.texts.update(online_private_chat="", online_private_report_reason="")

    def online_action(self, action):
        super().online_action(action)
        data = self.snapshot["private_chat"]
        if action.startswith("private_open:"):
            data["selected"] = action.partition(":")[2]
            for thread in data["threads"]:
                if thread["id"] == data["selected"]:
                    thread["unread"] = 0
        elif action == "private_close":
            data["selected"] = ""
        elif action.startswith("private_select:"):
            target = action.partition(":")[2]
            for thread in data["threads"]:
                for message in thread["messages"]:
                    if message["id"] == target:
                        message["selected"] = not message["selected"]


class PrivateChatNavigationTests(unittest.TestCase):
    choose = OnlineNavigation.choose
    pad_key = OnlineNavigation.pad_key

    def setUp(self):
        self.a = PrivateLobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def ids(self):
        return [item.get("id") for item in self.nav.items()]

    def test_pad_opens_unread_thread_composes_sends_and_closes(self):
        item = next(item for item in self.nav.items() if item.get("id") == "private_open:peer")
        self.assertEqual(i18n.localize(item["value"], "en"), "Unread: 2")
        self.choose("private_open:peer")
        self.assertEqual(self.a.snapshot["private_chat"]["selected"], "peer")
        self.assertEqual(self.a.snapshot["private_chat"]["threads"][0]["unread"], 0)
        self.choose("online_private_chat")
        self.assertEqual(self.nav.osk["tid"], "online_private_chat")
        for char in "Hi!":
            self.pad_key(char)
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.texts["online_private_chat"], "Hi!")
        self.choose("private_send")
        self.assertIn(("online", "private_send"), self.a.calls)
        self.choose("private_close")
        self.assertNotIn("online_private_chat", self.ids())

    def test_report_requires_explicit_message_selection_and_reason_keyboard(self):
        self.choose("private_open:peer")
        self.choose("private_select:line")
        self.assertTrue(self.a.snapshot["private_chat"]["threads"][0]["messages"][0]["selected"])
        self.choose("online_private_report_reason")
        for char in "spam":
            self.pad_key(char)
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.texts["online_private_report_reason"], "spam")
        self.choose("private_report")
        self.assertIn(("online", "private_report"), self.a.calls)

    def test_report_cap_absence_keeps_history_and_hides_reporting(self):
        self.a.snapshot["capabilities"]["private_reports"] = False
        self.choose("private_open:peer")
        ids = self.ids()
        self.assertIn("online_private_chat", ids)
        self.assertNotIn("private_select:line", ids)
        self.assertNotIn("online_private_report_reason", ids)
        self.assertNotIn("private_report", ids)
        self.assertIn("Hello", str(i18n.localize(self.nav.items(), "en")))

    def test_private_cap_absence_hides_all_private_data_and_controls(self):
        self.a.snapshot["capabilities"]["private_chat"] = False
        self.assertFalse(any(str(iid).startswith("private_") for iid in self.ids()))
        self.assertNotIn("Hello", str(self.nav.items()))

    def test_thread_and_roster_ids_offer_one_conversation_per_name(self):
        self.a.snapshot["players"] = [dict(id="lobby-uuid", name="PEER")]
        opens = [item for item in self.nav.items() if str(item.get("id", "")).startswith("private_open:")]
        self.assertEqual([item["id"] for item in opens], ["private_open:peer"])
        self.assertEqual(opens[0]["target"], ("peer", "Peer"))
        self.assertEqual(i18n.localize(opens[0]["value"], "en"), "Unread: 2")

    def test_renamed_roster_target_cannot_open_from_stale_focus(self):
        self.a.snapshot["private_chat"]["threads"] = []
        self.a.snapshot["players"] = [dict(id="lobby-uuid", name="Peer")]
        items = self.nav.items()
        self.nav.focus[self.nav.key()] = next(i for i, item in enumerate(items)
                                               if item.get("id") == "private_open:lobby-uuid")
        self.a.snapshot["players"][0]["name"] = "Replacement"
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("online", "private_open:lobby-uuid"), self.a.calls)
        self.assertEqual(self.nav.focus[self.nav.key()], 0)

    def test_thread_change_cannot_send_to_replacement_from_stale_focus(self):
        self.choose("private_open:peer")
        items = self.nav.items()
        self.nav.focus[self.nav.key()] = next(i for i, item in enumerate(items) if item.get("id") == "private_send")
        data = self.a.snapshot["private_chat"]
        data["threads"].append(dict(id="other", name="Other", unread=0, messages=[]))
        data["selected"] = "other"
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("online", "private_send"), self.a.calls)
        self.assertEqual(self.nav.focus[self.nav.key()], 0)

    def test_remote_names_and_messages_remain_literal(self):
        thread = self.a.snapshot["private_chat"]["threads"][0]
        thread.update(name="@online.logout")
        thread["messages"][0].update(name="@online.logout", text="@online.account")
        self.choose("private_open:peer")
        items = self.nav.items()
        self.nav.focus[self.nav.key()] = next(i for i, item in enumerate(items) if item.get("id") == "private_select:line")
        self.assertEqual(self.nav.view()["detail"]["title"], "@online.logout")
        self.assertEqual(self.nav.view()["detail"]["lead"], "@online.account")

    def test_dry_private_actions_and_keyboard_never_write_or_send(self):
        self.a.snapshot["private_chat"]["selected"] = "peer"
        self.nav.dry = True
        for iid in ("private_open:peer", "private_select:line", "private_send", "private_report", "private_close"):
            self.choose(iid)
        self.choose("online_private_chat")
        self.pad_key("a")
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.calls, [])


if __name__ == "__main__":
    unittest.main()
