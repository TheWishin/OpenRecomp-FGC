"""Offline failures and empty states remain actionable with fake adapters only."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.base import Adapter
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class OfflineFeedback(unittest.TestCase):
    def setUp(self):
        self.adapter = Fake(manifest())
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")

    def test_start_on_unbuilt_game_opens_build_without_starting(self):
        self.adapter.is_ready = False
        self.nav.act("play")
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual((self.nav.screen, self.nav.section()), ("hub", "build"))

    def test_unready_game_without_build_does_not_offer_nonexistent_section(self):
        self.adapter.m["sections"] = ["play"]
        self.adapter.is_ready = False
        self.nav.act("confirm")
        view = self.nav.view()
        self.assertEqual(view["detail"]["primary"], "")
        self.assertFalse(any(p["action"] == "confirm" for p in view["prompts"]))
        self.nav.act("confirm")
        self.assertEqual(self.nav.section(), "play")

    def test_failed_offline_actions_preserve_cause_and_recovery_in_all_languages(self):
        for code in i18n.LANGUAGES:
            self.nav.language = code
            for method, action in (
                ("start", lambda: self.nav.start_game(self.nav.game)),
                ("play_replay", lambda: self.nav._play_replay(self.nav.game, "fake")),
                ("open_native", lambda: self.nav._native_item(self.nav.game)["run"]()),
                ("build_start", lambda: self.nav._items_build(self.nav.game)[1]["run"]()),
            ):
                with self.subTest(language=code, method=method), mock.patch.object(self.adapter, method, side_effect=RuntimeError("fake failure")):
                    action()
                    self.assertEqual(self.nav.view()["toast"], i18n.text(code, "action_failed", error="fake failure"))
                    self.assertGreaterEqual(self.nav.toast_left, 10)

    def test_empty_settings_and_replays_explain_exit_controls(self):
        self.adapter.settings = lambda: []
        self.adapter.native_label = ""
        self.adapter.replays = lambda: []
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "settings"
        view = self.nav.view()
        self.assertEqual(view["settingsPage"]["adapterEmptyHint"], i18n.text("en", "no_settings_hint"))
        self.assertIn("text_size", [item.get("id") for item in self.nav.items()])
        self.assertIn("back", [prompt["action"] for prompt in view["prompts"]])
        for section, key in (("replays", "replays_hint"),):
            self.nav.screen = "hub"
            self.nav.sec[self.nav.game.id] = section
            view = self.nav.view()
            self.assertEqual(view["hint"], i18n.text("en", key))
            self.assertIn("Back", view["hint"])
            self.assertEqual([p["action"] for p in view["prompts"]][0], "back")

    def test_empty_build_has_a_focused_explanation(self):
        adapter = Adapter(manifest())
        state = Nav([Game(adapter.m, adapter)], language="en")
        state.act("confirm")
        view = state.view()
        self.assertEqual(state.section(), "build")
        self.assertTrue(view["rows"][0]["focused"])
        self.assertEqual(view["hint"], i18n.text("en", "build_unavailable_hint"))

    def test_build_wait_has_progress_and_a_nonempty_lead_without_output(self):
        self.adapter.build_state = lambda: dict(running=True, fraction=0.25, title="fake", line="", steps=[], result="")
        self.nav.screen = "hub"
        self.nav.sec[self.nav.game.id] = "build"
        self.nav.focus[self.nav.key()] = 1
        view = self.nav.view()
        self.assertEqual(view["detail"]["progress"], 0.25)
        self.assertEqual(view["detail"]["lead"], i18n.text("en", "build_running_hint"))


class PickerFeedback(unittest.TestCase):
    def setUp(self):
        adapter = Fake(manifest())
        self.nav = Nav([Game(adapter.m, adapter)], language="en")
        self.nav.overlay = "picker"
        self.nav.picker = dict(target="manifest", title="@choose_manifest", exts=[".json"], kind="file", dir="fake-folder", focus=0)

    def test_unreadable_folder_explains_failure_and_allows_parent_navigation(self):
        with mock.patch("openrecomp.nav_picker.os.scandir", side_effect=PermissionError("fake denied")):
            view = self.nav.view()
        self.assertEqual(view["picker"]["message"], i18n.text("en", "picker_unreadable"))
        self.assertEqual(view["picker"]["rows"][0]["name"], "..")
        self.nav.act("back")
        self.assertIsNone(self.nav.overlay)

    def test_unreadable_folder_cannot_be_saved_as_a_source(self):
        self.nav.picker.update(kind="folder", target="source:folder")
        with mock.patch("openrecomp.nav_picker.os.scandir", side_effect=PermissionError("fake denied")):
            view = self.nav.view()
        self.assertTrue(view["picker"]["rows"])
        self.assertTrue(all(row["kind"] == "dir" for row in view["picker"]["rows"]))
        self.assertEqual(view["prompts"][0]["label"], i18n.text("en", "open"))

    def test_empty_drives_explains_recovery_without_false_confirm_prompt(self):
        self.nav.picker["dir"] = ""
        with mock.patch("openrecomp.nav_picker.os.path.exists", return_value=False):
            self.nav.act("down")
            view = self.nav.view()
        self.assertEqual(self.nav.picker["focus"], 0)
        self.assertEqual(view["picker"]["message"], i18n.text("en", "picker_empty"))
        self.assertEqual([p["action"] for p in view["prompts"]], ["back"])

    def test_no_matching_files_explains_filter_and_choose_prompt_tracks_kind(self):
        entries = [dict(name="..", path="", kind="dir")]
        with mock.patch.object(self.nav, "_picker_entries", return_value=entries):
            self.assertEqual(self.nav.view()["picker"]["message"], i18n.text("en", "picker_no_matches"))
        entries.append(dict(name="manifest.json", path="fake", kind="file"))
        with mock.patch.object(self.nav, "_picker_entries", return_value=entries):
            self.nav.picker["focus"] = 99
            view = self.nav.view()
        self.assertEqual(self.nav.picker["focus"], 1)
        self.assertEqual(view["prompts"][0]["label"], i18n.text("en", "choose"))
        self.assertEqual(view["picker"]["message"], "")


if __name__ == "__main__":
    unittest.main()
