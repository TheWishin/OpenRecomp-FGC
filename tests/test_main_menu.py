"""Main menu routes are controller-first and never start matchmaking on entry."""
import unittest
from pathlib import Path

from openrecomp import i18n
from openrecomp.nav import Game, Nav
from openrecomp.nav_settings_page import TAB_OF
from tools.online_shots import SyntheticOnline


class MainMenuTests(unittest.TestCase):
    def make(self, game="t5"):
        adapter = SyntheticOnline(game)
        adapter.m["adapter"] = "t4" if game == "t4" else "t5dr"
        nav = Nav([Game(adapter.m, adapter)], language="en")
        return adapter, nav

    def test_shelf_confirm_opens_main_menu_and_back_returns_to_games(self):
        adapter, nav = self.make()
        nav.act("confirm")
        view = nav.view()
        self.assertTrue(view["mainMenu"]["show"])
        self.assertEqual(view["mainMenu"]["entries"][0]["id"], "ranked")
        self.assertEqual(adapter.calls, [])
        nav.act("back")
        self.assertEqual(nav.screen, "start")

    def test_every_entry_routes_without_launching_or_searching(self):
        adapter, nav = self.make()
        nav.dry = True
        nav.open_main_menu()
        entries = nav._main_entries(nav.game)
        for index, entry in enumerate(entries):
            with self.subTest(entry=entry["id"]):
                nav.open_main_menu()
                nav.main_menu_focus = index
                nav.act("confirm")
                self.assertEqual(getattr(nav, "main_menu_game", ""), "")
                if entry["id"] == "games":
                    self.assertEqual(nav.screen, "start")
                else:
                    self.assertEqual(nav.section(), entry["section"])
                    self.assertEqual(nav.screen, "hub")
                    if entry["id"] == "ranked":
                        self.assertEqual(nav.view()["online"]["chapter"], "ranked")
                    nav.act("back")
                    self.assertTrue(nav.view()["mainMenu"]["show"])
        self.assertFalse(any(call[0] in ("start", "search_ranked", "search_casual") for call in adapter.calls))

    def test_capability_hides_unavailable_t4_ranked(self):
        adapter, nav = self.make("t4")
        nav.open_main_menu()
        ids = {entry["id"] for entry in nav._main_entries(nav.game)}
        self.assertNotIn("ranked", ids)
        self.assertIn("rooms", ids)
        adapter.snapshot["capabilities"]["friends"] = False
        self.assertNotIn("friend", {entry["id"] for entry in nav._main_entries(nav.game)})

    def test_pad_selection_and_shoulders_reach_online_pages(self):
        _, nav = self.make()
        nav.dry = True
        nav.open_main_menu()
        nav.act("down")
        self.assertEqual(nav.view()["mainMenu"]["selected"], 1)
        nav.act("prev")
        self.assertEqual(nav.view()["mainMenu"]["selected"], 0)
        nav._open_main_entry(next(e for e in nav._main_entries(nav.game) if e["id"] == "rooms"))
        self.assertEqual(nav.view()["online"]["chapter"], "rooms")
        nav.act("next")
        self.assertEqual(nav.view()["online"]["chapter"], "friends")

    def test_settings_tabs_select_real_rows_and_keep_subtitles_and_values(self):
        _, nav = self.make()
        nav.screen = "hub"
        nav.sec[nav.game.id] = "settings"
        page = nav.view()["settingsPage"]
        self.assertEqual(page["activeTab"], "video")
        self.assertTrue(any(line.get("value") for line in page["tabLines"]))
        self.assertTrue(all(line.get("focused") for line in page["tabLines"] if line.get("hint")))
        for tab in page["tabs"]:
            nav.select_settings_tab(tab["id"])
            item = nav.items()[nav.focus_index(nav.items())]
            self.assertEqual(TAB_OF[item["settingsGroup"]], tab["id"])
            self.assertEqual(nav.view()["settingsPage"]["activeTab"], tab["id"])

    def test_menu_and_tab_captions_exist_in_all_catalogs(self):
        _, nav = self.make()
        keys = [entry["label"][1:] for entry in nav._main_entries(nav.game)]
        keys += ["settings_tabs." + tab for tab in ("video", "audio", "controls", "game", "help")]
        for language in i18n.LANGUAGES:
            for key in keys:
                self.assertIn(key, i18n.catalog(language), (language, key))

    def test_unfinished_install_keeps_the_build_onboarding_flow(self):
        adapter, nav = self.make("t4")
        adapter.is_ready = False
        nav.act("confirm")
        self.assertFalse(nav.view()["mainMenu"]["show"])
        self.assertEqual(nav.section(), "build")

    def test_back_and_social_prompts_match_their_current_destinations(self):
        adapter, nav = self.make()
        nav.dry = True
        nav.open_main_menu()
        nav._open_main_entry(next(e for e in nav._main_entries(nav.game) if e["id"] == "lobby"))
        items = nav.items()
        nav.focus[nav.key()] = next(n for n, row in enumerate(items) if row.get("id") == "challenge:p1")
        prompts = {prompt["action"]: prompt["label"] for prompt in nav.view()["prompts"]}
        self.assertEqual(prompts["social"], i18n.text("en", "online_ui.chapter.profile"))
        self.assertEqual(prompts["back"], i18n.text("en", "main_menu.title"))
        nav.open_main_menu()
        nav.act("social")
        self.assertEqual(nav.overlay, "drawer")
        self.assertEqual(adapter.calls, [])

    def test_game_art_overlay_keeps_help_readable_over_a_white_background(self):
        import tempfile
        from PySide6.QtCore import QObject, QUrl
        from PySide6.QtGui import QColor, QGuiApplication, QImage
        from PySide6.QtQml import QQmlApplicationEngine
        from test_accessibility import contrast
        from test_ui_loads import FakeBackend, spin, wait_pages
        ui = Path(__file__).parents[1] / "openrecomp" / "ui"
        app = QGuiApplication.instance() or QGuiApplication([])
        adapter, nav = self.make()
        nav.open_main_menu()
        backend = FakeBackend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda entries: warnings.extend(item.toString() for item in entries))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(str(ui / "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.show()

        def rgb(colour):
            return colour.redF(), colour.greenF(), colour.blueF()

        def blend(front, back, alpha):
            return tuple(front[index] * alpha + back[index] * (1 - alpha) for index in range(3))

        def stops(item):
            children = item.findChildren(QObject)
            return [QColor(child.property("color")) for child in children
                    if child.property("position") is not None and child.property("color") is not None]

        try:
            with tempfile.TemporaryDirectory(prefix="vibe-menu-white-", dir=ui.parents[1] / "build") as directory:
                image = QImage(8, 8, QImage.Format_RGB32)
                image.fill(QColor("white"))
                path = Path(directory) / "white.png"
                self.assertTrue(image.save(str(path)))
                for game in ("", "t5dr", "t4"):
                    for high_contrast in (False, True):
                        backend._v = nav.view()
                        backend._v.update(gameTheme=game, highContrast=high_contrast, reducedMotion=True,
                                          livingBackground=dict(theme=game, source=QUrl.fromLocalFile(str(path)).toString()))
                        backend.viewChanged.emit()
                        wait_pages(window)
                        spin(220)
                        backdrop = next(item for item in window.findChildren(QObject, "livingBackground")
                                        if item.isVisible())
                        art = backdrop.findChild(QObject, "backgroundRuntimeArt")
                        self.assertGreater(art.property("paintedWidth"), 0)
                        atmosphere = backdrop.findChild(QObject, "backgroundAtmosphere")
                        veil = backdrop.findChild(QObject, "backgroundReadabilityVeil")
                        veil_stops = stops(veil)
                        self.assertTrue(veil_stops)
                        ground = rgb(window.property("ground"))
                        # Maximal atmosphere and one maximal streak conservatively
                        # bound the underlay, without relying on source picture colours.
                        underlay = blend(rgb(backdrop.property("atmosphere")), ground, atmosphere.opacity())
                        streaks = [item for item in backdrop.childItems()
                                   if item.property("index") is not None and item.property("color") is not None]
                        self.assertTrue(streaks)
                        streak = max(streaks, key=lambda item: item.opacity())
                        underlay = blend(rgb(streak.property("color")), underlay, streak.opacity())
                        underlay = blend((1, 1, 1), underlay, art.opacity())
                        veil_colour = min(veil_stops, key=lambda colour: colour.alphaF())
                        underlay = blend(rgb(veil_colour), underlay, veil_colour.alphaF())
                        fighters = window.findChild(QObject, "mainMenuFighters")
                        menu = fighters.parentItem().parentItem()
                        menu_overlay = menu.childItems()[0]
                        overlay_stops = stops(menu_overlay)
                        self.assertTrue(overlay_stops)
                        overlay = min(overlay_stops, key=lambda colour: colour.alphaF())
                        background = QColor.fromRgbF(*blend(rgb(overlay), underlay, overlay.alphaF())).name()
                        with self.subTest(game=game, high_contrast=high_contrast):
                            self.assertGreaterEqual(contrast(window.property("muted").name(), background), 4.5)
                            self.assertGreaterEqual(contrast(window.property("textC").name(), background), 4.5)
        finally:
            window.hide()
            window.setProperty("allowClose", True)
            window.close()
            del engine
        self.assertEqual(warnings, [])

    def test_practice_entry_focuses_the_real_practice_setting(self):
        adapter, nav = self.make()
        adapter.settings = lambda: [dict(id="practice", label="@practice_tools", value=False,
                                         options=[(False, "@off"), (True, "@on")], hint="@practice.hint")]
        nav.open_main_menu()
        entry = next(e for e in nav._main_entries(nav.game) if e["id"] == "practice")
        nav._open_main_entry(entry)
        self.assertEqual(nav.section(), "settings")
        self.assertEqual(nav.items()[nav.focus_index(nav.items())]["id"], "practice")
        page = nav.view()["settingsPage"]
        # the Game tab holds one row here, so it is shown on its neighbour's page (0.1.7): the active tab owns it
        self.assertIn(page["activeTab"], [tab["id"] for tab in page["tabs"]])
        self.assertTrue(any(line.get("index") == nav.focus_index(nav.items()) for line in page["tabLines"]))
        self.assertEqual(adapter.calls, [])
        adapter.settings = lambda: [dict(id="training", value="off", label="@training_display", options=[])]
        self.assertNotIn("practice", {e["id"] for e in nav._main_entries(nav.game)})


class MenuScene(unittest.TestCase):
    from test_ui_polish import ScenePolish
    setUpClass = classmethod(ScenePolish.setUpClass.__func__)
    setUp = ScenePolish.setUp
    tearDown = ScenePolish.tearDown
    named = ScenePolish.named
    wait_pages = ScenePolish.wait_pages
    publish = ScenePolish.publish

    def test_result_toast_keeps_its_caption_during_fade_and_reduced_motion_is_immediate(self):
        from test_ui_loads import spin
        self.nav.reduced_motion = True
        self.nav.say("Receipt")
        self.publish()
        toast = self.named("resultToast")[0]
        self.assertTrue(toast.isVisible())
        self.assertGreater(toast.x(), 960)
        self.nav.tick(3.1)
        self.publish()
        self.assertFalse(toast.isVisible())
        self.assertEqual(self.win.property("lastToast"), "Receipt")
        self.nav.reduced_motion = False
        self.nav.say("Next receipt")
        self.publish()
        spin(200)
        self.nav.tick(3.1)
        self.backend._v = self.nav.view()
        self.backend.viewChanged.emit()
        spin(60)
        self.assertGreater(toast.opacity(), 0)
        self.assertLess(toast.opacity(), 1)
        self.assertEqual(self.win.property("lastToast"), "Next receipt")
        spin(200)
        self.assertFalse(toast.isVisible())

    def test_larger_rooms_create_action_stays_visible_and_settings_values_fit(self):
        from PySide6.QtCore import QPointF
        from tools.online_shots import scene, snapshot
        self.win.setWidth(1280)
        self.win.setHeight(720)
        for chapter in ("rooms", "settings", "home"):
            self.nav = scene("t5", chapter, "de", text_size=130, high_contrast=True)
            self.backend.nav = self.nav
            self.backend._v = snapshot(self.nav)
            self.backend.viewChanged.emit()
            self.wait_pages()
            from test_ui_loads import spin
            spin(50)
            if chapter == "rooms":
                self.assertFalse(any(item.isVisible() for item in self.named("roomAccessHelp")))
                action = next(item for item in self.named("onlinePrimaryButton") if item.isVisible())
                bottom = action.mapToScene(QPointF(action.width(), action.height()))
                self.assertGreater(action.height(), 30)
                self.assertLess(bottom.y(), self.win.height() - 60)
            elif chapter == "settings":
                detail = self.named("settingsDetail")[0]
                self.assertLessEqual(detail.x() + detail.width(), 1920)
                self.assertTrue(all(line.get("focused") for line in self.nav.view()["settingsPage"]["tabLines"] if line.get("hint")))
            else:
                status = self.named("mainMenuStatus")[0]
                self.assertTrue(status.isVisible())
                self.assertGreater(status.width(), 100)
                self.assertLessEqual(status.property("contentHeight"), status.height() + 1)


if __name__ == "__main__":
    unittest.main()
