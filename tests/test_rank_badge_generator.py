"""Regenerating a shorter ladder removes old badges instead of shipping stale ranks."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rank_badge_generator", ROOT / "tools" / "make_rank_badges.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class BadgeGeneratorTests(unittest.TestCase):
    def setUp(self):
        home = ROOT / "build" / "tmp-home"
        home.mkdir(parents=True, exist_ok=True)
        directory = self.enterContext(tempfile.TemporaryDirectory(dir=home))
        self.folder = Path(directory)

    def test_check_reports_badges_outside_the_ladder(self):
        tool.write_svgs(self.folder)
        stale = self.folder / "t4_rank_99.svg"
        stale.write_text("old rank", encoding="utf-8")
        self.assertEqual(tool.check(self.folder), [stale.name])

    def test_regeneration_removes_only_stale_generated_badges(self):
        tool.write_svgs(self.folder)
        stale = self.folder / "t4_rank_99.svg"
        stale.write_text("old rank", encoding="utf-8")
        other = self.folder / "review.svg"
        other.write_text("keep", encoding="utf-8")
        tool.write_svgs(self.folder)
        self.assertFalse(stale.exists())
        self.assertEqual(other.read_text(encoding="utf-8"), "keep")
        self.assertEqual(tool.check(self.folder), [])

    def test_header_contains_every_tier_in_the_ladders_order(self):
        path = self.folder / "tekken4_rank_badges.h"
        tool.header(path)
        text = path.read_text(encoding="utf-8")
        rows = [line.split('"')[1] for line in text.splitlines() if line.startswith('    {"')]
        self.assertEqual(rows, tool.NAMES)
        self.assertIn("constexpr int kCount = %d;" % len(tool.NAMES), text)


if __name__ == "__main__":
    unittest.main()
