"""T5DR's Lobby address on a fresh home: the servers lists' default, never a guessed loopback (drill120).

Only fakes and repository-local temporary files: the fake client connects nowhere.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.nav_online_login import FIELD_ERRORS
from test_online_adapter import LobbyError, Subject

PIN = "ab" * 32


def servers(path, *entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump({"format": "t5dr-servers/1", "servers": list(entries)}, stream)


def entry(name, host="lobby.example", default=False, **extra):
    out = dict(name=name, host=host, port=7781, tls="pin", fingerprint=PIN, **extra)
    if default:
        out["default"] = True
    return out


class Base(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            self.enterContext(mock.patch(target, side_effect=AssertionError("external I/O denied")))
        self.directory = self.enterContext(tempfile.TemporaryDirectory(dir=os.getcwd()))
        self.enterContext(mock.patch.dict(os.environ, T5_ONLINE_DIR=self.directory))
        for name in ("OPENRECOMP_T5_SERVER", "OPENRECOMP_T4_SERVER"):
            if name in os.environ:
                self.enterContext(mock.patch.dict(os.environ, {name: ""}))
        self.enterContext(mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False))
        self.shipped = os.path.join(self.directory, "lobby", "servers.json")       # the install's own list
        self.own = os.path.join(self.directory, "servers.json")                    # the player's list

    def subject(self, config=None):
        owner = Subject(self.directory)
        owner.config = dict(config or {})
        self.addCleanup(owner.online_close)
        return owner

    def guest(self, owner):
        owner.online_action("login_guest")
        owner.online_poll()
        return owner.online_state()


class LobbyDefault(Base):
    def test_fresh_home_shows_and_uses_the_shipped_default(self):
        servers(self.shipped, entry("Other lobby", host="other.example"), entry("T5DR Online", default=True))
        owner = self.subject()
        self.assertEqual(owner.text_value("online_server"), "T5DR Online")
        self.assertEqual(self.guest(owner)["phase"], "logged_in")
        self.assertEqual(owner.clients[-1].kwargs["server"], "T5DR Online")

    def test_an_emptied_field_still_means_the_default_never_loopback(self):
        servers(self.shipped, entry("T5DR Online", default=True))
        owner = self.subject()
        owner.set_text_value("online_server", "")
        self.assertEqual(self.guest(owner)["phase"], "logged_in")
        self.assertEqual(owner.clients[-1].kwargs["server"], "T5DR Online")

    def test_the_players_own_default_wins_and_without_a_default_the_first_entry(self):
        servers(self.shipped, entry("T5DR Online", default=True))
        servers(self.own, entry("Club lobby", host="club.example", default=True))
        self.assertEqual(self.subject()._online_default_server(), "Club lobby")
        servers(self.own, entry("Club lobby", host="club.example"))
        servers(self.shipped, entry("First"), entry("Second", host="second.example"))
        self.assertEqual(self.subject()._online_default_server(), "First")

    def test_a_list_installed_later_is_read_without_a_restart(self):
        owner = self.subject()
        self.assertEqual(owner._online_default_server(), "")             # nothing listed: no address is guessed
        servers(self.shipped, entry("T5DR Online", default=True))
        self.assertEqual(owner._online_default_server(), "T5DR Online")

    def test_placeholders_and_other_formats_are_not_defaults(self):
        servers(self.shipped, entry("T5DR Online", default=True))
        with open(self.own, "w", encoding="utf-8") as stream:
            json.dump({"format": "other/1", "servers": [entry("Wrong", default=True)]}, stream)
        self.assertEqual(self.subject()._online_default_server(), "T5DR Online")
        servers(self.own, dict(name="Placeholder", host="", default=True))
        self.assertEqual(self.subject()._online_default_server(), "T5DR Online")

    def test_explicit_server_and_the_t5dr_launchers_saved_server_win(self):
        servers(self.shipped, entry("T5DR Online", default=True))
        with open(os.path.join(self.directory, "online.json"), "w", encoding="utf-8") as stream:
            json.dump(dict(server="saved.example:7781"), stream)
        self.assertEqual(self.subject().text_value("online_server"), "saved.example:7781")
        owner = self.subject(dict(t5_lobby_server="config.example:7781"))
        self.assertEqual(owner.text_value("online_server"), "config.example:7781")
        with mock.patch.dict(os.environ, OPENRECOMP_T5_SERVER="127.0.0.1:7781"):     # a test names loopback
            owner = self.subject(dict(t5_lobby_server="config.example:7781"))
            self.assertEqual(owner.text_value("online_server"), "127.0.0.1:7781")
            owner.set_text_value("online_server", "")
            self.guest(owner)
            self.assertEqual(owner.clients[-1].kwargs["server"], "127.0.0.1:7781")

    def test_a_saved_login_is_looked_up_under_the_server_it_is_sent_to(self):
        servers(self.shipped, entry("T5DR Online", default=True))
        with open(os.path.join(self.directory, "online.json"), "w", encoding="utf-8") as stream:
            json.dump(dict(sessions={"127.0.0.1:7781": dict(token="loopback-only"),
                                     "t5dr online": dict(name="Player", token="for-t5dr-online")}), stream)
        owner = self.subject()
        owner.set_text_value("online_server", "")
        owner.online_action("login_saved")
        owner.online_poll()
        client = owner.clients[-1]
        self.assertEqual(client.kwargs["server"], "T5DR Online")
        self.assertIn(("session", "for-t5dr-online"), client.calls)
        self.assertNotIn(("session", "loopback-only"), client.calls)


class Unreachable(Base):
    def failing(self, error):
        servers(self.shipped, entry("T5DR Online", default=True))
        owner = self.subject()
        make = owner.make_client

        def client(**kwargs):
            made = make(**kwargs)
            made.connect = mock.Mock(side_effect=error)
            return made
        owner._online_api["client"] = client
        return self.guest(owner)

    def test_a_connection_that_never_came_about_says_not_reachable(self):
        for code in ("connect_failed", "not_connected", "disconnected"):
            with self.subTest(code=code):
                state = self.failing(LobbyError(code))
                self.assertEqual((state["phase"], state["message"]), ("error", "@online.unreachable"))
        self.assertIn("@online.unreachable", FIELD_ERRORS["online_server"])     # the red line under the address

    def test_a_certificate_other_than_the_pinned_one_is_a_server_setting(self):
        self.assertEqual(self.failing(LobbyError("tls_mismatch"))["message"], "@online.server_invalid")

    def test_a_real_refusal_still_says_refused(self):
        self.assertEqual(self.failing(LobbyError("not_allowed"))["message"], "@online.refused")

    def test_the_text_is_in_every_catalog(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                self.assertIn("online.unreachable", i18n.catalog(language))


if __name__ == "__main__":
    unittest.main()
