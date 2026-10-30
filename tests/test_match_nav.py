"""Match result and rematch controls never launch a game from Nav."""
import unittest

from openrecomp.nav import Game, Nav
from test_online_nav import Lobby, OnlineNavigation


class MatchNavigation(unittest.TestCase):
    choose = OnlineNavigation.choose

    def setUp(self):
        self.a = Lobby()
        self.a.snapshot.update(phase="result_sent", capabilities=dict(match_flow=True, rematch=True))
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def test_rematch_and_lobby_are_pad_actions(self):
        self.choose("rematch")
        self.choose("return_lobby")
        self.assertEqual(self.a.calls, [("online", "rematch"), ("online", "return_lobby")])

    def test_unavailable_rematch_is_hidden(self):
        self.a.snapshot["capabilities"]["rematch"] = False
        self.assertNotIn("rematch", [item.get("id") for item in self.nav.items()])

    def test_dry_rematch_never_calls_adapter(self):
        self.nav.dry = True
        self.choose("rematch")
        self.choose("return_lobby")
        self.nav.tick(.016)
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.a.polls, 0)


if __name__ == "__main__":
    unittest.main()
