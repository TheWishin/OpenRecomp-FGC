"""Only a confirmed rank increase for the same account shows a finite cue."""
import unittest

from openrecomp.nav import Game, Nav
from test_online_nav import Lobby


class RankCue(unittest.TestCase):
    def setUp(self):
        self.adapter = Lobby()
        self.adapter.snapshot.update(phase="logged_in", account=True, name="Me",
                                     me=dict(id="me", name="Me", tier=2, rank="2nd Dan"))
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")

    def update(self, **fields):
        self.adapter.pending = fields
        self.assertTrue(self.nav.poll_online())

    def test_confirmed_increase_projects_rank_and_expires_without_focus_change(self):
        focus = dict(self.nav.focus)
        self.update(me=dict(id="me", name="Me", tier=3, rank="3rd Dan"))
        cue = self.nav.view().get("promotion", {})
        self.assertEqual(cue.get("rank"), "3rd Dan")
        self.assertEqual(cue.get("label"), "Rank up")
        self.nav.tick(5.1)
        self.assertEqual(self.nav.view().get("promotion", {}), {})
        self.assertEqual(self.nav.focus, focus)

    def test_login_account_switch_demotion_and_malformed_tiers_do_not_celebrate(self):
        for me, account in ((dict(id="other", name="Other", tier=3), True),
                            (dict(id="me", name="Me", tier=1), True),
                            (dict(id="me", name="Me", tier="3"), True),
                            (dict(id="me", name="Me", tier=True), True),
                            (dict(id="me", name="Me", tier=3), False)):
            with self.subTest(me=me, account=account):
                self.setUp()
                self.update(me=me, account=account)
                self.assertEqual(self.nav.view().get("promotion", {}), {})

    def test_repeated_poll_does_not_extend_the_banner(self):
        self.update(me=dict(id="me", name="Me", tier=3, rank="3rd Dan"))
        self.nav.tick(3)
        self.update(message="@online.logged_in")
        self.nav.tick(2.1)
        self.assertEqual(self.nav.view().get("promotion", {}), {})

    def test_account_switch_clears_an_existing_banner(self):
        self.update(me=dict(id="me", name="Me", tier=3, rank="3rd Dan"))
        self.assertTrue(self.nav.view().get("promotion"))
        self.update(me=dict(id="other", name="Other", tier=4, rank="4th Dan"))
        self.assertEqual(self.nav.view().get("promotion", {}), {})


if __name__ == "__main__":
    unittest.main()
