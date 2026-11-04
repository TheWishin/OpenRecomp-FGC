"""Beta options use a fake core and never run a game or open a window."""
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t4 import BETA_DISABLED_SWITCHES, BETA_HARNESS_SWITCHES, T4
from openrecomp.nav import Game, Nav
from pad_step import pad_step


MANIFEST = dict(id="t4", short="T4", title="T4", numeral="4", accent="#ffffff",
                subtitle="", sections=["settings"])


class FakeCore:
    RESOLUTIONS = [("auto", "Auto", 1)]

    def __init__(self):
        self.saved = {}
        self.launched = None

    def load_settings(self):
        return dict(self.saved)

    def save_settings(self, settings):
        self.saved = dict(settings)

    def play_problems(self, settings):
        return []

    def run_lock_holder(self):
        return ""

    def graphics_support(self, exe):
        return dict(aa=True)

    def game_env(self, settings, exe=None):
        return dict.fromkeys((*BETA_DISABLED_SWITCHES, "TEKKEN4_NET_DIAG"), "1")

    def GameRun(self, settings):
        def start():
            self.launched = self.game_env(settings)
        return SimpleNamespace(start=start, proc=SimpleNamespace(pid=12))

    def take_run_lock(self, owner):
        pass


class BetaSettings(unittest.TestCase):
    def setUp(self):
        self.save = self.enterContext(mock.patch("openrecomp.adapters.t4.save_config"))
        self.enterContext(mock.patch("openrecomp.adapters.t4.threading.Thread"))
        self.core = FakeCore()
        self.config = {}
        self.adapter = T4(MANIFEST, self.config, "fake-root", core=self.core)
        self.adapter.hero = lambda: ""

    def row(self):
        return next(row for row in self.adapter.settings() if row["id"] == "net_diagnostics")

    def test_shelf_describes_available_direct_ip_online(self):
        self.assertEqual(self.adapter.status()["players"], "@t4.direct_title")

    def test_diagnostics_are_explicit_opt_in_and_stay_in_launcher_settings(self):
        self.assertIs(self.row()["value"], False)
        self.assertEqual(self.row()["options"], [(False, "@off"), (True, "@on")])
        self.adapter.set_setting("net_diagnostics", True)
        self.save.assert_called_once_with(self.config)
        self.assertIs(self.row()["value"], True)
        self.assertEqual(self.core.saved, {})
        other = T4(MANIFEST, self.config, "fake-root", core=self.core)
        self.assertEqual(other._beta_env()["TEKKEN4_NET_DIAG"], "1")
        self.adapter.set_setting("net_diagnostics", False)
        self.assertEqual(self.adapter._beta_env()["TEKKEN4_NET_DIAG"], "0")

    def test_only_a_saved_boolean_can_enable_diagnostics(self):
        for invalid in ("1", "0", "false", 1, [], None):
            with self.subTest(value=invalid):
                self.config["t4_diagnostics"] = dict(net_diagnostics=invalid)
                self.assertIs(self.row()["value"], False)
                self.adapter.set_setting("net_diagnostics", invalid)
                self.assertEqual(self.adapter._beta_env()["TEKKEN4_NET_DIAG"], "0")
        self.save.assert_not_called()

    def test_malformed_diagnostics_config_falls_back_to_off_and_can_be_replaced(self):
        for invalid in ("enabled", True, 1, [True]):
            with self.subTest(value=invalid):
                self.config["t4_diagnostics"] = invalid
                self.assertIs(self.row()["value"], False)
                self.assertEqual(self.adapter._beta_env()["TEKKEN4_NET_DIAG"], "0")
                self.adapter.set_setting("net_diagnostics", True)
                self.assertIs(self.row()["value"], True)

    def test_launch_clears_inherited_experiments_and_honors_diagnostic_opt_in(self):
        extras = dict.fromkeys(BETA_DISABLED_SWITCHES, "1")
        extras["TEKKEN4_NET_DIAG"] = "1"
        extras["TEKKEN4_NET"] = "host:7400"
        self.adapter._start(extras)
        for switch in (*BETA_DISABLED_SWITCHES, "TEKKEN4_NET_DIAG"):
            self.assertEqual(self.core.launched[switch], "0", switch)
        self.assertEqual(self.core.launched["TEKKEN4_NET"], "host:7400")
        self.adapter.set_setting("net_diagnostics", True)
        self.adapter._start()
        self.assertEqual(self.core.launched["TEKKEN4_NET_DIAG"], "1")
        self.assertTrue(all(self.core.launched[switch] == "0" for switch in BETA_DISABLED_SWITCHES))

    def test_diagnostics_setting_is_reachable_and_toggleable_with_pad(self):
        nav = Nav([Game(MANIFEST, self.adapter)])
        nav.act("confirm", "xbox")
        target = next(i for i, row in enumerate(nav.items()) if row.get("id") == "net_diagnostics")
        for _ in range(len(nav.items())):
            if nav.focus_index(nav.items()) == target:
                break
            pad_step(nav, target)
        self.assertEqual(nav.focus_index(nav.items()), target)
        nav.act("right", "xbox")
        self.assertIs(self.row()["value"], True)
        nav.act("left", "xbox")
        self.assertIs(self.row()["value"], False)
        nav.act("back", "xbox")
        self.assertEqual(nav.screen, "start")

    def test_beta_launch_removes_inherited_and_explicit_net_test_harness(self):
        inherited = {
            "TEKKEN4_NET_END": "9000", "TEKKEN4_NET_SHOTS": "1000,2000",
            "TEKKEN4_NET_DESYNC_DUMP": "1", "TEKKEN4_NET_SIM": "lat=25,jitter=5,loss=3",
            "TEKKEN4_SOUND": "1",
        }
        with mock.patch.object(self.core, "game_env", return_value=inherited) as original:
            self.adapter._start()
            for name in BETA_HARNESS_SWITCHES:
                self.assertNotIn(name, self.core.launched)
            self.assertEqual(self.core.launched["TEKKEN4_SOUND"], "1")
            self.assertIs(self.core.game_env, original)
        self.adapter._start(dict(inherited, TEKKEN4_NET="host:7400"))
        for name in BETA_HARNESS_SWITCHES:
            self.assertNotIn(name, self.core.launched)
        self.assertEqual(self.core.launched["TEKKEN4_NET"], "host:7400")

    def test_offline_start_is_blocked_during_preflight_verified_start_and_log_work(self):
        with mock.patch("openrecomp.adapters.t4.LaunchGuard") as guard:
            for phase, busy in (("checking", True), ("checked", False), ("starting", True),
                                ("playing", False), ("offline", True)):
                with self.subTest(phase=phase, busy=busy):
                    self.adapter._online_phase, self.adapter._direct_busy = phase, busy
                    with self.assertRaisesRegex(RuntimeError, "@online.game_running"):
                        self.adapter.start()
            guard.assert_not_called()

    def test_online_worker_can_start_its_verified_net_session(self):
        self.adapter._online_phase, self.adapter._direct_busy = "starting", True
        self.core.find_runtime = lambda settings: ("fake-runtime", "")
        with (mock.patch("openrecomp.adapters.t4.LaunchGuard"),
              mock.patch("openrecomp.adapters.t4.game_process_running", return_value=False)):
            self.assertEqual(self.adapter.start(dict(TEKKEN4_NET="host:7400")), 12)
        self.assertEqual(self.core.launched["TEKKEN4_NET"], "host:7400")

    def test_online_work_keeps_verified_settings_sources_and_build_unchanged(self):
        for phase, busy in (("checking", True), ("checked", False), ("starting", True),
                            ("playing", False), ("offline", True)):
            with self.subTest(phase=phase, busy=busy):
                self.adapter._online_phase, self.adapter._direct_busy = phase, busy
                for sid, value in (("net_diagnostics", True), ("resolution", "native"),
                                   ("aa", "off")):
                    with self.assertRaisesRegex(RuntimeError, "@t4.work_busy"):
                        self.adapter.set_setting(sid, value)
                self.assertEqual(self.adapter.set_source("iso", "other.fixture"), "@t4.work_busy")
                self.assertEqual(self.adapter.set_source("folder", "other-folder"), "@t4.work_busy")
                self.assertEqual(self.adapter.build_ready(), "@t4.work_busy")
                with self.assertRaisesRegex(RuntimeError, "@t4.work_busy"):
                    self.adapter.build_start()
                self.assertFalse(self.adapter.source_state()["running"])
        self.assertEqual(self.config, {})
        self.assertEqual(self.core.saved, {})
        self.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
