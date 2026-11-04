"""The native lobby contract, exercised only with fakes and repository-local temporary files."""
import json
import os
import queue
import subprocess
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t5_online import Online, game_process_running
from openrecomp.adapters.t5dr import T5DR


class LobbyError(Exception):
    def __init__(self, code):
        self.code = code


class Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.tls = bool(kwargs.get("tls"))
        self.events = queue.Queue()
        self.calls = []
        self.session = "fake-remembered-session"
        self.closed = threading.Event()

    def connect(self):
        self.calls.append("connect")

    def login_guest(self, name):
        self.calls.append(("guest", name))
        return dict(name=name, guest=True)

    def login(self, name, password, remember):
        self.calls.append(("account", name, password, remember))
        return dict(name=name, guest=False)

    def login_session(self, token):
        self.calls.append(("session", token))
        return dict(name="Remembered", guest=False)

    def quick_match(self, char):
        self.calls.append(("quick", char))

    def ranked_match(self, char):
        self.calls.append(("ranked", char))

    def cancel_queue(self):
        self.calls.append("cancel")

    def close(self):
        self.calls.append("close")
        self.closed.set()


class Build:
    @staticmethod
    def has_online(out):
        return True

    @staticmethod
    def from_out_dir(out, release):
        return (out, release)


class Servers:
    @staticmethod
    def load(user_dir):
        return [], []

    @staticmethod
    def default_entry(entries):
        return None

    @staticmethod
    def resolve(server, entries):
        return SimpleNamespace(tls="off", client_kwargs=lambda: dict(server=server, tls=False))


class Settings(dict):
    pass


def runtime_modules(directory, package, modules):
    """Give test client modules the same install origins production validates."""
    root = os.path.join(directory, "lobby", package)
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "__init__.py"), "w", encoding="utf-8"):
        pass
    for name, module in modules.items():
        module.__file__ = os.path.join(root, name + ".py")
    return modules


class Subject(Online, Adapter):
    text_value = T5DR.text_value
    set_text_value = T5DR.set_text_value
    online_cfg_path = T5DR.online_cfg_path
    _online_cfg = T5DR._online_cfg

    def __init__(self, directory):
        super().__init__(dict(id="fake", short="Fake"))
        self.root = directory
        self.s = Settings(nickname="PadUser")
        self.s.out_dir = directory
        self.s.path = os.path.join(directory, "launcher.json")
        self.clients = []
        self.child_running = False
        self._online_api = dict(client=self.make_client, build=Build, servers=Servers)

    def make_client(self, **kwargs):
        client = Client(**kwargs)
        self.clients.append(client)
        return client

    def ready(self):
        return True

    def release(self):
        return dict(version="test")

    def chosen_fighter(self):
        return "random"

    def running(self):
        return self.child_running

    def _online_submit(self, operation, work):
        # Deterministic worker completion: the production thread plumbing is tested separately below.
        self._online_busy = True
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        self._online_results.put((self._online_generation, operation, value, error))


class OnlineAdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.env = mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.probe = mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False)
        self.scan = self.probe.start()
        self.addCleanup(self.probe.stop)
        self.a = Subject(self.directory.name)
        self.addCleanup(self.a.online_close)

    def login(self, account=False):
        if account:
            self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_account" if account else "login_guest")
        self.assertEqual(self.a.online_state()["phase"], "connecting")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        return self.a.clients[-1]

    def write_cfg(self, value):
        with open(self.a.online_cfg_path(), "w", encoding="utf-8") as stream:
            json.dump(value, stream)

    def read_cfg(self):
        with open(self.a.online_cfg_path(), encoding="utf-8") as stream:
            return json.load(stream)

    def test_base_interface_is_optional_and_safe(self):
        adapter = Adapter(dict(id="fake", short="Fake"))
        self.assertFalse(adapter.online_supported())
        self.assertFalse(adapter.online_poll())
        self.assertEqual(adapter.online_state()["phase"], "offline")
        adapter.online_action("login_guest")
        adapter.online_close()

    def test_snapshot_and_text_do_not_import_connect_or_scan(self):
        with mock.patch("openrecomp.adapters.t5_online.importlib.import_module", side_effect=AssertionError):
            for _ in range(3):
                self.assertEqual(self.a.online_state()["phase"], "offline")
                self.assertEqual(self.a.text_value("online_name"), "PadUser")
                self.a.online_poll()
        self.assertEqual(self.a.clients, [])
        self.scan.assert_not_called()

    def test_runtime_client_is_loaded_from_install_only_on_explicit_request(self):
        del self.a._online_api
        api = runtime_modules(self.directory.name, "t5lobby", dict(
            client=SimpleNamespace(LobbyClient=self.a.make_client),
            buildid=SimpleNamespace(BuildInfo=Build), servers=Servers,
            proto=SimpleNamespace(PROTO_VERSION=1)))
        def module(name):
            return api[name.split(".")[-1]]
        # Resolve the string patch target before replacing importlib's shared resolver.
        with mock.patch("openrecomp.adapters.t5_online.add_path") as add_path, mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module", side_effect=module) as load:
            self.a.online_state()
            load.assert_not_called()
            self.login()
            add_path.assert_called_once_with(os.path.join(self.directory.name, "lobby"))
            self.assertEqual([call.args[0] for call in load.call_args_list], [
                "t5lobby.client", "t5lobby.buildid", "t5lobby.servers", "t5lobby.proto"])

    def test_incompatible_protocol_is_refused_without_connecting(self):
        del self.a._online_api
        module = SimpleNamespace(PROTO_VERSION=2)
        runtime_modules(self.directory.name, "t5lobby", dict(proto=module))
        with mock.patch("openrecomp.adapters.t5_online.add_path"), mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module", return_value=module):
            self.a.online_action("login_guest")
            self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.client_missing")
        self.assertEqual(self.a.clients, [])

    def test_guest_casual_cancel_and_secure_runtime_options(self):
        client = self.login()
        self.assertFalse(client.kwargs["auto_ready"])
        # A drop resumes the session (no logout) for as long as the lobby keeps it (600 s).
        self.assertEqual(client.kwargs["reconnect"], Online.RECONNECT_SECONDS)
        self.assertLess(Online.RECONNECT_SECONDS, 600)
        self.assertTrue(client.kwargs["blind_ready"])
        self.assertFalse(client.kwargs["port_mapping"])
        self.assertNotIn("plain_passwords", client.kwargs)
        self.a.online_action("search_casual")
        self.assertEqual(self.a.online_state()["phase"], "searching")
        self.a.online_poll()
        self.assertIn(("quick", "random"), client.calls)
        self.a.online_action("cancel")
        # Cancelling a search leaves the queue and stays logged in (it used to close the connection: a logout).
        for _ in range(200):
            self.a.online_poll()
            if "cancel" in client.calls and not self.a._online_busy:
                break
            threading.Event().wait(0.01)
        self.assertIn("cancel", client.calls)
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.cancelled")
        self.assertEqual(client.calls.count("connect"), 1)

    def test_dropped_connection_resumes_without_logout(self):
        client = self.login()
        client.events.put(dict(t="reconnecting", reason="the connection to the lobby server was cut"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.reconnecting")
        client.events.put(dict(t="reconnected"))
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.reconnected")
        self.assertFalse(client.closed.is_set())

    def test_guest_cannot_search_ranked_and_search_requires_login(self):
        self.a.online_action("search_ranked")
        self.assertEqual(self.a.online_state()["message"], "@online.login_required")
        client = self.login()
        self.a.online_action("search_ranked")
        self.assertEqual(self.a.online_state()["message"], "@online.account_required")
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "ranked" for call in client.calls))

    def test_account_shares_native_session_and_preserves_other_settings(self):
        self.write_cfg(dict(server="Local Lobby", name="Old", strict=True, sessions={
            "elsewhere": dict(name="Other", token="other-fake-session")}))
        client = self.login(account=True)
        cfg = self.read_cfg()
        self.assertTrue(cfg["strict"])
        self.assertEqual(cfg["sessions"]["elsewhere"]["token"], "other-fake-session")
        self.assertEqual(cfg["sessions"]["local lobby"]["token"], client.session)
        self.assertEqual(self.a.text_value("online_password"), "")
        self.assertNotIn("fake-password", json.dumps(cfg))
        self.assertNotIn("fake-remembered-session", json.dumps(self.a.online_state()))
        self.a.online_action("search_ranked")
        self.a.online_poll()
        self.assertIn(("ranked", "random"), client.calls)

    def test_native_saved_login_is_reused_only_on_explicit_action(self):
        self.write_cfg(dict(server="LOCAL:7781", sessions={"local:7781": dict(
            name="Remembered", token="native-fake-session")}))
        self.assertTrue(self.a.online_state()["saved_available"])
        self.assertEqual(self.a.clients, [])
        self.a.online_action("login_saved")
        self.a.online_poll()
        self.assertIn(("session", "native-fake-session"), self.a.clients[0].calls)
        self.assertTrue(self.a.online_state()["account"])

    def test_expired_session_is_cleared_without_removing_a_replacement(self):
        cfg = dict(server="local", sessions={"local": dict(name="Remembered", token="old-fake-session")})
        self.write_cfg(cfg)
        self.a.make_client = mock.Mock()  # the API factory below controls the fake failure
        def factory(**kwargs):
            client = Client(**kwargs)
            client.login_session = mock.Mock(side_effect=LobbyError("auth_failed"))
            self.a.clients.append(client)
            return client
        self.a._online_api["client"] = factory
        self.a.online_action("login_saved")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.saved_expired")
        self.assertFalse(self.a.online_state()["saved_available"])
        cfg["sessions"]["local"]["token"] = "replacement-fake-session"
        self.write_cfg(cfg)
        self.a._online_write_session("local", None, None, expected="old-fake-session")
        self.assertEqual(self.read_cfg()["sessions"]["local"]["token"], "replacement-fake-session")

    def test_running_child_external_game_and_failed_scan_refuse_search(self):
        client = self.login(account=True)
        self.a.child_running = True
        self.a.online_action("search_casual")
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["message"], "@online.game_running")
        self.a.child_running = False
        for result, expected in ((True, "@online.game_running"), (None, "@online.process_unknown")):
            self.scan.return_value = result
            self.a.online_action("search_ranked")
            self.a.online_poll()
            self.assertEqual(self.a.online_state()["message"], expected)
        self.assertFalse(any(isinstance(call, tuple) and call[0] in ("ranked", "quick") for call in client.calls))

    def test_external_game_started_during_search_stops_lobby(self):
        client = self.login()
        self.a.online_action("search_casual")
        self.a.online_poll()
        self.scan.return_value = True
        self.a._online_guard_at = 0
        self.a.online_poll()
        self.a.online_poll()
        # The search stops (the queue is left); the player stays logged in.
        self.assertFalse(client.closed.is_set())
        self.assertIn("cancel", client.calls)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.game_running")

    def test_one_failed_process_check_while_searching_keeps_the_search(self):
        client = self.login()
        self.a.online_action("search_casual")
        self.a.online_poll()
        self.scan.return_value = None              # tasklist busy on a loaded PC
        for n in range(2):
            self.a._online_guard_at = 0
            self.a.online_poll()
            self.a.online_poll()
            self.assertEqual(self.a.online_state()["phase"], "searching", n)
        self.a._online_guard_at = 0
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.process_unknown")
        self.assertFalse(client.closed.is_set())

    def test_kick_is_terminal_even_when_disconnect_and_success_are_pending(self):
        client = self.login(account=True)
        self.a.online_action("search_ranked")
        client.events.put(dict(t="kicked", reason="logged in from another place"))
        client.events.put(dict(t="disconnected", reason="connection ended"))
        self.a.online_poll()
        for _ in range(3):
            self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["phase"], "kicked")
        self.assertEqual(state["message"], "@online.kicked")
        self.assertEqual(len(self.a.clients), 1)
        self.assertTrue(client.closed.wait(1))

    def test_found_match_detaches_and_latches_without_ready_or_game_start(self):
        client = self.login(account=True)
        self.a.online_action("search_ranked")
        self.a.online_poll()
        client.events.put(dict(t="match_found", opponent=None, ping=dict(ms=35),
                               ticket="not-for-the-view", secret="not-for-the-view"))
        client.events.put(dict(t="match_cancel", reason="ready_timeout"))
        self.a.online_poll()
        for _ in range(3):
            self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["phase"], "matched")
        self.assertEqual(state["match"], dict(opponent="", ping=35))
        self.assertTrue(state["account"])
        self.assertEqual(state["name"], "PadUser")
        self.assertTrue(client.closed.wait(1))
        self.assertIsNone(self.a._online_client)
        self.assertNotIn("not-for-the-view", json.dumps(state))

    def test_cancel_before_queue_reply_is_not_lost(self):
        # Cancel pressed while the search request is still on its way (owner: "cancel search, logged out"): the
        # leave goes out after the search, and the player stays logged in.
        client = self.login()
        self.a.online_action("search_casual")
        self.a.online_action("cancel")
        self.assertEqual(self.a.online_state()["message"], "@online.cancelled")
        self.a.online_poll()
        self.a.online_poll()
        self.assertFalse(client.closed.is_set())
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertLess(client.calls.index(("quick", "random")), client.calls.index("cancel"))
        self.assertEqual(client.calls.count("connect"), 1)

    def test_lost_queue_ack_leaves_the_queue_and_stays_logged_in(self):
        # The answer never came, so the server may have queued the player: leave the queue again (closing the
        # connection here was a logout).
        client = self.login()
        def quick(char):
            client.calls.append(("quick", char))
            raise LobbyError("timeout")
        client.quick_match = quick
        self.a.online_action("search_casual")
        for _ in range(3):
            self.a.online_poll()
        self.assertFalse(client.closed.is_set())
        self.assertIs(self.a._online_client, client)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assertEqual(self.a.online_state()["message"], "@online.unavailable")
        self.assertIn("cancel", client.calls)
        self.assertEqual(client.calls.count(("quick", "random")), 1)

    def test_refused_or_cut_queue_request_stays_logged_in_without_a_leave(self):
        # A refusal (rate limited: fast search/cancel presses) queued nothing; a cut connection took the player out
        # of the queue on the server and the client resumes it.
        for error, message in ((LobbyError("rate_limited"), "@online.rate_limited"),
                               (LobbyError("not_connected"), "@online.unavailable")):
            with self.subTest(code=error.code):
                client = self.login()
                client.quick_match = mock.Mock(side_effect=error)
                self.a.online_action("search_casual")
                self.a.online_poll()
                self.assertFalse(client.closed.is_set())
                self.assertEqual(self.a.online_state()["phase"], "logged_in")
                self.assertEqual(self.a.online_state()["message"], message)
                self.assertNotIn("cancel", client.calls)
                self.a.online_close()

    def test_queued_kick_wins_over_a_failed_queue_request_and_disconnect(self):
        client = self.login(account=True)
        def ranked(_char):
            client.events.put(dict(t="disconnected", reason="connection ended"))
            client.events.put(dict(t="kicked", reason="logged in from another place"))
            raise LobbyError("timeout")
        client.ranked_match = ranked
        self.a.online_action("search_ranked")
        self.a.online_poll()
        for _ in range(3):
            self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["phase"], "kicked")
        self.assertEqual(state["message"], "@online.kicked")
        self.assertTrue(client.closed.wait(1))
        self.assertEqual(len(self.a.clients), 1)

    def test_found_match_wins_over_a_lost_queue_ack(self):
        client = self.login()
        def quick(_char):
            client.events.put(dict(t="match_found", opponent=None, ping=dict(ms=30)))
            raise LobbyError("timeout")
        client.quick_match = quick
        self.a.online_action("search_casual")
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "matched")
        self.assertEqual(self.a.online_state()["match"], dict(opponent="", ping=30))

    def test_logout_keeps_saved_session(self):
        self.login(account=True)
        self.a.online_action("logout")
        state = self.a.online_state()
        self.assertEqual(state["phase"], "offline")
        self.assertTrue(state["saved_available"])

    def test_missing_runtime_and_build_fail_without_a_client(self):
        for problem in (ImportError(), RuntimeError("@online.no_online")):
            self.a._online_modules = mock.Mock(side_effect=problem)
            self.a.online_action("login_guest")
            self.a.online_poll()
            self.assertEqual(self.a.online_state()["phase"], "error")
        self.assertEqual(self.a.clients, [])

    def test_connection_errors_never_expose_raw_credentials_or_addresses(self):
        for error in (OSError("fake-password at private-address"),
                      RuntimeError("@online.unknown private-address"), LobbyError("not_allowed")):
            self.assertNotIn("private-address", self.a._online_error(error))
            self.assertNotIn("fake-password", self.a._online_error(error))

    def test_cancel_connecting_invalidates_worker_and_never_saves_session(self):
        started, resume = threading.Event(), threading.Event()
        client = Client()
        def connect():
            started.set()
            self.assertTrue(resume.wait(2))
        client.connect = connect
        self.a._online_api["client"] = lambda **_kwargs: client
        self.a._online_submit = Online._online_submit.__get__(self.a)
        self.a.set_text_value("online_password", "fake-password")
        self.a.online_action("login_account")
        self.assertTrue(started.wait(1))
        self.a.online_action("cancel")
        resume.set()
        self.assertTrue(client.closed.wait(1))
        # Wait for the cancelled worker's completion without any real network or search.
        completion = self.a._online_results.get(timeout=2)
        self.a._online_results.put(completion)
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertIsNone(self.a._online_client)
        self.assertFalse(os.path.isfile(self.a.online_cfg_path()))
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "account" for call in client.calls))

    def test_logout_before_client_creation_cannot_resurrect_login(self):
        started, resume = threading.Event(), threading.Event()
        api = self.a._online_api
        def modules():
            started.set()
            self.assertTrue(resume.wait(2))
            return api
        self.a._online_modules = modules
        self.a._online_submit = Online._online_submit.__get__(self.a)
        self.a.online_action("login_guest")
        self.assertTrue(started.wait(1))
        self.a.online_action("logout")
        resume.set()
        completion = self.a._online_results.get(timeout=2)
        self.a._online_results.put(completion)
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assertIsNone(self.a._online_client)
        self.assertNotIn("connect", self.a.clients[0].calls)


class ProcessProbeTests(unittest.TestCase):
    def test_tasklist_is_read_only_and_includes_native_launcher_game(self):
        with mock.patch("openrecomp.adapters.t5_online.os.name", "nt"), mock.patch(
                "openrecomp.adapters.t5_online.subprocess.run", return_value=SimpleNamespace(
                    returncode=0, stdout='"t5dr.exe","4242","Console","1","1 K"\n')) as run:
            self.assertTrue(game_process_running())
        self.assertEqual(run.call_args.args[0], ["tasklist", "/FI", "IMAGENAME eq t5dr.exe", "/FO", "CSV", "/NH"])
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_localized_no_process_output_is_not_treated_as_a_game(self):
        with mock.patch("openrecomp.adapters.t5_online.os.name", "nt"), mock.patch(
                "openrecomp.adapters.t5_online.subprocess.run", return_value=SimpleNamespace(
                    returncode=0, stdout="INFO: Keine Tasks vorhanden.\n")):
            self.assertFalse(game_process_running())

    def test_failed_process_inspection_is_unknown(self):
        with mock.patch("openrecomp.adapters.t5_online.os.name", "nt"), mock.patch(
                "openrecomp.adapters.t5_online.subprocess.run", side_effect=subprocess.TimeoutExpired("tasklist", 5)):
            self.assertIsNone(game_process_running())


if __name__ == "__main__":
    unittest.main()
