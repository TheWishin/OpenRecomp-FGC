"""Owner (again, strongly): "make sure you are NOT logged out when you cancel the search etc." Every event that used to
log a player out of the lobby, with fakes only (no network, no game)."""
import os
import tempfile
import threading
import unittest
from unittest import mock

from openrecomp import manifest as mf
from openrecomp.adapters.t5_online import Online
from openrecomp.nav import Game, Nav
from test_online_adapter import LobbyError, Subject
from test_t4_online import Subject as T4Subject


def wait_for(predicate, poll=None, tries=300):
    for _ in range(tries):
        if poll:
            poll()
        if predicate():
            return True
        threading.Event().wait(0.01)
    return False


class StayLoggedInTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory, OPENRECOMP_HOME=self.directory))
        self.enterContext(mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))

    def adapter(self, kind=Subject):
        a = kind(self.directory)
        self.addCleanup(a.online_close)
        return a

    def login(self, a, account=False):
        a.set_text_value("online_name", "PadUser")
        if account:
            a.set_text_value("online_password", "fake-password")
        a.online_action("login_account" if account else "login_guest")
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "logged_in")
        return a.clients[-1]

    # ------------------------------------------------------------ a connection the client could not resume
    def test_lost_connection_logs_the_guest_in_again_with_the_same_name(self):
        a = self.adapter()
        client = self.login(a)
        client.events.put(dict(t="disconnected", reason="the lobby server closed the connection"))
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "connecting")
        self.assertEqual(a.online_state()["message"], "@online.reconnecting")
        a.online_poll()
        self.assertEqual(len(a.clients), 1)                  # not at once: RELOGIN_FIRST
        a._online_relogin["at"] = 0
        a.online_poll()
        a.online_poll()
        state = a.online_state()
        self.assertEqual(state["phase"], "logged_in")
        self.assertEqual(state["message"], "@online.reconnected")
        self.assertEqual(a.clients[-1].calls[-1], ("guest", "PadUser"))
        self.assertIsNone(a._online_relogin)

    def test_lost_connection_logs_the_account_in_again_with_its_remembered_login_never_the_password(self):
        a = self.adapter()
        client = self.login(a, account=True)
        client.events.put(dict(t="disconnected", reason="server restart"))
        a.online_poll()
        a._online_relogin["at"] = 0
        a.online_poll()
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertTrue(a.online_state()["account"])
        self.assertEqual(a.clients[-1].calls[-1], ("session", "fake-remembered-session"))
        self.assertFalse(any(isinstance(c, tuple) and c[0] == "account" for c in a.clients[-1].calls))

    def test_relogin_retries_while_the_lobby_is_away_and_ends_on_an_expired_login(self):
        a = self.adapter()
        client = self.login(a, account=True)
        client.events.put(dict(t="disconnected"))
        a.online_poll()
        refusals = [OSError("refused"), LobbyError("busy")]

        def make_client(**kwargs):
            c = Subject.make_client(a, **kwargs)
            if refusals:
                c.connect = mock.Mock(side_effect=refusals.pop(0))
            else:
                c.login_session = mock.Mock(side_effect=LobbyError("auth_failed"))
            return c
        a._online_api["client"] = make_client
        for expected in ("connecting", "connecting"):
            a._online_relogin["at"] = 0
            a.online_poll()
            a.online_poll()
            self.assertEqual(a.online_state()["phase"], expected)
            self.assertEqual(a.online_state()["message"], "@online.reconnecting")
        a._online_relogin["at"] = 0
        a.online_poll()
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "error")
        self.assertEqual(a.online_state()["message"], "@online.saved_expired")
        self.assertIsNone(a._online_relogin)
        count = len(a.clients)
        for _ in range(3):
            a.online_poll()
        self.assertEqual(len(a.clients), count)

    def test_no_relogin_after_a_kick_a_logout_or_a_cancel(self):
        for how in ("kicked", "logout", "cancel"):
            with self.subTest(how=how):
                a = self.adapter()
                client = self.login(a, account=True)
                if how == "kicked":
                    client.events.put(dict(t="kicked", reason="logged in from another place"))
                    client.events.put(dict(t="disconnected"))
                    a.online_poll()
                    self.assertEqual(a.online_state()["message"], "@online.kicked")
                else:
                    client.events.put(dict(t="disconnected"))
                    a.online_poll()
                    a.online_action(how)
                self.assertIsNone(a._online_relogin)
                for _ in range(3):
                    a.online_poll()
                self.assertEqual(len(a.clients), 1)

    def test_relogin_gives_up_after_its_time(self):
        a = self.adapter()
        client = self.login(a)
        client.events.put(dict(t="disconnected"))
        a.online_poll()
        a._online_relogin["until"] = 0
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "offline")
        self.assertEqual(a.online_state()["message"], "@online.disconnected")

    # ------------------------------------------------------------ the client resumed the same session
    def test_resumed_session_searches_again_the_server_dropped_the_queue(self):
        a = self.adapter()
        client = self.login(a)
        a.online_action("search_casual")
        a.online_poll()
        self.assertEqual(client.calls.count(("quick", "random")), 1)
        client.events.put(dict(t="reconnecting", reason="cut"))
        client.events.put(dict(t="reconnected"))
        a.online_poll()
        a.online_poll()
        self.assertEqual(client.calls.count(("quick", "random")), 2)
        self.assertEqual(a.online_state()["phase"], "searching")
        self.assertIs(a._online_client, client)

    def test_resumed_session_ends_a_ready_check_and_a_room(self):
        a = self.adapter(T4Subject)
        client = self.login(a)
        client.events.put(dict(t="match_found", match="gone"))
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "matched")
        client.events.put(dict(t="reconnected"))
        a.online_poll()
        self.assertTrue(wait_for(lambda: not a._online_busy, a.online_poll))
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertEqual(a.online_state()["message"], "@online.reconnected")
        self.assertFalse(client.closed.is_set())

    # ------------------------------------------------------------ fast and late cancels
    def test_many_fast_search_and_cancel_presses_stay_one_session(self):
        a = self.adapter()
        client = self.login(a)
        a._online_submit = Online._online_submit.__get__(a)
        for _ in range(10):
            a.online_action("search_casual")
            a.online_action("cancel")
            a.online_poll()
        self.assertTrue(wait_for(lambda: not a._online_busy, a.online_poll))
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertEqual(len(a.clients), 1)
        self.assertFalse(client.closed.is_set())
        # every queue request that went out was followed by a leave
        last_quick = max((i for i, c in enumerate(client.calls) if c == ("quick", "random")), default=-1)
        self.assertGreater(client.calls.index("cancel", last_quick + 1 if last_quick >= 0 else 0), last_quick)

    def test_rate_limited_leave_is_asked_again_never_left_queued(self):
        # Local lobby run: fast search/cancel presses met the lobby's request limit; the refused leave left the
        # player queued behind "Search stopped", and the next player's search was matched with them.
        a = self.adapter(T4Subject)
        client = self.login(a)
        a.online_action("search_casual")
        a.online_poll()
        answers = [LobbyError("rate_limited"), LobbyError("rate_limited")]

        def cancel_queue():
            client.calls.append("cancel")
            if answers:
                raise answers.pop(0)
        client.cancel_queue = cancel_queue
        with mock.patch.object(type(a), "UNQUEUE_WAIT", 0):
            a.online_action("cancel")
            client.events.put(dict(t="match_found", match="while-leaving"))
            a.online_poll()
            a.online_poll()
        self.assertEqual(client.calls.count("cancel"), 3)
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertEqual(a.online_state()["message"], "@online.cancelled")
        self.assertIn(("ready", False), client.calls)          # the offer made before the leave got through
        self.assertFalse(a._online_leaving)
        self.assertFalse(client.closed.is_set())

    def test_offer_that_crossed_the_leave_is_declined_not_shown(self):
        a = self.adapter(T4Subject)
        client = self.login(a)
        a.online_action("search_casual")
        a.online_poll()
        block = threading.Event()
        client.cancel_queue = lambda: (block.wait(2), client.calls.append("cancel"))
        a._online_submit = Online._online_submit.__get__(a)
        a.online_action("cancel")
        client.events.put(dict(t="match_found", match="crossed"))
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertTrue(wait_for(lambda: ("ready", False) in client.calls))
        block.set()
        self.assertTrue(wait_for(lambda: not a._online_busy, a.online_poll))
        self.assertEqual(a.online_state()["phase"], "logged_in")
        client.events.put(dict(t="match_found", match="new"))      # after the leave: a real new offer
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "matched")

    def test_cancel_after_start_leaves_the_match_and_stays_logged_in(self):
        a = self.adapter(T4Subject)
        client = self.login(a)
        client.leave_match = lambda mid=None: client.calls.append(("leave_match", mid))
        client.events.put(dict(t="match_found", match="m1"))
        a.online_poll()
        a.online_action("start_match")
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "starting")
        a.online_action("cancel_match")
        self.assertTrue(wait_for(lambda: not a._online_busy, a.online_poll))
        self.assertIn(("leave_match", "m1"), client.calls)
        self.assertIn("cancel", client.calls)
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertFalse(client.closed.is_set())

    # ------------------------------------------------------------ remembered login when the Online section shows
    def test_online_shown_logs_in_with_the_remembered_login_once(self):
        a = self.adapter()
        self.login(a, account=True)
        a.online_close()
        fresh = self.adapter()                           # the launcher started again
        self.assertTrue(fresh.online_state()["saved_available"])
        fresh.online_shown()
        fresh.online_poll()
        self.assertEqual(fresh.online_state()["phase"], "logged_in")
        self.assertEqual(fresh.clients[-1].calls[-1], ("session", "fake-remembered-session"))
        fresh.online_action("logout")
        fresh.online_shown()
        fresh.online_poll()
        self.assertEqual(fresh.online_state()["phase"], "offline")
        self.assertEqual(len(fresh.clients), 1)

    def test_online_shown_never_logs_in_without_a_saved_login_or_a_build(self):
        a = self.adapter()
        a.online_shown()
        a.online_poll()
        self.assertEqual(a.clients, [])
        self.login(a, account=True)
        a.online_close()
        fresh = self.adapter()
        fresh.ready = lambda: False
        fresh.online_shown()
        self.assertEqual(fresh.clients, [])

    def test_nav_tells_the_adapter_when_its_online_section_is_shown(self):
        ms, _ = mf.load_all([mf.BUILTIN_DIR])
        m = next(x for x in ms if x["id"] == "t5dr")
        a = self.adapter()                               # a fake install: nothing is imported from a real one
        a.online_shown = mock.Mock()
        a.found = lambda: True
        nav = Nav([Game(m, a)], language="en")
        nav.screen = "hub"
        nav.sec[m["id"]] = "online"
        nav.items()
        a.online_shown.assert_called()
        a.online_shown.reset_mock()
        nav.dry = True
        nav.items()
        a.online_shown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
