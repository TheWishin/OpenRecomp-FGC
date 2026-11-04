"""Folder recovery and old-release updates work through controller actions, with inert layouts."""
import unittest
from unittest import mock

from openrecomp import adapters, i18n
from openrecomp.adapters.base import Missing
from openrecomp.adapters.t5dr import LegacyT5DR
from openrecomp.nav import Game, Nav
import test_t5_folder_choice as layouts
from test_game_setup_nav import Setup
from test_nav import manifest


class FolderNavigation(layouts.FolderLayout):
    def nav(self, config=None):
        self.config = config if config is not None else {}
        self.m = manifest("t5dr", adapter="t5dr")
        adapter = Missing(self.m, self.config)
        self.reload = mock.Mock(side_effect=self.reload_game)
        self.setup = Setup()
        nav = Nav([Game(self.m, adapter)], install=self.reload, language="en", on_setup=self.setup,
                  native_picker=True)
        nav._select_game(nav.games[0])
        nav.screen = "hub"
        nav.sec["t5dr"] = "build"
        self.navigation = nav
        return nav

    def reload_game(self, path):
        adapter = adapters.make(self.m, self.config)
        self.navigation.set_games([Game(self.m, adapter)])
        return "@folder_saved"

    def test_native_result_uses_parent_root_and_tells_player_which_folder(self):
        root = self.install("existing")
        native = root / "native"
        native.mkdir()
        nav = self.nav()
        nav._request_native("source:folder", "@t5.choose_install", [], "folder", str(native))
        nav.native_result(nav.native_request(), str(native))
        self.assertEqual(self.config["roots"]["t5dr"], str(root.resolve()))
        self.reload.assert_called_once_with(None)
        self.assertIn(str(root.resolve()), i18n.localize(nav.toast, "en"))
        self.process.assert_not_called()

    def test_ambiguous_choice_can_be_cancelled_without_changing_config(self):
        root = self.install("wrapper/one")
        self.install("wrapper/two")
        nav = self.nav(dict(roots=dict(t5dr="previous"), t5dr_settings_copy="previous-copy"))
        nav._picked("source:folder", str(root.parent))
        self.assertEqual(nav.overlay, "picker")
        self.assertIn("Several T5DR", nav.view()["picker"]["message"])
        nav.act("back", device="xbox")
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.config, dict(roots=dict(t5dr="previous"), t5dr_settings_copy="previous-copy"))
        self.reload.assert_not_called()

    def test_controller_selects_second_candidate_from_list_and_rechecks_it(self):
        one = self.install("wrapper/one")
        two = self.install("wrapper/two")
        nav = self.nav()
        nav._picked("source:folder", str(one.parent))
        self.assertEqual([row["name"] for row in nav.view()["picker"]["rows"]], [str(one), str(two)])
        nav.act("down", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.config["roots"]["t5dr"], str(two.resolve()))
        self.assertIn(str(two.resolve()), i18n.localize(nav.toast, "en"))
        self.assertIsNone(nav.overlay)

    def test_missing_candidate_uses_existing_clear_reinstall_message(self):
        chosen = self.folder / "empty"
        chosen.mkdir()
        nav = self.nav(dict(roots=dict(t5dr="previous")))
        nav._picked("source:folder", str(chosen))
        self.assertEqual(nav.toast, "@t5.install_incomplete_python")
        self.assertEqual(self.config["roots"]["t5dr"], "previous")
        self.reload.assert_not_called()

    def test_failed_reload_keeps_failure_message_instead_of_announcing_folder_taken(self):
        root = self.install("existing")
        nav = self.nav()
        for result in ("@preferences.save_failed", "@library.busy", RuntimeError("synthetic save failure")):
            with self.subTest(result=result):
                self.reload.side_effect = result if isinstance(result, Exception) else None
                self.reload.return_value = result
                nav._picked("source:folder", str(root))
                self.assertEqual(nav.toast, "@t4.install_failed" if isinstance(result, Exception) else result)

    def test_chosen_old_install_offers_update_here_and_waits_for_controller_approval(self):
        root = self.install("old", "1.1.9")
        nav = self.nav()
        nav._picked("source:folder", str(root))
        self.assertIsInstance(nav.game.a, LegacyT5DR)
        row = nav.items()[0]
        self.assertEqual(i18n.localize(row["label"], "en"), "Update T5DR here")
        self.assertIn("1.1.x", nav.view()["build"]["cards"][0]["text"])
        self.assertEqual(self.setup.calls, [])
        nav.focus["t5dr:build"] = 0
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.confirm_kind, "setup_loading")
        self.assertEqual(self.setup.calls, [("check", "t5dr", True)])
        nav.setup_state = {"t5dr": dict(phase="ready", installed="1.1.9", latest="1.2.0")}
        nav.poll_setup([("t5dr", "check", {}, None)])
        dialog = nav.view()["dialog"]
        self.assertEqual(dialog["options"][1]["label"], "Update T5DR here")
        self.assertIn(str(root.resolve()), dialog["text"])
        self.assertEqual(self.setup.calls, [("check", "t5dr", True)])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("update", "t5dr", None))
        self.assertEqual(nav.confirm_kind, "setup_progress")
        self.runtime.assert_not_called()

    def test_cancel_old_update_check_does_not_open_install_dialog_or_update(self):
        root = self.install("old", "1.1.8")
        nav = self.nav()
        nav._picked("source:folder", str(root))
        nav.setup_offer_update(nav.game)
        nav.act("back", device="xbox")
        nav.setup_state = {"t5dr": dict(phase="ready", installed="1.1.8", latest="1.2.0")}
        nav.poll_setup([("t5dr", "check", {}, None)])
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.setup.calls, [("check", "t5dr", True)])

    def test_old_update_completion_keeps_restart_action_on_build_page(self):
        root = self.install("old", "1.1.9")
        nav = self.nav()
        nav._picked("source:folder", str(root))
        nav.setup_game = "t5dr"
        nav.setup_state = {"t5dr": dict(phase="updated", installed="1.2.0", restart=True)}
        nav.poll_setup([("t5dr", "update", dict(restart=True), None)])
        self.assertEqual(nav.confirm_kind, "setup_restart")
        nav.act("back", device="xbox")
        self.assertEqual(nav.items()[0]["id"], "game_update")
        self.assertEqual(nav.items()[0]["label"], "@setup.updated_restart")


if __name__ == "__main__":
    unittest.main()
