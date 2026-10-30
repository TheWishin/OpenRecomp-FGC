"""Rank labels are optional text from a maintainer-controlled table."""
import json
from pathlib import Path
import unittest
from unittest import mock

from openrecomp.ranks import t4_rank_name


class T4RankTests(unittest.TestCase):
    def test_shipped_table_has_blank_names_and_shows_no_rank(self):
        path = Path(__file__).parents[1] / "openrecomp" / "data" / "t4_ranks.json"
        table = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(table["ranks"])
        self.assertTrue(all(row["name"] == "" for row in table["ranks"]))
        self.assertNotIn("icon", table)
        for rating in (-1, 0, 500, 1500, 100000):
            self.assertEqual(t4_rank_name(rating), "")

    def test_maintainer_filled_boundaries_select_text_including_exact_boundary(self):
        table = dict(ranks=[dict(minimum_rating=0, name="First label"),
                            dict(minimum_rating=100, name="Second label"),
                            dict(minimum_rating=200, name="")])
        for rating, expected in ((-1, ""), (0, "First label"), (99, "First label"),
                                 (100, "Second label"), (199, "Second label"), (200, "")):
            self.assertEqual(t4_rank_name(rating, table), expected)

    def test_invalid_ratings_or_table_never_display_a_rank(self):
        valid = dict(ranks=[dict(minimum_rating=0, name="Label")])
        for rating in (None, "100", True, float("nan"), float("inf")):
            self.assertEqual(t4_rank_name(rating, valid), "")
        for table in ({}, [], dict(ranks=None), dict(ranks=[None]),
                      dict(ranks=[dict(minimum_rating="0", name="Label")]),
                      dict(ranks=[dict(minimum_rating=0, name=1)]),
                      dict(ranks=[dict(minimum_rating=0, name="Label"),
                                  dict(minimum_rating=0, name="Duplicate")])):
            self.assertEqual(t4_rank_name(100, table), "")

    def test_missing_or_malformed_data_hides_ranks(self):
        for error in (OSError(), ValueError()):
            with mock.patch.object(Path, "read_text", side_effect=error):
                self.assertEqual(t4_rank_name(100), "")


if __name__ == "__main__":
    unittest.main()
