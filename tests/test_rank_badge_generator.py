"""Regenerating a shorter ladder removes old badges instead of shipping stale ranks."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from openrecomp.vendor.t4lobby import ranks


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

    def test_regeneration_replaces_the_previous_47_badge_ladder(self):
        for tier in range(47):
            (self.folder / tool.file_name(tier)).write_text("old badge", encoding="utf-8")
        self.assertEqual(tool.write_svgs(self.folder), 37)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()),
                         ["t4_rank_%02d.svg" % tier for tier in range(37)])
        self.assertEqual(tool.check(self.folder), [])

    def test_committed_badges_are_the_37_current_lobby_ranks(self):
        self.assertEqual(len(ranks.RANKS), 37)
        self.assertEqual(tool.check(), [])
        for tier, (name, _) in enumerate(ranks.RANKS):
            with self.subTest(tier=tier):
                path = Path(tool.OUT) / tool.file_name(tier)
                text = path.read_text(encoding="utf-8")
                self.assertIn("rank badge %d: %s (" % (tier, name), text)
                root = ET.fromstring(text)
                label = " ".join(element.text for element in
                                 root.findall("{http://www.w3.org/2000/svg}text"))
                self.assertEqual(label, name.upper())

    def test_header_contains_every_tier_in_the_ladders_order(self):
        path = self.folder / "runtime" / "tekken4_rank_badges.h"
        tool.header(path)
        text = path.read_text(encoding="utf-8")
        rows = [line.split('"')[1] for line in text.splitlines() if line.startswith('    {"')]
        self.assertEqual(rows, [name for name, _ in ranks.RANKS])
        self.assertEqual(len(rows), 37)
        self.assertIn("constexpr int kCount = 37;", text)


if __name__ == "__main__":
    unittest.main()
