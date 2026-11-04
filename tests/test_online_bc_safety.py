"""Independent b/c safety checks: inert adapters, denied I/O and local fixtures only."""
import json
import os
import tempfile
import unittest
from unittest import mock

from openrecomp.nav import Game, Nav
from test_online_adapter import Subject
from test_online_nav import Lobby
from pad_step import pad_step


class OnlineBCSafetyTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied in safety test")))

    def navigation(self, adapter=None):
        adapter = adapter or Lobby()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec[adapter.m["id"]] = "online"
        return adapter, nav

    def choose(self, nav, action):
        items = nav.items()
        target = next(i for i, item in enumerate(items) if item.get("id") == action)
        while nav.focus_index(items) != target:
            pad_step(nav, target)
        nav.act("confirm", device="xbox")

    def social_snapshot(self):
        return dict(phase="logged_in", capabilities=dict(lobby=True, match_flow=True, ranked=True,
                                                         private_rooms=True, friends=True),
                    players=[dict(id="other", name="Other")], rooms=[dict(id="public", name="Public")],
                    room=dict(id="own", code="TESTCODE"), challenge=dict(id="challenge", name="Other"),
                    friends=[dict(name="Friend", invite=True)], friend_incoming=[dict(name="Incoming")],
                    friend_outgoing=[dict(name="Pending")], invites=[dict(id="invite", name="Friend")],
                    outgoing_invite=dict(id="sent", name="Friend"))

    def test_generic_manifest_routes_to_shared_online_flow(self):
        adapter, nav = self.navigation()
        actions = {item.get("id") for item in nav.items()}
        self.assertIn("login_guest", actions)
        self.assertIn("login_account", actions)
        self.assertIn("native", actions)

    def test_t5dr_manifest_uses_adapter_without_implicit_native_launch(self):
        adapter, nav = self.navigation()
        adapter.m["adapter"] = "t5dr"
        adapter.snapshot.update(self.social_snapshot())
        for phase in ("offline", "logged_in", "matched", "playing", "result_sent"):
            with self.subTest(phase=phase):
                adapter.snapshot["phase"] = phase
                self.assertIn("online_status", [item.get("id") for item in nav.items()])
                nav.act("play", device="xbox")
                self.assertEqual(adapter.calls, [])
        adapter.snapshot["phase"] = "offline"
        self.choose(nav, "login_guest")
        self.assertEqual(adapter.calls, [("online", "login_guest")])
        self.assertEqual(adapter.polls, 0)

    def test_dry_all_match_steps_and_social_actions_deny_io(self):
        adapter, nav = self.navigation()
        nav.dry = True
        adapter.snapshot.update(self.social_snapshot())
        actions = ("refresh_players", "challenge:other", "accept_challenge", "decline_challenge",
                   "refresh_rooms", "create_room", "create_password_room", "create_code_room",
                   "join_room:public", "join_room_code", "leave_room", "send_chat", "refresh_friends",
                   "add_friend", "accept_friend:Incoming", "decline_friend:Incoming", "cancel_friend:Pending",
                   "remove_friend:Friend", "invite_friend:Friend", "invite_room:Friend",
                   "accept_invite:invite", "decline_invite:invite", "cancel_invite")
        for action in actions:
            with self.subTest(action=action):
                self.choose(nav, action)
        for phase, actions in (("matched", ("start_match", "cancel_match")),
                               ("starting", ("cancel_match",)), ("playing", ("stop_match",)),
                               ("result", ("result_win", "result_loss", "result_none")),
                               ("result_sent", ("rematch", "return_lobby"))):
            adapter.snapshot.update(phase=phase)
            adapter.snapshot["capabilities"]["rematch"] = True
            for action in actions:
                with self.subTest(phase=phase, action=action):
                    self.choose(nav, action)
        nav.tick(120)
        nav.close_online()
        self.assertEqual(adapter.calls, [])
        self.assertEqual(adapter.polls, 0)

    def test_replaced_invite_cannot_be_accepted_using_stale_focus(self):
        adapter, nav = self.navigation()
        adapter.snapshot.update(self.social_snapshot())
        items = nav.items()
        index = next(i for i, item in enumerate(items) if item.get("id") == "accept_invite:invite")
        nav.focus[adapter.m["id"] + ":online"] = index
        adapter.snapshot["invites"] = [dict(id="replacement", name="Another")]
        nav.act("confirm", device="xbox")
        self.assertEqual(adapter.calls, [])
        self.assertEqual(nav.focus[adapter.m["id"] + ":online"], 0)

    def test_generic_lobby_hides_unsupported_social_and_rematch_rows(self):
        adapter, nav = self.navigation()
        adapter.snapshot.update(self.social_snapshot())
        adapter.snapshot["capabilities"] = dict(lobby=True, match_flow=True, ranked=False)
        actions = {item.get("id") for item in nav.items()}
        self.assertTrue({"challenge:other", "create_room", "join_room:public", "send_chat"} <= actions)
        unsupported = {"search_ranked", "online_room_password", "online_room_code", "create_password_room",
                       "create_code_room", "join_room_code", "refresh_friends", "add_friend",
                       "invite_friend:Friend", "invite_room:Friend", "accept_invite:invite"}
        self.assertTrue(actions.isdisjoint(unsupported))
        adapter.snapshot["phase"] = "result_sent"
        self.assertNotIn("rematch", {item.get("id") for item in nav.items()})

    def test_explicit_advanced_direct_mode_ignores_stale_lobby_state(self):
        adapter, nav = self.navigation()
        adapter.m["adapter"] = "t4"
        adapter.snapshot.update(self.social_snapshot())
        adapter.snapshot["capabilities"]["direct_ip"] = True
        adapter.snapshot["capabilities"]["rematch"] = True
        unsupported = {"login_guest", "login_account", "login_saved", "search_casual", "search_ranked",
                       "challenge:other", "create_room", "join_room:public", "send_chat", "online_chat",
                       "create_password_room", "create_code_room", "join_room_code", "refresh_friends",
                       "add_friend", "invite_friend:Friend", "invite_room:Friend", "accept_invite:invite",
                       "result_win", "result_loss", "result_none", "rematch", "return_lobby", "native"}
        for phase in ("offline", "logged_in", "matched", "playing", "result", "result_sent"):
            with self.subTest(phase=phase):
                adapter.snapshot["phase"] = phase
                actions = {item.get("id") for item in nav.items()}
                self.assertTrue({"host", "join", "online_address", "check", "collect_logs", "direct_back"} <= actions)
                self.assertTrue(actions.isdisjoint(unsupported))
                self.assertNotIn("start_match", actions)
        adapter.snapshot["phase"] = "offline"
        self.choose(nav, "host")
        self.assertEqual(adapter.calls, [("online", "host")])

    def test_kicked_session_ignores_late_login_completion_and_cannot_reconnect_itself(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=directory))
        adapter = Subject(directory)
        self.addCleanup(adapter.online_close)
        adapter.online_action("login_guest")
        old_client = adapter.clients[-1]
        old_client.events.put(dict(t="kicked", reason="logged in from another place"))
        adapter.online_poll()
        self.assertTrue(old_client.closed.wait(1))
        self.assertEqual(adapter.online_state()["phase"], "kicked")
        self.assertIsNone(adapter._online_client)
        adapter._online_fields["online_password"] = "fake-sensitive-password"
        adapter._online_fields["online_room_password"] = "fake-sensitive-room-password"
        for _ in range(5):
            adapter.online_poll()
            adapter.online_state()
        self.assertEqual(len(adapter.clients), 1)
        self.assertEqual(old_client.calls.count("connect"), 1)
        self.assertEqual(adapter.online_state()["phase"], "kicked")
        public = json.dumps(adapter.online_state())
        self.assertNotIn("fake-sensitive-password", public)
        self.assertNotIn("fake-sensitive-room-password", public)
        self.assertNotIn(old_client.session, public)


if __name__ == "__main__":
    unittest.main()
