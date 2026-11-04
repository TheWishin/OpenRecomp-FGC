"""Feature dispatch and compatibility without importing an install or opening a socket."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters import t5_features
from openrecomp.adapters.t5_online import SearchRefused
from test_online_adapter import Client, Subject


class FeatureSubject(Subject):
    online_lobby = True


def feature(**overrides):
    hooks = dict(init=mock.Mock(), state=mock.Mock(return_value={}),
                 action=mock.Mock(return_value=False), completion=mock.Mock(return_value=False),
                 event=mock.Mock(return_value=False), close=mock.Mock())
    hooks.update(overrides)
    return SimpleNamespace(**hooks)


class FeatureBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.env = mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory.name)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.module = feature()
        self.patch = mock.patch.object(t5_features, "MODULES", (self.module,))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.a = FeatureSubject(self.directory.name)
        self.a._online_init()
        self.addCleanup(self.a.online_close)

    def connect_fake(self):
        self.a._online_client = Client()
        self.a._online_phase = "logged_in"
        return self.a._online_client

    def test_snapshot_merges_capabilities_without_requesting_anything(self):
        self.module.state.return_value = dict(capabilities=dict(tournaments=True), tournaments=dict(items=[]))
        before = len(self.a.clients)
        snapshot = self.a.online_state()
        self.assertTrue(snapshot["capabilities"]["tournaments"])
        self.assertEqual(snapshot["tournaments"], dict(items=[]))
        self.assertEqual(len(self.a.clients), before)
        self.module.action.assert_not_called()
        self.module.completion.assert_not_called()

    def test_t4_and_non_lobby_adapters_do_not_initialize_t5_features(self):
        for package, game, lobby in (("t4lobby", "t4", True), ("t5lobby", "t4", True),
                                      ("t5lobby", "", False)):
            with self.subTest(package=package, game=game, lobby=lobby):
                self.module.init.reset_mock()
                owner = SimpleNamespace(online_package=package, online_game=game, online_lobby=lobby)
                t5_features.init(owner)
                self.module.init.assert_not_called()

    def test_idle_logged_in_actions_preempt_legacy_lobby_dispatch(self):
        client = self.connect_fake()
        self.module.action.return_value = True
        with mock.patch.object(self.a, "_online_lobby_action") as legacy:
            self.a.online_action("feature_refresh")
        self.module.action.assert_called_once_with(self.a, "feature_refresh", client)
        legacy.assert_not_called()

    def test_offline_busy_and_playing_actions_cannot_request_feature_work(self):
        self.a.online_action("feature_refresh")
        self.module.action.assert_not_called()
        self.connect_fake()
        self.a._online_busy = True
        self.a.online_action("feature_refresh")
        self.module.action.assert_not_called()
        self.a._online_busy = False
        self.a._online_phase = "playing"
        self.a.online_action("feature_refresh")
        self.module.action.assert_not_called()

    def test_stop_watching_can_cancel_an_inflight_request(self):
        client = self.connect_fake()
        self.a._online_busy = True
        self.module.action.return_value = True
        self.a.online_action("spec_stop")
        self.module.action.assert_called_once_with(self.a, "spec_stop", client)

    def test_event_consumption_still_notifies_every_feature(self):
        first = feature(event=mock.Mock(return_value=True))
        second = feature(event=mock.Mock(return_value=False))
        event = dict(t="tour_call")
        with mock.patch.object(t5_features, "MODULES", (first, second)):
            self.assertTrue(t5_features.event(self.a, event))
        first.event.assert_called_once_with(self.a, event)
        second.event.assert_called_once_with(self.a, event)

    def test_feature_observes_match_offer_before_match_driver(self):
        client = self.connect_fake()
        self.a.online_match_flow = True
        order = []
        self.module.event.side_effect = lambda *_: order.append("feature") or False
        client.events.put(dict(t="match_found", match="fake-match"))
        with mock.patch.object(self.a, "_online_match_found",
                               side_effect=lambda *_: order.append("match") or True):
            self.a._online_events()
        self.assertEqual(order, ["feature", "match"])

    def test_close_revokes_generation_before_cleanup_and_retains_client_for_cancel(self):
        client = self.connect_fake()
        generation = self.a._online_generation
        observed = []
        self.module.close.side_effect = lambda owner: observed.append(
            (owner._online_generation, owner._online_client))
        self.a.online_close()
        self.assertEqual(observed, [(generation + 1, client)])
        self.assertIsNone(self.a._online_client)
        self.assertTrue(client.closed.wait(1))

    def test_failed_feature_cleanup_still_closes_client_and_other_features(self):
        client = self.connect_fake()
        first = feature(close=mock.Mock(side_effect=RuntimeError("fake viewer failure")))
        second = feature()
        with mock.patch.object(t5_features, "MODULES", (first, second)):
            self.a.online_close()
        second.close.assert_called_once_with(self.a)
        self.assertTrue(client.closed.wait(1))

    def test_stale_feature_completion_does_not_repopulate_disconnected_state(self):
        self.connect_fake()
        self.a._online_results.put((self.a._online_generation, "feature_demo:load", {"fake": True}, None))
        self.a.online_close()
        self.a.online_poll()
        self.module.completion.assert_not_called()

    def test_uncertain_feature_match_requests_disconnect_before_custom_completion(self):
        operations = ("feature_challenges:send", "feature_challenges:cancel",
                      "feature_community:community_create", "feature_community:community_pair",
                      "feature_community:community_back_in_line", "feature_community:community_sit_out",
                      "feature_tour:accept:fake-tournament:fake-set")
        for operation in operations:
            with self.subTest(operation=operation):
                client = self.connect_fake()
                self.module.completion.reset_mock()
                self.a._online_results.put((self.a._online_generation, operation, None, OSError("fake lost reply")))
                self.a.online_poll()
                # A cut connection: the server dropped the request's queue/room itself; the login stays.
                self.assertIs(self.a._online_client, client)
                self.assertFalse(client.closed.is_set())
                self.assertEqual(self.a._online_phase, "logged_in")
                self.assertEqual(self.a._online_message, "@online.unavailable")
                self.module.completion.assert_not_called()

    def test_feature_match_local_refusal_retains_session(self):
        client = self.connect_fake()
        self.module.completion.return_value = True
        error = SearchRefused("@online.game_running")
        operation = "feature_community:community_create"
        self.a._online_results.put((self.a._online_generation, operation, None, error))
        self.a.online_poll()
        self.assertIs(self.a._online_client, client)
        self.module.completion.assert_called_once_with(self.a, operation, None, error)

    def test_lost_feature_reply_preserves_confirmed_match_offer(self):
        client = self.connect_fake()
        self.a.online_match_flow = True
        self.a._online_phase = "matched"
        self.a._online_results.put((self.a._online_generation, "feature_challenges:send", None,
                                    OSError("fake lost reply")))
        self.a.online_poll()
        self.assertIs(self.a._online_client, client)
        self.assertEqual(self.a._online_phase, "matched")
        self.module.completion.assert_not_called()

    def test_new_text_fields_are_editable_without_changing_connected_login_fields(self):
        self.connect_fake()
        self.a._online_fields["online_profile_name"] = ""
        self.a.set_online_text_value("online_profile_name", "Friend")
        self.a.set_online_text_value("online_server", "changed.invalid")
        self.assertEqual(self.a.online_text_value("online_profile_name"), "Friend")
        self.assertNotEqual(self.a.online_text_value("online_server"), "changed.invalid")

    def test_offline_recovery_dispatch_does_not_request_a_login(self):
        self.module.offline_action = mock.Mock(return_value=True)
        self.a.online_action("recover_account")
        self.module.offline_action.assert_called_once_with(self.a, "recover_account")
        self.assertEqual(self.a.clients, [])

    def test_local_feature_errors_keep_translatable_recovery_messages(self):
        for message in ("@online.watch_unavailable", "@online.rules_unavailable"):
            with self.subTest(message=message):
                self.assertEqual(self.a._online_error(RuntimeError(message)), message)
        self.assertEqual(self.a._online_error(RuntimeError("arbitrary untrusted message")), "@online.refused")

    def test_optional_constructor_flags_require_native_support(self):
        self.module.client_options = lambda _owner: dict(spectate=True, watch_dir="fake-watch-dir")

        def legacy(*, build=None, auto_ready=False):
            return None

        def current(*, build=None, auto_ready=False, tournaments=False, spectate=False):
            return None

        base = dict(auto_ready=False)
        self.assertEqual(t5_features.options(self.a, legacy, base), base)
        self.assertEqual(t5_features.options(self.a, current, base),
                         dict(auto_ready=False, tournaments=True, spectate=True))

    def test_native_connection_configuration_precedes_connect_and_login(self):
        order = []
        self.module.client_created = lambda *_: order.append("created")
        self.module.logged_in = lambda *_: order.append("logged_in")
        original = self.a.make_client

        def make_client(**kwargs):
            client = original(**kwargs)
            connect, login = client.connect, client.login_guest
            client.connect = lambda: (order.append("connect"), connect())[-1]
            client.login_guest = lambda name: (order.append("login"), login(name))[-1]
            return client

        self.a._online_api["client"] = make_client
        self.a.online_action("login_guest")
        self.a.online_poll()
        self.assertEqual(order, ["created", "connect", "login", "logged_in"])

    def test_preference_merge_preserves_native_sessions_and_unrelated_fields(self):
        with open(self.a.online_cfg_path(), "w", encoding="utf-8") as stream:
            json.dump(dict(native_setting=dict(keep=True)), stream)
        self.a._online_write_session("local", "PadUser", "fake-session")
        self.a._online_write_preferences(dict(challenge_delay=8, casual_first_to=3))
        with open(self.a.online_cfg_path(), encoding="utf-8") as stream:
            saved = json.load(stream)
        self.assertEqual(saved["sessions"]["local"]["token"], "fake-session")
        self.assertEqual(saved["name"], "PadUser")
        self.assertEqual(saved["native_setting"], dict(keep=True))
        self.assertEqual(saved["challenge_delay"], 8)
        self.assertEqual(saved["casual_first_to"], 3)
        with self.assertRaises(ValueError):
            self.a._online_write_preferences(dict(sessions={}))

    def test_preference_merge_does_not_replace_malformed_native_file(self):
        path = self.a.online_cfg_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("{malformed-native-config")
        with self.assertRaises(ValueError):
            self.a._online_write_preferences(dict(challenge_delay=8))
        with open(path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "{malformed-native-config")

    def test_online_preferences_are_isolated_to_fixture_directory(self):
        self.assertEqual(self.a.online_cfg_path(), os.path.join(self.directory.name, "online.json"))

    def test_session_merge_does_not_replace_malformed_native_file(self):
        path = self.a.online_cfg_path()
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("{malformed-native-config")
        with self.assertRaises(ValueError):
            self.a._online_write_session("local", "PadUser", "fake-session")
        with open(path, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "{malformed-native-config")


if __name__ == "__main__":
    unittest.main()
