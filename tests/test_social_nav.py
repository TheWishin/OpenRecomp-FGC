"""Social controls use only fake snapshots and controller input."""
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from test_online_nav import Lobby, OnlineNavigation


class SocialLobby(Lobby):
    def __init__(self):
        super().__init__()
        self.snapshot.update(phase="logged_in", capabilities=dict(lobby=True, private_rooms=True, friends=True),
                             rooms=[dict(id="locked", name="Locked room", lock="password")],
                             room=dict(id="mine", code="ABC123"), friends=[dict(name="Rival", status="online", invite=True)],
                             friend_incoming=[dict(name="New friend")], friend_outgoing=[dict(name="Pending")],
                             invites=[dict(id="incoming", name="Rival")],
                             outgoing_invite=dict(id="outgoing", name="Rival"))
        self.texts.update(online_chat="", online_room_name="", online_room_password="secret",
                          online_room_code="", online_friend_name="")


class SocialNavigation(unittest.TestCase):
    choose = OnlineNavigation.choose
    pad_key = OnlineNavigation.pad_key

    def setUp(self):
        self.a = SocialLobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def ids(self):
        return [item.get("id") for item in self.nav.items()]

    def test_all_social_actions_are_pad_reachable(self):
        actions = ("create_password_room", "create_code_room", "join_room_code", "join_room:locked",
                   "refresh_friends", "add_friend", "remove_friend:Rival", "invite_friend:Rival", "invite_room:Rival",
                   "accept_friend:New friend", "decline_friend:New friend", "cancel_friend:Pending",
                   "accept_invite:incoming", "decline_invite:incoming", "cancel_invite")
        for action in actions:
            self.choose(action)
        self.assertTrue(all(("online", action) in self.a.calls for action in actions))
        self.choose("room_invite_code")
        self.assertEqual(self.nav.view()["detail"]["lead"], "ABC123")

    def test_each_new_field_opens_pad_keyboard_and_password_stays_hidden(self):
        for tid in ("online_room_name", "online_room_password", "online_room_code", "online_friend_name"):
            self.choose(tid)
            self.assertEqual(self.nav.osk["tid"], tid)
            self.pad_key("a")
            self.nav.act("play", device="xbox")
            self.assertTrue(self.a.texts[tid].endswith("a"))
        self.assertNotIn("secreta", str(self.nav.view()))

    def test_t4_capabilities_hide_private_rooms_friends_and_invites(self):
        self.a.snapshot["capabilities"] = dict(lobby=True, match_flow=True, ranked=False)
        ids = self.ids()
        for iid in ("online_room_password", "create_password_room", "create_code_room", "join_room_code",
                    "join_room:locked", "room_invite_code", "refresh_friends", "add_friend",
                    "remove_friend:Rival", "accept_invite:incoming"):
            self.assertNotIn(iid, ids)
        self.assertIn("create_room", ids)
        self.assertIn("online_chat", ids)

    def test_dry_suppresses_all_social_mutations_and_writes(self):
        self.nav.dry = True
        for item in list(self.nav.items()):
            iid = item.get("id")
            if iid and item.get("run") and iid != "native":
                self.choose(iid)
                if self.nav.overlay == "osk":
                    self.nav.type_text("dry text")
                    self.nav.act("play", device="xbox")
        self.nav.tick(.016)
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.a.polls, 0)

    def test_changed_outgoing_invite_cannot_be_cancelled_by_old_focus(self):
        items = self.nav.items()
        index = next(i for i, item in enumerate(items) if item.get("id") == "cancel_invite")
        self.nav.focus[self.a.m["id"] + ":online"] = index
        self.a.snapshot["outgoing_invite"] = dict(id="replacement", name="Other friend")
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("online", "cancel_invite"), self.a.calls)
        self.assertEqual(self.nav.focus[self.a.m["id"] + ":online"], 0)

    def test_remote_friend_names_and_codes_remain_literal(self):
        literal = "@online.logout"
        self.a.snapshot.update(friends=[dict(name=literal, status=literal, invite=True)],
                               room=dict(id="mine", code=literal))
        items = self.nav.items()
        target = next(i for i, item in enumerate(items) if item.get("id") == "remove_friend:" + literal)
        while self.nav.focus_index(items) != target:
            self.nav.act("down" if self.nav.focus_index(items) < target else "up", device="xbox")
        self.assertIn(literal, str(self.nav.view()["detail"]))
        self.choose("room_invite_code")
        self.assertEqual(self.nav.view()["detail"]["lead"], literal)

    def test_social_rows_localize_in_all_catalogs(self):
        for language in i18n.LANGUAGES:
            self.nav.language = language
            for index, item in enumerate(self.nav.items()):
                if item.get("kind") != "heading":
                    self.nav.focus[self.a.m["id"] + ":online"] = index
                    self.assertNotIn("@online.", str(self.nav.view()), (language, item.get("id")))


if __name__ == "__main__":
    unittest.main()
