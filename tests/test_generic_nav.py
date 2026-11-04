"""Third-party registration stays controller driven and requires review."""
import unittest
from unittest import mock

from openrecomp import i18n, manifest as mf
from openrecomp.nav import Game, Nav
from openrecomp.nav_keyboard import ONLINE_KEYS
from test_nav import Fake, manifest
from pad_step import pad_step


class GenericNavigation(unittest.TestCase):
    def preview(self):
        return dict(source="author/project", root="", manifest=dict(
            id="example", title="Example", author="Example author", requirements=[dict(
                id="disc", label="Player disc", kind="iso", version="1.0", sha256="a" * 64)]))

    def confirm_yes(self, nav):
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")

    def test_repository_can_be_entered_with_only_controller_and_empty_library(self):
        preview = mock.Mock(return_value=self.preview())
        nav = Nav([], on_game_preview=preview, language="en")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.confirm_kind, "library_source")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.osk["tid"], "library_repository")
        nav.act("social")
        nav.act("social")
        self.assertIn("/", "".join(nav._osk_keys()))
        self.assertEqual(nav._osk_keys(), ONLINE_KEYS[2])
        nav.osk["text"] = "author/project"
        nav.act("play", device="xbox")
        preview.assert_called_once_with("author/project")
        self.assertEqual(nav.confirm_kind, "library_preview")
        self.assertIsNotNone(nav.library_preview)

    def test_game_ids_cannot_hide_the_free_registration_slot(self):
        games = []
        for index in range(mf.TOTAL_SLOTS):
            m = manifest(f"slot{index}")
            m["schema_version"] = 1
            games.append(Game(m, Fake(m)))
        nav = Nav(games, on_game_preview=mock.Mock(), language="en")
        ids = nav.tile_ids()
        self.assertEqual(len(set(ids)), len(ids))
        self.assertEqual(sum(tile["free"] for tile in nav.view()["shelf"]["tiles"]), 1)
        for _ in games:
            nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.confirm_kind, "library_source")

    def test_local_folder_choice_goes_through_preview_not_install(self):
        preview = mock.Mock(return_value=self.preview())
        install = mock.Mock()
        nav = Nav([], on_game_preview=preview, install=install, language="en")
        nav.act("confirm")
        with mock.patch.object(nav, "_picker_entries", return_value=[]):
            self.confirm_yes(nav)
        self.assertEqual(nav.picker["target"], "library_folder")
        nav._picked("library_folder", "chosen-folder")
        preview.assert_called_once_with("chosen-folder")
        install.assert_not_called()

    def test_controller_cycles_distinct_scalar_options_with_their_own_labels(self):
        m = manifest("example", sections=("settings",))
        adapter = Fake(m)
        adapter.values["mode"] = False
        options = [(False, "Boolean"), (0, "Integer"), (0.0, "Float"), ("next", "Next")]
        nav = Nav([Game(m, adapter)], language="en")
        with mock.patch.object(adapter, "settings", side_effect=lambda: [dict(
                id="mode", label="Mode", options=options, value=adapter.values["mode"])]):
            nav.act("confirm", device="xbox")
            target = next(i for i, item in enumerate(nav.items()) if item.get("id") == "mode")
            for _ in range(len(nav.items())):
                if nav.focus_index(nav.items()) == target:
                    break
                pad_step(nav, target)
            self.assertEqual(nav.focus_index(nav.items()), target)
            for value, label in options + options[:1]:
                with self.subTest(value=value, value_type=type(value).__name__):
                    self.assertIs(type(adapter.values["mode"]), type(value))
                    self.assertEqual(adapter.values["mode"], value)
                    self.assertEqual(nav.view()["detail"]["rows"][0]["v"], label)
                    nav.act("right", device="xbox")
            nav.act("left", device="xbox")
            self.assertIs(adapter.values["mode"], False)
            nav.act("left", device="xbox")
            self.assertEqual(adapter.values["mode"], "next")

    def test_author_warning_and_every_requirement_are_reviewed_before_accept(self):
        accept = mock.Mock(return_value="@library.added")
        nav = Nav([], on_game_preview=lambda source: self.preview(), on_game_accept=accept, language="en")
        nav._preview_game("author/project")
        shown = []
        while nav.library_preview is not None:
            shown.append(nav.view()["dialog"]["text"])
            accept.assert_not_called()
            self.confirm_yes(nav)
        joined = "".join(shown)
        self.assertIn("Example author", joined)
        self.assertIn("author/project", joined)
        self.assertIn(i18n.text("en", "library.third_party"), joined)
        self.assertIn("Player disc", joined)
        self.assertIn(i18n.text("en", "game_iso"), joined)
        self.assertIn("a" * 64, joined)
        accept.assert_called_once()

    def test_cancelled_preview_request_cannot_reopen_dialog(self):
        nav = Nav([], on_game_preview=lambda source: "@library.loading", language="en")
        nav._preview_game("author/project")
        request = nav.library_request
        nav.act("back")
        self.assertFalse(nav.complete_game_preview(self.preview(), request))
        self.assertIsNone(nav.overlay)
        self.assertIsNone(nav.library_preview)

    def test_external_game_menu_checks_own_release_then_confirms_install(self):
        m = manifest("example")
        m["schema_version"] = 1
        check = mock.Mock(return_value=dict(id="example", repository="author/project", channel="stable", version="v2"))
        install = mock.Mock(return_value="@library.updating")
        nav = Nav([Game(m, Fake(m))], on_game_update_check=check, on_game_update_install=install, language="en")
        nav.act("x", device="ps")
        self.assertEqual(nav.confirm_kind, "library_manage")
        nav.act("confirm", device="ps")
        check.assert_called_once_with("example")
        install.assert_not_called()
        self.assertEqual(nav.confirm_kind, "library_update")
        self.assertIn("author/project", nav.view()["dialog"]["text"])
        self.confirm_yes(nav)
        install.assert_called_once_with("example")

    def test_removal_requires_confirmation_and_only_calls_registration_callback(self):
        m = manifest("example")
        m["schema_version"] = 1
        remove = mock.Mock(return_value="@library.removed")
        nav = Nav([Game(m, Fake(m))], on_game_remove=remove, language="en")
        nav.act("x")
        self.confirm_yes(nav)
        remove.assert_not_called()
        self.assertEqual(nav.confirm_kind, "library_remove")
        self.confirm_yes(nav)
        remove.assert_called_once_with("example")

    def test_dry_registration_never_calls_service(self):
        preview = mock.Mock()
        nav = Nav([], on_game_preview=preview)
        nav.dry = True
        nav._preview_game("author/project")
        preview.assert_not_called()

    def test_library_worker_blocks_launch_and_reload(self):
        m = manifest("example")
        adapter = Fake(m)
        nav = Nav([Game(m, adapter)], language="en")
        nav.library_busy = True
        with mock.patch.object(adapter, "start") as start:
            nav.start_game(nav.game)
        start.assert_not_called()
        self.assertFalse(nav.can_reload_games())

    def test_library_worker_blocks_quit_and_online_actions_but_allows_cancel(self):
        m = manifest("example")
        nav = Nav([Game(m, Fake(m))], language="en")
        nav.screen = "hub"
        nav.library_busy = True
        with mock.patch.object(nav, "_hub") as hub:
            nav.act("confirm")
        hub.assert_not_called()
        self.assertFalse(nav.request_quit())
        nav.library_pending = "preview"
        nav._ask("library_loading")
        request = nav.library_request
        nav.act("back")
        self.assertEqual(nav.library_request, request + 1)
        self.assertIsNone(nav.overlay)
        self.assertTrue(nav.library_busy)

    def test_busy_library_loading_cancel_buttons_invalidate_late_preview(self):
        for entry in (None, 0, 1):
            with self.subTest(entry=entry):
                nav = Nav([], on_game_preview=lambda source: "@library.loading", language="en")
                nav._preview_game("author/project")
                nav.library_busy = True
                request = nav.library_request
                if entry is None:
                    nav.act("confirm", device="xbox")
                else:
                    nav.click_entry(entry)
                self.assertEqual(nav.library_request, request + 1)
                self.assertEqual(nav.library_pending, "")
                self.assertIsNone(nav.overlay)
                self.assertTrue(nav.library_busy)
                self.assertFalse(nav.complete_game_preview(self.preview(), request))
                self.assertIsNone(nav.library_preview)
                self.assertIsNone(nav.overlay)

    def test_busy_library_confirm_cannot_install_from_another_dialog(self):
        install = mock.Mock()
        nav = Nav([], on_game_update_install=install, language="en")
        nav.library_busy = True
        nav._ask("library_update")
        nav.exit_focus = 1
        request = nav.library_request
        nav.act("confirm", device="xbox")
        install.assert_not_called()
        self.assertEqual(nav.library_request, request)
        self.assertEqual(nav.overlay, "dialog")
        self.assertTrue(nav.library_busy)

    def test_empty_extensions_allow_requirement_files_without_known_extension(self):
        nav = Nav([])
        nav.picker = dict(target="source:disc", title="", kind="file", dir="folder", exts=[], focus=0)
        entry = mock.Mock(name="entry")
        entry.name = "player-disc.bin"
        entry.path = "folder/player-disc.bin"
        entry.is_dir.return_value = False
        with mock.patch("openrecomp.nav_picker.os.scandir") as scan:
            scan.return_value.__enter__.return_value = iter([entry])
            self.assertTrue(any(row["kind"] == "file" for row in nav._picker_entries()))


if __name__ == "__main__":
    unittest.main()
