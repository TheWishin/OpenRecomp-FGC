"""Hidden future lobby navigation uses generic fakes and controller actions only."""
import json
from pathlib import Path
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
import test_online_nav as online_fakes


class T4Lobby(online_fakes.Lobby):
    def __init__(self):
        super().__init__()
        self.m.update(id="t4", sections=["play", "online"])
        self.snapshot.update(capabilities=dict(ranked=False, lobby=True, match_flow=True),
                             players=[dict(id="player-2", name="Rival", rank="")],
                             rooms=[dict(id="room-1", name="Open room")],
                             chat=[dict(name="Rival", text="Hello <b>there</b>")],
                             challenge=dict(id="incoming", name="Challenger"), room=dict(id="mine"))
        self.texts["online_chat"] = ""


class T4OnlineNavigation(unittest.TestCase):
    choose = online_fakes.OnlineNavigation.choose
    pad_key = online_fakes.OnlineNavigation.pad_key

    def setUp(self):
        self.a = T4Lobby()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec["t4"] = "online"

    def ids(self):
        return [item.get("id") for item in self.nav.items()]

    def test_t4_manifest_offers_online(self):
        manifest = json.loads((Path(__file__).resolve().parents[1] / "games" / "t4.json").read_text(encoding="utf-8"))
        self.assertIn("online", manifest["sections"])

    def test_controller_reaches_day_one_actions_without_ranked(self):
        self.choose("login_guest")
        self.assertNotIn("search_ranked", self.ids())
        actions = ("refresh_players", "challenge:player-2", "accept_challenge", "decline_challenge",
                   "refresh_rooms", "create_room", "join_room:room-1", "leave_room")
        for action in actions:
            if action == "decline_challenge":
                # The prior offer is pending after Accept; a new server offer has its own answer controls.
                self.a.snapshot["challenge"] = dict(id="next-incoming", name="Another challenger")
            self.choose(action)
        self.assertTrue(all(("online", action) in self.a.calls for action in actions))
        self.choose("online_chat")
        for char in "Hi!":
            self.pad_key(char)
        self.nav.act("play", device="xbox")
        self.assertEqual(self.a.texts["online_chat"], "Hi!")
        self.choose("send_chat")
        self.assertIn(("online", "send_chat"), self.a.calls)
        self.choose("chat:0")
        view = self.nav.view()
        self.assertEqual(view["detail"]["lead"], "Hello <b>there</b>")
        self.assertEqual(view["detail"]["leadLines"], 10)
        self.assertFalse(any(row["k"] == "Rank" for row in view["detail"]["rows"]))
        self.assertFalse(any(call[0] == "start" for call in self.a.calls))

    def test_match_start_stop_and_each_manual_result_are_pad_actions(self):
        self.a.snapshot.update(phase="matched", match=dict(opponent="Rival", ping=30))
        self.assertIn("start_match", self.ids())
        self.choose("start_match")
        self.choose("cancel_match")
        self.a.snapshot["phase"] = "starting"
        self.choose("cancel_match")
        self.a.snapshot["phase"] = "playing"
        self.choose("stop_match")
        self.a.snapshot["phase"] = "result"
        for action in ("result_win", "result_loss", "result_none"):
            self.choose(action)
        self.a.snapshot["phase"] = "result_sent"
        self.choose("return_lobby")
        for action in ("start_match", "cancel_match", "stop_match", "result_win", "result_loss", "result_none", "return_lobby"):
            self.assertIn(("online", action), self.a.calls)
        self.assertFalse(any(call[0] == "start" for call in self.a.calls))

    def test_dry_suppresses_every_new_action_and_chat_write(self):
        self.nav.dry = True
        self.a.snapshot["phase"] = "logged_in"
        for action in ("refresh_players", "challenge:player-2", "accept_challenge", "decline_challenge",
                       "refresh_rooms", "create_room", "join_room:room-1", "leave_room", "send_chat"):
            self.choose(action)
        self.choose("online_chat")
        self.nav.type_text("Hello")
        self.nav.act("play")
        for phase, actions in (("matched", ("start_match", "cancel_match")),
                               ("playing", ("stop_match",)),
                               ("result", ("result_win", "result_loss", "result_none")),
                               ("result_sent", ("return_lobby",))):
            self.a.snapshot["phase"] = phase
            for action in actions:
                self.choose(action)
        self.nav.tick(.016)
        self.assertEqual(self.a.calls, [])
        self.assertEqual(self.a.polls, 0)

    def test_match_sides_keep_peer_ping_and_path(self):
        badge = Path(__file__).resolve().parents[1] / "openrecomp" / "ui" / "assets" / "ranks" / "t4_rank_13.svg"
        self.a.rank_plate = lambda tier: str(badge)
        sides = [dict(name="Host", rank="Initiate", tier=13),
                 dict(name="Guest", you=True)]
        for phase in ("matched", "starting", "playing", "result", "result_sent"):
            for ping, text, path in (({}, "@online_ui.ping_unknown", ""),
                                    (dict(ping=48, ping_path="relay"),
                                     i18n.message("online_ui.ping_est", ping=48), "@online_ui.path_relay"),
                                    (dict(ping=31, ping_measured=True, ping_path="direct"),
                                     i18n.message("online_ui.ping_ms", ping=31), "@online_ui.path_direct")):
                with self.subTest(phase=phase, ping=ping):
                    self.a.snapshot.update(phase=phase, match=dict(opponent="Host", sides=sides, **ping))
                    status = next(item for item in self.nav.items() if item.get("id") == "online_status")
                    rows = status["detail"]["rows"]
                    self.assertEqual([row["v"] for row in rows if row["k"] == "@online.ping"], [text])
                    self.assertEqual([row["v"] for row in rows if row["k"] == "@online_ui.path"],
                                     [path] if path else [])
                    players = [row for row in rows if row["k"] in ("@online.challenge_p1", "@online.challenge_p2")]
                    self.assertEqual([row["k"] for row in players], ["@online.challenge_p1", "@online.challenge_p2"])
                    self.assertTrue(players[0]["plate"].endswith("t4_rank_13.svg"))
                    self.assertEqual(players[0]["v"], i18n.message("t4.side_rank", name=i18n.literal("Host"),
                                                               rank=i18n.literal("Initiate")))
                    self.assertEqual(players[1]["v"], i18n.message("t4.side_you", name=i18n.literal("Guest")))
                    self.assertTrue(players[1]["accent"])

    def test_all_day_one_states_localize_and_hide_empty_rank(self):
        for language in i18n.LANGUAGES:
            self.nav.language = language
            for phase in ("logged_in", "matched", "starting", "playing", "result", "result_sent"):
                self.a.snapshot["phase"] = phase
                for index, item in enumerate(self.nav.items()):
                    if item.get("kind") == "heading":
                        continue
                    self.nav.focus["t4:online"] = index
                    view = self.nav.view()
                    self.assertNotIn("@online.", str(view), (language, phase, item.get("id")))
                    self.assertFalse(any(row["k"] == i18n.text(language, "online.rank") for row in view["detail"]["rows"]))
        self.a.snapshot.update(phase="logged_in", rank="Checked rank")
        self.nav.focus["t4:online"] = 0
        self.assertIn("Checked rank", str(self.nav.view()))

    def test_chat_and_lobby_names_render_as_plain_text(self):
        qml = (Path(__file__).resolve().parents[1] / "openrecomp" / "ui" / "Hub.qml").read_text(encoding="utf-8")
        for binding in ('row.r.label', 'row.r.value', 'hub.d.title', 'hub.d.lead', 'parent.r.v'):
            self.assertIn('textFormat: Text.PlainText; text: ' + binding, qml)
        overlays = (Path(__file__).resolve().parents[1] / "openrecomp" / "ui" / "Overlays.qml").read_text(encoding="utf-8")
        self.assertIn('textFormat: Text.PlainText; text: ov.v.osk.text;', overlays)

    def test_remote_catalog_shaped_text_stays_literal_in_every_language(self):
        literal = "@online.logout"
        self.a.snapshot.update(phase="logged_in", name=literal, rank=literal,
                               players=[dict(id="rival", name=literal, rank=literal)],
                               rooms=[dict(id="open", name=literal)],
                               chat=[dict(name=literal, text=literal)],
                               challenge=dict(id="incoming", name=literal))
        self.a.texts["online_chat"] = literal
        for language in i18n.LANGUAGES:
            self.nav.language = language
            for iid in ("online_status", "challenge:rival", "join_room:open", "chat:0", "online_chat", "accept_challenge"):
                self.choose(iid)
                view = self.nav.view()
                detail = view["detail"]
                self.assertIn(literal, str(detail) + str(view["rows"]), (language, iid))
                if iid == "chat:0":
                    self.assertEqual(detail["title"], literal)
                    self.assertEqual(detail["lead"], literal)
                if self.nav.overlay == "osk":
                    self.nav.act("back")
            self.assertEqual(i18n.localize(i18n.literal(literal), language), literal)
            self.assertEqual(i18n.localize(literal, language), i18n.text(language, "online.logout"))
        self.a.snapshot.update(phase="matched", match=dict(opponent=literal))
        self.nav.focus["t4:online"] = 0
        self.assertIn(literal, str(self.nav.view()["detail"]["rows"]))


if __name__ == "__main__":
    unittest.main()
