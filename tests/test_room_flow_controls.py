"""Room next steps and ready controls use public snapshots, without games or sockets."""
import unittest

from openrecomp import i18n, nav_community
from openrecomp.nav import Game, Nav
from test_online_nav import Lobby
from test_online_page import lobby_snapshot
from test_t5_community import Owner
from openrecomp.adapters import t5_community


class RoomControls(unittest.TestCase):
    def setUp(self):
        self.a = Lobby()
        self.a.snapshot.update(lobby_snapshot())
        self.a.snapshot["capabilities"]["community"] = True
        self.room = dict(id="room", name="Local test room", me_id="me", host=True,
                         size=2, mode="line", line=["me", "peer"], in_line=True,
                         members=[dict(id="me", name="Me"), dict(id="peer", name="Peer")])
        self.a.snapshot.update(room=dict(id="room"), community=dict(room=self.room, preferences={}))
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def rows(self):
        return {row.get("id"): row for row in self.nav.items()}

    def test_classic_ready_check_shows_both_states_and_controller_action(self):
        self.a.snapshot.update(phase="matched", match=dict(my_ready=False, peer_ready=True))
        rows = self.rows()
        self.assertEqual(rows["start_match"]["value"], "@online.room_not_ready")
        self.assertFalse(rows["start_match"].get("disabled", False))
        self.assertEqual(rows["community_ready:peer"]["value"], "@online.room_is_ready")
        self.assertTrue(rows["community_ready:peer"]["disabled"])
        items = self.nav.items()
        self.nav.focus[self.nav.key()] = next(i for i, item in enumerate(items) if item.get("id") == "start_match")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.a.calls[-1], ("online", "start_match"))

    def test_starting_keeps_both_readiness_states_and_prevents_second_ready(self):
        self.a.snapshot.update(phase="starting", match=dict(my_ready=True, peer_ready=False))
        rows = self.rows()
        self.assertEqual(rows["start_match"]["value"], "@online.room_is_ready")
        self.assertTrue(rows["start_match"]["disabled"])
        self.assertEqual(rows["community_ready:peer"]["value"], "@online.room_not_ready")
        self.assertTrue(rows["community_kick:peer"]["disabled"])

    def test_joined_room_is_shown_before_creation_and_host_controls_are_available(self):
        items = self.nav.items()
        ids = [item.get("id") for item in items]
        self.assertLess(ids.index("community_next"), ids.index("create_room"))
        self.assertLess(ids.index("community_kick:peer"), ids.index("community_create"))
        self.assertLess(ids.index("community_option:access"), ids.index("community_apply"))
        page = self.nav.view()["online"]
        self.assertEqual(page["chapter"], "rooms")
        self.assertIn("What happens next", [line.get("label") for line in page["body"]["lines"]])
        rows = self.rows()
        rows["community_kick:peer"]["run"]()
        self.assertEqual(self.a.calls[-1], ("online", "community_kick:peer"))

    def test_community_line_names_current_next_and_own_position(self):
        self.room.update(size=4, line=["peer", "third", "me"],
                         members=self.room["members"] + [dict(id="third", name="Third")])
        rows = self.rows()
        self.assertEqual(i18n.localize(rows["community_line:now"]["value"], "en"), "Peer / Third")
        self.assertEqual(i18n.localize(rows["community_line:next"]["value"], "en"), "Me")
        self.assertEqual(rows["community_line:place"]["value"], "3")
        rows["community_sit_out"]["run"]()
        self.assertEqual(self.a.calls[-1], ("online", "community_sit_out"))
        self.room.update(in_line=False, line=["peer", "third"])
        self.assertIn("community_back_in_line", self.rows())

    def test_table_queue_does_not_claim_waiting_players_are_playing(self):
        self.room.update(size=4, mode="tables", tables=[dict(id="1", players=[], playing=False)])
        rows = self.rows()
        self.assertEqual(rows["community_line:now"]["value"], "@online.room_waiting")
        self.assertEqual(i18n.localize(rows["community_line:next"]["value"], "en"), "Me / Peer")

    def test_community_pair_keeps_ready_states_and_line_controls_visible(self):
        self.room.update(size=4, line=["me", "peer", "third"],
                         members=self.room["members"] + [dict(id="third", name="Third")])
        self.a.snapshot.update(phase="matched", match=dict(my_ready=False, peer_ready=True))
        rows = self.rows()
        self.assertEqual(rows["community_ready:peer"]["value"], "@online.room_is_ready")
        self.assertNotIn("community_ready:third", rows)
        self.assertFalse(rows["start_match"].get("disabled", False))
        self.assertTrue(rows["community_sit_out"]["disabled"])

    def test_adapter_exposes_identity_for_line_place_without_name_comparison(self):
        owner = Owner()
        room = t5_community.state(owner)["community"]["room"]
        self.assertEqual(room["me_id"], "me")
        self.assertNotIn("password", room)


if __name__ == "__main__":
    unittest.main()
