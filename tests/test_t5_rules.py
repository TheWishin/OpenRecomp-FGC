"""Health rules stay local in tests; no network client or game can be started."""
import os
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5_rules
from openrecomp import nav_rules


class Client:
    def __init__(self, maximum=150, supported=True):
        self.maximum = maximum
        self.supported = supported
        self.life = 100
        self.calls = []

    def handicap_ok(self):
        return self.supported

    def life_max(self):
        return self.maximum

    def set_life(self, value):
        self.calls.append(value)
        self.life = value
        return value


class Subject:
    def __init__(self, client=None):
        self._online_client = client or Client()
        self._online_generation = 1
        self._online_phase = "logged_in"
        self._online_busy = False
        self._online_lock = threading.RLock()
        self._online_match_id = None
        self.saved = {}
        self.submitted = []
        self.root = os.path.join(os.path.dirname(__file__), "selected-install")
        self.online_package = "t5lobby"

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("cancelled")

    def _online_submit(self, operation, work):
        self.submitted.append((operation, work))

    def _online_write_preferences(self, values):
        self.saved.update(values)

    def _online_config(self):
        return dict(self.saved)

    def _online_error(self, error):
        return "@online.connection_failed"

    def _online_modules(self):
        return {}

    def _online_out_dir(self):
        return "output"


class HealthRulesTests(unittest.TestCase):
    def setUp(self):
        for name in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(name, side_effect=AssertionError("external I/O denied")))

    def test_snapshot_and_init_do_not_send_health_request(self):
        owner = Subject()
        t5_rules.init(owner)
        snapshot = t5_rules.state(owner)
        self.assertTrue(snapshot["capabilities"]["handicap"])
        self.assertEqual(snapshot["rules"], dict(life=100, maximum=150))
        self.assertEqual(owner._online_client.calls, [])
        self.assertEqual(owner.submitted, [])

    def test_life_request_delegates_and_persists_confirmed_native_value(self):
        owner = Subject()
        self.assertTrue(t5_rules.action(owner, "rules_life:150", owner._online_client))
        operation, worker = owner.submitted.pop()
        self.assertEqual(operation, "feature_rules:life")
        value = worker()
        self.assertEqual(owner._online_client.calls, [150])
        self.assertEqual(owner.saved, dict(life=150))
        self.assertTrue(t5_rules.completion(owner, operation, value, None))
        self.assertEqual(owner._online_message, "@online.life_updated")

    def test_old_capability_limits_values_and_never_submits_invalid_input(self):
        owner = Subject(Client(maximum=100))
        for raw in ("150", "101", "20", "0", "-10", "true", "100.0", "0100", "100:other"):
            with self.subTest(raw=raw):
                self.assertTrue(t5_rules.action(owner, "rules_life:" + raw, owner._online_client))
        self.assertEqual(owner.submitted, [])
        owner._online_client.supported = False
        t5_rules.action(owner, "rules_life:80", owner._online_client)
        self.assertEqual(owner.submitted, [])
        self.assertEqual(owner._online_message, "@online.rules_unavailable")

    def test_requests_require_live_idle_logged_in_client(self):
        for phase, busy in (("offline", False), ("matched", False), ("playing", False), ("logged_in", True)):
            owner = Subject()
            owner._online_phase, owner._online_busy = phase, busy
            t5_rules.action(owner, "rules_life:80", owner._online_client)
            self.assertEqual(owner.submitted, [])
        owner = Subject()
        t5_rules.action(owner, "rules_life:80", Client())
        self.assertEqual(owner.submitted, [])

    def test_cancelled_worker_cannot_send_or_persist(self):
        owner = Subject()
        t5_rules.action(owner, "rules_life:80", owner._online_client)
        owner._online_generation += 1
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            owner.submitted[0][1]()
        self.assertEqual(owner._online_client.calls, [])
        self.assertEqual(owner.saved, {})

    def test_late_confirmation_cannot_write_another_sessions_preferences(self):
        owner = Subject()

        def late(value):
            owner._online_generation += 1
            return value

        owner._online_client.set_life = late
        t5_rules.action(owner, "rules_life:80", owner._online_client)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            owner.submitted[0][1]()
        self.assertEqual(owner.saved, {})

    def test_invalid_confirmation_never_changes_native_preferences(self):
        for value in (False, 0, 101, 200, "80"):
            owner = Subject()
            owner._online_client.set_life = lambda requested: value
            t5_rules.action(owner, "rules_life:80", owner._online_client)
            with self.assertRaises(RuntimeError):
                owner.submitted[0][1]()
            self.assertEqual(owner.saved, {})

    def test_login_restores_native_saved_health_with_negotiated_maximum(self):
        owner = Subject(Client(maximum=100))
        owner.saved["life"] = 150
        t5_rules.logged_in(owner, owner._online_client)
        self.assertEqual(owner._online_client.calls, [])
        owner.saved["life"] = 80
        t5_rules.logged_in(owner, owner._online_client)
        self.assertEqual(owner._online_client.calls, [80])
        owner._online_client.supported = False
        owner.saved["life"] = 30
        t5_rules.logged_in(owner, owner._online_client)
        self.assertEqual(owner._online_client.calls, [80])

    def test_options_use_selected_installs_native_build_checks(self):
        owner = Subject()
        module = SimpleNamespace(__file__=os.path.join(owner.root, "lobby", "t5lobby", "match_driver.py"),
                                 game_files=mock.Mock(return_value=["local-game"]),
                                 game_supports_rules=mock.Mock(return_value=True),
                                 game_supports_life150=mock.Mock(return_value=True))
        with mock.patch.object(t5_rules.importlib, "import_module", return_value=module):
            self.assertEqual(t5_rules.client_options(owner), dict(match_rules=True, life150=True))
        module.game_files.assert_called_once_with("output")
        module.game_supports_rules.assert_called_once_with(["local-game"])
        module.__file__ = os.path.join(owner.root, "other-install", "match_driver.py")
        module.game_files.reset_mock()
        with mock.patch.object(t5_rules.importlib, "import_module", return_value=module):
            self.assertEqual(t5_rules.client_options(owner), dict(match_rules=False, life150=False))
        module.game_files.assert_not_called()

    def test_match_rule_metadata_never_consumes_driver_events(self):
        owner = Subject()
        found = dict(t="match_found", match="active", training=True, life=dict(you=80, opponent=150))
        self.assertFalse(t5_rules.event(owner, found))
        owner._online_match_id = "active"
        self.assertEqual(t5_rules.state(owner)["match_rules"], dict(training=True, you=80, opponent=150))
        self.assertFalse(t5_rules.event(owner, dict(t="match_reveal", match="active")))
        self.assertTrue(t5_rules.state(owner)["match_rules"]["training"])
        self.assertFalse(t5_rules.event(owner, dict(t="match_start", match="active", slot=1,
                                                  fight=dict(training=False, life=[150, 80]))))
        self.assertEqual(t5_rules.state(owner)["match_rules"], dict(training=False, you=80, opponent=150))
        t5_rules.event(owner, dict(t="match_cancel", match="stale"))
        self.assertEqual(t5_rules.state(owner)["match_rules"]["you"], 80)
        t5_rules.reset(owner)
        self.assertEqual(t5_rules.state(owner)["match_rules"], {})

    def test_pad_cycler_uses_negotiated_values_and_adapter_action(self):
        calls = []
        nav = SimpleNamespace(_online_action=lambda g, action: calls.append(action))
        owner = Subject(Client(maximum=100))
        row = nav_rules.rows(nav, object(), t5_rules.state(owner), None)[0]
        self.assertEqual([value for value, label in row["options"]], list(range(100, 29, -10)))
        row["set"](80)
        self.assertEqual(calls, ["rules_life:80"])
        self.assertEqual(nav_rules.rows(nav, object(), dict(capabilities={}), None), [])
        details = nav_rules.detail_rows(dict(match_rules=dict(training=True, you=80, opponent=150)))
        self.assertEqual(len(details), 2)
        self.assertEqual(details[0]["v"], "@online.training_rule")


if __name__ == "__main__":
    unittest.main()
