"""T5DR online and new preferences stay reachable with controller actions alone."""
from pathlib import Path
from contextlib import ExitStack
import tempfile
import unittest
from unittest import mock

from openrecomp.nav import Game, Nav
import test_online_nav as online_nav


class T5OnlineNavigationTests(unittest.TestCase):
    choose = online_nav.OnlineNavigation.choose
    pad_key = online_nav.OnlineNavigation.pad_key

    def setUp(self):
        self.a = online_nav.Lobby()
        self.a.m["adapter"] = "t5dr"
        self.a.snapshot["capabilities"] = dict(lobby=True, ranked=True)
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def test_t5_login_uses_adapter_without_opening_native_launcher(self):
        self.choose("login_guest")
        self.assertIn(("online", "login_guest"), self.a.calls)
        self.assertNotIn(("native",), self.a.calls)
        self.assertIn("logout", [item.get("id") for item in self.nav.items()])

    def test_each_supported_feature_row_is_reachable_by_pad(self):
        from openrecomp import nav_accounts, nav_challenges, nav_community, nav_profiles, nav_rules, nav_spectating, nav_tournaments

        modules = (nav_profiles, nav_tournaments, nav_spectating, nav_community, nav_accounts, nav_rules, nav_challenges)
        self.a.snapshot["phase"] = "logged_in"
        with ExitStack() as stack:
            for index, module in enumerate(modules):
                def rows(nav, game, state, action, index=index):
                    return [action("feature:" + str(index), "@online.status")]
                stack.enter_context(mock.patch.object(module, "rows", side_effect=rows))
            for index in range(len(modules)):
                self.choose("feature:" + str(index))
                self.assertIn(("online", "feature:" + str(index)), self.a.calls)

    def test_start_button_cannot_open_native_or_start_game_from_online(self):
        for phase in ("offline", "logged_in", "searching", "matched", "playing"):
            with self.subTest(phase=phase):
                self.a.snapshot["phase"] = phase
                self.nav.act("play", device="xbox")
        self.assertFalse(any(call[0] in ("native", "start") for call in self.a.calls))

    def test_missing_t5_install_keeps_controller_folder_recovery(self):
        with mock.patch.object(self.a, "found", return_value=False):
            self.assertEqual([item.get("id") for item in self.nav.items()], ["folder"])
            self.choose("folder")
        self.assertEqual(self.nav.section(), "build")

    def test_fighter_selection_is_reachable_and_locked_set_cannot_change_it(self):
        self.a.snapshot.update(phase="logged_in", character_locked=False)
        self.choose("online_fighter")
        self.assertEqual(self.nav.overlay, "fighters")
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertIn(("fighter", "f0"), self.a.calls)
        self.a.snapshot["character_locked"] = True
        self.choose("online_fighter")
        self.assertIsNone(self.nav.overlay)
        self.assertTrue(next(item for item in self.nav.items() if item.get("id") == "online_fighter")["disabled"])

    def test_new_text_fields_have_titles_and_passwords_stay_masked(self):
        fields = {
            "online_tour_name": "@online.tour_name", "online_tour_clock": "@online.tour_clock",
            "online_tour_dq": "@online.tour_dq", "online_profile_name": "@online.profile_lookup",
            "online_current_password": "@online120.current_password", "online_new_password": "@online120.new_password",
            "online_repeat_password": "@online120.repeat_password", "online_recovery_code": "@online120.recovery_code",
            "online_block_name": "@online120.block_name", "online_fingerprint": "@online120.fingerprint",
        }
        for tid, title in fields.items():
            with self.subTest(tid=tid):
                self.nav._open_osk(tid)
                self.assertEqual(self.nav.osk["title"], title)
                self.nav.act("back", device="xbox")
        for tid in ("online_current_password", "online_new_password", "online_repeat_password", "online_recovery_code"):
            self.nav._open_osk(tid)
            for char in "aB@":
                self.pad_key(char)
            self.assertNotIn("aB@", str(self.nav.view()))
            self.nav.act("play", device="xbox")
            self.assertEqual(self.a.texts[tid], "aB@")

    def test_ranked_set_score_lock_and_leave_action_are_visible(self):
        self.a.snapshot.update(phase="result_sent", character_locked=True,
                               capabilities=dict(match_flow=True, leave_set=True),
                               set=dict(rated=True, wins=[2, 1], first_to=3, number=4, best_of=5,
                                        next={"in": 3}))
        detail = self.nav.items()[0]["detail"]
        self.assertIn("@online.character_locked", str(detail))
        self.assertTrue(any(row["v"].get("_text") == "online.set_score" for row in detail["rows"] if isinstance(row["v"], dict)))
        self.choose("leave_set")
        self.assertIn(("online", "leave_set"), self.a.calls)

    def test_replay_folder_picker_saves_and_resets_by_pad(self):
        self.nav.sec[self.a.m["id"]] = "settings"
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            setting = dict(id="replay_dir", kind="folder", label="@t5.replay_folder",
                           hint="@t5.replay_folder_hint", value=directory)
            with mock.patch.object(self.a, "settings", return_value=[setting]):
                self.choose("replay_dir")
                self.assertEqual(self.nav.overlay, "picker")
                self.assertEqual(self.nav.picker["target"], "setting:replay_dir")
                self.nav.act("confirm", device="xbox")
                self.assertIn(("set", "replay_dir", directory), self.a.calls)
                self.choose("reset:replay_dir")
                self.assertIn(("set", "replay_dir", ""), self.a.calls)

    def test_dry_replay_folder_picker_and_reset_do_not_write(self):
        self.nav.sec[self.a.m["id"]] = "settings"
        self.nav.dry = True
        setting = dict(id="replay_dir", kind="folder", label="@t5.replay_folder", value="temporary")
        with mock.patch.object(self.a, "settings", return_value=[setting]):
            self.choose("reset:replay_dir")
            self.nav._picked("setting:replay_dir", "temporary")
        self.assertFalse(any(call[0] == "set" for call in self.a.calls))


if __name__ == "__main__":
    unittest.main()
