"""T4 borrows only a known T5DR adapter's cached plates; fixtures contain no game art."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t4 import T4
from openrecomp.adapters.t5dr import T5DR
from openrecomp.vendor.t4lobby import ranks


ROOT = Path(__file__).resolve().parents[1]
BADGES = ROOT / "openrecomp" / "ui" / "assets" / "ranks"


class T4RankPlateTests(unittest.TestCase):
    def setUp(self):
        home = ROOT / "build" / "tmp-home"
        home.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=home)
        self.addCleanup(self.directory.cleanup)
        self.a = T4.__new__(T4)
        self.a.m = dict(id="t4")
        self.a.problem = ""
        self.t5 = T5DR.__new__(T5DR)
        self.t5.m = dict(id="t5dr")
        self.t5.problem = ""
        self.t5.s = SimpleNamespace(out_dir=self.directory.name)

    def plate(self, tier=13):
        path = Path(self.directory.name) / "cache" / "ranks" / ("rank_%02d.png" % tier)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake cache marker, not an image")
        return os.fspath(path)

    def test_known_t5dr_plate_is_exactly_the_plate_its_own_pages_use(self):
        expected = self.plate()
        self.a.account_peers = (self.t5,)
        self.assertEqual(self.t5.rank_plate(13), expected)
        with mock.patch("os.path.isfile", side_effect=AssertionError("cached plate asked for disk again")):
            self.assertEqual(self.a.rank_plate(13), self.t5.rank_plate(13))

    def test_missing_t5dr_plate_uses_our_drawn_badge(self):
        self.a.account_peers = (self.t5,)
        self.assertEqual(self.t5.rank_plate(13), "")
        self.assertEqual(self.a.rank_plate(13), os.fspath(BADGES / "t4_rank_13.svg"))

    def test_no_known_t5dr_uses_our_drawn_badge(self):
        self.assertEqual(self.a.rank_plate(13), os.fspath(BADGES / "t4_rank_13.svg"))

    def test_other_game_and_missing_t5dr_do_not_supply_plates(self):
        other = mock.Mock(m=dict(id="other"))
        missing = Adapter(dict(id="t5dr"))
        missing.rank_plate = mock.Mock(return_value="unexpected")
        self.a.account_peers = (other, missing)
        self.assertEqual(self.a.rank_plate(13), os.fspath(BADGES / "t4_rank_13.svg"))
        other.rank_plate.assert_not_called()
        missing.rank_plate.assert_not_called()

    def test_invalid_tiers_never_reach_the_borrowed_adapter(self):
        self.t5.rank_plate = mock.Mock(return_value="unexpected")
        self.a.account_peers = (self.t5,)
        for tier in (None, True, False, -1, len(ranks.NAMES), 64, "13", 13.0):
            with self.subTest(tier=tier):
                self.assertEqual(self.a.rank_plate(tier), "")
        self.t5.rank_plate.assert_not_called()

    def test_replaced_peers_do_not_leave_a_previous_installs_plate(self):
        expected = self.plate()
        self.a.account_peers = (self.t5,)
        self.assertEqual(self.a.rank_plate(13), expected)
        self.a.account_peers = ()
        self.assertEqual(self.a.rank_plate(13), os.fspath(BADGES / "t4_rank_13.svg"))

    def test_load_games_wires_the_known_t5dr_adapter_for_t4(self):
        from openrecomp import app
        manifests = [dict(id="t4", short="T4", accent="#fff"),
                     dict(id="t5dr", short="T5DR", accent="#fff")]
        with mock.patch.object(app.mf, "load_all", return_value=(manifests, [])), \
                mock.patch.object(app.adapters, "make", side_effect=(self.a, self.t5)):
            games, problems = app.load_games({})
        self.assertEqual(problems, [])
        self.assertEqual(self.a.account_peers, (self.t5,))
        self.assertEqual(self.t5.account_peers, (self.a,))
        self.assertEqual([game.id for game in games], ["t4", "t5dr"])


if __name__ == "__main__":
    unittest.main()
