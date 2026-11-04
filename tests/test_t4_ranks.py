"""Rating labels share the lobby ladder; explicit custom tables remain validated."""
from pathlib import Path
import unittest
from unittest import mock

from openrecomp.ranks import t4_rank_name
from openrecomp.vendor.t4lobby import ranks


class T4RankTests(unittest.TestCase):
    def test_default_labels_use_the_lobby_table_without_a_second_shipped_ladder(self):
        path = Path(__file__).parents[1] / "openrecomp" / "data" / "t4_ranks.json"
        self.assertFalse(path.exists())
        for rating in (-1, 0, 500, 1500, 1640, 2600, 100000):
            self.assertEqual(t4_rank_name(rating), ranks.name(ranks.tier_for(rating)))
        self.assertEqual(t4_rank_name(1640), "4th Dan")
        self.assertEqual(t4_rank_name(2600), "Tekken Lord (Kirin)")

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

    def test_default_labels_read_the_canonical_ladder_at_call_time(self):
        with mock.patch.object(ranks, "RANKS", [("Beginner", None), ("9th Kyu", None), ("8th Kyu", 900)]):
            self.assertEqual(t4_rank_name(900), "8th Kyu")


if __name__ == "__main__":
    unittest.main()
