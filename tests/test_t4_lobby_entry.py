"""Shared lobby entry and invitation dialogs, driven without games or network."""
import unittest

from openrecomp import i18n
from openrecomp.nav import Game, Nav
import test_online_nav as online_fakes


class LobbyModes(online_fakes.Lobby):
    def __init__(self, game="t4"):
        super().__init__()
        self.m.update(id=game, adapter=game, sections=["play", "online", "settings"])
        self.snapshot.update(capabilities=dict(lobby=True, match_flow=True, direct_available=game == "t4"),
                             players=[], rooms=[], chat=[])

    def online_action(self, action):
        super().online_action(action)
        if action in ("mode_direct", "mode_lobby"):
            self.snapshot["capabilities"]["direct_ip"] = action == "mode_direct"
        elif action == "disconnect":
            self.snapshot["phase"] = "offline"
        elif action in ("accept_challenge", "decline_challenge"):
            self.snapshot.pop("challenge", None)


class T4LobbyEntry(unittest.TestCase):
    choose = online_fakes.OnlineNavigation.choose

    def setUp(self):
        self.a = LobbyModes()
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec["t4"] = "online"

    def test_direct_connection_is_only_under_advanced_and_back_restores_lobby(self):
        self.assertNotIn("mode_direct", [row.get("id") for row in self.nav.items()])
        self.nav.sec["t4"] = "settings"
        direct = next(row for row in self.nav.items() if row.get("id") == "mode_direct")
        self.assertEqual(direct["settingsGroup"], "advanced")
        self.assertEqual(direct["label"], "@t4.direct_advanced")
        self.choose("mode_direct")
        self.assertEqual(self.nav.section(), "online")
        self.assertIn("host", [row.get("id") for row in self.nav.items()])
        self.nav.act("back", device="xbox")
        self.assertEqual(self.nav.section(), "settings")
        self.assertEqual(self.a.calls[-2:], [("online", "disconnect"), ("online", "mode_lobby")])
        self.nav.sec["t4"] = "online"
        self.assertIn("login_guest", [row.get("id") for row in self.nav.items()])

    def test_advanced_direct_is_disabled_during_lobby_session(self):
        self.a.snapshot["phase"] = "logged_in"
        self.nav.sec["t4"] = "settings"
        row = next(row for row in self.nav.items() if row.get("id") == "mode_direct")
        self.assertTrue(row["disabled"])
        self.choose("mode_direct")
        self.assertEqual(self.a.calls, [])

    def test_both_games_use_same_invitation_dialog_in_all_catalogs(self):
        for game in ("t4", "t5dr"):
            for language in i18n.LANGUAGES:
                with self.subTest(game=game, language=language):
                    a = LobbyModes(game)
                    a.snapshot.update(phase="logged_in", challenge=dict(id="offer", name="@online.logout",
                                      ping=34, ping_measured=True, ping_path="relay"))
                    nav = Nav([Game(a.m, a)], language=language)
                    nav.screen, nav.sec[game] = "hub", "online"
                    nav.tick(0)
                    self.assertEqual(nav.overlay, "dialog")
                    dialog = nav.view()["dialog"]
                    self.assertIn("@online.logout", dialog["title"])
                    self.assertIn("34", dialog["text"])
                    self.assertIn(i18n.text(language, "online_ui.path_relay"), dialog["text"])
                    self.assertEqual(dialog["options"][0]["label"], i18n.text(language, "online.decline_challenge"))
                    self.assertTrue(dialog["options"][0]["focused"])
                    nav.act("right", device="xbox")
                    nav.act("confirm", device="xbox")
                    self.assertEqual(a.calls[-1], ("online", "accept_challenge"))

    def invite(self, challenge_id="offer"):
        self.a.snapshot.update(phase="logged_in", challenge=dict(id=challenge_id, name="Rival"))
        self.nav.tick(0)

    def test_back_declines_and_each_invitation_is_shown_once(self):
        self.invite()
        self.nav.act("back", device="xbox")
        self.assertEqual(self.a.calls[-1], ("online", "decline_challenge"))
        self.invite()
        self.assertIsNone(self.nav.overlay)
        self.invite("new-offer")
        self.assertEqual(self.nav.overlay, "dialog")

    def test_expired_invitation_cannot_accept_its_replacement(self):
        self.invite()
        self.a.snapshot["challenge"] = dict(id="replacement", name="Other")
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls, [])
        self.nav.tick(0)
        self.assertEqual(self.nav.online_challenge[1], "replacement")

    def test_busy_lobby_request_keeps_invitation_available_for_retry(self):
        self.invite()
        self.a.snapshot["busy"] = True
        self.nav.act("right", device="xbox")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.nav.overlay, "dialog")
        self.assertEqual(self.a.calls, [])
        self.a.snapshot["busy"] = False
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls[-1], ("online", "accept_challenge"))

    def test_new_session_can_reuse_an_invitation_id(self):
        self.invite()
        self.nav.act("back", device="xbox")
        self.a.snapshot["phase"] = "offline"
        self.nav.tick(0)
        self.invite()
        self.assertEqual(self.nav.overlay, "dialog")

    def test_popup_waits_for_keyboard_and_closes_when_invitation_expires(self):
        self.choose("online_name")
        self.invite()
        self.assertEqual(self.nav.overlay, "osk")
        self.nav.act("back", device="xbox")
        self.nav.tick(0)
        self.assertEqual(self.nav.overlay, "dialog")
        self.a.snapshot.pop("challenge")
        self.nav.tick(0)
        self.assertIsNone(self.nav.overlay)
        self.assertEqual(self.a.calls, [])

    def test_game_result_shows_outcome_and_round_score_for_each_side(self):
        for language in i18n.LANGUAGES:
            self.nav.language = language
            for winner, slot, key in ((0, 0, "online.result_won"), (0, 1, "online.result_lost"),
                                      (None, 1, "online.result_draw")):
                with self.subTest(language=language, winner=winner, slot=slot):
                    self.a.snapshot.update(phase="result_sent", result=dict(winner=winner, slot=slot, score=[2, 1]))
                    self.nav.focus["t4:online"] = 0
                    rows = self.nav.view()["detail"]["rows"]
                    values = {row["k"]: row["v"] for row in rows}
                    self.assertEqual(values[i18n.text(language, "online.result")], i18n.text(language, key))
                    self.assertEqual(values[i18n.text(language, "online.score")], "2–1")


if __name__ == "__main__":
    unittest.main()
