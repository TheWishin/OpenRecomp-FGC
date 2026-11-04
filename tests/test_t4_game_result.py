"""The T4 game's own match result (TEKKEN4_NET_RESULT) reported to the lobby, with fakes only."""
import json
import os
import tempfile
import unittest
from unittest import mock

from openrecomp.vendor.t4lobby import t4game
from test_t4_online import Subject, ticket

SCHEMA = "tekken4-online-session-v2"


def game_file(path, **values):
    """What runtime/tekken4_online_result.h writes once the match is decided on confirmed frames."""
    data = {"schema": SCHEMA, "match": "fake-match", "match_result_proven": True, "winner": 1, "draw": False,
            "score": [1, 2], "chars": [14, 0], "costumes": [1, 1], "stage": 3, "rounds_to_win": 2,
            "match_code": 2, "frames": 9000, "hash": "00ff00ff00ff00ff", "hash_frame": 9000, "hash_agreed": True,
            "desync": 0, "hashes_compared": 300, "rounds": []}
    data.update(values)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream)


class ReadGameResultTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "r.json")

    def read(self, expected="fake-match", **values):
        game_file(self.path, **values)
        return t4game.read_game_result(self.path, expected)

    def test_proven_result_with_fighters_stage_and_hash(self):
        res = self.read()
        self.assertEqual((res["winner"], res["score"], res["chars"], res["stage"]), (1, [1, 2], [14, 0], 3))
        self.assertEqual((res["desync"], res["hash"], res["hash_agreed"], res["frames"]), (0, "00ff00ff00ff00ff", True, 9000))
        kw = t4game.game_result_report(res)
        self.assertEqual(kw, {"source": "game", "desync": 0, "hash": "00ff00ff00ff00ff", "frames": 9000,
                              "chars": [14, 0], "stage": 3})

    def test_draw(self):
        res = self.read(winner=None, draw=True, score=[2, 2], match_code=3)
        self.assertIsNone(res["winner"])
        self.assertEqual(res["score"], [2, 2])

    def test_unproven_missing_or_other_matches_are_no_result(self):
        self.assertIsNone(t4game.read_game_result(self.path, "fake-match"))          # no file yet
        self.assertIsNone(self.read(match_result_proven=False))                       # the session report only
        self.assertIsNone(self.read(schema="tekken4-online-session-v1"))              # an older game build
        self.assertIsNone(self.read(match="other-match"))                             # a stale file of another match
        self.assertIsNone(self.read(match=None))
        with open(self.path, "w", encoding="utf-8") as stream:
            stream.write("{\"schema\": ")                                            # half written
        self.assertIsNone(t4game.read_game_result(self.path, "fake-match"))

    def test_inconsistent_winner_and_score_are_refused(self):
        self.assertIsNone(self.read(winner=0, score=[1, 2]))
        self.assertIsNone(self.read(winner=None, draw=True, score=[2, 1]))
        self.assertIsNone(self.read(winner=None, draw=False))
        self.assertIsNone(self.read(winner=True))
        self.assertIsNone(self.read(score=[1, 2, 3]))
        self.assertIsNone(self.read(score=[1, 12]))

    def test_unknown_fighters_and_stage_are_left_out_not_the_result(self):
        res = self.read(chars=[-1, 0], stage=-1)
        self.assertEqual((res["winner"], res["chars"], res["stage"]), (1, None, None))
        self.assertNotIn("chars", t4game.game_result_report(res))

    def test_different_hashes_count_as_desync(self):
        self.assertEqual(self.read(hash_agreed=False, desync=0)["desync"], 1)

    def test_game_env_names_the_result_file(self):
        env = t4game.game_env(ticket(rtt_ms=12.0), result_file=self.path)
        self.assertEqual(env["TEKKEN4_NET_RESULT"], self.path)
        self.assertEqual(env["TEKKEN4_NET_MATCH"], "fake-match")
        self.assertNotIn("TEKKEN4_NET_RESULT", t4game.game_env(ticket(rtt_ms=12.0)))


class AdapterGameResultTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory.name))
        self.enterContext(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        self.a = Subject(self.directory.name)
        self.a._online_api["game_result"] = (t4game.read_game_result, t4game.game_result_report)
        self.addCleanup(self.a.online_close)

    def playing(self, current=None):
        self.a.set_text_value("online_name", "FakePlayer")
        self.a.online_action("login_guest")
        self.a.online_poll()
        client = self.a.clients[-1]
        client.events.put(dict(t="match_found", opponent=dict(name="Other"), ping=dict(ms=10)))
        self.a.online_poll()
        self.a.online_action("start_match")
        self.a.online_poll()
        client.events.put(dict(t="match_start", ticket=current or ticket()))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "playing")
        return client

    def results(self, client):
        return [call[1] for call in client.calls if isinstance(call, tuple) and call[0] == "result"]

    def test_game_result_is_reported_once_and_the_game_closed_after_a_grace(self):
        client = self.playing(ticket("join"))
        path = self.a.starts[-1]["TEKKEN4_NET_RESULT"]
        self.assertEqual(os.path.dirname(path), self.directory.name)        # beside the game's net.log
        self.a.online_poll()
        self.assertEqual(self.results(client), [])                           # nothing written yet
        game_file(path)
        self.a.online_poll()
        self.a.online_poll()
        res = self.results(client)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0], {"winner": 1, "score": [1, 2], "match_id": "fake-match", "source": "game",
                                  "desync": 0, "hash": "00ff00ff00ff00ff", "frames": 9000, "chars": [14, 0],
                                  "stage": 3})
        self.assertEqual(self.a.online_state()["phase"], "result_sent")
        self.assertEqual(self.a.stops, [])                                  # the opponent may still need our game
        with mock.patch("openrecomp.adapters.t4_online.time.monotonic", return_value=self.a._t4_result_stop_at + 1):
            self.a.online_poll()
        self.assertEqual(len(self.a.stops), 1)
        self.a.online_poll()
        self.assertEqual(len(self.results(client)), 1)                       # never twice

    def test_stale_file_of_the_last_match_is_removed_before_the_game_starts(self):
        stale = os.path.join(self.directory.name, "t4_result-fake-match.json")
        game_file(stale, winner=0, score=[2, 0], match_code=1)
        client = self.playing()
        self.assertFalse(os.path.exists(stale))
        self.a.online_poll()
        self.assertEqual(self.results(client), [])

    def test_unproven_file_leaves_the_manual_answer(self):
        client = self.playing()
        game_file(self.a.starts[-1]["TEKKEN4_NET_RESULT"], match_result_proven=False, winner=None, score=None)
        self.a.child_exit = 0                                               # the game closed without a result
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result")
        self.assertEqual(self.results(client), [])
        self.a.online_action("result_win")
        self.a.online_poll()
        self.assertEqual(self.results(client)[0]["source"], "manual")

    def test_refused_report_falls_back_to_the_manual_answer(self):
        client = self.playing()

        def refuse(**kwargs):
            client.calls.append(("result", kwargs))
            raise RuntimeError("refused")
        client.report_result = refuse
        game_file(self.a.starts[-1]["TEKKEN4_NET_RESULT"])
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["phase"], "result")

    def test_an_older_client_without_the_reader_gets_no_result_file(self):
        del self.a._online_api["game_result"]
        self.a._online_api["game_result"] = None
        self.playing()
        self.assertNotIn("TEKKEN4_NET_RESULT", self.a.starts[-1])


if __name__ == "__main__":
    unittest.main()
