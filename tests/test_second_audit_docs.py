"""Owner checklist keeps active online tests separate from the short pad walk."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SecondAuditDocsTests(unittest.TestCase):
    def read(self, name):
        return " ".join((ROOT / name).read_text(encoding="utf-8").split())

    def test_short_pad_walk_has_time_budget_and_active_action_boundary(self):
        text = self.read("docs/HAND_CHECK.md")
        for phrase in ("20 Minuten", "0–2 Min.", "2–5 Min.", "5–9 Min.",
                       "9–14 Min.", "14–20 Min.", "keine Freigabe",
                       "Keine Anmeldung", "Ranked", "Quick Match",
                       "Check connection", "Start game", "Start/Options",
                       "Separat und ausdrücklich planen", "privaten Testserver",
                       "Rollback", "Alte Installation behalten"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_entry_points_link_checklist_and_links_resolve(self):
        for name in ("README.md", "docs/T5DR_ONLINE.md", "docs/HAND_CHECK.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            if name != "docs/HAND_CHECK.md":
                self.assertIn("HAND_CHECK.md", text)
            for target in re.findall(r"\]\(([^)]+\.md)\)", text):
                with self.subTest(source=name, target=target):
                    self.assertTrue((ROOT / name).parent.joinpath(target).is_file())

    def test_parity_guide_does_not_claim_optional_integration_was_verified(self):
        text = self.read("docs/T5DR_ONLINE.md")
        self.assertIn("intended counterparts", text)
        self.assertIn("not a fresh verification", text)
        self.assertIn("disallowed sources must be reported as skips", text)
        self.assertIn("not evidence that protocol integration passed", text)
        self.assertIn("do not establish translation quality", text)

    def test_audit_report_keeps_unexecuted_tests_and_native_risks_visible(self):
        text = self.read("docs/SECOND_AUDIT.md")
        for phrase in ("Blockiert vor dem ersten Test", "unittest discover -s tests",
                       "weder alte noch neue Tests", "T5_NET_*", "ungeprüft",
                       "final_diff_review"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
