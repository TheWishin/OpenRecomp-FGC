"""First start and update confirmation driven by pad actions and fake adapters only."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Missing
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class Onboarding(unittest.TestCase):
    def missing(self):
        adapter = Missing(manifest("t4"), {})
        return Nav([Game(adapter.m, adapter)], language="en"), adapter

    def test_first_start_without_an_install_explains_what_the_player_needs(self):
        nav, _adapter = self.missing()
        view = nav.view()
        self.assertEqual(view["hint"], i18n.text("en", "onboarding.hint"))
        self.assertEqual(view["shelf"]["tiles"][0]["bar"], i18n.text("en", "onboarding.choose_folder"))
        self.assertEqual(view["shelf"]["tiles"][0]["hero"], "")

    def test_missing_game_opens_folder_picker_and_saves_by_pad_alone(self):
        nav, adapter = self.missing()
        nav.install = mock.Mock(return_value="@folder_saved")
        with mock.patch.object(nav, "_picker_entries", return_value=[]):
            nav.act("confirm", device="xbox")
        self.assertEqual(nav.overlay, "picker")
        self.assertEqual(nav.picker["target"], "source:folder")
        entries = [dict(kind="pick", name="@picker.choose_folder", path="fake-install")]
        with mock.patch.object(nav, "_picker_entries", return_value=entries):
            nav.act("confirm", device="xbox")
        self.assertEqual(adapter.config["roots"]["t4"], "fake-install")
        nav.install.assert_called_once_with(None)
        self.assertIsNone(nav.overlay)

    def test_mixed_picker_has_current_folder_zips_and_subfolders(self):
        nav, _adapter = self.missing()
        nav.picker = dict(target="source:folder", title="", kind="file_or_folder", exts=[".zip"], dir="fake-install", focus=0)
        folder = mock.Mock(name="folder")
        folder.name, folder.path = "nested", "fake-install/nested"
        folder.is_dir.return_value = True
        archive = mock.Mock(name="archive")
        archive.name, archive.path = "T4.ZIP", "fake-install/T4.ZIP"
        archive.is_dir.return_value = False
        ignored = mock.Mock(name="ignored")
        ignored.name, ignored.path = "settings.json", "fake-install/settings.json"
        ignored.is_dir.return_value = False
        scan = mock.MagicMock()
        scan.__enter__.return_value = [folder, archive, ignored]
        with mock.patch("openrecomp.nav_picker.os.scandir", return_value=scan):
            entries = nav._picker_entries()
        self.assertEqual([entry["kind"] for entry in entries], ["pick", "dir", "file", "dir"])
        self.assertEqual(entries[2]["name"], "T4.ZIP")

    def test_empty_manifest_set_still_has_a_pad_reachable_add_slot(self):
        nav = Nav([], language="en")
        self.assertEqual(nav.view()["hint"], i18n.text("en", "onboarding.empty"))
        with mock.patch.object(nav, "_picker_entries", return_value=[]):
            nav.act("confirm", device="ps")
        self.assertEqual(nav.picker["target"], "manifest")
        nav.act("back", device="ps")
        self.assertIsNone(nav.overlay)


class LauncherUpdates(unittest.TestCase):
    def setUp(self):
        self.adapter = Fake(manifest())
        self.check = mock.Mock()
        self.install = mock.Mock()
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en", on_update_check=self.check,
                       on_update_install=self.install)

    def available(self):
        self.nav.update_state = dict(phase="available", version="v1.2.3", size=1234, notes="Release notes")

    def press(self, *actions):
        for action in actions:
            self.nav.act(action, device="xbox")

    def test_check_for_launcher_updates_is_reachable_without_entering_a_game(self):
        self.press("social", "down", "down", "down", "confirm")
        self.check.assert_called_once_with()
        self.install.assert_not_called()

    def test_update_offer_defaults_to_no_and_requires_yes_to_install(self):
        self.available()
        self.assertTrue(self.nav.offer_update())
        view = self.nav.view()
        self.assertTrue(view["dialog"]["options"][0]["focused"])
        self.assertIn("v1.2.3", view["dialog"]["text"])
        self.press("confirm")
        self.install.assert_not_called()
        self.assertFalse(self.nav.offer_update())
        self.press("social", "down", "down", "down", "confirm", "right", "confirm")
        self.install.assert_called_once_with()

    def test_updates_wait_for_overlays_and_busy_games_then_recheck_at_confirmation(self):
        self.available()
        self.press("social")
        self.assertFalse(self.nav.offer_update())
        self.press("back")
        self.adapter.is_running = True
        self.assertFalse(self.nav.offer_update())
        self.adapter.is_running = False
        self.assertTrue(self.nav.offer_update())
        self.adapter.is_running = True
        self.press("right", "confirm")
        # The download needs no closed game: it starts, and the restart waits ("installs when you close the game")
        self.install.assert_called_once()
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "updates.queued"))

    def test_updates_wait_for_build_support_and_online_sessions(self):
        self.available()
        for method, state in (("build_state", dict(running=True)), ("support_state", dict(running=True)),
                              ("online_state", dict(phase="logged_in"))):
            with self.subTest(method=method), mock.patch.object(self.adapter, method, return_value=state):
                self.assertFalse(self.nav.offer_update())

    def test_changed_offer_and_dry_run_cannot_install(self):
        self.available()
        self.nav.offer_update()
        self.nav.update_state["version"] = "v1.2.4"
        self.press("right", "confirm")
        self.install.assert_not_called()
        self.nav.offer_update()
        self.nav.dry = True
        self.press("right", "confirm")
        self.install.assert_not_called()

    def test_update_size_is_said_in_megabytes(self):
        # The QA run showed "Install v0.1.1 (106157269 bytes)": a player reads megabytes.
        self.available()
        self.nav.update_state["size"] = 106_157_269
        self.nav.offer_update()
        for language in ("en", "de"):
            self.nav.language = language
            body = self.nav.view()["dialog"]["text"]
            self.assertIn("(106 MB)", body)
            self.assertNotIn("106157269", body)

    def test_release_notes_are_literal_and_bound_to_a_readable_paragraph(self):
        self.available()
        self.nav.update_state["notes"] = "@yes\n" + "line\n" * 300
        self.nav.offer_update()
        body = self.nav.view()["dialog"]["text"]
        self.assertIn("@yes line", body)
        self.assertLess(len(body), 600)


if __name__ == "__main__":
    unittest.main()
