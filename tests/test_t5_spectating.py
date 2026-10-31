"""Spectator requests and races with inert clients and game handles only."""
import os
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp.adapters import t5_spectating as spec
from openrecomp import nav_spectating


class Client:
    def __init__(self):
        self.friend_list = dict(friends=[dict(name="Friend", watch=True), dict(name="Private", watch=False)])
        self.rooms = [dict(id="room", name="Room", watch=True),
                      dict(id="group", name="Group", mode="tables", tables=[dict(id=2, watch=True)])]
        self.my_room = None
        self.me = dict(id="self", status="idle")
        self.match = None
        self.spec_watch = None
        self.spec_generation = 1
        self.calls = []
        self.cancel_watch = mock.Mock(side_effect=self.cancel)
        self.set_spectate_prefs = mock.Mock()

    def cancel(self):
        self.spec_generation += 1
        self.spec_watch = None

    def has_spectate(self):
        return True

    def watch(self, name=None, room=None, tournament=None, set_id=None, table=None, generation=None):
        self.calls.append(dict(name=name, room=room, tournament=tournament, set_id=set_id,
                               table=table, generation=generation))
        self.spec_watch = dict(stream="live", path="local-stream")
        return dict(stream="live", players=[dict(name="One"), dict(name="Two")], ranked=False)


class Owner:
    online_package = "t5lobby"

    def __init__(self, folder):
        self.s = dict(spectators=True, spectators_ranked=False, auto_spectate=False)
        self.folder = folder
        self._online_client = Client()
        self._online_generation = 0
        self._online_phase = "logged_in"
        self._online_busy = False
        self._online_message = ""
        self._online_lock = threading.RLock()
        self._online_match = {}
        self.game = None
        self.queue = []
        self.started = []
        self.problem = ""
        spec.init(self)
        spec.client_created(self, self._online_client)

    def _online_out_dir(self):
        return self.folder

    def _online_game_check(self):
        return self.problem

    def _online_submit(self, operation, work):
        self._online_busy = True
        self.queue.append((operation, work))

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("@online.cancelled")

    def _online_error(self, error):
        return str(error)

    def finish(self):
        operation, work = self.queue.pop(0)
        try:
            value, error = work(), None
        except Exception as exc:
            value, error = None, exc
        self._online_busy = False
        spec.completion(self, operation, value, error)

    def start(self, extra_env):
        self.started.append(extra_env)
        self.game = SimpleNamespace(running=mock.Mock(return_value=True), stop=mock.Mock())


class SpectatingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.owner = Owner(self.temp.name)
        self.native = SimpleNamespace(watch_env=mock.Mock(return_value=dict(SPECTATOR="1")))
        self.loader = mock.patch.object(spec, "_module", return_value=self.native)
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def watch(self, action="spec_watch_friend:Friend"):
        self.assertTrue(spec.action(self.owner, action, self.owner._online_client))
        self.owner.finish()
        self.owner.finish()

    def test_snapshot_is_private_and_does_not_request_or_launch(self):
        state = spec.state(self.owner)
        self.assertTrue(state["capabilities"]["spectating"])
        self.assertEqual([row["id"] for row in state["spectating"]["targets"]],
                         ["spec_watch_friend:Friend", "spec_watch_room:room", "spec_watch_table:group:2"])
        self.assertNotIn("path", str(state))
        self.assertEqual(self.owner.queue, [])
        self.assertEqual(self.owner.started, [])
        self.owner._online_client.set_spectate_prefs.assert_called_once_with(True, False)

    def test_advertised_watch_delegates_then_starts_native_spectator(self):
        self.watch()
        self.assertEqual(self.owner._online_client.calls[0]["name"], "Friend")
        self.assertEqual(self.owner.started, [dict(SPECTATOR="1")])
        self.native.watch_env.assert_called_once_with("local-stream",
            os.path.join(self.temp.name, "logs", "online", "watch-verdict.json"),
            os.path.join(self.temp.name, "logs", "online", "watch-status.json"))
        snapshot = spec.state(self.owner)["spectating"]
        self.assertEqual(snapshot["state"], "starting")
        self.assertNotIn("local-stream", str(snapshot))

    def test_unadvertised_target_and_unsolicited_ready_cannot_launch(self):
        spec.action(self.owner, "spec_watch_friend:Private", self.owner._online_client)
        self.assertEqual(self.owner.queue, [])
        self.assertEqual(self.owner._online_message, "@online.watch_unavailable")
        spec.event(self.owner, dict(t="spec_ready", stream="live", path="untrusted"))
        self.assertEqual(self.owner.started, [])

    def test_table_watch_keeps_native_table_type(self):
        self.watch("spec_watch_table:group:2")
        call = self.owner._online_client.calls[0]
        self.assertEqual((call["room"], call["table"]), ("group", 2))

    def test_tournament_watch_requires_advertised_other_players_live_set(self):
        from openrecomp.adapters import t5_tournaments
        self.owner._online_name = "Self"
        data = dict(tournaments=dict(selected="cup", detail=dict(bracket=dict(sets=[
            dict(id="set-1", live="playing", watch=True, p=["One", "Two"])]))))
        with mock.patch.object(t5_tournaments, "state", return_value=data):
            self.watch("spec_watch_tour:cup:set-1")
        call = self.owner._online_client.calls[0]
        self.assertEqual((call["tournament"], call["set_id"]), ("cup", "set-1"))
        spec.action(self.owner, "spec_stop", self.owner._online_client)
        data["tournaments"]["detail"]["bracket"]["sets"][0]["p"] = ["Self", "Two"]
        with mock.patch.object(t5_tournaments, "state", return_value=data):
            spec.action(self.owner, "spec_watch_tour:cup:set-1", self.owner._online_client)
        self.assertEqual(self.owner.queue, [])

    def test_late_watch_reply_after_cancel_does_not_own_game(self):
        client = self.owner._online_client
        spec.action(self.owner, "spec_watch_friend:Friend", client)
        operation, worker = self.owner.queue.pop()
        reply = worker()
        spec.action(self.owner, "spec_stop", client)
        self.owner._online_busy = False
        spec.completion(self.owner, operation, reply, None)
        self.assertIsNone(self.owner._spec_view)
        self.assertEqual(self.owner.started, [])
        self.assertEqual(self.owner.queue, [])

    def test_stop_cancels_queued_watch_without_sending_or_starting(self):
        client = self.owner._online_client
        spec.action(self.owner, "spec_watch_friend:Friend", client)
        spec.action(self.owner, "spec_stop", client)
        self.owner.finish()
        self.assertEqual(client.calls, [])
        self.assertEqual(self.owner.started, [])
        client.cancel_watch.assert_called_once()

    def test_match_preempts_pending_start_and_owned_viewer(self):
        spec.action(self.owner, "spec_watch_friend:Friend", self.owner._online_client)
        self.owner.finish()
        spec.event(self.owner, dict(t="match_found", match="own"))
        self.owner.finish()
        self.assertEqual(self.owner.started, [])
        self.owner._spec_view = None
        self.watch()
        game = self.owner.game
        spec.event(self.owner, dict(t="tour_call", tournament="tour"))
        game.stop.assert_called_once()
        self.assertEqual(spec.state(self.owner)["spectating"]["state"], "over")

    def test_stop_never_stops_match_drivers_game(self):
        self.watch()
        self.owner._online_driver = SimpleNamespace(game=self.owner.game)
        spec.action(self.owner, "spec_stop", self.owner._online_client)
        self.owner.game.stop.assert_not_called()

    def test_privacy_end_stops_owned_game_immediately(self):
        self.watch()
        game = self.owner.game
        spec.event(self.owner, dict(t="spec_end", stream="live", reason="not_allowed"))
        game.stop.assert_called_once()
        self.assertEqual(self.owner._spec_view["state"], "over")

    def test_ended_subscription_before_reply_never_launches(self):
        spec.action(self.owner, "spec_watch_friend:Friend", self.owner._online_client)
        operation, worker = self.owner.queue.pop()
        value = worker()
        self.owner._online_client.spec_watch = None
        spec.event(self.owner, dict(t="spec_end", stream="live", reason="not_allowed"))
        self.owner._online_busy = False
        spec.completion(self.owner, operation, value, None)
        self.assertEqual(self.owner.started, [])
        self.assertEqual(self.owner.queue, [])

    def test_auto_spectate_uses_installed_policy_only_after_opt_in(self):
        policy = SimpleNamespace(due=mock.Mock(return_value=dict(name="Friend")),
                                 attempted=mock.Mock(), pause=mock.Mock())
        self.native.Policy = mock.Mock(return_value=policy)
        self.assertFalse(spec.poll(self.owner))
        self.native.Policy.assert_not_called()
        self.owner.s["auto_spectate"] = True
        self.assertTrue(spec.poll(self.owner))
        policy.due.assert_called_once()
        policy.attempted.assert_called_once()
        self.assertEqual(len(self.owner.queue), 1)
        self.owner.s["auto_spectate"] = False
        spec.poll(self.owner)
        self.owner.finish()
        self.assertEqual(self.owner.started, [])

    def test_running_game_and_busy_match_refuse_watch(self):
        self.owner.problem = "@online.game_running"
        spec.action(self.owner, "spec_watch_room:room", self.owner._online_client)
        self.assertEqual(self.owner.queue, [])
        self.assertEqual(self.owner._online_message, "@online.game_running")
        self.owner.problem = ""
        self.owner._online_match = dict(id="own")
        spec.action(self.owner, "spec_watch_room:room", self.owner._online_client)
        self.assertEqual(self.owner.queue, [])

    def test_controller_stop_remains_available_while_request_is_pending(self):
        spec.action(self.owner, "spec_watch_room:room", self.owner._online_client)
        nav = SimpleNamespace(_online_action=mock.Mock())
        game = SimpleNamespace(a=self.owner)

        def action(iid, label):
            return dict(id=iid, label=label, disabled=True, detail=dict(rows=[]))
        rows = nav_spectating.rows(nav, game, spec.state(self.owner), action)
        stop = next(r for r in rows if r.get("id") == "spec_stop")
        self.assertFalse(stop["disabled"])
        stop["run"]()
        nav._online_action.assert_called_once_with(game, "spec_stop")

    def test_tournament_call_and_ranked_lock_block_manual_and_auto_watch(self):
        self.owner.s["auto_spectate"] = True
        self.native.Policy = mock.Mock()
        for field, value in (("_online_tours", dict(call=dict(tournament="cup", set="one"))),
                             ("_online_character_locked", True)):
            setattr(self.owner, field, value)
            spec.action(self.owner, "spec_watch_friend:Friend", self.owner._online_client)
            self.assertFalse(spec.poll(self.owner))
            self.assertEqual(self.owner.queue, [])
            self.native.Policy.assert_not_called()
            delattr(self.owner, field)

    def test_privacy_end_revokes_a_queued_spectator_start(self):
        spec.action(self.owner, "spec_watch_friend:Friend", self.owner._online_client)
        self.owner.finish()
        spec.event(self.owner, dict(t="spec_end", stream="live", reason="not_allowed"))
        self.owner.finish()
        self.assertEqual(self.owner.started, [])
        self.assertEqual(self.owner._spec_view["state"], "over")

    def test_absent_native_auto_policy_reports_unavailable_without_launch(self):
        self.owner.s["auto_spectate"] = True
        with mock.patch.object(spec, "_module", side_effect=ImportError):
            self.assertTrue(spec.poll(self.owner))
            self.assertFalse(spec.poll(self.owner))
        self.assertEqual(self.owner._online_message, "@online.watch_unavailable")
        self.assertEqual(self.owner.started, [])


if __name__ == "__main__":
    unittest.main()
