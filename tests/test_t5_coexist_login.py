"""Side-by-side saved login uses inert files and a fake lobby client only."""
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_online_adapter import Build, LobbyError, Servers, Subject, runtime_modules


class CoexistingLogin(Subject):
    def __init__(self, directory):
        super().__init__(directory)
        self.s.coexistence = True
        self.s.legacy_online_paths = (os.path.join(directory, "native", "online.json"),
                                      os.path.join(directory, "legacy", "online.json"))

    def online_cfg_path(self):
        return os.path.join(self.root, "private", "online.json")


class CoexistingLoginTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.a = CoexistingLogin(self.directory.name)
        self.addCleanup(self.a.online_close)
        self.native = self.a.s.legacy_online_paths[0]
        self.write(self.native, dict(server="LOCAL:7781", name="Remembered", char="random",
            unknown=dict(keep=True), sessions={"local:7781": dict(name="Remembered", token="fake-native-token")}))
        with open(self.native, "rb") as stream:
            self.original = stream.read()
        self.probe = mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False)
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def write(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream)

    def read(self, path):
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)

    def assert_native_unchanged(self):
        with open(self.native, "rb") as stream:
            self.assertEqual(stream.read(), self.original)

    def action(self, action):
        self.a.online_action(action)
        self.a.online_poll()

    def test_discovery_reads_saved_login_without_copying_connecting_or_writing(self):
        state = self.a.online_state()
        self.assertTrue(state["saved_available"])
        self.assertEqual(self.a.online_text_value("online_name"), "Remembered")
        self.assertEqual(self.a.online_text_value("online_server"), "LOCAL:7781")
        self.assertEqual(self.a.clients, [])
        self.assertFalse(os.path.exists(self.a.online_cfg_path()))
        self.assert_native_unchanged()

    def test_explicit_saved_login_and_logout_leave_old_session_in_place(self):
        self.action("login_saved")
        client = self.a.clients[-1]
        self.assertIn(("session", "fake-native-token"), client.calls)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.action("logout")
        self.assertTrue(self.a.online_state()["saved_available"])
        self.assertFalse(os.path.exists(self.a.online_cfg_path()))
        self.assert_native_unchanged()

    def test_showing_online_never_logs_in_with_the_native_launchers_token(self):
        # Beside the native launcher its remembered login is used only when the player chooses it: logging in with
        # it by itself would push the native launcher out ("logged in from another place").
        self.a.online_shown()
        self.a.online_poll()
        self.assertEqual(self.a.clients, [])
        self.assertEqual(self.a.online_state()["phase"], "offline")
        self.assert_native_unchanged()

    def test_showing_online_logs_in_with_this_launchers_own_saved_login(self):
        self.write(self.a.online_cfg_path(), dict(sessions={"local:7781": dict(name="Own", token="fake-own-token")}))
        self.a.online_shown()
        self.a.online_poll()
        self.assertIn(("session", "fake-own-token"), self.a.clients[-1].calls)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        self.assert_native_unchanged()

    def test_expired_borrowed_session_is_not_removed_or_copied(self):
        def make_client(**kwargs):
            client = type(self.a).make_client(self.a, **kwargs)
            client.login_session = mock.Mock(side_effect=LobbyError("auth_failed"))
            return client
        self.a._online_api["client"] = make_client
        self.action("login_saved")
        self.assertEqual(self.a.online_state()["message"], "@online.saved_expired")
        self.assertFalse(self.a.online_state()["saved_available"])
        self.assertFalse(os.path.exists(self.a.online_cfg_path()))
        self.assert_native_unchanged()
        replacement = self.read(self.native)
        replacement["sessions"]["local:7781"]["token"] = "fake-replacement-token"
        self.write(self.native, replacement)
        self.assertTrue(self.a.online_state()["saved_available"])

    def test_password_login_writes_only_new_session_and_preserves_private_unknown_fields(self):
        self.write(self.a.online_cfg_path(), dict(private_unknown="keep"))
        self.a.set_online_text_value("online_password", "fake-password")
        self.action("login_account")
        cfg = self.read(self.a.online_cfg_path())
        self.assertEqual(cfg["private_unknown"], "keep")
        self.assertEqual(cfg["sessions"]["local:7781"]["token"], self.a.clients[-1].session)
        self.assertNotIn("unknown", cfg)
        self.assertNotIn("fake-native-token", json.dumps(cfg))
        self.assert_native_unchanged()

    def test_preference_write_keeps_source_visible_without_copying_source_session(self):
        self.a.online_state()
        self.a._online_write_preferences(dict(char="chosen"))
        self.assertEqual(self.read(self.a.online_cfg_path()), dict(char="chosen"))
        self.assertTrue(self.a.online_state()["saved_available"])
        self.assertEqual(self.a._online_config()["char"], "chosen")
        self.assert_native_unchanged()

    def test_sessions_from_private_and_preferred_native_file_merge_in_memory(self):
        self.write(self.a.s.legacy_online_paths[1], dict(sessions={
            "legacy-only": dict(token="fake-ignored-token")}))
        self.write(self.a.online_cfg_path(), dict(sessions={
            "private-only": dict(token="fake-private-token")}))
        cfg = self.a._online_config()
        self.assertEqual(set(cfg["sessions"]), {"local:7781", "private-only"})
        self.assertNotIn("fake-native-token", json.dumps(self.read(self.a.online_cfg_path())))
        self.assert_native_unchanged()

    def test_writes_refuse_a_private_destination_that_aliases_native_file(self):
        with mock.patch.object(self.a, "online_cfg_path", return_value=self.native):
            with self.assertRaisesRegex(ValueError, "@online.save_failed"):
                self.a._online_write_session("local", "User", "fake-new-token")
            self.a.online_state()
            with self.assertRaisesRegex(ValueError, "@online.save_failed"):
                self.a._online_write_preferences(dict(char="chosen"))
        self.assert_native_unchanged()

    def test_existing_named_servers_are_read_from_source_until_player_has_private_list(self):
        with mock.patch.object(Servers, "load", return_value=([], [])) as load:
            self.action("login_guest")
        load.assert_called_once_with(user_dir=os.path.dirname(self.native))
        self.assert_native_unchanged()
        self.action("logout")
        self.write(os.path.join(os.path.dirname(self.a.online_cfg_path()), "servers.json"), {})
        with mock.patch.object(Servers, "load", return_value=([], [])) as load:
            self.action("login_guest")
        load.assert_called_once_with(user_dir=os.path.dirname(self.a.online_cfg_path()))

    def test_installed_lobby_imports_do_not_write_bytecode(self):
        del self.a._online_api
        modules = runtime_modules(self.directory.name, "t5lobby", dict(
            client=SimpleNamespace(LobbyClient=self.a.make_client),
            buildid=SimpleNamespace(BuildInfo=Build), servers=Servers,
            proto=SimpleNamespace(PROTO_VERSION=1)))
        previous = sys.dont_write_bytecode
        def module(name):
            self.assertTrue(sys.dont_write_bytecode)
            return modules[name.rsplit(".", 1)[-1]]
        with mock.patch("openrecomp.adapters.t5_online.importlib.import_module", side_effect=module):
            self.a._online_modules()
        self.assertEqual(sys.dont_write_bytecode, previous)


if __name__ == "__main__":
    unittest.main()
