"""Tournament controller commands use client doubles, with no server or game."""
import json
import types
import unittest
from unittest import mock

from openrecomp.adapters import t5_tournaments as tours
from openrecomp import nav_tournaments


def tournament(tid="cup", **values):
    result = dict(id=tid, name="Friday Cup", state="signup", format="double", set_wins=2,
                  players=2, max_players=16, can_manage=True, organizer="Host",
                  you=dict(entrant=False, build_ok=True), entrants=[dict(name="One"), dict(name="Two")],
                  standings=[], bracket=dict(format="double", rounds=1, losers_rounds=0,
                                             sets=[dict(id="W1-1", state="ready", p=["One", "Two"],
                                                        bracket="W", round=1, index=1)]))
    result.update(values)
    return result


class Client:
    tournaments = True

    def __init__(self):
        self.calls = []
        self.current = tournament()
        self.welcome = dict(features=["tournaments"], caps=["tournaments"])

    def tour_list(self):
        self.calls.append(("list",))
        return dict(rows=[self.current], can_create=True)

    def tour_get(self, tid):
        self.calls.append(("get", tid))
        return self.current

    def tour_create(self, name, **kw):
        self.calls.append(("create", name, kw))
        return tournament(name=name)

    def tour_join(self, tid):
        self.calls.append(("join", tid))
        return tournament(you=dict(entrant=True, build_ok=True))

    def tour_leave(self, tid):
        self.calls.append(("leave", tid))
        return tournament(you=dict(entrant=False))

    def tour_checkin(self, tid):
        self.calls.append(("checkin", tid))
        return tournament(state="checkin", you=dict(entrant=True, checked_in=True))

    def tour_admin(self, tid, operation, **kw):
        self.calls.append(("admin", tid, operation, kw))
        return self.current

    def tour_accept(self, tid, sid):
        self.calls.append(("accept", tid, sid))


class Owner:
    def __init__(self):
        self._online_client = Client()
        self._online_fields = {}
        self._online_generation = 1
        self._online_message = ""
        self._online_account = True
        self.work = None
        self._online_game_check = mock.Mock(return_value="")
        tours.init(self)

    def _online_submit(self, operation, work):
        self.work = operation, work

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("@online.cancelled")

    def _online_error(self, error):
        return "@online.failure"

    def text_value(self, tid):
        return self._online_fields.get(tid, "")

    def act(self, action):
        self.work = None
        self.assert_handled = tours.action(self, action, self._online_client)
        if self.work:
            operation, work = self.work
            tours.completion(self, operation, work(), None)


class TournamentTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client

    def select(self):
        self.owner.act("tour_refresh")
        self.owner.act("tour_select:cup")

    def test_snapshots_and_init_never_request_data(self):
        tours.init(self.owner)
        first = tours.state(self.owner)
        first["tournaments"]["options"]["set_wins"] = 99
        self.assertEqual(tours.state(self.owner)["tournaments"]["options"]["set_wins"], 2)
        self.assertTrue(first["capabilities"]["tournaments"])
        self.assertEqual(self.client.calls, [])

    def test_list_get_join_checkin_leave_delegate_to_client(self):
        self.select()
        self.owner.act("tour_join:cup")
        self.assertTrue(tours.state(self.owner)["tournaments"]["detail"]["you"]["entrant"])
        self.owner._online_tours["detail"].update(state="checkin")
        self.owner.act("tour_checkin:cup")
        self.owner.act("tour_leave:cup")
        self.assertEqual(self.client.calls, [("list",), ("get", "cup"), ("join", "cup"),
                                            ("checkin", "cup"), ("leave", "cup")])

    def test_create_preserves_native_options_with_explicit_clock(self):
        self.owner.act("tour_refresh")
        self.owner._online_fields.update(online_tour_name="New Cup", online_tour_clock="20:30")
        self.owner.act("tour_option:format")
        with mock.patch.object(tours, "_clock", return_value=1234567890):
            self.owner.act("tour_create")
        self.assertEqual(self.client.calls[-1], ("create", "New Cup", dict(fmt="single", set_wins=2,
                                                                          start=1234567890, max_players=16,
                                                                          checkin_minutes=10, seeding="random")))
        self.assertEqual(self.owner._online_tours["selected"], "cup")

    def test_bad_name_clock_and_non_host_cannot_create(self):
        self.owner.act("tour_refresh")
        for name, clock in (("No", ""), ("Valid", "25:00"), ("Valid", "unknown")):
            self.owner._online_fields.update(online_tour_name=name, online_tour_clock=clock)
            self.owner.act("tour_create")
            self.assertEqual(self.owner._online_message, "@online.tour_invalid")
        self.owner._online_tours["can_create"] = False
        self.owner._online_fields.update(online_tour_name="Valid", online_tour_clock="")
        self.owner.act("tour_create")
        self.assertEqual(self.client.calls, [("list",)])

    def test_admin_changes_require_bound_review_and_revalidate_permissions(self):
        self.select()
        self.owner.act("tour_start:cup")
        self.assertEqual(self.owner._online_tours["pending"], "tour_start:cup")
        self.assertFalse(any(row[0] == "admin" for row in self.client.calls))
        self.owner.act("tour_confirm:tour_cancel:cup")
        self.assertEqual(self.owner._online_tours["pending"], "tour_start:cup")
        self.owner.act("tour_confirm:tour_start:cup")
        self.assertEqual(self.client.calls[-1], ("admin", "cup", "start", {}))
        self.owner._online_tours["detail"].update(can_manage=False)
        self.owner.act("tour_cancel:cup")
        self.assertEqual(self.owner._online_tours["pending"], "")

    def test_bracket_selection_report_override_reset_and_dq(self):
        self.client.current["state"] = "running"
        self.select()
        self.owner.act("tour_select_set:W1-1")
        self.owner.act("tour_win1:cup:W1-1")
        self.owner.act("tour_confirm:tour_win1:cup:W1-1")
        self.assertEqual(self.client.calls[-1], ("admin", "cup", "report", dict(set="W1-1", winner=1)))
        self.owner._online_tours["detail"]["bracket"]["sets"][0]["state"] = "done"
        self.owner.act("tour_win0:cup:W1-1")
        self.owner.act("tour_confirm:tour_win0:cup:W1-1")
        self.assertEqual(self.client.calls[-1], ("admin", "cup", "override", dict(set="W1-1", winner=0)))
        self.owner.act("tour_reset:cup:W1-1")
        self.owner.act("tour_confirm:tour_reset:cup:W1-1")
        self.assertEqual(self.client.calls[-1], ("admin", "cup", "reset", dict(set="W1-1")))
        self.owner._online_fields["online_tour_dq"] = "One"
        self.owner.act("tour_dq:cup:One")
        self.owner._online_fields["online_tour_dq"] = "Two"
        self.owner.act("tour_confirm:tour_dq:cup:One")
        self.assertEqual(self.client.calls[-1], ("admin", "cup", "reset", dict(set="W1-1")))
        self.owner.act("tour_dq:cup:Two")
        self.owner.act("tour_confirm:tour_dq:cup:Two")
        self.assertEqual(self.client.calls[-1], ("admin", "cup", "dq", dict(player="Two")))

    def test_stale_row_and_session_cannot_issue_tournament_call(self):
        self.select()
        self.owner.act("tour_join:other")
        self.owner.act("tour_select_set:old")
        self.assertEqual(self.owner._online_tours["selected_set"], "")
        self.assertEqual(self.client.calls, [("list",), ("get", "cup")])
        tours.action(self.owner, "tour_refresh", self.client)
        self.owner._online_generation += 1
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.owner.work[1]()

    def test_native_call_accept_has_deadline_identity_and_game_guard(self):
        tours.event(self.owner, dict(t="tour_call", tournament=dict(id="cup", name="Cup"),
                                     set=dict(id="W1-1"), opponent=dict(name="Opponent"), deadline=60))
        self.owner.act("tour_accept:cup:old")
        self.assertEqual(self.client.calls, [])
        self.owner._online_game_check.return_value = "@online.game_running"
        self.owner.act("tour_accept:cup:W1-1")
        self.assertEqual(self.client.calls, [])
        self.owner._online_game_check.return_value = ""
        self.owner.act("tour_accept:cup:W1-1")
        self.assertEqual(self.client.calls, [("accept", "cup", "W1-1")])
        self.assertTrue(self.owner._online_tours["call"]["accepted"])
        self.owner.act("tour_accept:cup:W1-1")
        self.assertEqual(len(self.client.calls), 1)
        tours.event(self.owner, dict(t="tour_call_end", tournament="other", set="W1-1"))
        self.assertTrue(self.owner._online_tours["call"])
        tours.event(self.owner, dict(t="tour_call_end", tournament="cup", set="W1-1"))
        self.assertFalse(self.owner._online_tours["call"])

    def test_snapshot_omits_server_tokens_and_returns_detached_bracket(self):
        self.client.current.update(token="secret", address="private", ticket="private-ticket")
        self.client.current["bracket"]["sets"][0]["token"] = "bracket-secret"
        self.select()
        snapshot = tours.state(self.owner)
        self.assertNotIn("secret", json.dumps(snapshot))
        self.assertNotIn("private", json.dumps(snapshot))
        snapshot["tournaments"]["detail"]["bracket"]["sets"][0]["p"][0] = "Changed"
        self.assertEqual(tours.state(self.owner)["tournaments"]["detail"]["bracket"]["sets"][0]["p"][0], "One")

    def test_events_mark_stale_clear_pending_and_close_clears_personal_state(self):
        self.select()
        self.owner.act("tour_start:cup")
        self.assertTrue(tours.event(self.owner, dict(t="tour_changed", id="cup")))
        self.assertTrue(self.owner._online_tours["stale"])
        self.assertFalse(self.owner._online_tours["pending"])
        tours.close(self.owner)
        self.assertEqual(self.owner._online_tours["rows"], [])
        self.assertEqual(self.owner._online_tours["detail"], {})

    def test_already_observed_changes_preserve_controller_review_until_confirmation(self):
        nav = types.SimpleNamespace(_online_text_item=lambda game, tid, label, hint: dict(id=tid, label=label))
        action = lambda iid, label, hint="": dict(id=iid, label=label, detail=dict(rows=[]))
        for kind in ("tour_changed", "tour_notice"):
            for current_revision, revision in ((0, 0), (4, 0), (4, 3), (4, 4)):
                with self.subTest(kind=kind, current_revision=current_revision, revision=revision):
                    self.setUp()
                    self.client.current["rev"] = current_revision
                    self.select()
                    self.owner.act("tour_start:cup")
                    summary = dict(id="cup", rev=revision)
                    event = dict(t=kind, **summary) if kind == "tour_changed" else dict(t=kind, tournament=summary)
                    self.assertTrue(tours.event(self.owner, event))
                    self.assertEqual(self.owner._online_tours["pending"], "tour_start:cup")
                    self.assertFalse(self.owner._online_tours["stale"])
                    self.assertFalse(self.owner._online_tour_refresh["detail_dirty"])
                    snapshot = tours.state(self.owner)
                    snapshot.update(account=True, name="Host")
                    rows = nav_tournaments.rows(nav, types.SimpleNamespace(a=self.owner), snapshot, action)
                    self.assertIn("tour_confirm:tour_start:cup", [row.get("id") for row in rows])
                    self.assertFalse(any(row[0] == "admin" for row in self.client.calls))
                    self.owner.act("tour_confirm:tour_start:cup")
                    self.assertEqual(self.client.calls[-1], ("admin", "cup", "start", {}))

    def test_unknown_or_new_changes_invalidate_review_and_reject_old_confirmation(self):
        for kind in ("tour_changed", "tour_notice"):
            for revision in (None, True, False, -1, 4.0, "4", 5):
                with self.subTest(kind=kind, revision=revision):
                    self.setUp()
                    self.client.current["rev"] = 4
                    self.select()
                    self.owner.act("tour_start:cup")
                    summary = dict(id="cup")
                    if revision is not None:
                        summary["rev"] = revision
                    event = dict(t=kind, **summary) if kind == "tour_changed" else dict(t=kind, tournament=summary)
                    self.assertTrue(tours.event(self.owner, event))
                    self.assertTrue(self.owner._online_tours["stale"])
                    self.assertEqual(self.owner._online_tours["pending"], "")
                    self.assertTrue(self.owner._online_tour_refresh["detail_dirty"])
                    self.owner.act("tour_confirm:tour_start:cup")
                    self.assertFalse(any(row[0] == "admin" for row in self.client.calls))

    def test_observed_revision_requires_valid_selected_detail(self):
        for kind in ("tour_changed", "tour_notice"):
            for detail_id, revision in (("cup", None), ("cup", True), ("cup", False),
                                        ("cup", -1), ("cup", 4.0), ("cup", "4"), ("other", 4)):
                with self.subTest(kind=kind, detail_id=detail_id, revision=revision):
                    self.setUp()
                    self.select()
                    self.owner.act("tour_start:cup")
                    self.owner._online_tours["detail"].update(id=detail_id)
                    if revision is not None:
                        self.owner._online_tours["detail"]["rev"] = revision
                    summary = dict(id="cup", rev=0)
                    event = dict(t=kind, **summary) if kind == "tour_changed" else dict(t=kind, tournament=summary)
                    self.assertTrue(tours.event(self.owner, event))
                    self.assertTrue(self.owner._online_tours["stale"])
                    self.assertEqual(self.owner._online_tours["pending"], "")
                    self.assertTrue(self.owner._online_tour_refresh["detail_dirty"])

    def test_preserved_review_revalidates_organizer_permission_at_confirmation(self):
        self.client.current["rev"] = 4
        self.select()
        self.owner.act("tour_start:cup")
        tours.event(self.owner, dict(t="tour_changed", id="cup", rev=4))
        self.assertEqual(self.owner._online_tours["pending"], "tour_start:cup")
        self.owner._online_tours["detail"]["can_manage"] = False
        self.owner.act("tour_confirm:tour_start:cup")
        self.assertEqual(self.owner._online_tours["pending"], "")
        self.assertFalse(any(row[0] == "admin" for row in self.client.calls))

    def test_event_refresh_coalesces_native_fetches_without_snapshot_side_effects(self):
        self.select()
        self.owner._online_phase = "logged_in"
        self.owner._online_busy = False
        tours.event(self.owner, dict(t="tour_changed", id="cup"))
        self.owner._online_tour_refresh.update(next_list=0, next_detail=0)
        before = list(self.client.calls)
        tours.state(self.owner)
        self.assertEqual(self.client.calls, before)
        self.assertTrue(tours.poll(self.owner))
        operation, work = self.owner.work
        tours.completion(self.owner, operation, work(), None)
        self.assertEqual(self.client.calls[-2:], [("list",), ("get", "cup")])
        self.assertFalse(self.owner._online_tours["stale"])
        self.assertFalse(tours.poll(self.owner))

    def test_unsupported_client_refuses_calls(self):
        self.client.tournaments = False
        self.owner.act("tour_refresh")
        self.assertFalse(tours.state(self.owner)["capabilities"]["tournaments"])
        self.assertEqual(self.owner._online_message, "@online.tour_unavailable")
        self.assertEqual(self.client.calls, [])

    def test_server_must_advertise_and_negotiate_tournaments_before_showing_or_requesting(self):
        for welcome in (None, {}, dict(features=[], caps=["tournaments"]),
                        dict(features=["tournaments"], caps=[]),
                        dict(features="tournaments", caps=["tournaments"]),
                        dict(features=["tournaments"], caps="tournaments")):
            with self.subTest(welcome=welcome):
                self.client.welcome = welcome
                snapshot = tours.state(self.owner)
                self.assertFalse(snapshot["capabilities"]["tournaments"])
                self.assertEqual(nav_tournaments.rows(None, None, snapshot, None), [])
                self.owner.act("tour_refresh")
                self.assertEqual(self.client.calls, [])
        self.client.welcome = dict(features=["tournaments"], caps=["tournaments"])
        self.assertTrue(tours.state(self.owner)["capabilities"]["tournaments"])
        self.owner.act("tour_refresh")
        self.assertEqual(self.client.calls, [("list",)])

    def test_navigation_exposes_detail_creation_and_bound_organizer_actions(self):
        self.client.current["state"] = "running"
        self.select()
        self.owner.act("tour_select_set:W1-1")
        self.owner.act("tour_win0:cup:W1-1")
        nav = types.SimpleNamespace(_online_text_item=lambda game, tid, label, hint: dict(id=tid, label=label))
        game = types.SimpleNamespace(a=self.owner)
        snapshot = tours.state(self.owner)
        snapshot.update(account=True, name="Host")
        action = lambda iid, label, hint="": dict(id=iid, label=label, detail=dict(rows=[]))
        result = nav_tournaments.rows(nav, game, snapshot, action)
        ids = [row.get("id") for row in result]
        for iid in ("tour_refresh", "tour_select:cup", "online_tour_name", "online_tour_clock",
                    "tour_option:format", "tour_create", "tour_select_set:W1-1", "tour_win0:cup:W1-1",
                    "tour_confirm:tour_win0:cup:W1-1", "online_tour_dq"):
            self.assertIn(iid, ids)

    def test_navigation_watch_uses_spectating_capability_and_current_live_set(self):
        self.client.current["state"] = "running"
        self.client.current["bracket"]["sets"][0].update(live="playing", watch=True)
        self.select()
        self.owner.act("tour_select_set:W1-1")
        nav = types.SimpleNamespace(_online_text_item=lambda game, tid, label, hint: dict(id=tid, label=label))
        game = types.SimpleNamespace(a=self.owner)
        action = lambda iid, label, hint="": dict(id=iid, label=label, detail=dict(rows=[]))
        snapshot = tours.state(self.owner)
        snapshot.update(account=True, name="Host")
        snapshot["capabilities"]["spectating"] = True
        ids = [row.get("id") for row in nav_tournaments.rows(nav, game, snapshot, action)]
        self.assertIn("spec_watch_tour:cup:W1-1", ids)
        snapshot["name"] = "One"
        ids = [row.get("id") for row in nav_tournaments.rows(nav, game, snapshot, action)]
        self.assertNotIn("spec_watch_tour:cup:W1-1", ids)


if __name__ == "__main__":
    unittest.main()
