"""Player identity and OS motion preferences, without player installs."""
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import app
from openrecomp.nav import Game, Nav
from tools.online_shots import SyntheticOnline


class VibeIntegration(unittest.TestCase):
    def test_home_starts_with_the_players_main_and_exposes_real_summary(self):
        for kind in ("t4", "t5"):
            with self.subTest(kind=kind):
                adapter = SyntheticOnline(kind)
                adapter.snapshot["me"].update(main="f7", tier=12)
                adapter.fighter_image = lambda key: ""
                adapter.rank_plate = lambda tier: ""
                adapter.recent_results = lambda: ["L", "W", "W"]
                nav = Nav([Game(adapter.m, adapter)], language="en")
                nav.open_main_menu()
                home = nav.view()["mainMenu"]
                self.assertEqual(home["fighters"][0]["key"], "f7")
                self.assertEqual(home["main"], "F7")
                self.assertEqual(home["recentResults"][0]["win"], False)
                self.assertEqual(home["friendsOnline"], 1)
                self.assertEqual(home["rank"], "3rd Dan")
                self.assertEqual(adapter.calls, [])

    def test_missing_main_does_not_claim_first_roster_fighter_as_the_player(self):
        adapter = SyntheticOnline("t4")
        adapter.main_fighter = lambda: ""
        adapter.snapshot["me"].pop("main", None)
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.open_main_menu()
        self.assertEqual(nav.view()["mainMenu"]["main"], "")

    def test_t4_result_uses_only_confirmed_history_for_current_player(self):
        adapter = SyntheticOnline("t4")
        adapter.recent_results = lambda: []
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.open_main_menu()
        self.assertTrue(nav.view()["mainMenu"]["recentResults"][0]["win"])
        adapter.snapshot["profile"]["name"] = "Another player"
        self.assertEqual(nav.view()["mainMenu"]["recentResults"], [])
        adapter.snapshot["profile"].update(name="Me", history=[dict(result="loss", status="void")])
        self.assertEqual(nav.view()["mainMenu"]["recentResults"], [])

    def test_windows_animation_preference_is_read_without_changing_it(self):
        def query(action, unused, result, flags):
            self.assertEqual((action, unused, flags), (0x1042, 0, 0))
            result._obj.value = 0
            return 1

        windows = SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=query))
        with mock.patch.object(app.os, "name", "nt"), mock.patch.object(app.ctypes, "windll", windows, create=True):
            self.assertTrue(app.system_reduced_motion())
        with mock.patch.object(app.os, "name", "posix"):
            self.assertFalse(app.system_reduced_motion())

    def test_os_motion_and_launcher_setting_are_combined_without_overwriting_setting(self):
        from PySide6.QtGui import QGuiApplication
        self.gui = QGuiApplication.instance() or QGuiApplication([])
        from test_launcher_perf import LauncherPerf
        fixture = LauncherPerf()
        fixture.addCleanup = self.addCleanup
        backend, _ = fixture.backend()
        backend.nav.reduced_motion = False
        backend._system_reduced_motion = True
        backend.refresh()
        self.assertTrue(backend.view["reducedMotion"])
        self.assertFalse(backend.nav.reduced_motion)
        backend._system_reduced_motion = False
        backend.nav.reduced_motion = True
        backend.refresh()
        self.assertTrue(backend.view["reducedMotion"])


if __name__ == "__main__":
    unittest.main()
