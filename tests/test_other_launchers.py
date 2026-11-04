"""Owner: "also with the old launcher open at the same time? it should say: hey, you are logged in, but you can really
only play in one launcher." Another launcher of the same game on this PC (the game's own launcher, a second OpenRecomp
window): a clear note, no automatic login against it, no logout ping-pong. Also: a library change (add/remove a game,
a folder chosen) keeps every unchanged game logged in. Fakes only, plus real processes and lock files for the detector."""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from openrecomp.adapters import other_launchers
from openrecomp.nav import Game, Nav
from test_online_adapter import Subject
from test_online_nav import Lobby
from test_online_page import lobby_snapshot


class FakeDetector:
    def __init__(self):
        self.enabled = True
        self.found = dict(native=False, window=False, online=False)
        self.presence = []
        self.refreshed = 0

    def others(self, game):
        return dict(self.found)

    def refresh(self):
        self.refreshed += 1

    def online(self, game, on):
        self.presence.append((game, on))


class T5Subject(Subject):
    other_launcher_game = "t5dr"


def wait_for(predicate, tries=500):
    for _ in range(tries):
        if predicate():
            return True
        threading.Event().wait(0.01)
    return False


# ---------------------------------------------------------------- the detector itself (real processes, real locks)
class DetectorTests(unittest.TestCase):
    def test_command_lines_name_the_launcher_scripts(self):
        lines = [(1, r'"C:\Games\T5DR-Online-1.2.0\python\pythonw.exe" "C:\Games\T5DR-Online-1.2.0\launcher\t5dr_launcher.pyw"'),
                 (2, r'"C:\T4\python\pythonw.exe" -I "launcher\t4_launcher.pyw"'),
                 (3, r'"C:\OpenRecomp\portable\pythonw.exe" -B -m openrecomp')]
        self.assertTrue(other_launchers.native_running("t5dr", lines))
        self.assertTrue(other_launchers.native_running("t4", lines))
        self.assertFalse(other_launchers.native_running("t5dr", lines[1:]))
        self.assertFalse(other_launchers.native_running("t4", [lines[0], lines[2]]))
        self.assertFalse(other_launchers.native_running("fake", lines))

    @unittest.skipUnless(os.name == "nt", "process command lines are read on Windows")
    def test_a_real_process_running_the_t5dr_launcher_script_is_found(self):
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        script = os.path.join(folder, "t5dr_launcher.pyw")
        with open(script, "w", encoding="utf-8") as stream:
            stream.write("import sys\nsys.stdin.readline()\n")
        # the real process list, only this test's own process (another launcher may really be open on this PC)
        detector = other_launchers.Detector(directory=os.path.join(folder, "locks"), scan=lambda: [
            line for line in other_launchers._command_lines() if folder.lower() in line[1].lower()])
        detector.enable(background=False)
        self.addCleanup(detector.disable)
        self.assertEqual(other_launchers.kind("t5dr", detector), "")
        child = subprocess.Popen([sys.executable, "-I", script], stdin=subprocess.PIPE)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.assertTrue(wait_for(lambda: (detector.refresh(), detector.others("t5dr")["native"])[1]))
        self.assertEqual(other_launchers.kind("t5dr", detector), "native")
        self.assertEqual(other_launchers.kind("t4", detector), "")
        child.stdin.close()                         # it ends
        child.wait()
        # (a venv's python.exe is a redirector: the real interpreter ends a moment after it)
        self.assertTrue(wait_for(lambda: (detector.refresh(), other_launchers.kind("t5dr", detector))[1] == ""))

    def test_another_window_and_its_login_are_seen_through_lock_files_and_let_go_when_it_ends(self):
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        mine = other_launchers.Detector(scan=lambda: [], directory=folder)
        mine.enable(background=False)
        self.addCleanup(mine.disable)
        self.assertEqual(other_launchers.kind("t5dr", mine), "")
        code = ("import os, sys; sys.path.insert(0, %r)\n"
                "from openrecomp.adapters import other_launchers as o\n"
                "d = o.Detector(scan=lambda: [], directory=%r); d.enable(background=False)\n"
                "d.online('t5dr', True); print('ready', flush=True); sys.stdin.readline(); os._exit(3)\n"
                % (os.getcwd(), folder))
        child = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 text=True)
        self.addCleanup(child.wait)
        self.addCleanup(child.kill)
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.stdin.close)
        self.assertEqual(child.stdout.readline().strip(), "ready")
        mine.refresh()
        self.assertEqual(mine.others("t5dr"), dict(native=False, window=True, online=True))
        self.assertEqual(other_launchers.kind("t5dr", mine), "online")
        self.assertEqual(other_launchers.kind("t4", mine), "window")
        child.stdin.write("go\n")                   # os._exit: no cleanup of its own, like a crash
        child.stdin.flush()
        child.wait()
        self.assertTrue(wait_for(lambda: (mine.refresh(), other_launchers.kind("t5dr", mine))[1] == ""))

    def test_off_until_enabled_and_a_broken_scan_means_nothing_found(self):
        folder = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        detector = other_launchers.Detector(scan=lambda: [(1, "t5dr_launcher.pyw")], directory=folder)
        self.assertEqual(other_launchers.kind("t5dr", detector), "")
        detector.enable(background=False)
        self.addCleanup(detector.disable)
        self.assertEqual(other_launchers.kind("t5dr", detector), "native")

        def broken():
            raise OSError("access denied")
        detector.scan = broken
        detector.refresh()
        self.assertEqual(other_launchers.kind("t5dr", detector), "")

    def test_the_app_switch_turns_it_off(self):
        with mock.patch.dict(os.environ, OPENRECOMP_OTHER_LAUNCHERS="0"), \
                mock.patch.object(other_launchers.DETECTOR, "enable") as enable:
            other_launchers.enable()
        enable.assert_not_called()


# ---------------------------------------------------------------- the adapter: no login against the other launcher
class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory, OPENRECOMP_HOME=self.directory))
        self.enterContext(mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False))
        self.detector = FakeDetector()

    def adapter(self):
        a = T5Subject(self.directory)
        a.other_launcher_detector = self.detector
        self.addCleanup(a.online_close)
        return a

    def login(self, a, account=True):
        a.set_text_value("online_name", "PadUser")
        if account:
            a.set_text_value("online_password", "fake-password")
        a.online_action("login_account" if account else "login_guest")
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "logged_in")
        return a.clients[-1]

    def remembered(self):
        """A launcher with a remembered login of its own (as after Remember me), logged out again."""
        a = self.adapter()
        self.login(a)
        a.online_close()
        a._online_auto_tried = False
        return a

    def test_no_automatic_login_while_the_native_launcher_is_open_until_use_here(self):
        a = self.remembered()
        count = len(a.clients)
        self.detector.found["native"] = True
        state = a.online_state()
        self.assertEqual(state["other_launcher"], dict(kind="native", game="t5dr", choice=None, logs_in=True))
        for _ in range(3):
            a.online_shown()
            a.online_poll()
        self.assertEqual(len(a.clients), count)              # it never logged in by itself
        self.assertEqual(a.online_state()["phase"], "offline")
        a.online_action("other_here")
        self.assertEqual(a.online_state()["other_launcher"]["choice"], "here")
        a.online_shown()
        a.online_poll()
        self.assertEqual(len(a.clients), count + 1)
        self.assertEqual(a.clients[-1].calls[-1], ("session", "fake-remembered-session"))
        self.assertEqual(a.online_state()["message"], "@other_launcher.logged_in_here")

    def test_without_another_launcher_the_remembered_login_still_logs_in_by_itself(self):
        a = self.remembered()
        count = len(a.clients)
        self.assertNotIn("other_launcher", a.online_state())
        a.online_shown()
        a.online_poll()
        self.assertEqual(len(a.clients), count + 1)
        self.assertEqual(a.online_state()["message"], "@online.logged_in")

    def test_keep_the_other_one_logs_out_here_and_stays_out(self):
        a = self.adapter()
        client = self.login(a)
        self.detector.found["native"] = True
        a.online_action("other_keep")
        state = a.online_state()
        self.assertEqual(state["phase"], "offline")
        self.assertEqual(state["message"], "@other_launcher.kept_other")
        self.assertEqual(state["other_launcher"]["choice"], "other")
        self.assertTrue(wait_for(client.closed.is_set) if hasattr(client.closed, "is_set") else True)
        count = len(a.clients)
        for _ in range(3):
            a.online_shown()
            a.online_poll()
        self.assertEqual(len(a.clients), count)

    def test_a_kick_by_the_native_launcher_names_it_and_never_logs_in_again_by_itself(self):
        a = self.adapter()
        client = self.login(a)
        self.detector.found["native"] = True
        client.events.put(dict(t="kicked", reason="logged in from another place"))
        client.events.put(dict(t="disconnected", reason="removed from the lobby: logged in from another place"))
        a.online_poll()
        state = a.online_state()
        self.assertEqual(state["phase"], "kicked")
        self.assertEqual(state["message"], "@other_launcher.kicked_native")
        self.assertEqual(state["other_launcher"]["choice"], "other")
        self.assertGreaterEqual(self.detector.refreshed, 1)   # looked again at once
        a._online_auto_tried = False                           # even a fresh Online visit does not log in
        for _ in range(3):
            a.online_shown()
            a.online_poll()
        self.assertEqual(len(a.clients), 1)
        self.assertIsNone(a._online_relogin)
        # logging in by hand is the player's choice: this launcher (the other one gets the kick then)
        self.login(a)
        self.assertEqual(a.online_state()["other_launcher"]["choice"], "here")

    def test_a_kick_by_another_window_says_so(self):
        a = self.adapter()
        client = self.login(a)
        self.detector.found.update(window=True, online=True)
        client.events.put(dict(t="kicked", reason="logged in from another place"))
        a.online_poll()
        self.assertEqual(a.online_state()["message"], "@other_launcher.kicked_window")

    def test_a_kick_with_no_other_launcher_here_keeps_the_plain_message(self):
        a = self.adapter()
        client = self.login(a)
        client.events.put(dict(t="kicked", reason="logged in from another place"))
        a.online_poll()
        self.assertEqual(a.online_state()["message"], "@online.kicked")

    def test_a_disconnect_that_names_the_kick_is_a_kick_not_a_relogin(self):
        # the kick line itself was not read before the connection closed: before, this started the automatic
        # relogin, which took the login back from the other launcher (ping-pong)
        a = self.adapter()
        client = self.login(a)
        client.events.put(dict(t="disconnected", reason="removed from the lobby: logged in from another place"))
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "kicked")
        self.assertEqual(a.online_state()["message"], "@online.kicked")
        self.assertIsNone(a._online_relogin)

    def test_a_lost_connection_does_not_log_in_again_by_itself_while_another_launcher_is_open(self):
        a = self.adapter()
        client = self.login(a)
        self.detector.found["native"] = True                   # opened after the login here: no choice yet
        a._other_choice = None
        client.events.put(dict(t="disconnected", reason="server restart"))
        a.online_poll()
        a.online_poll()
        state = a.online_state()
        self.assertEqual(state["phase"], "offline")
        self.assertEqual(state["message"], "@other_launcher.relogin_paused")
        self.assertEqual(len(a.clients), 1)

    def test_the_relogin_goes_on_when_the_player_chose_this_launcher(self):
        a = self.adapter()
        self.detector.found["native"] = True
        client = self.login(a)                                 # by hand: choice "here"
        client.events.put(dict(t="disconnected", reason="server restart"))
        a.online_poll()
        a._online_relogin["at"] = 0
        a.online_poll()
        a.online_poll()
        self.assertEqual(a.online_state()["phase"], "logged_in")
        self.assertEqual(len(a.clients), 2)

    def test_the_choice_is_forgotten_when_the_other_launcher_closes_and_presence_follows_the_login(self):
        a = self.adapter()
        self.detector.found["native"] = True
        self.login(a)
        self.assertEqual(self.detector.presence, [("t5dr", True)])
        self.detector.found["native"] = False
        self.assertNotIn("other_launcher", a.online_state())
        self.assertIsNone(a._other_choice)
        a.online_close()
        self.assertEqual(self.detector.presence[-1], ("t5dr", False))

    def test_a_game_without_a_launcher_to_look_for_never_asks(self):
        a = Subject(self.directory)
        self.addCleanup(a.online_close)
        a.other_launcher_detector = self.detector
        self.detector.found["native"] = True
        self.assertNotIn("other_launcher", a.online_state())


# ---------------------------------------------------------------- the note on the Online pages
class NoteTests(unittest.TestCase):
    def setUp(self):
        self.a = Lobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def test_login_card_shows_the_note_with_both_buttons(self):
        self.a.snapshot["other_launcher"] = dict(kind="native", game="t5dr", choice=None, logs_in=True)
        view = self.nav.view()["online"]
        self.assertEqual(view["layout"], "login")
        self.assertIn("T5DR Online's own launcher is open too", view["notice"]["text"])
        self.assertEqual([b["label"] for b in view["notice"]["buttons"]], ["Use OpenRecomp here", "Keep the other one"])
        # pad: the first press after the message lands on Use OpenRecomp here
        ids = [it.get("id") for it in self.nav.items()]
        self.assertEqual(ids[1:3], ["other_here", "other_keep"])
        self.nav.click_row(ids.index("other_keep"))
        self.assertIn(("online", "other_keep"), self.a.calls)

    def test_after_keep_the_note_offers_only_use_here(self):
        self.a.snapshot["other_launcher"] = dict(kind="native", game="t5dr", choice="other", logs_in=True)
        view = self.nav.view()["online"]
        self.assertIn("You play online in the other launcher", view["notice"]["text"])
        self.assertEqual([b["label"] for b in view["notice"]["buttons"]], ["Use OpenRecomp here"])

    def test_no_note_once_the_player_chose_here_or_without_another_launcher(self):
        self.assertIsNone(self.nav.view()["online"].get("notice"))
        self.a.snapshot["other_launcher"] = dict(kind="native", game="t5dr", choice="here", logs_in=True)
        self.assertIsNone(self.nav.view()["online"].get("notice"))
        self.assertNotIn("other_here", [it.get("id") for it in self.nav.items()])

    def test_lobby_page_shows_the_note_in_the_find_card(self):
        self.a.snapshot.update(lobby_snapshot())
        self.a.snapshot["other_launcher"] = dict(kind="window", game="t5dr", choice=None, logs_in=True)
        page = self.nav.view()["online"]
        self.assertEqual(page["layout"], "lobby")
        notice = page["find"]["notice"]
        self.assertIn("Another OpenRecomp window is open", notice["text"])
        self.assertEqual(len(notice["buttons"]), 2)
        items = self.nav.items()
        here = next(it for it in items if it.get("id") == "other_here")
        keep = next(it for it in items if it.get("id") == "other_keep")
        self.assertEqual((here["region"], keep["region"]), ("find", "find"))
        self.assertEqual(here["group"], keep["group"])          # one line: left/right between them
        self.nav.click_row(items.index(here))
        self.assertIn(("online", "other_here"), self.a.calls)

    def test_tekken_4_easy_launcher_text(self):
        self.a.snapshot["other_launcher"] = dict(kind="native", game="t4", choice=None, logs_in=False)
        self.assertIn("Tekken 4's own launcher is open too", self.nav.view()["online"]["notice"]["text"])

    def test_no_note_during_a_match(self):
        self.a.snapshot.update(phase="playing", other_launcher=dict(kind="native", game="t5dr", choice=None))
        self.assertNotIn("other_here", [it.get("id") for it in self.nav.items()])

    def test_every_catalog_has_the_texts(self):
        from openrecomp import i18n
        keys = [k for k in i18n.catalog("en") if k.startswith("other_launcher.")]
        self.assertGreaterEqual(len(keys), 14)
        for code in i18n.LANGUAGES:
            for key in keys:
                self.assertIn(key, i18n._catalog(code), (code, key))


# ---------------------------------------------------------------- a library change keeps the other games logged in
class ReloadKeepsLoginsTests(unittest.TestCase):
    def two_games(self):
        first, second = Lobby(), Lobby()
        second.m = dict(second.m, id="other", short="Other")
        first.root, second.root = "A", "B"
        first.snapshot.update(phase="logged_in", name="Me")
        second.snapshot.update(phase="logged_in", name="Me")
        nav = Nav([Game(first.m, first), Game(second.m, second)], language="en")
        return nav, first, second

    def test_adding_a_game_keeps_every_game_logged_in(self):
        nav, first, second = self.two_games()
        again_first, again_second, added = Lobby(), Lobby(), Lobby()
        again_second.m = dict(again_second.m, id="other", short="Other")
        added.m = dict(added.m, id="new", short="New")
        again_first.root, again_second.root, added.root = "A", "B", "N"
        self.assertTrue(nav.can_reload_games())                # a login alone no longer blocks the change
        self.assertTrue(nav.set_games([Game(again_first.m, again_first), Game(again_second.m, again_second),
                                       Game(added.m, added)]))
        self.assertIs(nav.game_by_id("lobby").a, first)        # the same adapter: the same lobby connection
        self.assertIs(nav.game_by_id("other").a, second)
        self.assertIs(nav.game_by_id("new").a, added)
        self.assertNotIn(("close",), first.calls + second.calls)
        self.assertEqual(first.account_peers, (second, added))

    def test_only_the_game_whose_folder_changed_is_logged_out(self):
        nav, first, second = self.two_games()
        again_first, moved = Lobby(), Lobby()
        again_first.root = "A"
        moved.m = dict(moved.m, id="other", short="Other")
        moved.root = "C"
        self.assertTrue(nav.set_games([Game(again_first.m, again_first), Game(moved.m, moved)]))
        self.assertIs(nav.game_by_id("lobby").a, first)
        self.assertIs(nav.game_by_id("other").a, moved)
        self.assertNotIn(("close",), first.calls)
        self.assertIn(("close",), second.calls)

    def test_removing_a_game_logs_out_only_that_game(self):
        nav, first, second = self.two_games()
        again_first = Lobby()
        again_first.root = "A"
        self.assertTrue(nav.set_games([Game(again_first.m, again_first)]))
        self.assertIs(nav.game_by_id("lobby").a, first)
        self.assertNotIn(("close",), first.calls)
        self.assertIn(("close",), second.calls)

    def test_a_game_now_found_in_the_same_folder_is_made_anew(self):
        nav, first, _second = self.two_games()
        again_first = Lobby()
        again_first.root = "A"
        again_first.found = lambda: not first.found()
        self.assertTrue(nav.set_games([Game(again_first.m, again_first)]))
        self.assertIs(nav.game_by_id("lobby").a, again_first)

    def test_the_backend_starts_a_library_job_while_a_game_is_only_logged_in(self):
        from types import SimpleNamespace
        from openrecomp import app
        nav, _first, _second = self.two_games()
        backend = SimpleNamespace(nav=nav, _library_work=None, _library_results=__import__("queue").Queue())
        backend._library_blocked = lambda: app.Backend._library_blocked(backend)
        with mock.patch.object(app.threading, "Thread"):
            self.assertEqual(app.Backend._library_job(backend, "preview", mock.Mock()), "@library.loading")

    def test_a_search_still_holds_the_change_back(self):
        nav, first, _second = self.two_games()
        first.snapshot["phase"] = "searching"
        self.assertFalse(nav.can_reload_games())

    def test_the_t5dr_update_closes_only_the_t5dr_lobby(self):
        nav, first, second = self.two_games()
        nav.close_online(only="other")
        self.assertNotIn(("close",), first.calls)
        self.assertIn(("close",), second.calls)


if __name__ == "__main__":
    unittest.main()
