"""Community screens and installed-client calls, with no sockets or game processes."""
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp.adapters import t5_community as feature
from openrecomp import nav_community


class Owner:
    def __init__(self):
        self._online_client = mock.Mock()
        client = self._online_client
        client.me = dict(id="me", name="Owner")
        client.welcome = dict(room_limits=dict(max_size=6))
        client.players = [dict(id="peer", name="Peer", badge="dev")]
        client.my_room = dict(id="room", name="Room", owner_id="me", size=4, mode="tables", lock="password",
            players=[dict(id="me", name="Owner"), dict(id="peer", name="Peer"), dict(id="third", name="Third")],
            line=["me", "peer", "third"], tables=[dict(id=0, players=[])], guesses=dict(wrong=2),
            password="never expose", token="never expose")
        for name in ("private_rooms_ok", "room_tables_ok", "badges_ok", "mentions_ok", "casual_sets_ok",
                     "training_ok", "ingame_rematch_ok", "auto_skip_ok"):
            getattr(client, name).return_value = True
        client.create_room.return_value = dict(id="room")
        client.room_line.return_value = dict(id="room")
        self._online_players = [dict(id="peer", name="Peer", rank="Rank")]
        self._online_chat = []
        self._online_fields = dict(online_room_password="", online_room_name="Test room", online_chat="")
        self._online_busy = False
        self._online_phase = "logged_in"
        self._online_generation = 1
        self._online_message = ""
        self.submitted = []
        self.pending = None
        self._online_game_check = mock.Mock(return_value="")
        self._online_own_room = mock.Mock()
        self.online_close = mock.Mock()

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise RuntimeError("stale request")

    def _online_submit(self, operation, work):
        self.submitted.append(operation)
        self.pending = work

    def _online_error(self, error):
        return "@online.connection_failed"


class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.owner = Owner()
        self.client = self.owner._online_client
        feature.init(self.owner)

    def action(self, name):
        return feature.action(self.owner, name, self.client)

    def perform(self):
        work, self.owner.pending = self.owner.pending, None
        return work()

    def test_snapshot_is_read_only_and_only_exposes_public_room_fields(self):
        snapshot = feature.state(self.owner)
        self.assertEqual(snapshot["community"]["maximum"], 6)
        self.assertEqual(snapshot["community"]["room"]["tables"][0]["id"], "0")
        self.assertTrue(snapshot["community"]["room"]["host"])
        self.assertEqual(snapshot["players"][0]["badge"], "dev")
        self.assertNotIn("never expose", json.dumps(snapshot))
        self.assertEqual(self.owner.submitted, [])
        self.client.create_room.assert_not_called()

    def test_every_room_first_to_choice_reaches_the_existing_client(self):
        self.assertEqual(feature.OPTIONS["first_to"], tuple(range(1, 11)))
        for wins in range(1, 11):
            with self.subTest(wins=wins):
                self.action("community_option:first_to:" + str(wins))
                self.assertEqual(feature.state(self.owner)["community"]["preferences"]["first_to"], wins)
                self.action("community_create")
                self.perform()
                self.assertEqual(self.client.create_room.call_args.kwargs["first_to"], wins)

    def test_room_capacity_choices_respect_eight_player_ui_and_server_limit(self):
        from tools.online_shots import scene
        nav = scene("t5", "rooms_create", "en")
        for maximum, expected in ((16, range(2, 9)), (6, range(2, 7))):
            nav.game.a.snapshot["community"]["maximum"] = maximum
            row = next(item for item in nav.items() if item.get("id") == "community_option:size")
            self.assertEqual([value for value, _ in row["options"]], list(expected))

    def test_configured_private_community_room_uses_installed_client(self):
        for key, value in (("size", "4"), ("mode", "tables"), ("rotation", "queue"),
                           ("first_to", "3"), ("access", "password"), ("hidden", "True")):
            self.action("community_option:" + key + ":" + value)
        self.owner._online_fields["online_room_password"] = "local-test"
        self.action("community_create")
        self.assertEqual(self.owner._online_fields["online_room_password"], "")
        self.perform()
        self.client.create_room.assert_called_once_with(name="Test room", ranked=False, size=4, rotation="queue",
            hidden=True, private="password", password="local-test", first_to=3, mode="tables")

    def test_classic_room_policy_and_training_do_not_mix(self):
        self.action("community_option:rematch_policy:auto_unless_declined")
        self.action("community_option:auto_skip_after_round:True")
        self.action("community_create")
        self.perform()
        self.assertEqual(self.client.create_room.call_args.kwargs["rematch_policy"], "auto_unless_declined")
        self.action("community_option:training:True")
        self.action("community_create")
        self.perform()
        kwargs = self.client.create_room.call_args.kwargs
        self.assertTrue(kwargs["training"])
        self.assertNotIn("rematch_policy", kwargs)
        self.assertNotIn("first_to", kwargs)
        self.client.my_room["training"] = True
        self.assertTrue(feature.state(self.owner)["community"]["room"]["training"])

    def test_negotiation_limits_and_password_validation_refuse_before_request(self):
        self.action("community_option:size:16")
        self.assertEqual(self.owner._online_community_prefs["size"], 2)
        self.client.room_tables_ok.return_value = False
        self.action("community_option:mode:tables")
        self.assertEqual(self.owner._online_community_prefs["mode"], "line")
        self.action("community_option:access:password")
        for password in ("", "abc", " abcd", "abcd ", "a" * 65):
            self.owner._online_fields["online_room_password"] = password
            self.action("community_create")
            self.assertEqual(self.owner.submitted, [])
        self.action("community_option:bad")
        self.assertEqual(self.owner._online_message, "@online.community_password_rule")

    def test_host_pair_validates_current_members_and_stale_generation(self):
        for key, value in (("table", "0"), ("p1", "peer"), ("p2", "third")):
            self.action("community_pair_option:" + key + ":" + value)
        self.action("community_pair")
        self.perform()
        self.client.room_pair.assert_called_once_with(0, ["peer", "third"])
        self.action("community_pair")
        self.owner._online_generation += 1
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.perform()
        self.assertEqual(self.client.room_pair.call_count, 1)
        self.client.my_room["owner_id"] = "peer"
        before = len(self.owner.submitted)
        self.action("community_kick:third")
        self.assertEqual(len(self.owner.submitted), before)

    def test_line_host_settings_and_code_controls_delegate(self):
        self.action("community_sit_out")
        self.perform()
        self.client.room_line.assert_called_once_with(back=False)
        self.action("community_back_in_line")
        self.perform()
        self.client.room_line.assert_called_with(back=True)
        self.action("community_new_code")
        self.perform()
        self.client.room_lock.assert_called_once_with(lock="code", password=None, hidden=False)
        self.action("community_bar")
        self.perform()
        self.client.room_bar.assert_called_once()
        self.client.room_code = "TEST-CODE"
        self.action("community_copy_code")
        self.assertEqual(self.owner._online_fields["online_room_code"], "TEST-CODE")

    def test_only_server_ids_resolve_mentions_and_negotiated_badges(self):
        feature.event(self.owner, dict(t="chat", **{"from": dict(id="peer", name="Peer", badge="dev")},
                                      text="@Owner", mentions=[]))
        self.assertFalse(self.owner._online_chat[-1]["mentioned"])
        feature.event(self.owner, dict(t="chat", **{"from": dict(id="peer", name="Peer", badge="dev")},
                                      text="Hello", mentions=["me"]))
        self.assertTrue(self.owner._online_chat[-1]["mentioned"])
        self.assertEqual(self.owner._online_chat[-1]["badge"], "dev")
        self.client.badges_ok.return_value = self.client.mentions_ok.return_value = False
        feature.event(self.owner, dict(t="chat", **{"from": dict(id="peer", name="Peer", badge="dev")},
                                      text="@Owner", mentions=["me"]))
        self.assertEqual(self.owner._online_chat[-1]["badge"], "")
        self.assertFalse(self.owner._online_chat[-1]["mentioned"])
        self.assertEqual(feature.state(self.owner)["players"][0]["badge"], "")

    def test_pad_mention_inserts_current_roster_name_without_sending(self):
        self.action("mention:peer")
        self.assertEqual(self.owner._online_fields["online_chat"], "@Peer ")
        self.action("mention:missing")
        self.assertEqual(self.owner._online_fields["online_chat"], "@Peer ")
        self.assertEqual(self.owner.submitted, [])
        self.client.chat.assert_not_called()

    def test_uncertain_room_reservation_closes_connection(self):
        for operation in ("community_create", "community_pair", "community_back_in_line", "community_sit_out"):
            self.owner.online_close.reset_mock()
            feature.completion(self.owner, feature.PREFIX + operation, None, TimeoutError())
            self.owner.online_close.assert_called_once()
        self.owner.online_close.reset_mock()
        feature.completion(self.owner, feature.PREFIX + "community_apply", None, TimeoutError())
        self.owner.online_close.assert_not_called()
        self.assertEqual(self.owner._online_message, "@online.connection_failed")
        feature.completion(self.owner, feature.PREFIX + "community_create", None, RuntimeError("@online.game_running"))
        self.owner.online_close.assert_not_called()

    def test_controller_rows_delegate_and_decorate_plain_snapshots(self):
        snapshot = feature.state(self.owner)
        snapshot.update(name="Owner", chat=[dict(name="Peer", text="Hello", badge="dev", mentioned=True)])
        nav = SimpleNamespace(_online_action=mock.Mock())
        def action(iid, label):
            return dict(kind="action", id=iid, label=label, run=lambda: nav._online_action(None, iid), detail=dict(rows=[]))
        rows = nav_community.rows(nav, None, snapshot, action)
        ids = {row.get("id"): row for row in rows}
        for iid in ("community_create", "community_sit_out", "community_apply", "community_kick:peer", "community_pair", "mention:peer"):
            self.assertIn(iid, ids)
            ids[iid]["run"]()
            nav._online_action.assert_called_with(None, iid)
        ids["community_option:size"]["set"](4)
        nav._online_action.assert_called_with(None, "community_option:size:4")
        existing = [action("challenge:peer", "Peer"), action("chat:0", "Peer")]
        nav_community.enhance_rows(existing, snapshot)
        self.assertEqual(existing[0]["value"], "@online.dev_badge")
        self.assertEqual(existing[1]["hint"], "@online.mention_notice")


if __name__ == "__main__":
    unittest.main()
