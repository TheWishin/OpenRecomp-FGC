"""T4 login and process-mode matches, using fake clients and fake game processes only."""
import json
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t4 import T4
from openrecomp.adapters.t4_online import ticket_env
from test_online_adapter import Build, Client, Servers, runtime_modules


class MatchClient(Client):
    def ready(self, accept=True, match_id=None):
        self.calls.append(("ready", accept))

    def game_started(self, match_id):
        self.calls.append(("game_started", match_id))

    def game_playing(self, match_id):
        self.calls.append(("game_playing", match_id))

    def nat_fallback(self, match_id):
        self.calls.append(("nat_fallback", match_id))
        return True

    def report_result(self, **kwargs):
        self.calls.append(("result", kwargs))


class Subject(T4):
    # Only this fake opts into future lobby regression coverage.
    online_direct_ip = False
    online_lobby = True

    def __init__(self, directory):
        core = SimpleNamespace(load_settings=lambda: {}, play_problems=lambda s: [],
                               find_runtime=lambda s: (os.path.join(directory, "bin", "ps2EntryRunner.exe"), "fake"),
                               run_lock_holder=lambda: "", SAVE_DIR=directory)
        # A configured test server; the T4 lobby has no built-in default.
        super().__init__(dict(id="t4", short="T4"), dict(t4_lobby_server="127.0.0.1:7791"), directory, core)
        self.clients = []
        self.starts = []
        self.stops = []
        self.child_exit = None
        self.fail_start = False
        self._online_api = dict(client=self.make_client, build=Build, servers=Servers, game_env=ticket_env)

    def _t4_identity_build(self, api, info, out):
        # The fake build has no stamp, ELF or ISO; test_t4_lobby_identity checks the real identity.
        return info

    def _online_lobby_dir(self):
        # Fake client packages are planted here; the shipping adapter loads openrecomp/vendor.
        return os.path.join(self.root, "lobby")

    def make_client(self, **kwargs):
        client = MatchClient(**kwargs)
        self.clients.append(client)
        return client

    def start(self, extra_env=None):
        if self.fail_start:
            raise OSError("private fake launch failure")
        self.starts.append(extra_env)
        self.child_exit = None
        proc = SimpleNamespace(poll=lambda: self.child_exit)
        self.run = SimpleNamespace(proc=proc, stop=self.stop)
        return 123

    def stop(self):
        self.stops.append(self.run)
        self.child_exit = 0

    def _online_submit(self, action, work):
        self._online_busy = True
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        self._online_results.put((self._online_generation, action, value, error))

    def _online_stop_submit(self, work):
        work()
        return None


def ticket(role="host", path="direct", **values):
    fields = dict(match_id="fake-match", role=role, slot=0 if role == "host" else 1,
                  local_port=30001, peer=("127.0.0.1", 30002), path=path, ranked=False,
                  build="fake-build", key="fake-key", seed=42, input_delay=None, timeout=20, rounds=2)
    fields.update(values)
    return SimpleNamespace(**fields)


class T4OnlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory.name))
        self.scan = self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.a = Subject(self.directory.name)
        self.addCleanup(self.a.online_close)

    def login(self):
        self.a.set_text_value("online_name", "FakePlayer")
        self.a.online_action("login_guest")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        return self.a.clients[-1]

    def found(self):
        client = self.login()
        client.events.put(dict(t="match_found", opponent=dict(name="Other"), ping=dict(ms=10)))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "matched")
        return client

    def playing(self, current=None):
        client = self.found()
        self.a.online_action("start_match")
        self.a.online_poll()
        client.events.put(dict(t="match_start", ticket=current or ticket()))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        return client

    def write_log(self, name, text):
        with open(os.path.join(self.directory.name, name), "w", encoding="utf-8") as stream:
            stream.write(text)

    def test_online_is_optional_runtime_and_reading_never_connects(self):
        del self.a._online_api
        with mock.patch("openrecomp.adapters.t5_online.importlib.import_module", side_effect=AssertionError):
            state = self.a.online_state()
            self.a.online_poll()
        self.assertEqual(state["phase"], "offline")
        caps = state["capabilities"]
        self.assertEqual({key: caps[key] for key in ("ranked", "lobby", "match_flow", "registration", "t4_lobby",
                                                     "direct_available", "server_set", "leave_set")},
                         dict(ranked=False, lobby=True, match_flow=True, registration=True, t4_lobby=True,
                              direct_available=True, server_set=True, leave_set=False))
        # T5DR's lobby features (t4-parity) show only what a logged-in server offers: nothing while offline.
        for key in ("tournaments", "profiles", "community", "private_chat", "mutes", "challenge_preferences"):
            self.assertFalse(caps[key], key)
        self.assertNotIn("spectating", caps)
        self.assertEqual(self.a.starts, [])
        self.scan.assert_not_called()

    def test_first_online_entry_explains_pad_name_server_and_login(self):
        self.assertEqual(self.a.online_state()["message"], "@t4.online_setup_hint")
        self.assertEqual(self.a.clients, [])

    def test_login_without_a_build_refuses_before_loading_the_client(self):
        self.a.core.play_problems = lambda settings: ["not built"]
        with mock.patch.object(self.a, "_online_modules", side_effect=AssertionError("must not import")):
            for action in ("login_guest", "login_account", "login_saved"):
                self.a.online_action(action)
                self.assertEqual(self.a.online_state()["phase"], "error")
                self.assertEqual(self.a.online_state()["message"], "@online.build_required")
        self.assertEqual(self.a.clients, [])

    def test_empty_name_refuses_locally_and_can_retry_after_pad_text(self):
        with mock.patch.object(self.a, "_online_modules", side_effect=AssertionError("must not import")):
            for action in ("login_guest", "login_account"):
                self.a.online_action(action)
                self.assertEqual(self.a.online_state()["message"], "@t4.online_name_required")
                self.assertEqual(self.a.online_state()["phase"], "error")
        self.assertEqual(self.a.clients, [])
        self.login()

    def test_t4_identity_default_port_and_process_mode_capabilities(self):
        client = self.login()
        self.assertEqual(client.kwargs["server"], "127.0.0.1:7791")
        self.assertEqual(client.kwargs["build"], (os.path.join(self.directory.name, "bin"), "dev"))
        self.assertFalse(client.kwargs["auto_ready"])
        self.assertTrue(client.kwargs["sets"])          # T4 ranked sets (best of 3, rated once)
        for key in ("spectate", "match_rules", "input_delay8", "ingame_rematch", "auto_skip_intro"):
            self.assertFalse(client.kwargs[key], key)
        for key in ("relays", "friends", "private_rooms", "tournaments", "private_chat", "casual_sets", "room_tables"):
            self.assertTrue(client.kwargs[key], key)
        self.a.online_action("search_ranked")
        self.assertFalse(any(call[0] == "ranked" for call in client.calls if isinstance(call, tuple)))

    def test_t4_runtime_module_names_and_wrong_game_refusal(self):
        del self.a._online_api
        modules = runtime_modules(self.directory.name, "t4lobby", dict(client=SimpleNamespace(LobbyClient=self.a.make_client),
                       buildid=SimpleNamespace(BuildInfo=Build), servers=Servers,
                       proto=SimpleNamespace(PROTO_VERSION=1, GAME="t4")))
        # Resolve the string patch target before replacing importlib's shared resolver.
        with mock.patch("openrecomp.adapters.t5_online.add_path"), mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module",
                side_effect=lambda name: modules[name.split(".")[-1]]) as load:
            self.login()
        self.assertTrue(all(call.args[0].startswith("t4lobby.") for call in load.call_args_list))
        self.a.online_close()
        del self.a._online_api
        modules["proto"].GAME = "t5"
        with mock.patch("openrecomp.adapters.t5_online.add_path"), mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module",
                side_effect=lambda name: modules[name.split(".")[-1]]):
            self.a.online_action("login_guest")
            self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.client_missing")
        self.assertEqual(len(self.a.clients), 1)

    def test_room_ready_states_are_independent_correlated_and_reset_for_each_offer(self):
        client = self.login()
        offer = dict(t="match_found", match="first", slot=0,
                     opponent=dict(name="Other", rank="Old server label", tier=13))
        client.events.put(offer)
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["match"]["my_ready"])
        self.assertFalse(self.a.online_state()["match"]["peer_ready"])
        client.events.put(dict(t="opponent_ready", match="previous"))
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["match"]["peer_ready"])
        client.events.put(dict(t="opponent_ready", match="first"))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["match"]["peer_ready"])
        self.assertFalse(self.a.online_state()["match"]["my_ready"])
        self.assertFalse(self.a._online_authorized)
        self.assertEqual(self.a.starts, [])
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["match"]["my_ready"])
        client.events.put(dict(t="match_reveal", match="first", slot=0,
                               opponent=dict(name="Other", rank="Old server label", tier=13)))
        self.a.online_poll()
        match = self.a.online_state()["match"]
        self.assertTrue(match["my_ready"] and match["peer_ready"])
        self.assertEqual(match["sides"][1]["rank"], "4th Dan")   # tier 13 uses the current ladder
        self.a.online_action("cancel_match")
        self.a.online_poll()
        client.events.put(dict(t="opponent_ready", match="first"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["match"], {})
        client.events.put(dict(offer, match="second"))
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["match"]["my_ready"])
        self.assertFalse(self.a.online_state()["match"]["peer_ready"])

    def test_found_waits_for_explicit_start_and_keeps_ticket_secret(self):
        client = self.found()
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.starts, [])
        self.assertNotIn(("ready", True), client.calls)
        self.a.online_action("start_match")
        self.a.online_poll()
        self.assertIn(("ready", True), client.calls)
        client.events.put(dict(t="match_start", ticket=ticket()))
        self.a.online_poll()
        self.a.online_poll()
        public = json.dumps(self.a.online_state())
        self.assertNotIn("fake-key", public)
        self.assertNotIn("fake-build", public)
        self.assertEqual(len(self.a.starts), 1)

    def test_documented_host_join_and_bridge_environment(self):
        host = ticket_env(ticket())
        self.assertEqual(host["TEKKEN4_NET"], "host:30001")
        self.assertEqual(host["TEKKEN4_NET_PEER"], "127.0.0.1:30002")
        self.assertEqual(host["TEKKEN4_NET_DELAY"], "auto")
        join = ticket_env(ticket("join", "relay", local_port=31001, peer=("127.0.0.1", 31002), input_delay=2))
        self.assertEqual(join["TEKKEN4_NET"], "join:127.0.0.1:31002")
        self.assertEqual(join["TEKKEN4_NET_PORT"], "31001")
        self.assertEqual(join["TEKKEN4_NET_DELAY"], "2")
        self.assertFalse(any(key.startswith("T5_") for key in join))
        # A ranked ticket gets the same documented network environment.
        self.assertEqual(ticket_env(ticket(ranked=True))["TEKKEN4_NET"], host["TEKKEN4_NET"])

    def test_lobby_auto_vs_overrides_source_profile_and_applies_to_native_core(self):
        for source in (False, True):
            with self.subTest(source=source):
                self.a.core.source_only = source
                self.assertEqual(self.a._online_game_env(ticket())["TEKKEN4_NET_AUTO_VS"], "1")

    def test_casual_rematch_is_offered_by_server_and_authorized_once_by_player(self):
        client = self.playing()
        client.rematch = mock.Mock()
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", rematch_window=True))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])
        self.a.online_action("rematch")
        self.a.online_poll()
        client.rematch.assert_called_once_with(match_id="fake-match", accept=True, keep=False)
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])
        client.events.put(dict(t="match_found", match="next-match", origin="rematch", ready_check=False))
        client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertEqual(len(self.a.starts), 2)

    def test_return_lobby_declines_outstanding_rematch_and_ignores_stale_expiry(self):
        client = self.playing()
        client.rematch = mock.Mock()
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", rematch_window=True))
        self.a.online_poll()
        client.events.put(dict(t="rematch", match="other-match", state="expired"))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])
        self.a.online_action("return_lobby")
        self.a.online_poll()
        client.rematch.assert_called_once_with(match_id="fake-match", accept=False, keep=False)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])

    def test_rematch_expiry_close_and_failed_vote_clear_pending_state(self):
        client = self.playing()
        client.rematch = mock.Mock(side_effect=OSError("fake unavailable"))
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", rematch_window=True))
        self.a.online_poll()
        self.a.online_action("rematch")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])
        client.events.put(dict(t="rematch", match="fake-match", state="expired"))
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])
        self.a._online_rematch = True
        self.a.online_close()
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])

    def test_duplicate_result_does_not_revoke_inflight_rematch_authorization(self):
        from openrecomp.adapters.t5_online import Online
        client = self.playing()
        verdict = dict(t="match_result", match="fake-match", status="confirmed", rematch_window=True)
        client.events.put(verdict)
        self.a.online_poll()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def rematch(**kwargs):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("fake request did not finish")
        client.rematch = mock.Mock(side_effect=rematch)
        self.a._online_submit = lambda action, work: Online._online_submit(self.a, action, work)
        self.a.online_action("rematch")
        self.assertTrue(entered.wait(1))
        self.a.online_action("return_lobby")
        self.assertEqual(self.a.online_state()["phase"], "result_sent")  # request still pending
        client.events.put(verdict)
        self.a.online_poll()
        self.assertTrue(self.a._online_rematch_pending)
        client.events.put(dict(t="match_found", match="next-match", origin="rematch", ready_check=False))
        client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "starting")
        release.set()
        for _ in range(200):
            self.a.online_poll()
            if self.a.online_state()["phase"] == "playing":
                break
            threading.Event().wait(0.005)
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertEqual(len(self.a.starts), 2)

    def test_expired_vote_cannot_be_reopened_by_duplicate_verdict(self):
        client = self.playing()
        client.rematch = mock.Mock()
        verdict = dict(t="match_result", match="fake-match", status="confirmed", rematch_window=True)
        client.events.put(verdict)
        client.events.put(dict(t="rematch", match="fake-match", state="expired"))
        client.events.put(verdict)
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])

    def test_late_rematch_after_lobby_return_is_left_without_new_card_or_game(self):
        client = self.playing()
        client.rematch = mock.Mock()
        client.leave_match = mock.Mock()
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", rematch_window=True))
        self.a.online_poll()
        self.a.online_action("rematch")
        self.a.online_poll()
        self.a.online_action("return_lobby")
        self.a.online_poll()
        client.events.put(dict(t="match_found", match="next-match", origin="rematch", ready_check=False))
        client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        for _ in range(100):
            if client.leave_match.called:
                break
            threading.Event().wait(0.005)
        client.leave_match.assert_called_once_with("next-match")
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(len(self.a.starts), 1)

    def test_late_rematch_request_error_cannot_replace_next_match_status(self):
        self.playing()
        self.a._online_phase, self.a._online_message = "starting", "@online.starting"
        self.a._online_completion("rematch", None, OSError("fake lost acknowledgement"))
        self.assertEqual(self.a.online_state()["message"], "@online.starting")

    def test_game_evidence_notifies_started_and_playing_once(self):
        client = self.playing()
        self.write_log("net.log", "connected\n")
        self.write_log("rb_frames.log", "NETSUMMARY frames 700 mismatches 2\n")
        for _ in range(5):
            self.a.online_poll()
        self.assertEqual(client.calls.count(("game_started", "fake-match")), 1)
        self.assertEqual(client.calls.count(("game_playing", "fake-match")), 1)
        self.assertEqual(self.a._online_evidence, dict(frames=700, desync=2))

    def test_evidence_reads_the_t4_games_own_summary_line(self):
        # The real game's line: the live frame count, never "resim frames".
        client = self.playing()
        self.write_log("net.log", "[10:00:00] connected (host, P1), peer 127.0.0.1:30002, session 1\n")
        self.write_log("rb_frames.log", "NETSUMMARY final live 1234 logical 1234: fps window 59.9 run 59.8; "
                       "rollbacks 3 resim frames 9 max depth 2 depths; rtt 12 ms (5) delay 1; hashes compared "
                       "41 mismatches 0; packets out 900 in 899 sim-dropped 0 resends 1; peer ok\n")
        for _ in range(3):
            self.a.online_poll()
        self.assertEqual(self.a._online_evidence, dict(frames=1234, desync=0))
        self.assertEqual(client.calls.count(("game_playing", "fake-match")), 1)

    def test_stale_logs_are_ignored_and_replaced_longer_logs_are_read(self):
        self.write_log("net.log", "old connected\n")
        self.write_log("rb_frames.log", "NETSUMMARY frames 9000 mismatches 8\n")
        client = self.playing()
        self.a.online_poll()
        self.assertNotIn(("game_started", "fake-match"), client.calls)
        self.assertEqual(self.a._online_evidence["frames"], 0)
        self.write_log("net.log", "new connected\n" + "boot detail\n" * 30)
        self.a.online_poll()
        self.a.online_poll()
        self.assertIn(("game_started", "fake-match"), client.calls)

    def test_direct_silence_asks_fallback_once_then_new_ticket_restarts_owned_game(self):
        client = self.playing()
        self.a._online_started_at -= 21
        for _ in range(3):
            self.a.online_poll()
        self.assertEqual(client.calls.count(("nat_fallback", "fake-match")), 1)
        client.events.put(dict(t="match_start", ticket=ticket(path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(len(self.a.starts), 2)
        self.assertEqual(len(self.a.stops), 1)

    def test_manual_result_maps_local_winner_to_host_join_slot(self):
        client = self.playing(ticket("join"))
        self.a.child_exit = 0
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result")
        self.a.online_action("result_win")
        self.a.online_poll()
        result = next(call[1] for call in client.calls if isinstance(call, tuple) and call[0] == "result")
        self.assertEqual(result["winner"], 1)
        self.assertEqual(result["source"], "manual")
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.a.online_action("return_lobby")
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_stop_offers_no_result_without_inventing_a_winner(self):
        client = self.playing()
        self.a.online_action("stop_match")
        self.a.online_poll()
        self.a.online_action("result_none")
        self.a.online_poll()
        result = next(call[1] for call in client.calls if isinstance(call, tuple) and call[0] == "result")
        self.assertIsNone(result["winner"])
        self.assertEqual(len(self.a.stops), 1)

    def test_failed_launch_closes_client_and_exposes_only_catalog_message(self):
        client = self.found()
        self.a.fail_start = True
        self.a.online_action("start_match")
        self.a.online_poll()
        client.events.put(dict(t="match_start", ticket=ticket()))
        self.a.online_poll()
        self.a.online_poll()
        # The game could not start: back to the lobby, still logged in, the match left.
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertNotIn("private fake launch failure", json.dumps(self.a.online_state()))

    def test_disconnect_stops_owned_game_and_closes_client(self):
        client = self.playing()
        client.events.put(dict(t="disconnected"))
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)
        self.assertTrue(client.closed.wait(1))
        self.assertIn(self.a.online_state()["phase"], ("offline", "connecting"))

    def settle(self, client, call):
        for _ in range(200):
            self.a.online_poll()
            if call in client.calls and not self.a._online_busy:
                return
            threading.Event().wait(0.01)
        self.fail("no %r" % (call,))

    def test_decline_and_server_cancel_stay_logged_in_and_leave_the_queue(self):
        # Owner report "logged out all the time": a declined or cancelled match used to close the lobby connection.
        client = self.found()
        self.a.online_action("cancel_match")
        self.settle(client, "cancel")
        self.assertIn(("ready", False), client.calls)
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.cancelled")
        self.assertEqual(len(self.a.clients), 1)
        client.calls.clear()
        client.events.put(dict(t="match_found", opponent=dict(name="Other"), ping=dict(ms=10)))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "matched")
        client.events.put(dict(t="match_cancel", reason="declined"))
        self.a.online_poll()
        self.settle(client, "cancel")       # the server re-queues the innocent side: leave the queue
        self.assertNotIn(("ready", False), client.calls)
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.peer_declined")
        self.assertEqual([c for c in client.calls if c == "connect"], [])

    def test_unanswered_unqueue_after_cancel_still_detaches(self):
        # Asked three times and never answered: the connection is closed (a launcher saying "in the lobby" must not
        # stay queued on the server).
        client = self.found()
        client.cancel_queue = mock.Mock(side_effect=type("Timeout", (Exception,), {"code": "timeout"})())
        self.a.online_action("cancel_match")
        for _ in range(300):
            self.a.online_poll()
            if client.closed.is_set():
                break
            threading.Event().wait(0.01)
        self.assertTrue(client.closed.is_set())
        self.assertEqual(client.cancel_queue.call_count, 3)
        self.assertEqual(self.a.online_state()["phase"], "offline")

    def test_unqueue_on_a_cut_connection_stays_logged_in(self):
        # The connection broke: the server already took the player out of its queue, and the client resumes.
        client = self.found()
        client.cancel_queue = mock.Mock(side_effect=type("Cut", (Exception,), {"code": "not_connected"})())
        self.a.online_action("cancel_match")
        for _ in range(100):
            self.a.online_poll()
            if not self.a._online_busy:
                break
            threading.Event().wait(0.01)
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_closing_without_an_online_owned_game_does_not_stop_offline_game(self):
        self.a.start()
        self.a.online_close()
        self.assertEqual(self.a.stops, [])

    def test_peer_requested_fallback_replaces_ticket_without_local_fallback_request(self):
        client = self.playing()
        client.events.put(dict(t="match_start", ticket=ticket(path="relay")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(len(self.a.starts), 2)
        self.assertEqual(len(self.a.stops), 1)
        self.assertNotIn(("nat_fallback", "fake-match"), client.calls)

    def test_duplicate_and_wrong_match_tickets_cannot_restart_or_revive_game(self):
        client = self.playing()
        for current in (ticket(), ticket(match_id="other-match")):
            client.events.put(dict(t="match_start", ticket=current))
            self.a.online_poll()
        self.assertEqual(len(self.a.starts), 1)
        self.a.child_exit = 0
        self.a.online_poll()
        client.events.put(dict(t="match_start", ticket=ticket(path="relay")))
        self.a.online_poll()
        self.assertEqual(len(self.a.starts), 1)

    def test_second_found_offer_never_loses_owned_process(self):
        client = self.playing()
        client.events.put(dict(t="match_found", match="other-match"))
        self.a.online_poll()
        # The second offer is declined; the owned game and the login stay.
        for _ in range(100):
            if ("ready", False) in client.calls:
                break
            threading.Event().wait(0.01)
        self.assertIn(("ready", False), client.calls)
        self.assertEqual(self.a.stops, [])
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertFalse(client.closed.is_set())

    def test_server_result_status_is_distinct_from_report_acknowledgement(self):
        client = self.playing()
        self.a.child_exit = 0
        self.a.online_poll()
        self.a.online_action("result_none")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.result_sent")
        client.events.put(dict(t="match_result", match="fake-match", status="void"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.result_void")

    def test_own_rank_is_the_t4_servers_and_hides_for_guests(self):
        self.login()
        self.a._online_rating = 1500
        self.assertEqual(self.a.online_state()["rank"], "")
        self.a._online_me = dict(name="Fake", rank="4th Dan", tier=13, rating=1640)
        self.assertEqual(self.a.online_state()["rank"], "4th Dan")         # Tekken 5 DR's names, from the T4 server
        self.a._online_me = dict(name="Fake", rank="Beginner", tier=0, guest=True)
        self.assertEqual(self.a.online_state()["rank"], "")

    def test_native_parent_online_config_cannot_supply_t5_endpoint_pin_or_session(self):
        with open(os.path.join(self.directory.name, "online.json"), "w", encoding="utf-8") as stream:
            json.dump(dict(server="wrong-game:7781", fingerprint="fake-pin", name="WrongGame",
                           sessions={"wrong-game:7781": dict(token="fake-token")}), stream)
        self.a.root = os.path.join(self.directory.name, "t4-install")
        client = self.login()
        self.assertEqual(client.kwargs["server"], "127.0.0.1:7791")
        self.assertNotIn("tls_fingerprint", client.kwargs)
        self.assertFalse(self.a.online_state()["saved_available"])

    def test_close_is_nonblocking_while_owned_stop_is_waiting(self):
        self.playing()
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        run = self.a._online_owned_run
        def stop():
            started.set()
            release.wait(2)
            self.a.child_exit = 0
            done.set()
        run.stop = stop
        from openrecomp.adapters.t4_online import T4Online
        self.a._online_stop_submit = T4Online._online_stop_submit.__get__(self.a)
        try:
            self.a.online_close()
            self.assertTrue(started.wait(1))
            self.assertFalse(done.is_set())
            self.assertIs(self.a._online_owned_run, run)
            self.assertEqual(self.a.online_state()["phase"], "offline")
        finally:
            release.set()
            self.assertTrue(done.wait(1))

    def test_finished_stop_with_late_waiter_is_reaped_before_next_offer(self):
        self.playing()
        waiter_alive = [True]
        self.a._run_waiter = SimpleNamespace(join=lambda timeout: None, is_alive=lambda: waiter_alive[0])
        run = self.a._online_owned_run
        self.a.online_close()
        self.assertIs(self.a._online_owned_run, run)
        waiter_alive[0] = False
        self.a.online_poll()
        self.assertIsNone(self.a._online_owned_run)
        self.assertEqual(self.a._online_game_check(), "")

    def test_failed_stop_can_be_retried_without_discarding_owned_process(self):
        self.playing()
        run = self.a._online_owned_run
        run.stop = mock.Mock(side_effect=OSError("fake stop failed"))
        self.a._online_stop_owned()
        self.assertIs(self.a._online_owned_run, run)
        run.stop = self.a.stop
        self.a._online_stop_owned()
        self.assertIsNone(self.a._online_owned_run)

    def test_offline_start_is_blocked_while_online_start_waits(self):
        from test_t4 import FakeCore, MANIFEST
        core = FakeCore()
        adapter = T4(MANIFEST, {}, self.directory.name, core=core)
        adapter._online_phase = "starting"
        with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
            adapter.start()
        self.assertEqual(core.started, [])

    def test_shutdown_stop_worker_survives_interpreter_shutdown(self):
        from openrecomp.adapters.t4_online import T4Online
        with mock.patch("openrecomp.adapters.t4_online.threading.Thread") as thread:
            T4Online._online_stop_submit(self.a, lambda: None)
        self.assertFalse(thread.call_args.kwargs["daemon"])


if __name__ == "__main__":
    unittest.main()
