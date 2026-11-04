"""Cancellation races exercise the production worker with inert local clients only."""
import os
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t5_online import Online
from test_online_adapter import Subject, runtime_modules
from test_shared_lobby import Playable
from test_t4_online import Subject as T4Subject, ticket


class OnlineAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory,
                                          OPENRECOMP_HOME=self.directory))
        self.enterContext(mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))

    def login(self, kind=Subject):
        adapter = kind(self.directory)
        self.addCleanup(adapter.online_close)
        adapter.set_text_value("online_name", "FakePlayer")
        adapter.online_action("login_guest")
        adapter.online_poll()
        self.assertEqual(adapter.online_state()["phase"], "logged_in")
        adapter._online_submit = Online._online_submit.__get__(adapter)
        return adapter, adapter.clients[-1]

    def settle(self, adapter, client):
        """Every worker of the cancelled request and of the leave has finished and been read."""
        for _ in range(300):
            adapter.online_poll()
            if not adapter._online_busy and not any(
                    t.name == "openrecomp-lobby" and t.is_alive() for t in threading.enumerate()):
                adapter.online_poll()
                return
            threading.Event().wait(0.01)
        self.fail("workers did not finish")

    def finish(self, adapter):
        result = adapter._online_results.get(timeout=2)
        adapter._online_results.put(result)
        adapter.online_poll()

    def test_cancel_during_process_probe_never_sends_queue_request(self):
        for kind in (Subject, T4Subject):
            with self.subTest(kind=kind.__name__):
                adapter, client = self.login(kind)
                entered, release = threading.Event(), threading.Event()

                def probe():
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test probe was not released")
                    return ""

                adapter._online_game_check = probe
                adapter.online_action("search_casual")
                self.assertTrue(entered.wait(1))
                try:
                    adapter.online_action("cancel")
                    self.assertEqual(adapter.online_state()["phase"], "logged_in")
                finally:
                    release.set()
                    self.settle(adapter, client)
                # Cancelled before the search was sent: it never is; the player stays logged in.
                self.assertFalse(any(isinstance(call, tuple) and call[0] == "quick" for call in client.calls))
                self.assertFalse(client.closed.is_set())
                self.assertEqual(adapter.online_state()["phase"], "logged_in")
                self.assertEqual(adapter.online_state()["message"], "@online.cancelled")

    def test_cancel_disconnects_before_blocked_queue_reply_and_discards_offer(self):
        adapter, client = self.login(T4Subject)
        entered, release = threading.Event(), threading.Event()

        def queue_request(_fighter):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test queue was not released")
            client.events.put(dict(t="match_found", match="late"))

        client.quick_match = queue_request
        adapter.online_action("search_casual")
        self.assertTrue(entered.wait(1))
        try:
            adapter.online_action("cancel")
            self.assertEqual(adapter.online_state()["phase"], "logged_in")
        finally:
            release.set()
            self.settle(adapter, client)
        # The search was already on its way: the leave goes out after it, and the offer the server made before
        # the leave arrived is declined -- never shown, never started; the player stays logged in.
        self.assertEqual(adapter.online_state()["phase"], "logged_in")
        self.assertFalse(client.closed.is_set())
        self.assertIn("cancel", client.calls)
        for _ in range(100):
            if ("ready", False) in client.calls:
                break
            threading.Event().wait(0.01)
        self.assertIn(("ready", False), client.calls)
        self.assertEqual(adapter.starts, [])
        self.assertNotIn(("ready", True), client.calls)

    def test_logout_during_lobby_probe_does_not_send_match_request(self):
        for action, prefix in (("challenge:other", "challenge"), ("create_room", "create"),
                               ("join_room:open", "join"), ("accept_challenge", "answer")):
            with self.subTest(action=action):
                adapter, client = self.login(Playable)
                adapter._online_players = [dict(id="other")]
                adapter._online_rooms = [dict(id="open")]
                adapter._online_challenge = dict(id="incoming")
                entered, release = threading.Event(), threading.Event()

                def probe():
                    entered.set()
                    if not release.wait(2):
                        raise RuntimeError("test probe was not released")
                    return ""

                adapter._online_game_check = probe
                adapter.online_action(action)
                self.assertTrue(entered.wait(1))
                try:
                    adapter.online_action("logout")
                    self.assertTrue(client.closed.wait(1))
                finally:
                    release.set()
                    self.finish(adapter)
                self.assertFalse(any(isinstance(call, tuple) and call[0] == prefix for call in client.calls))

    def test_cancel_match_during_ready_probe_never_sends_ready(self):
        adapter, client = self.login(T4Subject)
        client.events.put(dict(t="match_found", match="pending"))
        adapter.online_poll()
        entered, release = threading.Event(), threading.Event()

        def probe():
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test probe was not released")
            return ""

        adapter._online_game_check = probe
        adapter.online_action("start_match")
        self.assertTrue(entered.wait(1))
        try:
            adapter.online_action("cancel_match")
            self.assertEqual(adapter.online_state()["phase"], "logged_in")
        finally:
            release.set()
            self.settle(adapter, client)
        self.assertNotIn(("ready", True), client.calls)
        self.assertEqual(adapter.starts, [])
        self.assertFalse(client.closed.is_set())
        self.assertEqual(adapter.online_state()["phase"], "logged_in")

    def test_cached_client_from_another_install_is_refused_before_import(self):
        adapter = Subject(self.directory)
        del adapter._online_api
        runtime_modules(self.directory, "t5lobby", {})
        foreign = SimpleNamespace(__file__=os.path.join(self.directory, "other", "t5lobby", "__init__.py"))
        with mock.patch.dict(sys.modules, t5lobby=foreign), mock.patch(
                "openrecomp.adapters.t5_online.importlib.import_module") as load:
            with self.assertRaisesRegex(RuntimeError, "@online.client_missing"):
                adapter._online_modules()
            load.assert_not_called()

    def test_delayed_cancelled_launch_cannot_stop_a_newer_owned_game(self):
        adapter, client = self.login(T4Subject)
        client.events.put(dict(t="match_found", match="fake-match"))
        adapter.online_poll()
        adapter._online_authorized = True
        adapter._online_phase = "starting"
        submitted = []
        adapter._online_submit = lambda action, work: submitted.append(work)
        adapter._online_event(dict(t="match_start", ticket=ticket()))
        self.assertEqual(len(submitted), 1)
        adapter.online_close()
        stops = []
        newer = SimpleNamespace(proc=SimpleNamespace(poll=lambda: None), stop=lambda: stops.append("newer"))
        adapter._online_owned_run = newer
        adapter._online_evidence = dict(frames=99)
        with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
            submitted[0]()
        self.assertEqual(stops, [])
        self.assertIs(adapter._online_owned_run, newer)
        self.assertEqual(adapter._online_evidence, dict(frames=99))
        adapter._online_owned_run = None

    def test_malformed_lobby_and_match_events_do_not_crash_poll(self):
        adapter, client = self.login(Playable)
        client.me = ["invalid"]
        client.events.put(None)
        client.events.put(dict(t="lobby_state", players=None, rooms=42))
        client.events.put(dict(t="error", code=[]))
        adapter.online_poll()
        self.assertEqual(adapter.online_state()["players"], [])
        self.assertEqual(adapter.online_state()["rooms"], [])
        self.assertEqual(adapter.online_state()["message"], "@online.refused")
        adapter, client = self.login(T4Subject)
        client.events.put(dict(t="match_found", opponent="invalid", ping=42))
        client.events.put(dict(t="match_reveal", opponent=["invalid"]))
        adapter.online_poll()
        self.assertEqual(adapter.online_state()["match"],
                         dict(opponent="", ping=None, my_ready=False, peer_ready=False))

    def test_session_save_preserves_malformed_settings_and_warns(self):
        for original in ('{"settings":', '[]', '{"sessions": ["preserve"]}'):
            with self.subTest(original=original):
                adapter = Subject(self.directory)
                self.addCleanup(adapter.online_close)
                with open(adapter.online_cfg_path(), "w", encoding="utf-8") as stream:
                    stream.write(original)
                adapter.set_online_text_value("online_password", "fake-password")
                adapter.online_action("login_account")
                adapter.online_poll()
                self.assertEqual(adapter.online_state()["phase"], "logged_in")
                self.assertEqual(adapter.online_state()["message"], "@online.save_failed")
                with open(adapter.online_cfg_path(), encoding="utf-8") as stream:
                    self.assertEqual(stream.read(), original)


if __name__ == "__main__":
    unittest.main()
