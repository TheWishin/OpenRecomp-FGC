"""The first T4 pad journey, using interface fakes and no game files or processes."""
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from test_nav import Fake, manifest


class FirstRunGame(Fake):
    def __init__(self, found=True):
        super().__init__(manifest("t4", adapter="t4"), is_ready=False)
        self.installed = found
        self.source = dict(running=False, result="", ok=False, id="")
        self.build_snapshot = dict(running=False, fraction=0, title="", steps=[], result="", line="")

    def found(self):
        return self.installed

    def source_state(self):
        return dict(self.source)

    def sources(self):
        if not self.installed:
            return [dict(id="folder", label="@game_folder", value="@missing", ok=False,
                         kind="file_or_folder", exts=[".zip"], dirs=[], hint="@onboarding.hint")]
        row = super().sources()[0]
        row.update(ok=self.source["ok"], note=self.source["result"])
        return [row]

    def set_source(self, sid, path):
        self.calls.append(("source", sid, path))
        self.source.update(running=True, id=sid, result="", ok=False)
        return "@iso.checking" if sid == "iso" else "@t4.installing"

    def build_ready(self):
        return "@iso.checking" if self.source["running"] else ("" if self.source["ok"] else "@iso.choose_first")

    def build_state(self):
        return dict(self.build_snapshot)

    def build_start(self, force=False):
        super().build_start(force)
        self.build_snapshot["running"] = True


class T4FirstRunNavigation(unittest.TestCase):
    def setUp(self):
        self.adapter = FirstRunGame()
        self.game = Game(self.adapter.m, self.adapter)
        self.quit = mock.Mock()
        self.nav = Nav([self.game], language="en", on_quit=self.quit)

    def press(self, *actions):
        for action in actions:
            self.nav.act(action, device="xbox")

    def choose_iso(self):
        self.press("confirm")
        with mock.patch.object(self.nav, "_picker_entries", return_value=[]):
            self.press("confirm")
        with mock.patch.object(self.nav, "_picker_entries", return_value=[dict(kind="file", name="own.iso", path="own.iso")]):
            self.press("confirm")

    def test_disc_check_keeps_navigation_live_and_prevents_duplicate_work(self):
        self.choose_iso()
        self.assertFalse(self.nav.can_reload_games())
        self.assertEqual(self.adapter.calls, [("source", "iso", "own.iso")])
        view = self.nav.view()
        self.assertTrue(view["rows"][0]["disabled"])
        self.assertEqual(view["detail"]["lead"], i18n.text("en", "iso.checking"))
        self.press("confirm")
        self.assertIsNone(self.nav.overlay)
        self.assertEqual(len(self.adapter.calls), 1)
        self.press("back")
        self.assertEqual(self.nav.screen, "start")

    def test_accepted_disc_moves_focus_to_build_then_shows_progress(self):
        self.choose_iso()
        self.adapter.source.update(running=False, ok=True, result="@iso.confirmed")
        self.assertTrue(self.nav.tick(.016))
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "build")
        self.press("confirm")
        self.assertEqual(self.adapter.calls[-1], ("build", False))
        self.adapter.build_snapshot.update(fraction=.5, title="Compile", line="Working")
        self.assertEqual(self.nav.view()["detail"]["progress"], .5)
        self.assertEqual(self.nav.view()["rows"][0]["verb"], "")
        self.assertTrue(self.nav.view()["rows"][0]["disabled"])

    def test_long_build_output_preserves_wait_and_cancel_guidance(self):
        self.press("confirm", "down")
        self.adapter.build_snapshot.update(running=True, fraction=.4, line="compiler " * 100 + "latest diagnostic")
        view = self.nav.view()
        self.assertEqual(view["hint"], i18n.text("en", "t4.build_wait"))
        self.assertEqual(view["detail"]["lead"], i18n.text("en", "t4.build_wait"))
        self.assertEqual(view["detail"]["rows"][-1]["v"], self.adapter.build_snapshot["line"][-160:])
        self.assertEqual(view["detail"]["rows"][-1]["k"], i18n.text("en", "t4.build_output"))
        self.press("confirm")
        self.assertEqual((self.nav.overlay, self.nav.confirm_kind), ("dialog", "cancel_build"))

    def test_t4_missing_shelf_offers_zip_guidance_even_beside_installed_t5dr(self):
        missing = FirstRunGame(found=False)
        other = Fake(manifest("t5dr", adapter="t5dr"))
        nav = Nav([Game(missing.m, missing), Game(other.m, other)], language="en")
        view = nav.view()
        self.assertEqual(view["hint"], i18n.text("en", "t4.onboarding_hint"))
        self.assertEqual(view["shelf"]["tiles"][0]["empty"], i18n.text("en", "t4.onboarding_source"))

    def test_wrong_disc_refusal_stays_in_the_iso_detail_and_can_be_retried(self):
        self.choose_iso()
        self.adapter.source.update(running=False, result="Wrong disc. Choose SLUS-20328.")
        self.nav.tick(.016)
        self.assertEqual(self.nav.view()["toast"], self.adapter.source["result"])
        self.nav.tick(20)
        self.assertEqual(self.nav.view()["detail"]["lead"], self.adapter.source["result"])
        with mock.patch.object(self.nav, "_picker_entries", return_value=[]):
            self.press("confirm")
        self.assertEqual(self.nav.overlay, "picker")

    def test_finished_t4_build_offers_first_play_instead_of_another_build(self):
        self.adapter.source["ok"] = True
        self.adapter.is_ready = True
        self.press("confirm", "next", "next", "down")
        view = self.nav.view()
        self.assertEqual(view["detail"]["primary"], i18n.text("en", "play"))
        self.assertEqual(view["detail"]["lead"], i18n.text("en", "t4.build_next"))
        self.press("confirm")
        self.assertEqual(self.adapter.calls, [("start", None)])

    def test_existing_build_can_play_before_disc_is_rechecked_for_rebuilding(self):
        self.adapter.is_ready = True
        self.press("confirm", "next", "next", "down")
        self.assertFalse(self.nav.view()["rows"][1]["disabled"])
        self.press("confirm")
        self.assertEqual(self.adapter.calls, [("start", None)])

    def test_ready_play_explains_how_to_return_after_a_fresh_launcher_start(self):
        self.adapter.is_ready = True
        self.press("confirm")
        self.assertEqual(self.nav.view()["detail"]["lead"], i18n.text("en", "t4.play_hint"))

    def test_failed_rebuild_remains_visible_even_when_the_previous_build_can_play(self):
        self.adapter.source["ok"] = True
        self.adapter.is_ready = True
        self.adapter.build_snapshot["result"] = "Build failed. Confirm retries."
        self.press("confirm", "next", "next", "down")
        self.assertEqual(self.nav.view()["detail"]["lead"], self.adapter.build_snapshot["result"])
        self.press("confirm")
        self.assertEqual(self.adapter.calls, [("build", False)])

    def test_async_install_finishes_at_the_iso_choice_without_a_second_shelf_step(self):
        missing = FirstRunGame(found=False)
        self.nav = Nav([Game(missing.m, missing)], language="en")

        def reload_games(path):
            self.assertIsNone(path)
            self.nav.set_games([self.game])
            return "@folder_saved"

        self.nav.install = mock.Mock(side_effect=reload_games)
        with mock.patch.object(self.nav, "_picker_entries", return_value=[]):
            self.press("confirm")
        with mock.patch.object(self.nav, "_picker_entries", return_value=[dict(kind="pick", name="Choose", path="release")]):
            self.press("confirm")
        self.nav.install.assert_not_called()
        self.press("confirm")
        self.assertIsNone(self.nav.overlay)
        missing.source.update(running=False, ok=True, result="reload")
        self.nav.tick(.016)
        self.nav.install.assert_called_once_with(None)
        self.assertEqual((self.nav.screen, self.nav.section()), ("hub", "build"))
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "iso")
        self.nav.tick(.016)
        self.nav.install.assert_called_once()

    def test_check_finishing_before_the_picker_returns_still_advances_to_build(self):
        def fast_check(sid, path):
            self.adapter.source.update(id=sid, running=False, ok=True, result="@iso.confirmed")
            return "@iso.checking"
        self.adapter.set_source = fast_check
        self.choose_iso()
        self.assertEqual(self.nav.items()[self.nav.focus_index(self.nav.items())]["id"], "build")
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "iso.confirmed"))

    def test_finished_import_waits_for_another_game_to_end_before_reloading(self):
        missing = FirstRunGame(found=False)
        other = Fake(manifest("t5dr", adapter="t5dr"))
        self.nav = Nav([Game(missing.m, missing), Game(other.m, other)], language="en")

        def reload_games(path):
            self.nav.set_games([self.game, Game(other.m, other)])
            return "@folder_saved"

        self.nav.install = mock.Mock(side_effect=reload_games)
        self.nav._picked("source:folder", "release")
        other.is_running = True
        missing.source.update(running=False, ok=True, result="reload")
        self.nav.tick(.016)
        self.nav.install.assert_not_called()
        self.assertIn("t4", self.nav.source_checks)
        other.is_running = False
        self.nav.tick(.016)
        self.nav.install.assert_called_once_with(None)
        self.assertNotIn("t4", self.nav.source_checks)
        self.assertIs(self.nav.game, self.game)

    def test_import_registration_failure_does_not_escape_the_timer(self):
        self.adapter.source.update(running=False, id="folder", result="reload", ok=True)
        self.nav.source_checks[self.game.id] = self.game
        self.nav.install = mock.Mock(side_effect=OSError("Cannot save configuration"))
        self.assertTrue(self.nav.tick(.016))
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "t4.install_failed"))
        self.assertNotIn(self.game.id, self.nav.source_checks)
        self.nav.tick(.016)
        self.nav.install.assert_called_once_with(None)

    def test_import_registration_error_is_not_replaced_by_success_for_an_existing_t4(self):
        self.adapter.source.update(running=False, id="folder", result="reload", ok=True)
        self.nav.source_checks[self.game.id] = self.game
        self.nav.install = mock.Mock(return_value="@t4.install_invalid")
        self.nav.tick(.016)
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "t4.install_invalid"))
        self.assertEqual(self.nav.screen, "start")
        self.assertNotIn(self.game.id, self.nav.source_checks)

    def test_quit_waits_for_checks_and_builds_and_rechecks_yes(self):
        self.choose_iso()
        self.press("back", "back")
        self.assertIsNone(self.nav.overlay)
        self.quit.assert_not_called()
        self.assertEqual(self.nav.view()["toast"], i18n.text("en", "t4.quit_busy"))
        self.adapter.source["running"] = False
        self.press("back", "back")
        self.assertEqual(self.nav.overlay, "dialog")
        self.adapter.build_snapshot["running"] = True
        self.press("right", "confirm")
        self.quit.assert_not_called()
        self.assertEqual((self.nav.screen, self.nav.section()), ("hub", "build"))

    def test_return_chord_stops_only_running_t4_and_restores_its_play_screen(self):
        other = Fake(manifest("t5dr", adapter="t5dr"))
        self.nav.games.append(Game(other.m, other))
        self.adapter.is_running = True
        self.nav.game = self.nav.games[1]
        self.nav.overlay = "drawer"
        self.press("returnGame")
        self.assertEqual(self.adapter.calls, [("stop",)])
        self.assertEqual(other.calls, [])
        self.assertEqual((self.nav.game.id, self.nav.screen, self.nav.section()), ("t4", "hub", "play"))
        self.assertIsNone(self.nav.overlay)

    def test_online_return_uses_match_stop_without_starting_another_match(self):
        self.adapter.is_running = True
        self.adapter.online_state = lambda: dict(phase="playing")
        self.adapter.online_action = mock.Mock()
        self.press("returnGame")
        self.adapter.online_action.assert_called_once_with("stop_match")
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.nav.section(), "online")

    def test_t5dr_online_uses_shared_login_and_keeps_native_launcher_available(self):
        adapter = Fake(manifest("t5dr", adapter="t5dr"))
        adapter.online_supported = lambda: True
        adapter.online_action = mock.Mock()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.act("confirm")
        nav.act("next")
        ids = [item["id"] for item in nav.items()]
        self.assertIn("login_guest", ids)
        self.assertIn("login_account", ids)
        self.assertIn("native", ids)
        nav.focus["t5dr:online"] = ids.index("native")
        nav.act("confirm", device="xbox")
        self.assertEqual(adapter.calls, [("native",)])
        adapter.online_action.assert_not_called()

    def test_downloaded_update_explains_wait_and_does_not_restart_download(self):
        self.nav.on_update_check = mock.Mock()
        self.nav.update_state = dict(phase="waiting")
        self.press("social", "down", "down", "down")
        self.assertEqual(self.nav.view()["hint"], i18n.text("en", "updates.waiting"))
        self.press("confirm")
        self.nav.on_update_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
