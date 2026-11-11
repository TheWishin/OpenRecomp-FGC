"""The rematch question in the T4 game (openrecomp/t4_rematch.py and its part in adapters/t4_online.py), with fakes only:
a fake lobby client, a fake game process and the files the real game writes next to its result."""
import json
import os
import tempfile
import unittest
from unittest import mock

from openrecomp import t4_rematch
from openrecomp.vendor.t4lobby import t4game
from test_t4_game_result import game_file
from test_t4_online import Subject, ticket

RULE = dict(v=1, kind="rematch", policy="both_confirm", timeout=10.0, actions=["accept", "decline"])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.base = os.path.join(self.directory.name, "t4_result-abc.json")

    def test_switch_is_off_unless_one(self):
        # on by default (owner 2026-11-11); off while T4 is a beta (the T4 game's own default is off too)
        self.assertEqual(t4_rematch.DEFAULT, "1")
        self.assertTrue(t4_rematch.wanted({}))
        self.assertTrue(t4_rematch.wanted({"T4_INGAME_REMATCH": "1"}))
        self.assertTrue(t4_rematch.wanted({"T4_INGAME_REMATCH": " 1 "}))
        self.assertFalse(t4_rematch.wanted({"T4_INGAME_REMATCH": "0"}))
        self.assertFalse(t4_rematch.wanted({"T4_INGAME_REMATCH": "yes"}))
        with mock.patch.object(t4_rematch, "DEFAULT", "1"):
            self.assertTrue(t4_rematch.wanted({}))

    def test_marker_is_found_across_read_blocks_and_missing_files_have_none(self):
        exe = os.path.join(self.directory.name, "game.exe")
        self.assertFalse(t4_rematch.game_has_it(exe))
        with open(exe, "wb") as stream:
            stream.write(b"\0" * ((1 << 20) - 7) + t4_rematch.MARKER + b"\0" * 100)
        self.assertTrue(t4_rematch.game_has_it(exe))
        with open(exe, "wb") as stream:
            stream.write(b"TEKKEN4_INGAME_REMATC" + b"\0" * 100)
        self.assertFalse(t4_rematch.game_has_it(exe))
        self.assertFalse(t4_rematch.game_has_it(None))

    def test_paths_are_the_games(self):
        self.assertEqual(t4_rematch.result_path(self.base, 1), self.base)
        self.assertTrue(t4_rematch.result_path(self.base, 2).endswith("t4_result-abc-m2.json"))
        self.assertTrue(t4_rematch.next_path(self.base).endswith("t4_result-abc-next.json"))

    def test_state_reads_only_known_values(self):
        self.assertIsNone(t4_rematch.state(self.base))
        for value in t4_rematch.STATES:
            game_file(self.base, rematch=value)
            self.assertEqual(t4_rematch.state(self.base), value)
        game_file(self.base, rematch="surprise")
        self.assertIsNone(t4_rematch.state(self.base))
        game_file(self.base)                                   # an older game: no field
        self.assertIsNone(t4_rematch.state(self.base))
        with open(self.base, "w", encoding="utf-8") as stream:
            stream.write("{\"rematch\": ")
        self.assertIsNone(t4_rematch.state(self.base))

    def test_next_file_takes_plain_ids_only(self):
        self.assertTrue(t4_rematch.write_next(self.base, 2, "m6208516c8782"))
        with open(t4_rematch.next_path(self.base), encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"index": 2, "match": "m6208516c8782"})
        for index, match in ((1, "ok"), (2, "..\\evil"), (2, ""), (2, "a b"), (65, "ok"), (True, "ok")):
            self.assertFalse(t4_rematch.write_next(self.base, index, match))

    def test_clear_removes_only_this_results_session_files(self):
        other = os.path.join(self.directory.name, "t4_result-abcd-m2.json")
        for path in (t4_rematch.result_path(self.base, 2), t4_rematch.result_path(self.base, 3) + ".tmp",
                     t4_rematch.next_path(self.base), other, self.base):
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("{}")
        t4_rematch.clear(self.base)
        self.assertEqual(sorted(os.listdir(self.directory.name)), ["t4_result-abc.json", "t4_result-abcd-m2.json"])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory.name))
        self.enterContext(mock.patch.dict(os.environ, T4_INGAME_REMATCH="1"))      # opt-in while T4 is a beta
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.a = Subject(self.directory.name)
        self.a._online_api["game_result"] = (t4game.read_game_result, t4game.game_result_report)
        self.addCleanup(self.a.online_close)
        self.clock = 1000.0
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.time.monotonic", side_effect=lambda: self.clock))

    def game(self, marker=True):
        """The fake game's program file, with or without the question."""
        exe = os.path.join(self.directory.name, "bin", "ps2EntryRunner.exe")
        os.makedirs(os.path.dirname(exe), exist_ok=True)
        with open(exe, "wb") as stream:
            stream.write(b"MZ" + b"\0" * 64 + (t4_rematch.MARKER if marker else b"") + b"\0" * 64)

    def playing(self, server=True, current=None, **found):
        self.a.set_text_value("online_name", "FakePlayer")
        self.a.online_action("login_guest")
        self.a.online_poll()
        client = self.a.clients[-1]
        client.ingame_rematch_ok = lambda: server
        client.rematch = mock.Mock()
        client.events.put(dict(dict(t="match_found", opponent=dict(name="Other"), ping=dict(ms=10)), **found))
        self.a.online_poll()
        self.a.online_action("start_match")
        self.a.online_poll()
        client.events.put(dict(t="match_start", ticket=current or ticket()))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        return client

    def result(self, client, path, match="fake-match", rule=True, **values):
        """The game's result is read and reported, then the lobby's verdict arrives."""
        game_file(path, **dict(dict(match=match, rematch="pending"), **values))
        self.a.online_poll()
        self.a.online_poll()
        event = dict(t="match_result", match=match, status="confirmed", rematch_window=10)
        if rule:
            event["rematch_ui"] = dict(RULE)
        client.events.put(event)
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result_sent")

    def results(self, client):
        return [call[1] for call in client.calls if isinstance(call, tuple) and call[0] == "result"]

    def test_capability_needs_the_switch_and_a_game_that_has_it(self):
        self.assertFalse(self.a._online_client_options()["ingame_rematch"])       # no game file at all
        self.game(marker=False)
        self.a.__dict__.pop("_t4_ingame_cache", None)
        self.assertFalse(self.a._online_client_options()["ingame_rematch"])       # an older game
        self.game()
        self.a.__dict__.pop("_t4_ingame_cache", None)
        self.assertTrue(self.a._online_client_options()["ingame_rematch"])
        with mock.patch.dict(os.environ, T4_INGAME_REMATCH="0"):
            self.assertFalse(self.a._online_client_options()["ingame_rematch"])
        os.environ.pop("T4_INGAME_REMATCH")
        self.assertTrue(self.a._online_client_options()["ingame_rematch"])        # the default: on (owner 2026-11-11)

    def test_default_on_starts_the_game_with_the_switch(self):
        self.game()
        os.environ.pop("T4_INGAME_REMATCH")
        client = self.playing()
        self.assertEqual(self.a.starts[-1].get("TEKKEN4_INGAME_REMATCH"), "1")
        self.assertIsNotNone(self.a._t4_ingame)
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base, rule=False)
        self.assertEqual(len(self.a.stops), 1)                              # closed with the verdict, as before
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])

    def test_game_gets_the_switch_only_for_a_casual_match_with_a_server_that_has_it(self):
        self.game()
        self.playing()
        self.assertEqual(self.a.starts[-1].get("TEKKEN4_INGAME_REMATCH"), "1")

    def test_no_switch_for_ranked_old_server_old_game_or_switch_zero(self):
        self.game()
        self.playing(current=ticket(ranked=True))
        self.assertNotIn("TEKKEN4_INGAME_REMATCH", self.a.starts[-1])
        self.a.online_close()
        for kwargs, marker, env in ((dict(server=False), True, {}), ({}, False, {}), ({}, True, {"T4_INGAME_REMATCH": "0"})):
            with self.subTest(kwargs=kwargs, marker=marker, env=env), mock.patch.dict(os.environ, env):
                self.a = Subject(self.directory.name)
                self.a._online_api["game_result"] = (t4game.read_game_result, t4game.game_result_report)
                self.addCleanup(self.a.online_close)
                self.game(marker=marker)
                self.playing(**kwargs)
                self.assertNotIn("TEKKEN4_INGAME_REMATCH", self.a.starts[-1])
                self.assertIsNone(self.a._t4_ingame)
                self.a.online_close()

    def test_game_stays_for_the_question_and_yes_continues_in_the_running_game(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base)
        self.assertEqual(self.a.stops, [])                                  # not closed by the lobby's verdict
        self.assertFalse(self.a.online_state()["capabilities"]["rematch"])  # the question is in the game
        self.clock += 6.0
        self.a.online_poll()
        self.assertEqual(self.a.stops, [])                                  # nor by the old 5 s grace
        client.rematch.assert_not_called()                                  # still "pending"
        game_file(base, rematch="rematch")
        self.a.online_poll()
        self.a.online_poll()
        client.rematch.assert_called_once_with(match_id="fake-match", accept=True, keep=True)
        client.events.put(dict(t="match_found", match="next-match", origin="rematch", ready_check=False,
                               rematch_of="fake-match"))
        client.events.put(dict({"t": "match_start", "match": "next-match", "ticket": None, "continue": True}))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertEqual(len(self.a.starts), 1)                             # the same game, no new process
        self.assertEqual(self.a.stops, [])
        with open(t4_rematch.next_path(base), encoding="utf-8") as stream:
            self.assertEqual(json.load(stream), {"index": 2, "match": "next-match"})
        self.a._online_connected = True                                     # (the game's log said so in match 1)
        self.a.online_poll()
        self.a.online_poll()
        self.assertIn(("game_started", "next-match"), client.calls)        # the lobby hears it for the new match
        # the second match's result comes from its own file, under the new match id
        second = t4_rematch.result_path(base, 2)
        game_file(second, match="next-match", winner=0, score=[2, 1], match_code=1, rematch="pending")
        self.a.online_poll()
        self.a.online_poll()
        reported = self.results(client)
        self.assertEqual([r["match_id"] for r in reported], ["fake-match", "next-match"])
        self.assertEqual((reported[1]["winner"], reported[1]["score"]), (0, [2, 1]))

    def test_no_or_timeout_declines_and_the_game_is_not_killed_before_it_closes_itself(self):
        for what in ("declined", "timeout"):
            with self.subTest(what=what):
                self.a = Subject(self.directory.name)
                self.a._online_api["game_result"] = (t4game.read_game_result, t4game.game_result_report)
                self.addCleanup(self.a.online_close)
                self.game()
                client = self.playing()
                base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
                self.result(client, base)
                game_file(base, rematch=what)
                self.a.online_poll()
                self.a.online_poll()
                client.rematch.assert_called_once_with(match_id="fake-match", accept=False, keep=False)
                self.assertEqual(self.a.stops, [])
                self.assertEqual(self.a.online_state()["message"], "@online.rematch_declined")
                self.clock += 7.0                                           # a game that did not close: closed now
                self.a.online_poll()
                self.assertEqual(len(self.a.stops), 1)
                self.a.online_close()

    def test_opponents_game_without_the_question_is_the_old_path(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base, rule=False, rematch="off")
        # the lobby did not offer the question: the game is closed with the verdict, the launcher asks itself
        self.assertEqual(len(self.a.stops), 1)
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])
        self.assertIsNone(self.a._t4_ingame)
        client.rematch.assert_not_called()

    def test_off_in_the_file_closes_after_the_usual_grace(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        game_file(base, rematch="off")
        self.a.online_poll()
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.stops, [])
        self.clock += 5.5
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)
        client.rematch.assert_not_called()

    def test_question_never_answered_or_rematch_never_made_closes_the_game(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base)
        self.clock += t4_rematch.HOLD_SECONDS + 1
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)                              # "pending" for ever
        self.assertIsNone(self.a._t4_ingame)

    def test_yes_without_a_continue_from_the_lobby_closes_the_game(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base)
        game_file(base, rematch="rematch")
        self.a.online_poll()
        self.a.online_poll()
        client.rematch.assert_called_once()
        self.clock += t4_rematch.CONTINUE_SECONDS + 1
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)

    def test_refused_vote_closes_the_game(self):
        self.game()
        client = self.playing()
        client.rematch = mock.Mock(side_effect=RuntimeError("that match is over"))
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base)
        game_file(base, rematch="rematch")
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)
        self.assertIsNone(self.a._t4_ingame)

    def test_lobby_expiry_and_back_to_lobby_close_the_kept_game(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base)
        client.events.put(dict(t="rematch", match="fake-match", state="expired"))
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)
        self.a.online_close()
        self.a = Subject(self.directory.name)
        self.a._online_api["game_result"] = (t4game.read_game_result, t4game.game_result_report)
        self.addCleanup(self.a.online_close)
        client = self.playing()
        self.result(client, self.a.starts[-1]["TEKKEN4_NET_RESULT"])
        self.a.online_action("return_lobby")
        self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)
        client.rematch.assert_called_once_with(match_id="fake-match", accept=False, keep=False)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_fresh_ticket_after_a_yes_starts_a_new_game_as_before(self):
        self.game()
        client = self.playing()
        base = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.result(client, base)
        game_file(base, rematch="rematch")
        self.a.online_poll()
        self.a.online_poll()
        client.events.put(dict(t="match_found", match="next-match", origin="rematch", ready_check=False))
        client.events.put(dict(t="match_start", ticket=ticket(match_id="next-match")))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        self.assertEqual(len(self.a.starts), 2)                             # the lobby wanted a new connection
        self.assertEqual(len(self.a.stops), 1)


if __name__ == "__main__":
    unittest.main()
