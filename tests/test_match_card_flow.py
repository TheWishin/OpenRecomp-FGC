"""The ready card retains its identity, compact terms and passive live lobby through start."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters.t5_online import Online
from tools.online_shots import scene


class MatchCardFlow(unittest.TestCase):
    def test_both_picks_and_localized_starting_survive_ready(self):
        for game in ("t4", "t5"):
            for language in ("de", "en"):
                nav = scene(game, "matched_picks", language)
                before = nav.view()["matchVersus"]
                nav.game.a.snapshot.update(phase="starting", message="@online.waiting_peer_ready")
                nav.game.a.snapshot["match"]["opponent_ready"] = False
                waiting = nav.view()
                self.assertFalse(waiting["matchVersus"]["starting"])
                self.assertTrue(waiting["matchVersus"]["waiting"])
                self.assertTrue(waiting["matchVersus"]["disabled"])
                for field in ("status", "readyLabel"):
                    self.assertEqual(waiting["matchVersus"][field], i18n.text(language, "online.waiting_peer_ready"))
                self.assertEqual(waiting["online"]["title"], i18n.text(language, "online.waiting_peer_ready"))
                nav.game.a.snapshot["match"]["opponent_ready"] = True
                nav.game.a.snapshot["message"] = "@online.starting"
                after = nav.view()
                for side in ("left", "right"):
                    self.assertTrue(after["matchVersus"][side]["picked"])
                    self.assertEqual(after["matchVersus"][side]["fighter"], before[side]["fighter"])
                self.assertTrue(after["matchVersus"]["starting"])
                self.assertFalse(after["matchVersus"]["waiting"])
                self.assertEqual(after["matchVersus"]["startingLabel"], i18n.text(language, "online.starting"))
                self.assertEqual(after["online"]["title"], i18n.text(language, "online.starting"))
                self.assertTrue(after["online"]["chat"]["compose"])
                self.assertEqual(nav.game.a.calls, [])

    def test_requested_connection_terms_have_one_compact_line(self):
        for game in ("t4", "t5"):
            for language in ("en", "de"):
                nav = scene(game, "matched", language)
                for path in ("direct", "relay"):
                    nav.game.a.snapshot["match"]["ping_path"] = path
                    line = nav.view()["matchVersus"]["infoLine"]
                    for text in ("Delay 2", i18n.text(language, "online.casual_mode"),
                                 "3 " + i18n.text(language, "feedback.rounds"), "42 ms",
                                 i18n.text(language, "online_ui.path_" + path)):
                        self.assertIn(text, line)
                    self.assertNotIn(i18n.text(language, "netext.online_feel"), line)
                    self.assertNotIn("\n", line)

    def test_live_backdrop_has_no_action_indices_and_respects_ranked_capability(self):
        for game in ("t4", "t5"):
            nav = scene(game, "matched", "en")
            nav.game.a.snapshot["players"][0]["name"] = "Fresh peer"
            memory = dict(nav.focus)
            nav.arcade_selected = {nav.game.id: "p1"}
            backdrop = nav.view()["online"]["backdrop"]
            self.assertEqual(nav.focus, memory)
            self.assertEqual(nav.arcade_selected[nav.game.id], "p1")
            self.assertIn("Fresh peer", [p["name"] for p in backdrop["arcade"]["players"]])
            self.assertEqual(backdrop["find"]["ranked"]["present"], game == "t5")

            def indices(value):
                if isinstance(value, dict):
                    if "index" in value:
                        self.assertEqual(value["index"], -1)
                    for child in value.values():
                        indices(child)
                elif isinstance(value, list):
                    for child in value:
                        indices(child)
            indices(backdrop)
            self.assertEqual(nav.game.a.calls, [])

    def test_launch_worker_only_waits_for_remaining_starting_dwell(self):
        owner = mock.Mock(_online_starting_until=10.35)
        with mock.patch("openrecomp.adapters.t5_online.time.monotonic", return_value=10.1), mock.patch(
                "openrecomp.adapters.t5_online.threading.Event") as event:
            Online._online_starting_pause(owner)
            self.assertAlmostEqual(event.return_value.wait.call_args.args[0], .25)
        with mock.patch("openrecomp.adapters.t5_online.time.monotonic", return_value=11), mock.patch(
                "openrecomp.adapters.t5_online.threading.Event") as event:
            Online._online_starting_pause(owner)
            event.assert_not_called()


if __name__ == "__main__":
    unittest.main()
