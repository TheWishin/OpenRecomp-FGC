"""Registration and one-time recovery codes remain controller-accessible."""
import unittest

from openrecomp.nav import Game, Nav
import test_online_nav as online_nav


class RegisterNavigationTests(unittest.TestCase):
    choose = online_nav.OnlineNavigation.choose

    def setUp(self):
        self.a = online_nav.Lobby()
        self.a.snapshot["capabilities"] = dict(registration=True)
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def test_registration_is_controller_selectable_only_when_supported(self):
        self.choose("login_register")
        self.assertIn(("online", "login_register"), self.a.calls)
        self.a.snapshot.update(phase="offline", capabilities={})
        self.assertNotIn("login_register", [item.get("id") for item in self.nav.items()])

    def test_every_recovery_code_is_reachable_before_acknowledgment(self):
        codes = ["FAKE-CODE-" + str(i) for i in range(8)]
        self.a.snapshot.update(phase="logged_in", recovery_codes=codes)
        ids = [item.get("id") for item in self.nav.items()]
        self.assertNotIn("search_casual", ids)
        for index, code in enumerate(codes):
            self.choose("recovery_code:" + str(index))
            self.assertIn(code, str(self.nav.view()["detail"]))
        self.choose("acknowledge_recovery")
        self.assertIn(("online", "acknowledge_recovery"), self.a.calls)
        self.a.snapshot["recovery_codes"] = []
        self.assertIn("search_casual", [item.get("id") for item in self.nav.items()])

    def test_dry_acknowledgment_keeps_codes_visible(self):
        self.a.snapshot.update(phase="logged_in", recovery_codes=["FAKE-CODE"])
        self.nav.dry = True
        self.choose("acknowledge_recovery")
        self.assertNotIn(("online", "acknowledge_recovery"), self.a.calls)
        self.assertEqual(self.a.snapshot["recovery_codes"], ["FAKE-CODE"])


if __name__ == "__main__":
    unittest.main()
