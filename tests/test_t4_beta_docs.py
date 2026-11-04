"""Release scope stays consistent across the shipped player documentation."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).parents[1]


class T4BetaDocsTests(unittest.TestCase):
    def read(self, name):
        return " ".join((ROOT / name).read_text(encoding="utf-8").split())

    def test_player_entry_points_describe_default_lobby_and_advanced_direct_connection(self):
        for name in ("README.md", "docs/T4_FIRST_RUN.md", "docs/T4_ONLINE.md", "docs/INSTALLING.md"):
            with self.subTest(name=name):
                text = self.read(name)
                self.assertIn("direct ip", text.lower())
                self.assertIn("VPN", text)
                self.assertIn("lobby server", text.lower())
                self.assertIn("Settings > Advanced", text)
                self.assertIn("account", text.lower())
                self.assertIn("ranked", text.lower())
                self.assertNotIn("no lobby", text.lower())
                self.assertNotIn("no ranked", text.lower())
                if name == "docs/T4_ONLINE.md":
                    # T4 ranked: only where the T4 server opens it, on results the games proved
                    self.assertIn("ranked on a t4 server that opens it", text.lower())
                    self.assertIn("only results the two games proved count", text.lower())
                self.assertNotIn("casual quick match", text.lower())
                self.assertIn("T5DR", text)

    def test_lobby_walk_documents_result_rematch_and_game_handoff_limits(self):
        text = self.read("docs/T4_ONLINE.md")
        self.assertIn("challenge pop-up", text)
        self.assertIn("ping", text)
        self.assertIn("TEKKEN4_NET_AUTO_VS=1", text)
        self.assertIn("not verified", text)
        self.assertIn("rematch", text.lower())
        self.assertNotIn("The choice between lobby and direct IP is remembered", text)

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

    def test_ranked_docs_describe_t5dr_ladder_runtime_plates_and_game_handoff(self):
        text = self.read("docs/T4_ONLINE.md")
        self.assertIn("same rank names in the same order as T5DR", text)
        self.assertIn("bundled legacy fallback", text)
        self.assertIn("does not migrate the server's ladder", text)
        self.assertIn("player's own game data", text)
        self.assertNotIn("Tekken 7", text)
        assets = self.read("docs/T4_RANKED.md")
        for phrase in ("T5DR's rank names in T5DR's order", "T5DR adapter", "own drawn SVG badge",
                       "build/out_badges/tekken4_rank_badges.h", "runtime/tekken4_rank_badges.h",
                       "coordinator must copy", "handled separately"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, assets)


if __name__ == "__main__":
    unittest.main()
