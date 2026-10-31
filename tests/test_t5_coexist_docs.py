"""The transition guide keeps its entry points and manual acceptance limits visible."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]


class CoexistenceDocsTests(unittest.TestCase):
    def read(self, name):
        return " ".join((ROOT / name).read_text(encoding="utf-8").split())

    def test_player_entry_points_link_the_transition_guide(self):
        for name in ("README.md", "docs/T5DR_ONLINE.md", "docs/UPDATES.md"):
            with self.subTest(name=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                links = re.findall(r"\]\(([^)]+T5DR_COEXISTENCE\.md)\)", text)
                # Relative Markdown links must resolve from each entry point.
                if not links:
                    links = re.findall(r"\]\((T5DR_COEXISTENCE\.md)\)", text)
                self.assertTrue(links)
                for link in links:
                    self.assertTrue((ROOT / name).parent.joinpath(link).is_file())

    def test_guide_covers_all_player_owned_data_and_explicit_setup(self):
        text = self.read("docs/T5DR_COEXISTENCE.md")
        for phrase in ("1.1.9", "Launcher settings", "Saved login", "Replays", "Controls",
                       "built game", "settings-folder", "copy", "--old-install",
                       "--settings-copy", "--work", "--expect rollback", "t5dr_settings_copy"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn("outside this checkout", text)
        self.assertIn("does not start a launcher, game, build", text)
        self.assertIn("does not establish that a packaged launcher survives", text)

    def test_guide_distinguishes_build_identity_and_real_acceptance(self):
        text = self.read("docs/T5DR_COEXISTENCE.md")
        for phrase in ("Code ID", "code_id", "t5dr_build.json", "Ready / Play",
                       "Build again", "Compatibility is unknown", "Not ready",
                       "original saved login", "token", "two PCs", "rollback",
                       "English", "German", "Spanish", "French", "Japanese",
                       "Korean", "Brazilian Portuguese"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)
        self.assertIn("Automated tests use fakes", text)
        self.assertIn("No real 1.1.9 installation", text)

    def test_drill_scope_separates_helper_persistence_from_native_runtime(self):
        text = self.read("docs/T5DR_COEXISTENCE.md")
        for phrase in ("real OpenRecomp settings helper", "inert Settings facade",
                       "instead of importing the native runtime", "synthetic explicit edit",
                       "saves and reloads", "original copied values return",
                       "inert_settings_facade", "private_write_checked",
                       "private_edit_rollback_checked"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
