"""The T4 ladder is pinned to the server's T5DR table; source checks never import it."""
import ast
import hashlib
import json
import os
from pathlib import Path
import unittest

from openrecomp.vendor.t4lobby import ranks


def source_table(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("RANKS", "BEGINNER", "FIRST_DAN", "OLD_NAMES"):
                    values[target.id] = ast.literal_eval(node.value)
        elif isinstance(node, ast.ClassDef) and node.name == "RankRules":
            values["rules"] = {row.target.id: ast.literal_eval(row.value) for row in node.body
                               if isinstance(row, ast.AnnAssign)}
    return values


class T4RankLadderTests(unittest.TestCase):
    def test_exact_37_names_order_and_rating_bands(self):
        # Fingerprint of RANKS from both supplied open-source lobby tables, 2026-11-04.
        data = json.dumps(ranks.RANKS, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "21f3ab3017f21b17e95dffd6f75672b2d4c6b0e245df5796c48e39be1f7a5f7b")
        self.assertEqual(len(ranks.RANKS), 37)
        self.assertEqual(ranks.NAMES, [name for name, _ in ranks.RANKS])

    def check_source(self, variable):
        path = os.environ.get(variable)
        if not path:
            self.skipTest("set " + variable + " for a read-only source parity check")
        source = source_table(path)
        self.assertEqual(ranks.RANKS, source["RANKS"])
        self.assertEqual(ranks.BEGINNER, source["BEGINNER"])
        self.assertEqual(ranks.FIRST_DAN, source["FIRST_DAN"])
        self.assertEqual(ranks.OLD_NAMES, source["OLD_NAMES"])
        self.assertEqual(vars(ranks.RankRules()), source["rules"])

    def test_table_and_rules_equal_t4_server(self):
        self.check_source("T4_SERVER_RANKS")

    def test_table_and_rules_equal_t5dr_lobby(self):
        self.check_source("T5DR_LOBBY_RANKS")

    def test_every_rating_boundary_and_name_maps_to_its_tier(self):
        self.assertEqual(ranks.tier_for(-10000), 1)
        for tier, (name, boundary) in enumerate(ranks.RANKS):
            with self.subTest(tier=tier):
                self.assertEqual(ranks.index(name), tier)
                self.assertEqual(ranks.display_name(dict(tier=tier, rank="old label")), name)
                if boundary is not None:
                    self.assertEqual(ranks.tier_for(boundary), tier)
                    self.assertEqual(ranks.tier_for(boundary - 0.01), tier - 1)
        self.assertEqual(ranks.index("kouryu"), 35)
        self.assertEqual(ranks.index("Kirin"), 36)
        self.assertEqual(ranks.display_name(dict(rank="Kouryu")), "Tekken Lord (Kouryu)")
        self.assertIsNone(ranks.index(37))

    def test_placement_promotion_shield_and_dan_floor(self):
        state = ranks.RankState()
        for _ in range(4):
            state, event = ranks.after_match(state, 2600)
            self.assertEqual((state.tier, event), (0, None))
        state, event = ranks.after_match(state, 2600)
        self.assertEqual((state.tier, state.floor, event), (12, 12, "placed"))
        state, event = ranks.after_match(state, 2600)
        self.assertEqual((state.tier, event), (36, "promoted"))
        for _ in range(3):
            state, event = ranks.after_match(state, 1000)
            self.assertEqual((state.tier, event), (36, None))
        state, event = ranks.after_match(state, 1000)
        self.assertEqual((state.tier, event), (10, "demoted"))

    def test_groups_cover_each_tier_once(self):
        self.assertEqual([tier for low, high, _ in ranks.GROUPS for tier in range(low, high + 1)],
                         list(range(37)))


if __name__ == "__main__":
    unittest.main()
