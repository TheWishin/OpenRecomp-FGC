"""Round-seven shell regressions use fake adapters and no installed game resources."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from openrecomp import app, nav_feedback
from openrecomp.adapters.t4 import T4
from tools.online_shots import scene


class RoundSevenShell(unittest.TestCase):
    def test_cross_game_response_receipt_stays_with_its_offering_game(self):
        nav = scene("t5", "lobby", "en")
        offering = nav.game
        other = scene("t4", "lobby", "en").game
        nav.games.append(other)
        row = dict(kind="pending", text="@feedback.sending", name="Rival", action="decline_challenge")
        nav_feedback.records(nav, offering.id)["decline_challenge"] = row
        nav.game = other
        nav_feedback.finish(nav, row, "declined", "@feedback.declined")
        self.assertIn(offering.id, nav.last_action_result)
        self.assertNotIn(other.id, nav.last_action_result)

    def test_delay_control_uses_only_supplied_choices_and_the_existing_setter(self):
        nav = scene("t5", "lobby", "en")
        nav.dry = False
        rows = nav.items()
        delay = next(row for row in rows if row.get("id") == "online_input_delay")
        self.assertEqual(delay["region"], "find")
        self.assertEqual([choice[0] for choice in delay["options"]], ["auto", "0", "1", "2", "3", "4"])
        nav._cycle(delay, 1)
        self.assertEqual(nav.game.a.calls, [("set", "input_delay", "0")])
        self.assertTrue(any(option["id"] == "online_input_delay" for option in nav._view_find(
            nav.game, nav.game.a.snapshot, nav.items(), 0, {row.get("id"): i for i, row in enumerate(nav.items())})["delayOptions"]))
        nav.game.a.settings = lambda: []
        unavailable = next(row for row in nav.items() if row.get("id") == "online_input_delay")
        self.assertTrue(unavailable["disabled"])
        self.assertIsNone(unavailable.get("set"))

    def test_themes_switch_with_selected_game_and_leave_shelf_identity(self):
        for game, theme in (("t4", "t4"), ("t5", "t5dr")):
            nav = scene(game, "home", "en")
            self.assertEqual(nav.view()["gameTheme"], theme)
            self.assertTrue(nav.view()["mainMenu"]["fighters"])
            nav.screen = "start"
            self.assertEqual(nav.view()["gameTheme"], "")

    def test_main_menu_delay_choices_are_pad_operable_without_opening_search(self):
        nav = scene("t5", "home", "en")
        nav.dry = False
        self.assertTrue(nav.view()["mainMenu"]["delayOptions"])
        nav.act("play", device="xbox")
        self.assertTrue(nav.main_menu_options)
        self.assertNotEqual(nav.view()["hint"], nav.view()["mainMenu"]["hint"])
        nav.act("right", device="xbox")
        self.assertEqual(nav.game.a.calls, [("set", "input_delay", "0")])
        nav.act("back", device="xbox")
        self.assertTrue(nav.view()["mainMenu"]["show"])
        self.assertFalse(nav.main_menu_options)

    def test_guest_main_menu_keeps_ranked_with_account_reason_and_never_opens_search(self):
        nav = scene("t5", "home", "en")
        nav.game.a.snapshot["account"] = False
        ranked = next(row for row in nav.view()["mainMenu"]["entries"] if row["id"] == "ranked")
        self.assertTrue(ranked["disabled"])
        self.assertEqual(ranked["subtitle"], "Needs an account")
        nav.act("confirm")
        self.assertTrue(nav.view()["mainMenu"]["show"])
        self.assertEqual(nav.game.a.calls, [])

    def test_cached_t4_fighter_paths_are_bounded_and_missing_art_is_empty(self):
        adapter = T4.__new__(T4)
        with tempfile.TemporaryDirectory() as directory, mock.patch("openrecomp.adapters.t4.art_dir", return_value=directory):
            cache = Path(directory) / "fighters"
            cache.mkdir()
            picture = cache / "jin.png"
            picture.touch()
            self.assertEqual(adapter.fighter_image("jin"), str(picture))
            self.assertEqual(adapter.fighter_image("unknown"), "")
            for key in ("../outside", "C:/outside", "", None):
                self.assertEqual(adapter.fighter_image(key), "")

    def test_attention_alerts_inactive_window_once_without_activating_or_interrupting_game(self):
        window = mock.Mock()
        window.isActive.return_value = False
        adapter = SimpleNamespace(running=lambda: False)
        backend = SimpleNamespace(window=window, nav=SimpleNamespace(games=[SimpleNamespace(a=adapter)]))
        with mock.patch.object(window, "alert") as alert:
            app.Backend._offer_attention(backend)
            alert.assert_called_once_with(0)
            window.requestActivate.assert_not_called()
            alert.reset_mock()
            adapter.running = lambda: True
            app.Backend._offer_attention(backend)
            alert.assert_not_called()
            adapter.running = lambda: False
            window.isActive.return_value = True
            app.Backend._offer_attention(backend)
            alert.assert_not_called()

    def test_activity_returns_to_existing_search_without_reissuing_it(self):
        nav = scene("t5", "searching", "en")
        nav.sec[nav.game.id] = "settings"
        self.assertTrue(nav.view()["activity"])
        nav.act("returnActivity")
        self.assertEqual(nav.section(), "online")
        self.assertEqual(nav.game.a.calls, [])

    def test_activity_returns_from_a_secondary_chapter_to_the_existing_search(self):
        nav = scene("t5", "searching", "en")
        nav.click_chapter("rooms")
        self.assertEqual(nav.view()["online"]["chapter"], "rooms")
        nav.act("returnActivity")
        self.assertEqual(nav.view()["online"]["chapter"], "lobby")
        self.assertIsNotNone(nav.view()["online"]["arcade"]["search"])
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "cancel")
        self.assertEqual(nav.game.a.calls, [])

    def test_pad_quick_access_returns_to_search_without_network_operation(self):
        nav = scene("t5", "searching", "en")
        nav.sec[nav.game.id] = "settings"
        nav.act("social", device="xbox")
        self.assertEqual(nav.overlay, "drawer")
        rows = nav._drawer_items()
        nav.drawer_focus = next(n for n, row in enumerate(rows) if row["id"] == "returnActivity")
        nav.act("confirm", device="xbox")
        self.assertEqual(nav.section(), "online")
        self.assertIsNone(nav.overlay)
        self.assertEqual(nav.game.a.calls, [])


class RoundSevenScene(unittest.TestCase):
    from test_ui_polish import ScenePolish
    setUpClass = classmethod(ScenePolish.setUpClass.__func__)
    setUp = ScenePolish.setUp
    tearDown = ScenePolish.tearDown
    named = ScenePolish.named
    wait_pages = ScenePolish.wait_pages

    def test_secondary_online_chapter_has_reserved_activity_space_and_full_height_chat(self):
        from PySide6.QtCore import QRectF
        from tools.online_shots import snapshot
        self.nav = scene("t5", "searching", "en")
        self.nav.click_chapter("rooms")
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        self.wait_pages()
        activity = self.named("onlineActivityReturn")[0]
        page = self.named("onlineHub")[0]
        self.assertTrue(activity.isVisible())
        bottom = activity.mapRectToScene(QRectF(0, 0, activity.width(), activity.height())).bottom()
        top = page.mapRectToScene(QRectF(0, 0, page.width(), page.height())).top()
        self.assertLessEqual(bottom, top)
        self.assertGreater(self.named("lobbyChatPane")[0].height(), page.height())

    def test_main_menu_match_actions_keep_eighty_output_pixels_with_chat_at_both_sizes(self):
        from tools.online_shots import snapshot
        from test_ui_loads import spin
        self.nav = scene("t5", "home", "de")
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        self.wait_pages()
        for width, height in ((1920, 1080), (1280, 720)):
            self.win.setWidth(width)
            self.win.setHeight(height)
            spin(20)
            actions = [row for row in self.named("mainMenuEntry") if row.property("modelData").toVariant()["id"] in ("ranked", "quick")]
            self.assertEqual(len(actions), 2)
            self.assertTrue(all(row.height() * width / 1920 >= 80 - .1 for row in actions))
            self.assertTrue(self.named("lobbyChatPane")[0].isVisible())

    def test_ranked_character_grid_uses_runtime_portrait_control_with_clean_missing_art(self):
        from tools.online_shots import snapshot
        self.nav = scene("t5", "ranked_select", "en")
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        self.wait_pages()
        portraits = self.named("fighterSelectPortrait")
        self.assertTrue(portraits)
        self.assertTrue(all(portrait.property("source").isEmpty() for portrait in portraits))
        self.assertTrue(all(portrait.height() > 0 for portrait in portraits))
        self.assertTrue(self.named("lobbyChatPane")[0].isVisible())

    def test_results_reuse_both_supplied_fighter_identities_and_runtime_art_boundary(self):
        from tools.online_shots import snapshot
        self.nav = scene("t5", "result", "en")
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        self.wait_pages()
        self.assertTrue(self.named("sessionFighterPortraits")[0].isVisible())
        for name in ("resultOwnPortrait", "resultPeerPortrait"):
            portrait = self.named(name)[0]
            self.assertTrue(portrait.isVisible())
            self.assertTrue(portrait.property("name"))
            self.assertTrue(portrait.property("source").isEmpty())

    def test_global_offer_stays_above_an_existing_overlapping_toast(self):
        from PySide6.QtCore import QRectF
        from tools.online_shots import snapshot
        from test_ui_loads import spin
        self.nav = scene("t5", "offer_settings", "en")
        self.nav.say("Synthetic notice " * 20)
        self.backend.nav = self.nav
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        self.wait_pages()
        spin(30)
        popup = self.named("globalOffer")[0]
        toast = self.named("resultToast")[0]
        def rect(item):
            return item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))
        overlap = rect(popup).intersected(rect(toast))
        self.assertFalse(overlap.isEmpty())
        region = overlap.adjusted(8, 8, -8, -8).toRect()
        with_toast = self.win.grabWindow().copy(region)
        self.nav.toast = ""
        self.backend._v = snapshot(self.nav)
        self.backend.viewChanged.emit()
        spin(30)
        without_toast = self.win.grabWindow().copy(region)
        self.assertEqual(with_toast, without_toast)
