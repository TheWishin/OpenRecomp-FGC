"""Existing-install consent uses controller actions and fake folders only."""
from types import SimpleNamespace
import os
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Missing
from openrecomp.app_game_setup import GameSetupBackend
from openrecomp.nav import Game, Nav
from test_game_setup_nav import Game5, Setup


class ExistingInstallNav(unittest.TestCase):
    def nav(self, roots=()):
        self.adapter = Game5(found=False)
        self.adapter.existing_installs = mock.Mock(return_value=list(roots))
        self.setup = Setup()
        self.nav_ = Nav([Game(self.adapter.m, self.adapter)], language="en", on_setup=self.setup)
        self.nav_.setup_state = {"t5dr": dict(phase="ready", latest="1.2.0", offer={})}
        return self.nav_

    def test_install_first_offers_existing_folder_and_use_never_downloads(self):
        root = "D:/player-owned/T5DR"
        nav = self.nav([root])
        nav.act("confirm", device="xbox")
        nav.act("confirm", device="xbox")
        dialog = nav.view()["dialog"]
        self.assertEqual(nav.confirm_kind, "setup_existing")
        self.assertEqual(dialog["text"], f"Use your existing T5DR in {root}? (keeps your saves and build)")
        self.assertEqual([o["label"] for o in dialog["options"]], ["Use", "Install a new copy"])
        self.assertEqual(self.setup.calls, [])
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls, [("use_existing", "t5dr", root)])
        self.assertIsNone(nav.overlay)
        self.assertIn(root, i18n.localize(nav.toast, "en"))

    def test_back_leaves_existing_folder_and_install_untouched(self):
        nav = self.nav(["D:/player-owned/T5DR"])
        nav.setup_begin(nav.games[0])
        nav.act("back", device="xbox")
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.setup.calls, [])

    def test_new_copy_requires_explicit_choice_for_every_discovered_install(self):
        roots = ["D:/first/T5DR", "E:/second/T5DR"]
        nav = self.nav(roots)
        nav.setup_begin(nav.games[0])
        for root in roots:
            self.assertEqual(nav.confirm_kind, "setup_existing")
            self.assertIn(root, nav.view()["dialog"]["text"])
            self.assertFalse(any(c[0] == "install" for c in self.setup.calls))
            nav.act("right", device="xbox")
            nav.act("confirm", device="xbox")
        self.assertEqual(nav.confirm_kind, "setup_install")
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-2:], [("allow_new", "t5dr", roots), ("install", "t5dr", "D:/Games")])

    def test_new_attempt_asks_again_after_cancellation(self):
        nav = self.nav(["D:/player-owned/T5DR"])
        nav.setup_begin(nav.games[0])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.confirm_kind, "setup_install")
        nav.act("back", device="xbox")
        nav.setup_begin(nav.games[0])
        self.assertEqual(nav.confirm_kind, "setup_existing")
        self.assertEqual(nav.exit_focus, 0)

    def test_rechecks_chosen_parent_and_final_install_for_newly_found_install(self):
        nav = self.nav()
        nav.setup_begin(nav.games[0])
        self.assertEqual(nav.confirm_kind, "setup_install")
        self.adapter.existing_installs.return_value = ["E:/chosen-parent/T5DR"]
        nav.setup_folder_picked("E:/chosen-parent")
        self.assertEqual(nav.confirm_kind, "setup_existing")
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.adapter.existing_installs.return_value.append("E:/another/T5DR")
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.confirm_kind, "setup_existing")
        self.assertIn("E:/another/T5DR", nav.view()["dialog"]["text"])
        self.assertFalse(any(c[0] == "install" for c in self.setup.calls))

    def test_use_failure_keeps_backend_error(self):
        nav = self.nav(["D:/player-owned/T5DR"])

        def fail(action, gid, arg):
            nav.say("@preferences.save_failed")
            return False

        nav.on_setup = fail
        nav.setup_begin(nav.games[0])
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.toast, "@preferences.save_failed")

    def test_prompt_is_translated_and_preserves_literal_path_in_every_language(self):
        root = "D:/@folder/{unchanged}/T5DR"
        nav = self.nav([root])
        nav.setup_begin(nav.games[0])
        for code in i18n.LANGUAGES:
            nav.language = code
            dialog = nav.view()["dialog"]
            self.assertIn(root, dialog["text"])
            self.assertNotIn("@t5.existing", repr(dialog))


class ExistingInstallBackend(unittest.TestCase):
    def backend(self):
        backend = GameSetupBackend()
        self.adapter = Game5(found=False)
        self.adapter.existing_installs = mock.Mock(return_value=["D:/player-owned/T5DR"])
        backend.nav = SimpleNamespace(game_by_id=lambda gid: SimpleNamespace(a=self.adapter), say=mock.Mock(),
                                      setup_parent="D:/Games", setup_installed=mock.Mock())
        backend.config = {}
        backend._update_busy = mock.Mock(return_value=False)
        backend.setup = SimpleNamespace(install=mock.Mock(return_value=True))
        backend._reload_library = mock.Mock(return_value="@folder_saved")
        return backend

    def test_backend_refuses_second_copy_without_acknowledged_existing_paths(self):
        backend = self.backend()
        self.assertFalse(backend._setup_action("install", "t5dr", "D:/Games"))
        backend.setup.install.assert_not_called()
        backend._setup_action("allow_new", "t5dr", ["D:/player-owned/T5DR"])
        self.assertTrue(backend._setup_action("install", "t5dr", "D:/Games"))
        backend.setup.install.assert_called_once_with("t5dr", "D:/Games")
        self.assertFalse(backend._setup_action("install", "t5dr", "D:/Games"))

    def test_use_registers_existing_folder_without_installing_or_copying_it(self):
        backend = self.backend()
        backend.config["t5dr_settings_copy"] = "previous-copy"
        with mock.patch("openrecomp.app_game_setup.mf.save_config") as save:
            self.assertTrue(backend._setup_action("use_existing", "t5dr", "D:/player-owned/T5DR"))
        self.assertEqual(backend.config["roots"], dict(t5dr="D:/player-owned/T5DR"))
        self.assertNotIn("t5dr_settings_copy", backend.config)
        # 0.1.3: the folder is remembered as a known install (the Build page's switch lists it)
        self.assertEqual(backend.config["known_roots"], dict(t5dr=[os.path.abspath("D:/player-owned/T5DR")]))
        save.assert_called_once_with(backend.config)
        backend._reload_library.assert_called_once_with()
        backend.nav.setup_installed.assert_called_once_with("t5dr")
        backend.setup.install.assert_not_called()

    def test_disappeared_existing_folder_cannot_be_registered(self):
        backend = self.backend()
        self.adapter.existing_installs.return_value = []
        self.assertFalse(backend._setup_action("use_existing", "t5dr", "D:/player-owned/T5DR"))
        self.assertEqual(backend.config, {})
        backend._reload_library.assert_not_called()

    def test_use_save_failure_restores_previous_folder_and_settings_without_reload(self):
        backend = self.backend()
        previous = dict(roots=dict(t5dr="D:/previous/T5DR", t4="D:/previous/T4"),
                        t5dr_settings_copy="previous-copy")
        backend.config.update(previous)
        with mock.patch("openrecomp.app_game_setup.mf.save_config", side_effect=OSError("synthetic save failure")):
            self.assertFalse(backend._setup_action("use_existing", "t5dr", "D:/player-owned/T5DR"))
        self.assertEqual(backend.config, previous)
        backend._reload_library.assert_not_called()
        backend.nav.setup_installed.assert_not_called()
        backend.nav.say.assert_called_once_with("@preferences.save_failed", 8)

    def test_use_reload_failure_does_not_report_success(self):
        backend = self.backend()
        backend._reload_library.return_value = "@library.busy"
        with mock.patch("openrecomp.app_game_setup.mf.save_config"):
            self.assertFalse(backend._setup_action("use_existing", "t5dr", "D:/player-owned/T5DR"))
        backend.nav.setup_installed.assert_not_called()
        backend.nav.say.assert_called_once_with("@library.busy")

    def test_missing_t5dr_adapter_uses_read_only_discovery_interface(self):
        adapter = Missing(dict(id="t5dr", adapter="t5dr"), {})
        with mock.patch("openrecomp.adapters.t5_discovery.existing_installs", return_value=["D:/existing"]) as scan:
            self.assertEqual(adapter.existing_installs("D:/Games"), ["D:/existing"])
        scan.assert_called_once_with(adapter.m, adapter.config, "D:/Games")


if __name__ == "__main__":
    unittest.main()
