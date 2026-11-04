"""Shared lobby operations use installed-client fakes, never sockets or game processes."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from test_online_adapter import Client, LobbyError, Subject, runtime_modules


class LobbyClient(Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.me = dict(id="self")

    def refresh(self):
        self.calls.append("refresh")
        return dict(players=[dict(id="self", name="Me"), dict(id="other", name="Other", rating=1200)],
                    rooms=[dict(id="open", name="Open"), dict(id="private", name="Private", private=True),
                           dict(id="ranked", name="Ranked", ranked=True)])

    def challenge(self, player):
        self.calls.append(("challenge", player))
        return "challenge-id"

    def answer_challenge(self, challenge, accept):
        self.calls.append(("answer", challenge, accept))

    def create_room(self, ranked):
        self.calls.append(("create", ranked))
        return dict(id="created", name="Created", secret="must-not-leak")

    def join_room(self, room):
        self.calls.append(("join", room))
        return dict(id=room, name="Open")

    def leave_room(self):
        self.calls.append("leave")

    def chat(self, text):
        self.calls.append(("chat", text))


class Playable(Subject):
    online_package = "t4lobby"
    online_game = "t4"
    online_port = 7791
    online_ranked = False
    online_lobby = True
    online_match_flow = True

    def make_client(self, **kwargs):
        client = LobbyClient(**kwargs)
        self.clients.append(client)
        return client

    def _online_match_found(self, event):
        self._online_phase = "matched"
        self._online_match = dict(opponent="Other", ping=30)
        return True


class SharedLobbyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name).start()
        self.probe = mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False).start()
        self.a = Playable(self.directory.name)
        self.addCleanup(self.a.online_close)

    def login(self):
        self.a.online_action("login_guest")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        return self.a.clients[-1]

    def action(self, action):
        self.a.online_action(action)
        self.a.online_poll()

    def test_package_identity_no_guessed_default_and_lazy_import(self):
        del self.a._online_api
        api = runtime_modules(self.directory.name, "t4lobby", dict(client=SimpleNamespace(LobbyClient=self.a.make_client),
                   buildid=SimpleNamespace(BuildInfo=SimpleNamespace(
                       has_online=lambda out: True, from_out_dir=lambda out, release: object())),
                   servers=SimpleNamespace(load=lambda user_dir: ([], []), default_entry=lambda entries: None,
                       resolve=lambda target, entries: SimpleNamespace(tls="off", client_kwargs=lambda: dict(server=target))),
                   proto=SimpleNamespace(PROTO_VERSION=1, GAME="t4")))
        # Resolve the string patch target before replacing importlib's shared resolver.
        with mock.patch("openrecomp.adapters.t5_online.add_path"), mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module",
                side_effect=lambda name: api[name.split(".")[-1]]) as load:
            self.a.online_state()
            load.assert_not_called()
            client = self.login()
        self.assertEqual(client.kwargs["server"], "")     # nothing listed: no guessed loopback address (drill120)
        self.assertEqual([call.args[0] for call in load.call_args_list], [
            "t4lobby.client", "t4lobby.buildid", "t4lobby.servers", "t4lobby.proto"])
        self.assertFalse(self.a.online_state()["capabilities"]["ranked"])

    def test_wrong_game_runtime_is_refused_before_connect(self):
        del self.a._online_api
        module = SimpleNamespace(PROTO_VERSION=1, GAME="t5", LobbyClient=object, BuildInfo=object)
        runtime_modules(self.directory.name, "t4lobby", dict(proto=module))
        with mock.patch("openrecomp.adapters.t5_online.add_path"), mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module", return_value=module):
            self.action("login_guest")
        self.assertEqual(self.a.online_state()["message"], "@online.client_missing")
        self.assertEqual(self.a.clients, [])

    def test_lists_challenges_and_open_rooms_use_shared_protocol(self):
        client = self.login()
        self.action("refresh_players")
        state = self.a.online_state()
        self.assertEqual([p["id"] for p in state["players"]], ["other"])
        self.assertEqual([r["id"] for r in state["rooms"]], ["open"])
        self.action("challenge:other")
        self.assertIn(("challenge", "other"), client.calls)
        client.events.put(dict(t="challenged", challenge="incoming", **{"from": dict(name="Other", secret="hidden")}))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["challenge"], dict(id="incoming", name="Other"))
        self.action("accept_challenge")
        self.assertIn(("answer", "incoming", True), client.calls)
        self.action("create_room")
        self.assertIn(("create", False), client.calls)
        self.assertNotIn("secret", self.a.online_state()["room"])
        self.action("leave_room")
        self.assertEqual(self.a.online_state()["room"], {})
        self.action("join_room:private")
        self.assertNotIn(("join", "private"), client.calls)
        self.action("join_room:open")
        self.assertIn(("join", "open"), client.calls)

    def test_chat_is_explicit_bounded_and_sanitized(self):
        client = self.login()
        self.a.set_text_value("online_chat", "Hello lobby")
        self.assertNotIn(("chat", "Hello lobby"), client.calls)
        self.action("send_chat")
        self.assertIn(("chat", "Hello lobby"), client.calls)
        self.assertEqual(self.a.text_value("online_chat"), "")
        for n in range(55):
            client.events.put(dict(t="chat", **{"from": dict(name="Other", token="hidden")}, text=str(n), secret="hidden"))
        self.a.online_poll()
        chat = self.a.online_state()["chat"]
        self.assertEqual(len(chat), 50)
        self.assertEqual(chat[0], dict(name="Other", text="5"))
        self.assertNotIn("hidden", json.dumps(self.a.online_state()))

    def test_t4_ranked_is_blocked_for_accounts_too(self):
        client = self.login()
        self.a._online_account = True
        self.action("search_ranked")
        self.assertEqual(self.a.online_state()["message"], "@online.ranked_unavailable")
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "ranked" for call in client.calls))

    def test_retained_match_wins_over_queue_completion(self):
        client = self.login()
        self.a.online_action("search_casual")
        client.events.put(dict(t="match_found", opponent=dict(name="Other")))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "matched")
        self.assertIs(self.a._online_client, client)
        self.assertFalse(client.closed.is_set())

    def test_disconnect_wins_over_match_for_playable_client(self):
        client = self.login()
        client.events.put(dict(t="match_found"))
        client.events.put(dict(t="disconnected"))
        self.a.online_poll()
        # The connection is gone for good: no match; the same guest name logs in again by itself.
        self.assertEqual(self.a.online_state()["phase"], "connecting")
        self.assertEqual(self.a.online_state()["message"], "@online.reconnecting")
        self.assertEqual(self.a.online_state()["match"], {})
        self.assertTrue(client.closed.wait(1))

    def test_retained_match_wins_over_lost_queue_acknowledgement(self):
        client = self.login()
        def quick(_char):
            client.events.put(dict(t="match_found"))
            raise LobbyError("timeout")
        client.quick_match = quick
        self.action("search_casual")
        self.assertEqual(self.a.online_state()["phase"], "matched")
        self.assertIs(self.a._online_client, client)

    def test_retained_match_wins_over_lost_challenge_and_room_acknowledgements(self):
        for action in ("accept_challenge", "create_room", "join_room:open"):
            with self.subTest(action=action):
                self.a.online_close()
                client = self.login()
                self.action("refresh_rooms")
                self.a._online_challenge = dict(id="incoming", name="Other")
                def request(*args, **kwargs):
                    client.events.put(dict(t="match_found"))
                    raise LobbyError("timeout")
                client.answer_challenge = client.create_room = client.join_room = request
                self.action(action)
                self.assertEqual(self.a.online_state()["phase"], "matched")
                self.assertIs(self.a._online_client, client)

    def test_process_guard_also_covers_challenges_and_rooms(self):
        client = self.login()
        self.action("refresh_rooms")
        self.probe.return_value = True
        for action in ("challenge:other", "create_room", "join_room:open"):
            self.action(action)
            self.assertEqual(self.a.online_state()["message"], "@online.game_running")
        self.assertFalse(any(isinstance(call, tuple) and call[0] in ("challenge", "create", "join")
                             for call in client.calls))

    def test_account_name_is_shared_without_credentials_or_session_transfer(self):
        self.a.set_text_value("online_password", "fake-password")
        self.action("login_account")
        self.assertEqual(self.a.config["online_identity"], dict(name="PadUser"))
        self.assertNotIn("fake-password", json.dumps(self.a.config))
        self.assertNotIn("fake-remembered-session", json.dumps(self.a.config))

    def test_later_shared_account_name_updates_prefill_until_player_edits_it(self):
        self.assertEqual(self.a.text_value("online_name"), "PadUser")
        self.a.config["online_identity"] = dict(name="SharedAccount")
        self.assertEqual(self.a.text_value("online_name"), "SharedAccount")
        self.a.set_text_value("online_name", "GuestChoice")
        self.a.config["online_identity"] = dict(name="AnotherAccount")
        self.assertEqual(self.a.text_value("online_name"), "GuestChoice")


if __name__ == "__main__":
    unittest.main()
