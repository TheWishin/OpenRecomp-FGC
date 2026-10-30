"""Social flow uses only installed-client doubles and repository-local temporary files."""
import json
import os
import tempfile
import unittest
from unittest import mock

from test_shared_lobby import LobbyClient, Playable


class SocialClient(LobbyClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.room_code = None
        self.friend_list = dict(friends=[dict(name="Friend", status="online", invite="ok", retry=0)],
                                incoming=[dict(name="Asker")], outgoing=[dict(name="Pending")])
        self.wait = 0

    def private_rooms_ok(self):
        return True

    def has_friends(self):
        return True

    def invite_wait(self, name):
        return self.wait

    def create_room(self, **kwargs):
        self.calls.append(("create", kwargs))
        self.room_code = "TEST-CODE" if kwargs.get("private") == "code" else None
        return dict(id="mine", name="Mine", lock=kwargs.get("private"), password="hidden")

    def join_room(self, room_id=None, **kwargs):
        self.calls.append(("join", room_id, kwargs))
        self.room_code = kwargs.get("code")
        return dict(id=room_id or "by-code", name="Room")

    def friends_list(self):
        return self.friend_list

    def add_friend(self, name):
        self.calls.append(("friend_add", name))

    def answer_friend(self, name, accept):
        self.calls.append(("friend_answer", name, accept))

    def remove_friend(self, name):
        self.calls.append(("friend_remove", name))

    def cancel_friend_request(self, name):
        self.calls.append(("friend_cancel", name))

    def invite(self, name, kind):
        self.calls.append(("invite", name, kind))
        return dict(invite="outgoing", name=name, kind=kind, token="hidden")

    def answer_invite(self, invite_id, accept):
        self.calls.append(("invite_answer", invite_id, accept))

    def cancel_invite(self, invite_id):
        self.calls.append(("invite_cancel", invite_id))


class Social(Playable):
    online_package = "t5lobby"
    online_game = ""
    online_ranked = True

    def make_client(self, **kwargs):
        client = SocialClient(**kwargs)
        self.clients.append(client)
        return client


class SocialOnlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name).start()
        self.probe = mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False).start()
        self.a = Social(self.directory.name)
        self.addCleanup(self.a.online_close)
        self.a.set_text_value("online_password", "fake-password")
        self.action("login_account")
        self.client = self.a.clients[-1]

    def action(self, action):
        self.a.online_action(action)
        self.a.online_poll()

    def test_private_room_password_is_explicit_and_not_in_snapshot(self):
        self.a.set_text_value("online_room_password", "fake-room-password")
        self.assertFalse(any(call[0] == "create" for call in self.client.calls if isinstance(call, tuple)))
        self.action("create_password_room")
        self.assertIn(("create", dict(name=None, ranked=False, private="password", password="fake-room-password")), self.client.calls)
        self.assertEqual(self.a.text_value("online_room_password"), "")
        self.assertNotIn("fake-room-password", json.dumps(self.a.online_state()))
        self.assertNotIn("hidden", json.dumps(self.a.online_state()))

    def test_initial_friends_before_login_completion_use_cached_native_snapshot(self):
        self.action("logout")
        self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_account")
        client = self.a.clients[-1]
        client.friend_list = dict(friends=[dict(name="InitialFriend", status="online", invite="ok")],
                                  incoming=[dict(name="InitialRequest")], outgoing=[])
        client.friends_list = mock.Mock(side_effect=AssertionError("no automatic network refresh"))
        client.events.put(dict(t="friends", **client.friend_list))
        self.assertFalse(self.a._online_account)
        self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["phase"], "logged_in")
        self.assertEqual([friend["name"] for friend in state["friends"]], ["InitialFriend"])
        self.assertEqual(state["friend_incoming"], [dict(name="InitialRequest")])
        client.friends_list.assert_not_called()

    def test_code_create_join_and_room_code_is_for_members_only(self):
        self.action("create_code_room")
        self.assertEqual(self.a.online_state()["room"]["code"], "TEST-CODE")
        self.action("leave_room")
        self.a.set_text_value("online_room_code", "ABCD-EFGH")
        self.action("join_room_code")
        self.assertIn(("join", None, dict(code="ABCD-EFGH")), self.client.calls)

    def test_locked_rooms_stay_visible_and_need_password(self):
        self.client.events.put(dict(t="lobby_state", rooms=[dict(id="locked", lock="password", name="Locked"),
            dict(id="hidden", hidden=True), dict(id="training", training=True)]))
        self.a.online_poll()
        self.assertEqual([room["id"] for room in self.a.online_state()["rooms"]], ["locked"])
        self.action("join_room:locked")
        self.assertEqual(self.a.online_state()["message"], "@online.room_password_required")
        self.a.set_text_value("online_room_password", "fake-room-password")
        self.action("join_room:locked")
        self.assertIn(("join", "locked", dict(password="fake-room-password")), self.client.calls)

    def test_friend_request_answers_and_removal_delegate_to_client(self):
        self.action("refresh_friends")
        self.a.set_text_value("online_friend_name", "NewFriend")
        self.action("add_friend")
        self.action("accept_friend:Asker")
        self.action("cancel_friend:Pending")
        self.action("remove_friend:Friend")
        for call in (("friend_add", "NewFriend"), ("friend_answer", "Asker", True),
                     ("friend_cancel", "Pending"), ("friend_remove", "Friend")):
            self.assertIn(call, self.client.calls)
        self.assertEqual(self.a.text_value("online_friend_name"), "")

    def test_invites_are_known_targets_and_respect_cooldown_and_game_guard(self):
        self.action("refresh_friends")
        self.client.wait = 5
        self.action("invite_friend:Friend")
        self.assertEqual(self.a.online_state()["message"], "@online.invite_wait")
        self.client.wait = 0
        self.probe.return_value = True
        self.action("invite_friend:Friend")
        self.assertNotIn(("invite", "Friend", "casual"), self.client.calls)
        self.probe.return_value = False
        self.action("invite_friend:Friend")
        self.assertIn(("invite", "Friend", "casual"), self.client.calls)
        self.assertEqual(self.a.online_state()["outgoing_invite"]["id"], "outgoing")
        self.action("cancel_invite")
        self.assertIn(("invite_cancel", "outgoing"), self.client.calls)
        self.client.events.put(dict(t="invited", invite="incoming", **{"from": dict(name="Friend", token="hidden")}))
        self.a.online_poll()
        self.action("accept_invite:unknown")
        self.assertNotIn(("invite_answer", "unknown", True), self.client.calls)
        self.action("decline_invite:incoming")
        self.assertIn(("invite_answer", "incoming", False), self.client.calls)
        self.assertEqual(self.a.online_state()["invites"], [])
        self.assertNotIn("hidden", json.dumps(self.a.online_state()))

    def test_t4_day_one_cannot_use_private_rooms_or_friends_even_with_rich_client(self):
        self.a.online_game = "t4"
        self.action("create_code_room")
        self.action("refresh_friends")
        self.a.set_text_value("online_friend_name", "Somebody")
        self.action("add_friend")
        state = self.a.online_state()
        self.assertFalse(state["capabilities"].get("private_rooms", False))
        self.assertFalse(state["capabilities"].get("friends", False))
        self.assertFalse(any(isinstance(call, tuple) and call[0] in ("create", "friend_add") for call in self.client.calls))

    def test_lost_acknowledgement_does_not_override_invite_match(self):
        self.action("refresh_friends")
        self.client.events.put(dict(t="invited", invite="incoming"))
        self.a.online_poll()
        def answer(*args, **kwargs):
            self.client.events.put(dict(t="match_found"))
            raise TimeoutError()
        self.client.answer_invite = answer
        self.action("accept_invite:incoming")
        self.assertEqual(self.a.online_state()["phase"], "matched")
        self.assertIs(self.a._online_client, self.client)

    def test_native_ineligibility_words_do_not_enable_invites(self):
        self.client.friend_list["friends"][0]["invite"] = "busy"
        self.action("refresh_friends")
        self.assertFalse(self.a.online_state()["friends"][0]["invite"])
        self.action("invite_friend:Friend")
        self.assertNotIn(("invite", "Friend", "casual"), self.client.calls)

    def test_invite_retry_countdown_updates_without_network_refresh(self):
        self.client.wait = 3
        self.action("refresh_friends")
        self.assertEqual(self.a.online_state()["friends"][0]["retry"], 3)
        self.client.wait = 0
        self.assertTrue(self.a.online_poll())
        self.assertEqual(self.a.online_state()["friends"][0]["retry"], 0)

    def test_old_result_is_processed_before_next_match_offer(self):
        seen = []
        self.a._online_event = lambda event: seen.append(event["t"]) or True
        original_found = self.a._online_match_found
        def found(event):
            seen.append(event["t"])
            return original_found(event)
        self.a._online_match_found = found
        self.client.events.put(dict(t="match_result", match="previous"))
        self.client.events.put(dict(t="match_found", match="next"))
        self.a.online_poll()
        self.assertEqual(seen, ["match_result", "match_found"])

    def test_match_offer_clears_pending_social_acceptance(self):
        self.a._online_invites = [dict(id="incoming", name="Friend")]
        self.a._online_outgoing_invite = dict(id="outgoing", name="Friend")
        self.a._online_challenge = dict(id="old-challenge", name="Friend")
        self.client.events.put(dict(t="match_found"))
        self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["invites"], [])
        self.assertEqual(state["outgoing_invite"], {})
        self.assertEqual(state["challenge"], {})

    def test_logout_during_game_probe_cancels_friend_invite_and_accept(self):
        for action in ("invite_friend:Friend", "accept_invite:incoming"):
            with self.subTest(action=action):
                if self.a._online_client is None:
                    self.a.set_text_value("online_password", "fake-password")
                    self.action("login_account")
                    self.client = self.a.clients[-1]
                self.action("refresh_friends")
                self.a._online_invites = [dict(id="incoming", name="Friend")]
                def probe():
                    self.a.online_close()
                    return ""
                with mock.patch.object(self.a, "_online_game_check", side_effect=probe):
                    self.action(action)
                self.assertNotIn(("invite", "Friend", "casual"), self.client.calls)
                self.assertNotIn(("invite_answer", "incoming", True), self.client.calls)
                self.assertEqual(self.a.online_state()["phase"], "offline")


if __name__ == "__main__":
    unittest.main()
