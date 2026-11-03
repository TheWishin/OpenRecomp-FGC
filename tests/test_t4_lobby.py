"""T4 lobby in the beta: the vendored client, the configured server, the mode switch and the lobby rows.

Fakes only (no server, no game). The real protocol run is tools/t4_lobby_e2e.py.
"""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from openrecomp.adapters import t4_online
from openrecomp.nav import Game, Nav
import test_t4_online as fakes
from test_t4_beta_network import Subject as DirectSubject

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "openrecomp" / "vendor" / "t4lobby"


def load_package_release():
    import importlib.util
    spec = importlib.util.spec_from_file_location("t4_lobby_package_release", ROOT / "tools" / "package_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VendoredClient(unittest.TestCase):
    def test_only_client_modules_are_vendored_and_all_are_shipped(self):
        names = {path.name for path in VENDOR.iterdir() if path.name != "__pycache__"}
        self.assertFalse(VENDOR.joinpath("server").exists())
        for forbidden in ("cli.py", "store.py", "rating.py", "relayctl.py", "servers.json", "admin.py"):
            self.assertNotIn(forbidden, names)
        shipped = set(load_package_release().SOURCE_GROUPS["openrecomp/vendor/t4lobby"])
        self.assertEqual(names, shipped)

    def test_the_shipped_server_list_is_one_t4_online_entry(self):
        """Placeholder (no server) until tools/set_t4_server.py fills in the deployed beta server."""
        path = ROOT / "openrecomp" / "vendor" / "servers.json"
        self.assertEqual(load_package_release().SOURCE_GROUPS["openrecomp/vendor"], ("servers.json",))
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["format"], "t5dr-servers/1")
        self.assertEqual(len(doc["servers"]), 1)
        entry = doc["servers"][0]
        self.assertEqual({k: entry[k] for k in ("name", "port", "tls", "shared_login", "default")},
                         dict(name="T4 Online", port=7791, tls="pin", shared_login=True, default=True))
        self.assertEqual(entry["udp_ports"], [7791, 7792])
        if entry["host"]:
            self.assertRegex(entry["fingerprint"], r"^[0-9a-f]{64}$")
        else:
            self.assertEqual(entry["fingerprint"], "", "a placeholder has neither host nor fingerprint")

    def test_vendored_imports_stay_inside_the_package(self):
        allowed = set(sys.stdlib_module_names)
        local = {path.stem for path in VENDOR.glob("*.py")}
        for path in VENDOR.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    for alias in node.names:
                        target = node.module or alias.name
                        if target.split(".")[0] not in local and not target.startswith("i18n_"):
                            self.fail(f"{path.name} imports .{target}, which is not vendored")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], allowed, path.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    self.assertIn(node.module.split(".")[0], allowed, path.name)

    def test_shipping_adapter_loads_the_vendored_t4_client(self):
        path, modules = sys.path[:], dict(sys.modules)

        def restore():
            # Other tests plant their own fake t4lobby package; never leave the real one imported.
            sys.path[:] = path
            for name in [name for name in sys.modules if name == "t4lobby" or name.startswith("t4lobby.")]:
                del sys.modules[name]
            sys.modules.update({k: v for k, v in modules.items() if k == "t4lobby" or k.startswith("t4lobby.")})
        self.addCleanup(restore)
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as directory, mock.patch.dict(
                os.environ, OPENRECOMP_HOME=directory):
            subject = fakes.Subject(directory)
            del subject._online_api
            with mock.patch.object(fakes.Subject, "_online_lobby_dir", t4_online.T4Online._online_lobby_dir):
                api = subject._online_modules()
            self.assertTrue(Path(sys.modules["t4lobby.proto"].__file__).resolve().is_relative_to(VENDOR))
            self.assertEqual(sys.modules["t4lobby.proto"].GAME, "t4")
            self.assertEqual(api["client"].__module__, "t4lobby.client")
            self.assertEqual(api["servers"].shipped_path(), str(ROOT / "openrecomp" / "vendor" / "servers.json"))


class ServerAndMode(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.temp.cleanup)
        environment = {key: value for key, value in os.environ.items() if key != t4_online.SERVER_ENV}
        environment["OPENRECOMP_HOME"] = self.temp.name
        self.enterContext(mock.patch.dict(os.environ, environment, clear=True))
        self.saved = self.enterContext(mock.patch.object(t4_online, "save_config"))
        self.enterContext(mock.patch.object(t4_online, "SHIPPED_SERVERS", os.path.join(self.temp.name, "none.json")))

    def subject(self, config=None):
        subject = DirectSubject(self.temp.name)
        subject.config.update(config or {})
        return subject

    def test_without_a_server_the_beta_opens_on_direct_ip_and_offers_the_lobby(self):
        subject = self.subject()
        state = subject.online_state()
        self.assertTrue(state["capabilities"]["direct_ip"])
        self.assertTrue(state["capabilities"]["lobby_available"])
        subject.online_action("mode_lobby")
        state = subject.online_state()
        self.assertFalse(state["capabilities"].get("direct_ip", False))
        self.assertEqual(state["message"], "@t4.lobby_no_server")
        self.assertFalse(state["capabilities"]["server_set"])
        self.assertEqual(subject.config["t4_online_mode"], "lobby")
        self.saved.assert_called_once()

    def test_blank_server_never_connects(self):
        subject = self.subject(dict(t4_online_mode="lobby"))
        subject.set_text_value("online_name", "Pad")
        with mock.patch.object(subject, "_online_login") as login:
            subject.online_action("login_guest")
        login.assert_not_called()
        self.assertEqual(subject.online_state()["message"], "@t4.lobby_no_server")

    def test_environment_then_config_then_server_list_name_the_server(self):
        self.assertEqual(self.subject(dict(t4_lobby_server="cfg.example:7791"))._online_default_server(),
                         "cfg.example:7791")
        with mock.patch.dict(os.environ, {t4_online.SERVER_ENV: "env.example:7791"}):
            subject = self.subject(dict(t4_lobby_server="cfg.example:7791"))
            self.assertEqual(subject._online_default_server(), "env.example:7791")
            self.assertTrue(subject.online_state()["capabilities"]["t4_lobby"])
            self.assertEqual(subject.text_value("online_server"), "env.example:7791")
        listed = Path(self.temp.name, "t4-online")
        listed.mkdir()
        listed.joinpath("servers.json").write_text(json.dumps(dict(format="t5dr-servers/1", servers=[
            dict(name="Other", host="other.example"), dict(name="T4 Beta", host="beta.example", default=True)])),
            encoding="utf-8")
        subject = self.subject()
        self.assertEqual(subject._online_default_server(), "T4 Beta")
        self.assertEqual(subject._online_servers_dir(), str(listed))
        self.assertEqual(subject.online_state()["message"], "@t4.online_setup_hint")

    def test_an_override_beats_the_address_the_last_login_saved(self):
        Path(self.temp.name, "online-t4.json").write_text(json.dumps(dict(server="old.example:7791")),
                                                          encoding="utf-8")
        self.assertEqual(self.subject().online_text_value("online_server"), "old.example:7791")     # nothing set: kept
        self.assertEqual(self.subject(dict(t4_lobby_server="cfg.example:7791")).online_text_value("online_server"),
                         "cfg.example:7791")
        with mock.patch.dict(os.environ, {t4_online.SERVER_ENV: "env.example:7791"}):
            self.assertEqual(self.subject(dict(t4_lobby_server="cfg.example:7791")).online_text_value("online_server"),
                             "env.example:7791")

    def test_back_to_direct_and_busy_sessions_keep_their_mode(self):
        subject = self.subject(dict(t4_online_mode="lobby", t4_lobby_server="cfg.example:7791"))
        subject.online_state()
        subject._online_busy = True
        subject.online_action("mode_direct")
        self.assertEqual(subject.online_state()["message"], "@t4.mode_busy")
        subject._online_busy = False
        subject.online_action("mode_direct")
        self.assertTrue(subject.online_state()["capabilities"]["direct_ip"])
        self.assertEqual(subject.config["t4_online_mode"], "direct")


class ShippedServer(unittest.TestCase):
    """The launcher's own "T4 Online" entry: a placeholder until set_t4_server.py fills in the deployed server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.temp.cleanup)
        environment = {key: value for key, value in os.environ.items() if key != t4_online.SERVER_ENV}
        environment["OPENRECOMP_HOME"] = self.temp.name
        self.enterContext(mock.patch.dict(os.environ, environment, clear=True))
        self.enterContext(mock.patch.object(t4_online, "save_config"))
        self.file = os.path.join(self.temp.name, "servers.json")
        self.enterContext(mock.patch.object(t4_online, "SHIPPED_SERVERS", self.file))
        import importlib.util
        spec = importlib.util.spec_from_file_location("set_t4_server", ROOT / "tools" / "set_t4_server.py")
        self.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tool)

    def run_tool(self, *argv):
        with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            return self.tool.main([*argv, "--file", self.file])

    def test_the_placeholder_means_no_server(self):
        self.run_tool("--clear")
        subject = DirectSubject(self.temp.name)
        self.assertEqual(subject._online_default_server(), "")
        self.assertTrue(subject.online_state()["capabilities"]["direct_ip"])

    def test_the_filled_entry_is_the_default_lobby_with_the_shared_t5dr_login(self):
        self.run_tool("--host", "46.224.146.6", "--fingerprint", ":".join(["AB"] * 32))
        entry = json.loads(Path(self.file).read_text(encoding="utf-8"))["servers"][0]
        self.assertEqual((entry["host"], entry["fingerprint"], entry["shared_login"]), ("46.224.146.6", "ab" * 32, True))
        subject = DirectSubject(self.temp.name)
        self.assertEqual(subject._online_default_server(), "T4 Online")
        state = subject.online_state()
        self.assertTrue(state["capabilities"]["t4_lobby"])
        self.assertTrue(state["capabilities"]["server_set"])
        self.assertEqual(subject._t4_shared_host(), "46.224.146.6")
        with mock.patch.dict(os.environ, {t4_online.SERVER_ENV: "env.example:7791"}):
            self.assertEqual(DirectSubject(self.temp.name)._online_default_server(), "env.example:7791")
        self.assertEqual(DirectSubject(self.temp.name)._online_default_server(), "T4 Online")

    def test_a_players_own_default_wins_over_the_shipped_one(self):
        self.run_tool("--host", "46.224.146.6", "--fingerprint", "ab" * 32)
        listed = Path(self.temp.name, "t4-online")
        listed.mkdir()
        listed.joinpath("servers.json").write_text(json.dumps(dict(format="t5dr-servers/1", servers=[
            dict(name="Club", host="club.example", default=True)])), encoding="utf-8")
        self.assertEqual(DirectSubject(self.temp.name)._online_default_server(), "Club")

    def test_the_tool_refuses_bad_values(self):
        for argv in (("--host", "46.224.146.6", "--fingerprint", "abc"),
                     ("--host", "192.168.1.5", "--fingerprint", "ab" * 32),
                     ("--host", "127.0.0.1", "--fingerprint", "ab" * 32),
                     ("--host", "bad host", "--fingerprint", "ab" * 32),
                     ("--host", "46.224.146.6", "--fingerprint", "ab" * 32, "--port", "0")):
            with self.assertRaises(SystemExit):
                self.run_tool(*argv)
        self.assertFalse(os.path.exists(self.file))


class LobbyActions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.temp.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.temp.name))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.a = fakes.Subject(self.temp.name)
        self.addCleanup(self.a.online_close)
        self.a.set_text_value("online_name", "Pad")
        self.a.online_action("login_guest")
        self.a.online_poll()
        self.client = self.a.clients[-1]

    def test_rooms_are_not_part_of_the_t4_beta_lobby(self):
        for action in ("create_room", "refresh_rooms", "join_room:room-1", "leave_room", "create_code_room"):
            self.a.online_action(action)
            self.assertEqual(self.a.online_state()["message"], "@online.social_unavailable")
        self.assertFalse(any(isinstance(call, tuple) and "room" in call[0] for call in self.client.calls))
        self.assertFalse(self.a.online_state()["capabilities"]["rooms"])

    def test_social_features_of_t5dr_stay_off(self):
        for key in ("friends", "private_rooms", "tournaments", "spectate", "relays", "sets", "match_rules"):
            self.assertFalse(self.client.kwargs[key], key)


class SharedLogin(unittest.TestCase):
    """One account for T5DR and T4: a T5DR remembered login is offered only for an approved, secured T4 server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.temp.cleanup)
        environment = {key: value for key, value in os.environ.items() if key != t4_online.SERVER_ENV}
        environment.update(OPENRECOMP_HOME=self.temp.name, T5_ONLINE_DIR=os.path.join(self.temp.name, "t5"))
        self.enterContext(mock.patch.dict(os.environ, environment, clear=True))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.enterContext(mock.patch.object(t4_online, "SHIPPED_SERVERS", os.path.join(self.temp.name, "none.json")))
        self.listed = Path(self.temp.name, "t4-online")
        self.listed.mkdir()
        self.sessions = [dict(host="lobby.example", name="Wishin", token="t5-remembered", saved=5),
                         dict(host="other.example", name="Else", token="other-token", saved=9)]

    def subject(self, **entry):
        values = dict(name="T4 Online", host="lobby.example", port=7791, tls="pin", fingerprint="ab" * 32,
                      default=True, shared_login=True)
        values.update(entry)
        self.listed.joinpath("servers.json").write_text(json.dumps(dict(format="t5dr-servers/1", servers=[values])),
                                                        encoding="utf-8")
        subject = fakes.Subject(self.temp.name)
        subject.config.pop("t4_lobby_server")
        self.addCleanup(subject.online_close)
        subject.account_peers = (mock.Mock(online_account_sessions=lambda: [dict(s) for s in self.sessions]),)
        secure = self.secure

        class Servers(fakes.Servers):
            @staticmethod
            def resolve(server, entries):
                return mock.Mock(tls="pin" if secure else "off",
                                 client_kwargs=lambda: dict(server=server, tls=secure))
        subject._online_api["servers"] = Servers
        return subject

    secure = True

    def test_a_saved_t5dr_login_logs_into_t4_with_one_press(self):
        subject = self.subject()
        state = subject.online_state()
        self.assertTrue(state["saved_available"])
        self.assertTrue(state["saved_shared"])
        self.assertNotIn("t5-remembered", json.dumps(state))
        subject.online_action("login_saved")
        subject.online_poll()
        self.assertEqual(subject.online_state()["phase"], "logged_in")
        self.assertIn(("session", "t5-remembered"), subject.clients[-1].calls)
        # The T5DR credential is used, never copied into T4's own settings.
        path = Path(subject.online_cfg_path())
        self.assertFalse(path.exists() and "t5-remembered" in path.read_text(encoding="utf-8"))

    def test_only_an_approved_secured_listed_server_gets_the_t5dr_login(self):
        for entry in (dict(shared_login=False), dict(tls="off"), dict(tls="pin", fingerprint=""),
                      dict(shared_login="elsewhere.example"),
                      dict(tls="", fingerprint="")):          # no TLS named: the connection is plain (review F3)
            with self.subTest(entry=entry):
                subject = self.subject(**entry)
                self.assertFalse(subject.online_state()["saved_available"])
                subject.online_close()
        subject = self.subject(shared_login="other.example")
        self.assertEqual(subject._online_saved()["token"], "other-token")
        subject.online_close()
        subject = self.subject()
        subject.set_text_value("online_server", "lobby.example:7791#" + "ab" * 32)   # typed, not listed
        self.assertFalse(subject.online_state()["saved_available"])
        with mock.patch.dict(os.environ, {t4_online.SERVER_ENV: "lobby.example:7791"}):
            typed = self.subject()
            self.assertFalse(typed.online_state()["saved_available"])

    def test_the_shared_login_never_goes_over_a_plain_connection(self):
        self.secure = False                                 # the resolver says plain TCP after all
        subject = self.subject()
        subject.online_action("login_saved")
        subject.online_poll()
        self.assertEqual(subject.online_state()["message"], "@online.insecure")
        self.assertNotIn(("session", "t5-remembered"), subject.clients[-1].calls)

    def test_t4s_own_saved_login_comes_first(self):
        subject = self.subject()
        subject._online_init()
        Path(subject.online_cfg_path()).write_text(json.dumps(dict(sessions={
            "t4 online": dict(name="Own", token="t4-own")})), encoding="utf-8")
        self.assertEqual(subject._online_saved()["token"], "t4-own")
        self.assertFalse(subject.online_state()["saved_shared"])

    def test_a_refused_t5dr_login_is_not_offered_again_and_never_deleted(self):
        from test_online_adapter import LobbyError
        subject = self.subject()

        def refuse(client, token):
            client.calls.append(("session", token))
            raise LobbyError("auth_failed")
        with mock.patch.object(fakes.MatchClient, "login_session", refuse):
            subject.online_action("login_saved")
            subject.online_poll()
        self.assertEqual(subject.online_state()["message"], "@t4.saved_shared_refused")
        self.assertFalse(subject.online_state()["saved_available"])
        self.assertEqual(self.sessions[0]["token"], "t5-remembered")

    def test_badges_from_the_server_reach_player_rows_and_chat(self):
        subject = self.subject()
        subject.online_action("login_saved")
        subject.online_poll()
        client = subject.clients[-1]
        client.events.put(dict(t="lobby_state", players=[dict(id="p1", name="Dev", badge="dev"),
                                                          dict(id="p2", name="Plain", badge="admin")]))
        client.events.put({"t": "chat", "from": dict(name="Dev", badge="dev"), "text": "hi"})
        subject.online_poll()
        state = subject.online_state()
        self.assertEqual([p.get("badge", "") for p in state["players"]], ["dev", ""])
        self.assertEqual(state["chat"][-1].get("badge"), "dev")


    def test_searching_says_when_the_only_other_searchers_have_another_build(self):
        from openrecomp import i18n
        from types import SimpleNamespace
        subject = self.subject()
        subject.online_action("login_saved")
        subject.online_poll()
        client = subject.clients[-1]
        client.build = SimpleNamespace(build_id="mine")
        if hasattr(client, "compatible"):
            del client.compatible
        client.events.put(dict(t="lobby_state", players=[dict(id="p1", name="A", status="queue", build="other"),
                                                          dict(id="p2", name="B", status="idle", build="other"),
                                                          dict(id="p3", name="C", status="queue", build="mine")]))
        subject.online_poll()
        subject._online_phase, subject._online_message = "searching", "@online.searching_casual"
        state = subject.online_state()
        self.assertEqual(state["other_builds"], 1)
        text = i18n.localize(state["message"], "en")
        self.assertIn("1 other player", text)
        self.assertIn("same launcher and game build", text)
        client.compatible = lambda entry: True              # the client's own rule (a compatibility group) wins
        client.events.put(dict(t="lobby_state", players=[dict(id="p1", name="A", status="queue", build="other")]))
        subject.online_poll()
        self.assertEqual(subject.online_state()["message"], "@online.searching_casual")
        subject._online_phase = "logged_in"
        client.compatible = lambda entry: False
        client.events.put(dict(t="lobby_state", players=[dict(id="p1", name="A", status="queue", build="other")]))
        subject.online_poll()
        self.assertNotEqual(subject.online_state()["phase"], "searching")
        self.assertFalse(isinstance(subject.online_state()["message"], dict))   # only while searching


class T5drSessionsForT4(unittest.TestCase):
    def test_t5dr_offers_its_secured_remembered_logins_with_their_hosts(self):
        from test_online_adapter import Subject as T5Subject
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as directory, mock.patch.dict(
                os.environ, T5_ONLINE_DIR=directory):
            subject = T5Subject(directory)
            Path(directory, "lobby").mkdir()
            Path(directory, "lobby", "servers.json").write_text(json.dumps(dict(format="t5dr-servers/1", servers=[
                dict(name="T5DR Online (EU)", host="Lobby.Example", tls="pin", fingerprint="cd" * 32),
                dict(name="LAN lobby", host="192.168.1.20")])),          # no tls named: plain, never shared
                encoding="utf-8")
            Path(directory, "online.json").write_text(json.dumps(dict(sessions={
                "t5dr online (eu)": dict(name="Wishin", token="listed", saved=3),
                "lan lobby": dict(name="Lan", token="lan-token"),
                "127.0.0.1:7781": dict(name="Local", token="plain"),
                "tls://ca.example:7781": dict(name="Ca", token="ca-token"),
                "pin.example:7781#" + "ef" * 32: dict(name="Pin", token="pin-token"),
                "broken": "not a session"})), encoding="utf-8")
            sessions = {s["token"]: s["host"] for s in subject.online_account_sessions()}
            self.assertEqual(sessions, {"listed": "lobby.example", "ca-token": "ca.example",
                                        "pin-token": "pin.example"})

    def test_other_games_share_nothing(self):
        from openrecomp.adapters.base import Adapter
        self.assertEqual(Adapter(dict(id="x", short="X")).online_account_sessions(), [])
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as directory, mock.patch.dict(
                os.environ, OPENRECOMP_HOME=directory):
            self.assertEqual(fakes.Subject(directory).online_account_sessions(), [])

    def test_the_launcher_gives_each_game_the_others(self):
        from openrecomp import app
        from test_nav import manifest
        first, second = mock.Mock(problem=""), mock.Mock(problem="")
        with mock.patch.object(app.mf, "load_all", return_value=([manifest("a"), manifest("b")], [])), \
                mock.patch.object(app.adapters, "make", side_effect=[first, second]):
            games, _problems = app.load_games({})
        self.assertEqual(games[0].a.account_peers, (second,))
        self.assertEqual(games[1].a.account_peers, (first,))


class T4LobbyRows(unittest.TestCase):
    def setUp(self):
        import test_t4_online_nav as nav_fakes
        self.a = nav_fakes.T4Lobby()
        self.a.snapshot["capabilities"].update(t4_lobby=True, rooms=False, direct_available=True, server_set=True)
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec["t4"] = "online"
        self.a.m["adapter"] = "t4"

    def ids(self):
        return [item.get("id") for item in self.nav.items()]

    def press(self, iid):
        items = self.nav.items()
        target = next(i for i, item in enumerate(items) if item.get("id") == iid)
        while self.nav.focus_index(items) != target:
            self.nav.act("down" if self.nav.focus_index(items) < target else "up", device="xbox")
            items = self.nav.items()
        self.nav.act("confirm", device="xbox")

    def test_login_screen_offers_guest_account_and_direct_ip(self):
        ids = self.ids()
        for iid in ("online_name", "online_password", "online_server", "login_guest", "login_account", "mode_direct"):
            self.assertIn(iid, ids)
        self.assertNotIn("host", ids)
        self.press("mode_direct")
        self.assertIn(("online", "mode_direct"), self.a.calls)

    def test_lobby_shows_players_chat_and_quick_match_but_no_rooms(self):
        self.press("login_guest")
        ids = self.ids()
        for iid in ("search_casual", "refresh_players", "challenge:player-2", "accept_challenge",
                    "decline_challenge", "online_chat", "send_chat", "chat:0", "logout"):
            self.assertIn(iid, ids)
        for iid in ("search_ranked", "refresh_rooms", "create_room", "join_room:room-1", "leave_room"):
            self.assertNotIn(iid, ids)
        labels = [item.get("label") for item in self.nav.items() if item.get("kind") == "heading"]
        self.assertNotIn("@online.rooms", labels)

    def test_connection_notices_while_matched_keep_the_focus_on_start(self):
        self.a.snapshot.update(phase="matched", match=dict(opponent="Rival"), message="@online.t4_matched")
        self.a.pending = dict(message="@online.connection_direct")
        self.nav.poll_online()                          # entering "matched" puts the focus on the status row
        items = self.nav.items()
        target = next(i for i, item in enumerate(items) if item.get("id") == "start_match")
        while self.nav.focus_index(items) != target:
            self.nav.act("down", device="xbox")
            items = self.nav.items()
        self.a.pending = dict(message="@online.connection_relay")
        self.assertTrue(self.nav.poll_online())
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "start_match")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("online", "start_match"), self.a.calls)

    def test_saved_t5dr_login_has_its_own_label(self):
        self.a.snapshot.update(saved_available=True, saved_shared=True)
        item = next(item for item in self.nav.items() if item.get("id") == "login_saved")
        self.assertEqual((item["label"], item["hint"]), ("@t4.saved_shared", "@t4.saved_shared_hint"))
        self.a.snapshot["saved_shared"] = False
        item = next(item for item in self.nav.items() if item.get("id") == "login_saved")
        self.assertEqual(item["label"], "@online.saved")

    def test_password_change_says_it_applies_to_both_games(self):
        self.press("login_guest")
        self.a.snapshot.update(phase="logged_in", account=True, name="Alice")
        self.a.snapshot["capabilities"]["account_tools"] = True
        hints = {item.get("id"): item.get("hint") for item in self.nav.items()}
        self.assertEqual(hints["account_change_password"], "@t4.account_both_hint")
        self.assertEqual(hints["account_new_codes"], "@t4.account_both_hint")
        self.a.snapshot["capabilities"]["t4_lobby"] = False          # T5DR's own screen keeps its text
        self.a.m["adapter"] = "t5"
        hints = {item.get("id"): item.get("hint") for item in self.nav.items()}
        self.assertEqual(hints.get("account_change_password"), "@online120.account_hint")

    def test_login_hint_names_the_shared_account(self):
        for language in ("en", "de"):
            from openrecomp import i18n
            text = i18n.text(language, "t4.online_setup_hint")
            self.assertIn("T5DR Online", text)
            self.assertIn("Tekken 4", text)

    def test_direct_screen_offers_the_lobby(self):
        self.a.snapshot.update(phase="offline", role="host", checks=[],
                               capabilities=dict(direct_ip=True, lobby_available=True))
        self.assertIn("host", self.ids())
        self.press("mode_lobby")
        self.assertIn(("online", "mode_lobby"), self.a.calls)


if __name__ == "__main__":
    unittest.main()
