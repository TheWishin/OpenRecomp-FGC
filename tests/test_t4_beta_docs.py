"""Release scope stays consistent across the shipped player documentation."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]


class T4BetaDocsTests(unittest.TestCase):
    def read(self, name):
        return " ".join((ROOT / name).read_text(encoding="utf-8").split())

    def test_player_entry_points_describe_direct_ip_beta(self):
        for name in ("README.md", "docs/T4_FIRST_RUN.md", "docs/T4_ONLINE.md", "docs/INSTALLING.md"):
            with self.subTest(name=name):
                text = self.read(name)
                self.assertIn("direct IP", text)
                self.assertIn("VPN", text)
                self.assertIn("no lobby", text.lower())
                self.assertIn("no ranked", text.lower())
                self.assertNotIn("casual quick match", text.lower())
                self.assertNotIn("shared login", text.lower())

    def test_online_walk_has_checks_and_two_pc_release_gate(self):
        text = self.read("docs/T4_ONLINE.md")
        for phrase in ("Host", "Join", "on-screen keyboard", "build", "MSVC", "ISO", "reachability", "Collect logs", "Back", "two physical PCs"):
            self.assertIn(phrase, text)
        self.assertNotIn("t4lobby", text)

    def test_t5dr_player_guide_describes_adapter_screens_and_remaining_checks(self):
        text = self.read("docs/T5DR_ONLINE.md")
        self.assertIn("old T5DR Online launcher", text)
        self.assertIn("controller", text.lower())
        self.assertIn("installed", text.lower())
        self.assertIn("Remaining", text)

    def test_release_docs_have_no_personal_paths_or_stale_test_result(self):
        paths = [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]
        personal = re.compile(r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/(?:home|Users)/[^/\s]+/", re.I)
        for path in paths:
            with self.subTest(name=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIsNone(personal.search(text))
                self.assertNotIn("virtual environment cannot", text)
                self.assertNotIn("interpreter is unavailable", text)

    def test_packaging_guide_documents_source_only_scan(self):
        self.assertIn("tools\\package_release.py --scan-only", self.read("docs/PACKAGING.md"))


if __name__ == "__main__":
    unittest.main()
