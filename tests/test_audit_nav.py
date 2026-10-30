"""Regression checks for changing online targets and controller-only overlays."""
import unittest

from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest
from test_online_nav import Lobby


class AuditNavigation(unittest.TestCase):
    def setUp(self):
        self.adapter = Lobby()
        self.nav = Nav([Game(self.adapter.m, self.adapter)], language="en")
        self.nav.screen = "hub"
        self.nav.sec["lobby"] = "online"

    def focus(self, iid):
        items = self.nav.items()
        self.nav.focus["lobby:online"] = next(i for i, item in enumerate(items) if item.get("id") == iid)
        self.nav.view()

    def test_login_reply_cannot_replace_focused_cancel_with_search(self):
        for polled in (False, True):
            with self.subTest(polled=polled):
                self.adapter.snapshot["phase"] = "connecting"
                self.focus("cancel")
                if polled:
                    self.adapter.pending = dict(phase="logged_in")
                    self.nav.tick(.016)
                else:
                    self.adapter.snapshot["phase"] = "logged_in"
                self.nav.act("confirm", device="xbox")
                self.assertEqual(self.adapter.calls, [])
                self.assertEqual(self.nav.focus_index(self.nav.items()), 0)

    def test_lobby_reorder_cannot_challenge_a_different_player(self):
        self.adapter.snapshot.update(phase="logged_in", capabilities=dict(lobby=True),
                                     players=[dict(id="first", name="First"), dict(id="second", name="Second")])
        self.focus("challenge:first")
        self.adapter.snapshot["players"].reverse()
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.adapter.calls, [])

    def test_new_challenge_requires_selecting_it_again(self):
        self.adapter.snapshot.update(phase="logged_in", capabilities=dict(lobby=True),
                                     challenge=dict(id="first", name="First"))
        self.focus("accept_challenge")
        self.adapter.snapshot["challenge"] = dict(id="second", name="Second")
        self.nav.act("confirm", device="xbox")
        self.assertEqual(self.adapter.calls, [])

    def test_stale_mouse_row_cannot_start_search(self):
        self.adapter.snapshot["phase"] = "connecting"
        self.focus("cancel")
        index = self.nav.focus["lobby:online"]
        self.adapter.snapshot["phase"] = "logged_in"
        self.nav.click_row(index)
        self.assertEqual(self.adapter.calls, [])

    def test_dry_language_change_does_not_write_preferences(self):
        saved = []
        self.nav.on_language = saved.append
        self.nav.dry = True
        self.nav.act("social")
        self.nav.act("confirm")
        self.assertEqual(saved, [])
        self.assertEqual(self.nav.language, "en")

    def test_manifest_text_is_literal_even_when_it_matches_a_catalog_key(self):
        adapter = Fake(manifest(title="@open", short="@play", subtitle="@yes", numeral="@no"))
        nav = Nav([Game(adapter.m, adapter)], language="en")
        tile = nav.view()["shelf"]["tiles"][0]
        self.assertEqual((tile["name"], tile["subtitle"], tile["num"]), ("@open", "@yes", "@no"))
        nav.act("confirm")
        view = nav.view()
        self.assertEqual((view["gameShort"], view["numeral"], view["detail"]["title"]), ("@play", "@no", "@play"))
        nav.act("play")
        self.assertIn("@play", nav.view()["toast"])

    def test_busy_library_keeps_adapters_and_rejects_picker_side_effects(self):
        for busy in ("search", "game", "build", "report", "binding"):
            with self.subTest(busy=busy):
                adapter = Lobby()
                game = Game(adapter.m, adapter)
                installs = []
                nav = Nav([game], install=installs.append, language="en")
                if busy == "search":
                    adapter.snapshot["phase"] = "searching"
                elif busy == "game":
                    adapter.is_running = True
                elif busy == "build":
                    adapter.build_state = lambda: dict(running=True)
                elif busy == "report":
                    adapter.support_state = lambda: dict(running=True)
                else:
                    nav.binding_game = game
                replacement = Fake(manifest("new"))
                self.assertFalse(nav.can_reload_games())
                self.assertFalse(nav.set_games([Game(replacement.m, replacement)]))
                self.assertEqual(nav.games, [game])
                nav._picked("manifest", "selection.json")
                nav._picked("source:folder", "selection")
                self.assertEqual(installs, [])
                self.assertEqual(adapter.calls, [])
                self.assertEqual(nav.toast, "@library.busy")

    def test_idle_reload_closes_old_clients_and_clears_online_row_cache(self):
        self.nav.view()
        self.assertIn("lobby", self.nav.online_rows)
        replacement = Fake(manifest("new"))
        self.assertTrue(self.nav.set_games([Game(replacement.m, replacement)]))
        self.assertEqual(self.adapter.calls, [("close",)])
        self.assertEqual(self.nav.game.a, replacement)
        self.assertEqual(self.nav.online_rows, {})

    def test_failed_disconnect_keeps_old_adapter_tracked(self):
        def fail():
            raise RuntimeError("disconnect failed")
        self.adapter.online_close = fail
        old_games = self.nav.games
        self.assertFalse(self.nav.set_games([]))
        self.assertIs(self.nav.games, old_games)

    def test_empty_reload_returns_to_drawable_shelf(self):
        self.assertTrue(self.nav.set_games([]))
        self.assertEqual(self.nav.view()["screen"], "start")

    def test_reload_dismisses_confirmations_targeting_the_old_game(self):
        self.nav._ask("rebuild")
        self.nav.act("right")
        replacement = Fake(manifest("new"))
        self.assertTrue(self.nav.set_games([Game(replacement.m, replacement)]))
        self.assertIsNone(self.nav.overlay)
        self.assertEqual(replacement.calls, [])


if __name__ == "__main__":
    unittest.main()
