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


class ResultPagePad(unittest.TestCase):
    """The pad on the online result page: A on Rematch works as soon as the row is shown (the real two-launcher
    run sometimes needed the same action sent directly)."""

    def setUp(self):
        self.a = Lobby()
        self.caps = dict(match_flow=True, lobby=True, rematch=False)
        self.a.snapshot.update(phase="playing", capabilities=self.caps)
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def focused(self):
        items = self.nav.items()
        return items[self.nav.focus_index(items)].get("id")

    def row(self, iid):
        return next(it for it in self.nav.items() if it.get("id") == iid)

    def result(self, **caps):
        self.caps.update(caps)
        self.a.snapshot.update(phase="result_sent", capabilities=dict(self.caps))
        self.nav.tick(.2)

    def test_focus_is_on_rematch_when_the_result_page_appears(self):
        self.assertEqual(self.focused(), "online_status")        # the playing page: nothing moved yet
        self.result(rematch=True)
        self.assertEqual(self.focused(), "rematch")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("online", "rematch")])

    def test_confirm_works_with_the_chat_rows_and_after_a_move_away_and_back(self):
        self.result(rematch=True)
        self.nav.act("down", device="xbox")
        self.assertEqual(self.focused(), "return_lobby")
        self.nav.act("up", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("online", "rematch")])

    def test_rematch_that_arrives_late_takes_an_untouched_focus(self):
        self.result()
        self.assertEqual(self.focused(), "return_lobby")
        self.caps.update(rematch=True)
        self.a.snapshot.update(capabilities=dict(self.caps))
        self.nav.tick(.2)
        self.assertEqual(self.focused(), "rematch")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("online", "rematch")])

    def test_rematch_that_arrives_late_leaves_a_focus_the_player_moved(self):
        self.result()
        self.nav.act("down", device="xbox")                       # onto the Eigener Launcher row
        before = self.focused()
        self.caps.update(rematch=True)
        self.a.snapshot.update(capabilities=dict(self.caps))
        self.nav.tick(.2)
        self.assertEqual(self.focused(), before)

    def test_rematch_row_looks_disabled_while_it_is_not_ready_and_a_press_is_not_lost_silently(self):
        self.result(rematch=True)
        self.a.snapshot["busy"] = True                            # another request of the launcher still runs
        row = self.row("rematch")
        self.assertTrue(row["disabled"])
        self.assertIsNone(row.get("run"))
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [])
        self.assertTrue(self.nav.pending_sound)                   # the error sound: the press was refused, not lost
        self.a.snapshot["busy"] = False
        self.assertFalse(self.row("rematch").get("disabled"))
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("online", "rematch")])

    def test_driver_not_ready_looks_disabled_too(self):
        self.result(rematch=True, rematch_ready=False)
        self.assertTrue(self.row("rematch")["disabled"])
        self.caps.update(rematch_ready=True)
        self.a.snapshot.update(capabilities=dict(self.caps))
        self.assertFalse(self.row("rematch").get("disabled"))

    def test_enter_and_mouse_reach_the_same_action(self):
        self.result(rematch=True)
        items = self.nav.items()
        self.nav.click_row(next(n for n, it in enumerate(items) if it["id"] == "rematch"))
        self.assertEqual(self.a.calls, [("online", "rematch")])

    def test_an_offer_popup_that_nobody_focused_does_not_take_the_press(self):
        self.result(rematch=True)
        self.a.snapshot["challenge"] = dict(id="c1", name="Third")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [("online", "rematch")])


if __name__ == "__main__":
    unittest.main()
