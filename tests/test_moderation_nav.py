"""Moderation controls are capability gated and reachable using only pad input."""
import unittest

from openrecomp import nav_moderation
from openrecomp.nav import Game, Nav
from test_online_nav import Lobby, OnlineNavigation


class ModerationNavigationTests(unittest.TestCase):
    choose = OnlineNavigation.choose

    def setUp(self):
        self.a = Lobby()
        self.a.snapshot.update(phase="logged_in", capabilities=dict(lobby=True, mutes=True, blocks=True),
                               players=[dict(id="rival", name="Rival"), dict(id="quiet", name="Quiet")],
                               moderation=dict(mutes=[dict(name="Quiet", guest=False)], notice=""))
        self.nav = Nav([Game(self.a.m, self.a)], language="en")
        self.nav.screen = "hub"
        self.nav.sec[self.a.m["id"]] = "online"

    def ids(self):
        return [item.get("id") for item in self.nav.items()]

    def test_mute_toggle_list_unmute_and_block_are_pad_reachable(self):
        for iid, requested in (("moderation_mute:rival", "moderation_mute:rival"),
                               ("moderation_unmute:Quiet", "moderation_unmute:Quiet"),
                               ("moderation_muted:Quiet", "moderation_unmute:Quiet"),
                               ("moderation_refresh_mutes", "moderation_refresh_mutes"),
                               ("moderation_block:rival", "moderation_block:rival")):
            with self.subTest(iid=iid):
                self.choose(iid)
                self.assertEqual(self.a.calls[-1], ("online", requested))

    def test_server_without_caps_hides_mute_list_and_player_blocks(self):
        self.a.snapshot["capabilities"] = dict(lobby=True)
        self.assertFalse(any(iid and iid.startswith("moderation_") for iid in self.ids()))
        self.a.snapshot["capabilities"]["mutes"] = True
        self.assertIn("moderation_mute:rival", self.ids())
        self.assertNotIn("moderation_block:rival", self.ids())

    def test_notice_is_passive_and_only_shown_after_actual_notice(self):
        self.assertNotIn("moderation_notice", self.ids())
        self.a.snapshot["moderation"]["notice"] = "@online_chat.filter_blocked"
        self.choose("moderation_notice")
        self.assertEqual(self.a.calls, [])
        item = next(item for item in self.nav.items() if item.get("id") == "moderation_notice")
        self.assertEqual(item["detail"]["lead"], "@online_chat.filter_blocked")

    def test_names_remain_literal_in_value_and_detail(self):
        name = "@online.logout"
        self.a.snapshot["players"] = [dict(id="literal", name=name)]
        item = next(item for item in self.nav.items() if item.get("id") == "moderation_mute:literal")
        self.assertEqual(item["value"], {"_literal": name})
        self.assertEqual(item["detail"]["rows"][0]["v"], {"_literal": name})

    def test_roster_name_change_does_not_apply_action_from_old_focus(self):
        items = self.nav.items()
        self.nav.focus[self.a.m["id"] + ":online"] = next(
            i for i, item in enumerate(items) if item.get("id") == "moderation_mute:rival")
        self.a.snapshot["players"][0]["name"] = "Replacement"
        self.nav.act("confirm", device="xbox")
        self.assertNotIn(("online", "moderation_mute:rival"), self.a.calls)
        self.assertEqual(self.nav.focus[self.a.m["id"] + ":online"], 0)

    def test_dry_mode_suppresses_mutations(self):
        self.nav.dry = True
        for iid in ("moderation_mute:rival", "moderation_block:rival", "moderation_muted:Quiet",
                    "moderation_refresh_mutes"):
            self.choose(iid)
        self.assertEqual(self.a.calls, [])

    def test_rows_hidden_outside_lobby(self):
        self.assertEqual(nav_moderation.rows(self.nav, self.nav.game, dict(phase="offline"), None), [])


if __name__ == "__main__":
    unittest.main()
