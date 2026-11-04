"""Ranked and FT set contracts with inert clients and a fake native driver."""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters.t5_match import T5Match, _DriverClient
from openrecomp import i18n
import test_t5_match_flow as flow


class SetTests(unittest.TestCase):
    setUp = flow.T5MatchTests.setUp
    login = flow.T5MatchTests.login
    match = flow.T5MatchTests.match
    start = flow.T5MatchTests.start

    def offer(self, client, **info):
        client.events.put(dict(t="match_found", match="one", slot=1,
                              set=dict(id="set-one", rated=True, locked=True, wins=[1, 0],
                                       best_of=3, number=2, **info)))
        self.a.online_poll()
        self.a.online_poll()

    def test_ranked_set_locks_character_and_exposes_score_from_own_side(self):
        client = self.login()
        self.offer(client)
        state = self.a.online_state()
        self.assertTrue(state["character_locked"])
        self.assertEqual(state["set"]["wins"], [0, 1])
        self.assertEqual(state["set"]["best_of"], 3)
        state["set"]["wins"][0] = 50
        self.assertEqual(self.a.online_state()["set"]["wins"], [0, 1])

    def test_lock_survives_result_and_only_current_set_end_unlocks(self):
        client = self.login()
        self.offer(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed",
                               set=dict(id="set-one", rated=True, locked=True, wins=[1, 0],
                                        best_of=3, next=dict(number=2, **{"in": 5}))))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["character_locked"])
        client.events.put(dict(t="set_end", set="other-set", rated=True, result="loss"))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["character_locked"])
        client.events.put(dict(t="set_end", set="set-one", rated=True, result="win", wins=[2, 1],
                               status="confirmed", rating=dict(before=dict(r=1400), after=dict(r=1432), delta=32),
                               token="private-token", address="private-address"))
        self.a.online_poll()
        state = self.a.online_state()
        self.assertFalse(state["character_locked"])
        self.assertEqual(state["set"]["wins"], [2, 1])
        self.assertEqual(state["set"]["rating"], dict(before=1400, after=1432, delta=32))
        self.assertEqual(state["message"], "@online.set_won")
        self.assertNotIn("private-", str(state))

    def test_casual_first_to_continuation_keeps_existing_ready_authority(self):
        client = self.match()
        self.start(client)
        client.events.put(dict(t="match_result", match="one", status="confirmed",
                               set=dict(id="ft", casual=True, first_to=3, wins=[1, 0],
                                        next=dict(number=2, **{"in": 5}))))
        client.events.put(dict(t="match_found", match="two", ready_check=False, origin="set",
                               set=dict(id="ft", casual=True, first_to=3, wins=[1, 0])))
        client.events.put(dict(t="match_start", match="two", **{"continue": True}))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 2)
        self.assertEqual(self.a.online_state()["set"]["first_to"], 3)
        self.assertEqual(self.a.online_state()["phase"], "playing")
        client.ready.assert_called_once_with(True)

    def test_unaccepted_match_cannot_authorize_later_set_game(self):
        client = self.match()
        client.events.put(dict(t="match_result", match="one", set=dict(rated=True, next=dict(number=2))))
        self.a.online_poll()
        self.a._online_driver_notes([dict(kind="set_next", match="one")])
        self.assertFalse(self.a._online_next_authorized)
        client.events.put(dict(t="match_found", match="two", ready_check=False, origin="set"))
        client.events.put(dict(t="match_start", match="two", **{"continue": True}))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.started, 0)
        self.assertEqual(self.a.online_state()["phase"], "matched")

    def test_decided_ranked_set_keeps_native_new_set_rematch_window(self):
        client = self.login()
        client.ready = mock.Mock(return_value={})
        self.offer(client)
        self.start(client)
        client.events.put(dict(t="match_result", match="one", rematch_window=20, status="confirmed",
                               set=dict(id="set-one", rated=True, locked=True, wins=[2, 1], state="ended")))
        client.events.put(dict(t="set_end", set="set-one", rated=True, reason="decided", result="win",
                               wins=[2, 1], status="confirmed"))
        self.a.online_poll()
        self.a.online_poll()
        self.assertFalse(self.a.online_state()["character_locked"])
        self.assertTrue(self.a.online_state()["capabilities"]["rematch"])
        self.a.online_action("rematch")
        self.a.online_poll()
        self.assertEqual(self.a.fake_driver.rematches, [("one", True)])

    def test_leaving_set_revokes_authority_before_request_and_blocks_late_offer(self):
        client = self.login()
        client.ready = mock.Mock(return_value={})
        client.leave_set = mock.Mock(return_value={})
        self.offer(client)
        self.start(client)
        client.events.put(dict(t="match_result", match="one", set=dict(
            id="set-one", rated=True, locked=True, wins=[1, 0], next=dict(number=2, **{"in": 5}))))
        self.a.online_poll()
        self.assertTrue(self.a.online_state()["capabilities"]["leave_set"])
        self.a.online_action("leave_set")
        self.assertFalse(self.a._online_authorized)
        self.assertFalse(self.a._online_next_authorized)
        self.a._online_match_found(dict(t="match_found", match="late", ready_check=False, origin="set"))
        self.assertEqual(self.a._online_match_id, "one")
        self.a.online_poll()
        client.leave_set.assert_called_once_with()
        self.assertFalse(self.a.online_state()["character_locked"])
        self.assertEqual(self.a.online_state()["phase"], "logged_in")
        client.events.put(dict(t="set_end", set="set-one", rated=True, result="loss"))
        self.a.online_poll()
        self.a.online_poll()
        self.assertTrue(any(event["t"] == "set_end" for event in self.a.fake_driver.events))

    def test_old_install_retains_sets_without_unavailable_native_game_helpers(self):
        module = SimpleNamespace(__file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
                                 game_files=mock.Mock(return_value=[]))
        with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module):
            self.assertEqual(self.a._online_match_client_options(),
                             dict(sets=True, ingame_pick=False, ingame_rematch=False, auto_skip_after_round=False))

    def test_native_game_capabilities_drive_opt_ins_and_driver_parameter(self):
        client = self.match()
        client.ingame_rematch = True
        driver_factory = mock.Mock(spec=lambda client, launch, workdir, ingame_rematch=None, **kwargs: None)
        # Keep an inspectable runtime signature, as installed MatchDriver has.
        def factory(client, launch, workdir, ingame_rematch=None, **kwargs):
            return driver_factory(client, launch, workdir, ingame_rematch=ingame_rematch, **kwargs)
        module = SimpleNamespace(__file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
                                 game_files=mock.Mock(return_value=["inert-file"]),
                                 game_supports_pick=mock.Mock(return_value=True),
                                 game_supports_ingame_ui=mock.Mock(return_value=True),
                                 game_supports_auto_skip=mock.Mock(return_value=True), MatchDriver=factory)
        with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module), \
                mock.patch.dict(os.environ, T5_INGAME_REMATCH="1"):
            options = self.a._online_match_client_options()
            self.assertTrue(options["sets"])
            self.assertTrue(options["ingame_pick"])
            self.assertTrue(options["ingame_rematch"])
            self.assertTrue(options["auto_skip_after_round"])
            T5Match._online_make_driver(self.a, client, self.a._online_generation)
        self.assertTrue(driver_factory.call_args.kwargs["ingame_rematch"])
        self.assertIsInstance(driver_factory.call_args.args[0], _DriverClient)

    def test_screen_side_reaches_a_driver_that_takes_it(self):
        # 1.2.0's MatchDriver reads screen_side() per match (T5_SCREEN_SIDE); 1.1.9's has no such parameter.
        client = self.match()
        calls = []

        def new_driver(client, launch, workdir, always_left=None, screen_side=None, **kwargs):
            calls.append(dict(always_left=always_left, screen_side=screen_side))

        def old_driver(client, launch, workdir, always_left=None, **kwargs):
            calls.append(dict(always_left=always_left, extra=sorted(kwargs)))

        self.a.screen_side = lambda: "right"
        for factory in (new_driver, old_driver):
            module = SimpleNamespace(__file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
                                     game_files=mock.Mock(return_value=[]), MatchDriver=factory)
            with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module):
                T5Match._online_make_driver(self.a, client, self.a._online_generation)
        self.assertEqual(calls[0]["screen_side"](), "right")
        self.assertNotIn("screen_side", calls[1]["extra"])
        self.assertTrue(callable(calls[1]["always_left"]))

    def test_ingame_rematch_needs_the_native_switch_as_in_the_1_2_0_launcher(self):
        # 1.2.0's tk_tab announces in-game rematch only with T5_INGAME_REMATCH=1 and a game that has it.
        module = SimpleNamespace(__file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
                                 game_files=mock.Mock(return_value=["inert-file"]),
                                 game_supports_ingame_ui=mock.Mock(return_value=True),
                                 game_supports_auto_skip=mock.Mock(return_value=True))
        with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module):
            for value in (None, "0", "1"):
                env = {} if value is None else dict(T5_INGAME_REMATCH=value)
                with mock.patch.dict(os.environ, env):
                    if value is None:
                        os.environ.pop("T5_INGAME_REMATCH", None)
                    options = self.a._online_match_client_options()
                self.assertEqual(options["ingame_rematch"], value == "1", value)
                self.assertEqual(options["auto_skip_after_round"], value == "1", value)

    def test_auto_skip_opt_in_requires_both_native_game_markers(self):
        module = SimpleNamespace(__file__=self.directory.name + "/lobby/t5lobby/match_driver.py",
                                 game_files=mock.Mock(return_value=[]),
                                 game_supports_ingame_ui=mock.Mock(return_value=False),
                                 game_supports_auto_skip=mock.Mock(return_value=True))
        with mock.patch("openrecomp.adapters.t5_match.importlib.import_module", return_value=module):
            self.assertFalse(self.a._online_match_client_options()["auto_skip_after_round"])
        module.game_supports_auto_skip.assert_not_called()

    def test_native_menu_uses_catalog_language_and_preserves_policy_on_later_events(self):
        self.a.config["language"] = "de"
        self.a.fake_driver.offer_ingame_ui = mock.Mock()
        client = self.match()
        self.start(client)
        event = dict(t="match_result", match="one", status="confirmed", rematch_window=20,
                     rematch_ui=dict(v=1, policy="auto_unless_declined", timeout=20),
                     text="private server text")
        client.events.put(event)
        self.a.online_poll()
        self.a.online_poll()
        labels = self.a.fake_driver.offer_ingame_ui.call_args.args[1]
        self.assertEqual(labels["body"], i18n.text("de", "online.rematch_auto"))
        self.assertEqual(labels["auto"], i18n.text("de", "online.rematch_countdown", seconds="{seconds}"))
        self.assertNotIn("private server text", str(labels))
        later = dict(t="rematch", match="one", state="waiting")
        client.events.put(later)
        self.a.online_poll()
        self.a.online_poll()
        self.a.fake_driver.offer_ingame_ui.assert_called_with(later)

    def test_room_updates_reach_native_menu_and_still_update_online_room(self):
        client = self.match()
        client.events.put(dict(t="room", room=dict(id="room-one", name="Room", members=[])))
        self.a.online_poll()
        self.a.online_poll()
        self.assertEqual(self.a.online_state()["room"]["id"], "room-one")
        self.assertTrue(any(event["t"] == "room" for event in self.a.fake_driver.events))

    def test_native_ready_and_rematch_keep_session_checks_and_rollback_failure(self):
        client = self.match()
        proxy = _DriverClient(self.a, client, self.a._online_generation)
        client.rematch = mock.Mock(return_value={})
        proxy.ready(True, "one")
        self.assertTrue(self.a._online_authorized)
        self.assertEqual(self.a._online_phase, "starting")
        proxy.rematch("one", True, True)
        self.assertTrue(self.a._online_next_authorized)
        client.rematch.assert_called_once_with("one", True, True)
        with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
            proxy.rematch("other", True)
        self.a._online_next_authorized = False
        client.rematch.side_effect = RuntimeError("inert failure")
        with self.assertRaisesRegex(RuntimeError, "inert failure"):
            proxy.rematch("one", True)
        self.assertFalse(self.a._online_next_authorized)
        self.a.online_close()
        with self.assertRaisesRegex(RuntimeError, "@online.cancelled"):
            proxy.ready(True, "one")

    def test_declined_casual_ready_check_keeps_its_reason_when_the_unplayed_set_ends(self):
        # QA run (two launchers, local lobby): the declined player read "The set has ended." instead of
        # "The other player declined the match." (1.2.0 sends set_end right after match_cancel).
        for rated, reason, expected in ((False, "declined", "@online.peer_declined"),
                                        (True, "declined", "@online.peer_declined")):
            with self.subTest(rated=rated):
                self.setUp()
                client = self.login()
                client.events.put(dict(t="match_found", match="one", slot=0,
                                       set=dict(id="set-one", rated=rated, casual=not rated, first_to=1, wins=[0, 0])))
                self.a.online_poll()
                self.a.online_poll()
                client.events.put(dict(t="match_cancel", match="one", reason=reason))
                self.a.online_poll()
                client.events.put(dict(t="set_end", set="set-one", rated=rated, reason=reason, wins=[0, 0]))
                self.a.online_poll()
                self.a.online_poll()
                self.assertEqual(self.a.online_state()["phase"], "logged_in")
                self.assertEqual(self.a.online_state()["message"], expected)

    def test_close_releases_character_lock(self):
        client = self.login()
        self.offer(client)
        self.a.online_close()
        self.assertFalse(self.a.online_state()["character_locked"])
        self.assertEqual(self.a.online_state()["set"], {})


if __name__ == "__main__":
    unittest.main()
