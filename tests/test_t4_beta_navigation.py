"""The direct-IP beta remains usable with semantic controller actions only."""
import unittest

from openrecomp.nav import Game, Nav
from test_online_nav import Lobby, OnlineNavigation


class Direct(Lobby):
    def __init__(self):
        super().__init__()
        self.m.update(id="t4", adapter="t4", sections=["play", "online", "build", "settings"])
        self.snapshot.update(role="host", busy=False, message="@t4.direct_hint",
                             capabilities=dict(direct_ip=True, lobby=True, ranked=True),
                             checks=[dict(id="build", label="@version", value="@t4.direct_pending", ok=None)])
        self.texts["online_address"] = ""

    def online_action(self, action):
        self.calls.append(("online", action))
        if action in ("host", "join"):
            self.snapshot.update(role=action, phase="offline")
        elif action == "check":
            self.snapshot.update(phase="checking", busy=True)
        elif action in ("cancel_match", "disconnect"):
            self.snapshot.update(phase="offline", busy=False)
        elif action == "start_match":
            self.snapshot.update(phase="playing")
        elif action == "stop_match":
            self.snapshot.update(phase="offline")


class T4BetaNavigation(unittest.TestCase):
    choose = OnlineNavigation.choose
    pad_key = OnlineNavigation.pad_key

    def setUp(self):
        self.a = Direct()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec["t4"] = "online"

    def ids(self):
        return [item.get("id") for item in self.nav.items()]

    def test_pad_selects_role_enters_address_and_runs_checks(self):
        self.choose("join")
        self.choose("online_address")
        self.assertEqual(self.nav.osk["title"], "@t4.direct_address")
        for char in "192.0.2.10":
            self.pad_key(char)
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.texts["online_address"], "192.0.2.10")
        self.choose("check")
        self.assertEqual(self.a.snapshot["phase"], "checking")
        self.assertNotIn("start_match", self.ids())
        for iid in ("host", "join", "online_address", "check"):
            item = next(item for item in self.nav.items() if item.get("id") == iid)
            self.assertTrue(item["disabled"])
            self.assertIsNone(item["run"])
        self.choose("cancel_match")
        self.choose("collect_logs")
        self.assertIn(("online", "collect_logs"), self.a.calls)
        self.nav.act("back", device="xbox")
        self.assertEqual(self.nav.screen, "start")
        self.assertEqual(self.a.calls[-1], ("online", "disconnect"))

    def test_explicit_direct_mode_stays_direct_but_missing_capabilities_use_lobby(self):
        forbidden = {"login_guest", "login_account", "login_saved", "search_ranked", "search_casual",
                     "refresh_players", "refresh_rooms", "online_chat", "native", "return_lobby"}
        for phase in ("offline", "error", "logged_in", "matched", "result", "result_sent", "playing"):
            self.a.snapshot["phase"] = phase
            self.assertFalse(forbidden.intersection(self.ids()), phase)
        self.a.snapshot["capabilities"] = dict(lobby=True, ranked=True)
        self.a.snapshot["phase"] = "offline"
        self.assertNotIn("host", self.ids())
        self.assertIn("login_guest", self.ids())

    def test_start_requires_successful_checks_and_stop_is_controller_action(self):
        self.a.snapshot.update(phase="checked", checks=[])
        self.assertNotIn("start_match", self.ids())
        self.a.snapshot["checks"] = [dict(id="build", label="@version", value="@ready", ok=False)]
        self.assertNotIn("start_match", self.ids())
        self.a.snapshot["checks"][0]["ok"] = True
        self.choose("start_match")
        self.assertNotIn("start_match", self.ids())
        self.choose("stop_match")
        self.assertEqual(self.a.calls[-1], ("online", "stop_match"))
        self.assertFalse(any(call[0] == "start" for call in self.a.calls))

    def test_check_rows_have_focusable_full_details(self):
        self.a.snapshot["checks"] = [dict(id="iso", label="@game_iso", value="A complete check explanation", ok=False)]
        self.choose("check:iso")
        detail = self.nav.view()["detail"]
        self.assertEqual(detail["lead"], "A complete check explanation")
        self.assertEqual(detail["leadLines"], 6)

    def test_log_collection_is_unavailable_until_the_owned_game_stops(self):
        self.a.snapshot.update(phase="playing", busy=False)
        item = next(item for item in self.nav.items() if item.get("id") == "collect_logs")
        self.assertTrue(item["disabled"])
        self.assertIsNone(item["run"])
        self.assertEqual(item["verb"], "")
        self.a.snapshot["phase"] = "offline"
        item = next(item for item in self.nav.items() if item.get("id") == "collect_logs")
        self.assertFalse(item["disabled"])

    def test_back_button_and_dry_mode_do_not_bypass_safety(self):
        self.nav.dry = True
        for iid in ("host", "join", "check", "collect_logs", "direct_back"):
            self.choose(iid)
            self.nav.screen = "hub"
        self.assertEqual(self.a.calls, [])
        self.nav._activate(dict(kind="action", disabled=True, run=lambda: self.a.calls.append("bad")))
        self.assertEqual(self.a.calls, [])

    def test_t5dr_online_uses_adapter_and_play_does_not_launch_native(self):
        self.a.m.update(id="t5dr", adapter="t5dr")
        self.a.snapshot["capabilities"] = dict(lobby=True, ranked=True)
        nav = Nav([Game(self.a.m, self.a)])
        nav.screen = "hub"
        nav.sec["t5dr"] = "online"
        ids = [item.get("id") for item in nav.items()]
        self.assertIn("login_guest", ids)
        self.assertIn("native", ids)
        nav.act("play", device="xbox")
        self.assertEqual(self.a.calls, [])
        nav.focus["t5dr:online"] = ids.index("login_guest")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("online", "login_guest")])
        self.assertFalse(any(prompt["action"] == "play" for prompt in nav.view()["prompts"]))

    def test_missing_t4_does_not_offer_unusable_host_join_actions(self):
        self.a.found = lambda: False
        self.assertEqual(self.ids(), ["folder"])
        self.choose("folder")
        self.assertEqual(self.nav.sec["t4"], "build")


if __name__ == "__main__":
    unittest.main()
