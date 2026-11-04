"""T4 ranked in the launcher (fakes only, no server, no game): ranked opens when the T4 server says so (accounts), our
own rank badges (tools/make_rank_badges.py, Tekken 7's names), the found match names both sides with name, rank and
badge, a ranked set's next game starts by itself, the game gets the name plates' environment, the server's verdicts
on unproven results and the set's character lock have their own texts."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from openrecomp.adapters import t4_online
from openrecomp.vendor.t4lobby import ranks as vranks, t4game
from test_t4_online import Subject, ticket

ROOT = Path(__file__).resolve().parents[1]
BADGES = ROOT / "openrecomp" / "ui" / "assets" / "ranks"


def load_tool(name):
    spec = importlib.util.spec_from_file_location("t4_ranked_" + name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(self.directory.cleanup)
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=self.directory.name))
        self.a = Subject(self.directory.name)
        self.a._online_api.update(game_result=(t4game.read_game_result, t4game.game_result_report),
                                  hud_env=t4game.hud_env)

    def login(self, ranked_queue=True):
        self.a.set_text_value("online_name", "FakePlayer")
        self.a.online_action("login_guest")
        self.a.online_poll()
        client = self.a.clients[-1]
        client.welcome = dict(ranked_queue=ranked_queue)
        client.leave_set = lambda: client.calls.append(("leave_set",))
        self.a._online_me = dict(name="FakePlayer", rank="Initiate", tier=13, rating=1640)
        return client

    def found(self, client, **values):
        event = dict(t="match_found", match="fake-match", ranked=True, slot=1, ready_check=True,
                     you=dict(name="FakePlayer", rank="Initiate", tier=13),
                     opponent=dict(name="Other", rank="Tekken King", tier=42), ping=dict(ms=10),
                     set=dict(id="s1", rated=True, wins_needed=2, best_of=3, number=1, wins=[0, 0]))
        event.update(values)
        client.events.put(event)
        self.a.online_poll()
        return event


class RankedOpensTest(Base):
    def test_follows_the_servers_welcome(self):
        client = self.login(ranked_queue=False)
        self.assertFalse(self.a.online_state()["capabilities"]["ranked"])
        client.welcome = dict(ranked_queue=True)
        self.assertTrue(self.a.online_state()["capabilities"]["ranked"])

    def test_guests_are_refused_accounts_search(self):
        client = self.login()
        self.a.online_action("search_ranked")
        self.a.online_poll()
        self.assertFalse(any(isinstance(c, tuple) and c[0] == "ranked" for c in client.calls))   # a guest
        self.a._online_account = True
        self.enterContext(mock.patch.object(t4_online, "game_process_running", return_value=False))
        self.a.online_action("search_ranked")
        self.a.online_poll()
        self.assertTrue(any(isinstance(c, tuple) and c[0] == "ranked" for c in client.calls), client.calls)


class BadgesTest(Base):
    def test_every_tier_has_our_own_badge(self):
        names = sorted(p.name for p in BADGES.iterdir())
        self.assertEqual(names, ["t4_rank_%02d.svg" % t for t in range(47)])
        for path in BADGES.iterdir():
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("<svg"), path.name)
            self.assertNotIn("<image", text)                  # drawn shapes only, no embedded picture
            self.assertNotIn("href", text)

    def test_the_committed_badges_are_what_the_script_makes(self):
        tool = load_tool("make_rank_badges")
        self.assertEqual(tool.check(), [])
        self.assertEqual(tool.NAMES, vranks.NAMES)          # the script's names = the T4 server's tiers

    def test_badges_are_shipped(self):
        shipped = load_tool("package_release").SOURCE_GROUPS["openrecomp/ui/assets/ranks"]
        self.assertEqual(sorted(shipped), sorted(p.name for p in BADGES.iterdir()))

    def test_rank_plate_and_progress(self):
        self.assertTrue(self.a.rank_plate(46).endswith("t4_rank_46.svg"))
        for bad in (None, -1, 64, True, "3"):
            self.assertEqual(self.a.rank_plate(bad), "")
        self.enterContext(mock.patch.dict(sys.modules, {"t4lobby.ranks": vranks}))
        self.assertEqual(self.a.rank_progress(1640), (1630.0, 1660.0, "Mentor"))
        self.assertIsNone(self.a.rank_progress(2800))         # Tekken God Omega: no next rank


class FoundMatchTest(Base):
    def test_both_sides_with_names_ranks_and_badges(self):
        client = self.login()
        self.found(client)
        match = self.a.online_state()["match"]
        self.assertEqual(match["slot"], 1)
        self.assertEqual([(s["name"], s["rank"], s["tier"], s["you"]) for s in match["sides"]],
                         [("Other", "Tekken King", 42, False), ("FakePlayer", "Initiate", 13, True)])

    def test_nav_rows_name_p1_and_p2(self):
        from openrecomp import i18n
        from openrecomp.nav import Game, Nav
        client = self.login()
        self.found(client)
        from test_nav import manifest
        m = manifest(self.a.m["id"])
        nav = Nav([Game(m, self.a)], language="en")
        nav.screen = "hub"
        nav.sec[self.a.m["id"]] = "online"
        status = next(it for it in nav.items() if it.get("id") == "online_status")
        sides = [r for r in status["detail"]["rows"] if r.get("k") in ("@online.challenge_p1", "@online.challenge_p2")]
        self.assertEqual([r["k"] for r in sides], ["@online.challenge_p1", "@online.challenge_p2"])
        self.assertTrue(sides[0]["plate"].endswith("t4_rank_42.svg"))
        self.assertEqual(sides[1]["v"], i18n.message("t4.side_you_rank", name=i18n.literal("FakePlayer"),
                                                     rank=i18n.literal("Initiate")))
        self.assertTrue(sides[1]["accent"])
        # the hub's detail panel keeps the badge (nav_hub) -- the found match's card shows it beside the name
        nav.focus[self.a.m["id"] + ":online"] = 0
        view = nav.view()
        plates = [r.get("plate", "") for r in view["detail"]["rows"]]
        self.assertTrue(any(p.endswith("t4_rank_42.svg") for p in plates), plates)

    def test_guest_opponent_has_no_rank(self):
        client = self.login()
        self.found(client, slot=0, ranked=False, set=None, opponent=dict(name="Guest1", guest=True, tier=0, rank="Beginner"))
        sides = self.a.online_state()["match"]["sides"]
        self.assertEqual((sides[1]["name"], sides[1]["rank"], sides[1]["tier"]), ("Guest1", "", None))


class GameEnvTest(Base):
    def env(self, slot=1, plates=None):
        client = self.login()
        self.found(client, slot=slot)
        if plates is not None:
            self.a.config["t4_name_plates"] = plates
        return self.a._online_game_env(ticket("join" if slot else "host", ranked=True,
                                              opponent=dict(name="Other", tier=42)))

    def test_ranked_ticket_gets_the_name_plates(self):
        env = self.env()
        self.assertEqual(env["TEKKEN4_HUD_NAMES"], "Other|FakePlayer")      # P1 = the host = the opponent here
        self.assertEqual(env["TEKKEN4_HUD_RANKS"], "42,13")
        self.assertIn("TEKKEN4_NET_RESULT", env)

    def test_the_setting_turns_them_off(self):
        env = self.env(plates=False)
        self.assertEqual(env["TEKKEN4_HUD_PLATES"], "0")
        self.assertNotIn("TEKKEN4_HUD_NAMES", env)

    def test_ranked_needs_the_games_result(self):
        self.login()
        self.a._online_api["game_result"] = None
        with self.assertRaises(RuntimeError):
            self.a._online_game_env(ticket(ranked=True))

    def test_setting_row(self):
        self.a.core.RESOLUTIONS = []
        self.a.core.save_settings = lambda s: None
        row = next(r for r in self.a.settings() if r["id"] == "name_plates")
        self.assertIs(row["value"], True)
        self.a.set_setting("name_plates", False)
        self.assertIs(self.a.config["t4_name_plates"], False)
        self.a.set_setting("name_plates", "no")
        self.assertIs(self.a.config["t4_name_plates"], False)


class SetFlowTest(Base):
    def test_the_next_game_starts_by_itself(self):
        client = self.login()
        self.found(client)
        self.a._online_phase = "result_sent"                 # game 1 reported and confirmed
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", winner=1,
                               set=dict(id="s1", rated=True, number=2, wins=[0, 1], best_of=3,
                                        next=dict(number=2, **{"in": 6}))))
        self.a.online_poll()
        state = self.a.online_state()
        self.assertEqual(state["set"]["wins"], [1, 0])        # (seen from this player's side: P2 won game 1)
        self.assertTrue(state["capabilities"]["leave_set"])
        self.found(client, match="fake-match-2", origin="set", ready_check=False,
                   set=dict(id="s1", rated=True, number=2, wins=[0, 1]))
        self.assertEqual(self.a.online_state()["phase"], "starting")
        self.assertTrue(self.a._online_authorized)
        self.assertFalse(any(c == ("ready", True) for c in client.calls))       # no ready vote between set games

    def test_the_next_casual_first_to_game_starts_without_a_decline(self):
        client = self.login()
        info = dict(id="s1", rated=False, casual=True, first_to=2, wins_needed=2, number=1, wins=[0, 0])
        self.found(client, ranked=False, set=info)
        initial = self.a.online_state()["set"]
        self.a._online_phase = "result_sent"
        next_info = dict(info, number=2, wins=[0, 1], next=dict(number=2, **{"in": 6}))
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", winner=1,
                               set=next_info))
        self.a.online_poll()
        result = self.a.online_state()
        self.found(client, match="fake-match-2", ranked=False, origin="set", ready_check=False, set=next_info)
        state = self.a.online_state()
        self.assertEqual(state["phase"], "starting")
        self.assertEqual(self.a._online_match_id, "fake-match-2")
        self.assertTrue(self.a._online_authorized)
        self.assertFalse(self.a._online_ready_check)
        self.assertNotIn(("ready", False), client.calls)     # do not decline the next game as an unsolicited offer
        self.assertNotIn(("ready", True), client.calls)      # no ready vote between set games
        self.assertEqual((initial["id"], initial["first_to"], initial["wins"]), ("s1", 2, [0, 0]))
        self.assertFalse(initial["rated"])
        self.assertTrue(initial["casual"])
        self.assertEqual(result["set"]["wins"], [1, 0])      # P2 won game 1, from this player's side
        self.assertEqual((state["set"]["number"], state["set"]["wins"]), (2, [1, 0]))

    def test_leave_set(self):
        client = self.login()
        self.found(client)
        self.a._online_phase = "result_sent"
        client.events.put(dict(t="match_result", match="fake-match", status="confirmed", winner=1,
                               set=dict(id="s1", rated=True, number=2, wins=[0, 1], next=dict(number=2))))
        self.a.online_poll()
        self.a.online_action("leave_set")
        self.a.online_poll()
        self.assertIn(("leave_set",), client.calls)
        self.assertEqual(self.a.online_state()["phase"], "logged_in")

    def test_verdict_texts(self):
        client = self.login()
        self.found(client)
        for reason, text in (("unproven", "@t4.result_unproven"), ("char_lock", "@t4.result_char_lock")):
            self.a._online_phase = "result_sent"
            client.events.put(dict(t="match_result", match="fake-match",
                                   status="void" if reason == "unproven" else "onesided", reason=reason))
            self.a.online_poll()
            self.assertEqual(self.a.online_state()["message"], text)


if __name__ == "__main__":
    unittest.main()
