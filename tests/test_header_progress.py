"""Owner (2026-11-10): while a build or an update runs, the top bar shows it on every screen -- the step, the
percentage and the time left of the card it belongs to -- and a click opens that card. The bar reads the card's own
state (the Build page's big card, the install / update progress card): there is no second progress source. It is gone
when the job ends: success, failure or cancel."""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openrecomp import i18n  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_build_page import STEPS, Page  # noqa: E402
from test_game_setup_nav import Setup  # noqa: E402
from test_progress_card import running  # noqa: E402


def text(nav, value):
    return i18n.localize(value, nav.language)


class Env(unittest.TestCase):
    """Two games on the fake build adapter of the Build page's tests; the clock is the test's."""

    def nav(self, language="en"):
        self.t4, self.t5 = Page("t4"), Page("t5dr", ready=True)
        self.setup = Setup()
        self.now = 1000.0
        nav = Nav([Game(self.t4.m, self.t4), Game(self.t5.m, self.t5)], language=language, on_setup=self.setup)
        nav.clock = lambda: self.now
        nav.on_update_cancel = lambda: True
        return nav

    def start_build(self, nav, adapter=None, **state):
        adapter = adapter or self.t4
        adapter.state.update(dict(running=True, phase="build", fraction=0.62, title="Compile", step_no=(5, 7),
                                  steps=[dict(k=s, v="", state="todo") for s in STEPS], line="cl", lines=["cl"]), **state)
        nav.poll_build(1.0)                     # the app's timer: it runs on every screen

    def end_build(self, nav, adapter=None, **state):
        adapter = adapter or self.t4
        adapter.state.update(dict(running=False, fraction=0.0, title="", step_no=None), **state)
        nav.poll_build(1.0)

    def bar(self, nav):
        return nav.view()["headerProgress"]

    def card(self, nav, gid="t4"):
        """The Build page's big card of one game, as the page draws it."""
        other = Nav.__new__(Nav)
        other.__dict__.update(nav.__dict__)
        other.overlay, other.screen, other.main_menu_game = None, "hub", ""
        other.game = next(g for g in nav.games if g.id == gid)
        other.sec = dict(nav.sec, **{gid: "build"})
        return other.view()["build"]["main"]


class Appears(Env):
    def test_nothing_runs_no_bar(self):
        nav = self.nav()
        self.assertEqual(self.bar(nav), dict(show=False))
        nav.poll_build(1.0)
        self.assertFalse(self.bar(nav)["show"])

    def test_a_build_shows_on_every_screen_and_tab(self):
        nav = self.nav()
        self.start_build(nav)
        self.assertTrue(self.bar(nav)["show"])                    # the shelf
        nav.screen = "hub"
        for game in nav.games:                                    # the game being built and the other one
            nav._select_game(game)
            for section in nav.sections(game):
                nav.sec[game.id] = section
                bar = self.bar(nav)
                self.assertTrue(bar["show"], (game.id, section))
                self.assertEqual((bar["id"], bar["build"]), ("t4", True))
        nav.open_launcher_settings()
        self.assertEqual(nav.screen, "launcher")
        self.assertTrue(self.bar(nav)["show"])
        nav.screen, nav.overlay = "hub", None
        nav.act("social", device="xbox")                          # behind the drawer too
        self.assertEqual(nav.overlay, "drawer")
        self.assertTrue(self.bar(nav)["show"])

    def test_an_update_shows_on_every_screen(self):
        nav = self.nav()
        nav.setup_state = {"t5dr": running()}
        self.assertTrue(self.bar(nav)["show"])
        nav.screen = "hub"
        for game in nav.games:
            nav._select_game(game)
            for section in nav.sections(game):
                nav.sec[game.id] = section
                bar = self.bar(nav)
                self.assertEqual((bar["show"], bar["id"], bar["build"]), (True, "t5dr", False), (game.id, section))

    def test_the_launcher_update_shows_too(self):
        nav = self.nav()
        nav.update_state = dict(phase="installing", version="v1.2.3", step="download", done=10, total=50, speed=0,
                                left=0, can_cancel=True, cancelling=False, reason="")
        bar = self.bar(nav)
        self.assertEqual((bar["show"], bar["id"], bar["name"], bar["percent"]), (True, "launcher", "Launcher", "20 %"))


class SameAsTheCard(Env):
    def test_step_percentage_and_time_left_are_the_build_cards(self):
        nav = self.nav()
        nav.build_history = {"t4": dict(steps=[["build:Compile", 300.0], ["build:Link", 60.0]], total=360.0)}
        self.start_build(nav)
        self.now += 17
        nav.poll_build(1.0)
        bar, card = self.bar(nav), self.card(nav)
        self.assertEqual(bar["step"], card["stepLine"])
        self.assertEqual(bar["step"], "Step 5 of 7: Compile")
        self.assertEqual(bar["fraction"], card["progress"])
        self.assertEqual(bar["percent"], "62 %")
        self.assertEqual(bar["eta"], card["eta"])
        self.assertEqual(bar["eta"], "About 6 min left")
        self.assertEqual(bar["title"], card["title"])
        self.assertEqual(bar["name"], "T4")

    def test_the_bar_follows_the_card_step_by_step(self):
        nav = self.nav()
        self.start_build(nav)
        for n, fraction in ((5, 0.62), (6, 0.8), (7, 0.99)):
            self.now += 40
            self.start_build(nav, fraction=fraction, step_no=(n, 7), title=STEPS[n - 1])
            bar, card = self.bar(nav), self.card(nav)
            self.assertEqual((bar["step"], bar["fraction"], bar["eta"]), (card["stepLine"], card["progress"], card["eta"]))
            self.assertEqual(bar["percent"], str(int(fraction * 100)) + " %")

    def test_installing_build_tools_has_the_cards_line_and_no_invented_percentage(self):
        nav = self.nav()
        self.start_build(nav, phase="tools", tools=dict(done=0, total=0, current=""), step_no=None, fraction=0.0)
        bar, card = self.bar(nav), self.card(nav)
        self.assertEqual((bar["step"], bar["fraction"], bar["percent"]), (card["stepLine"], -1.0, ""))
        self.start_build(nav, phase="tools", tools=dict(done=1, total=4, current="CMake"), step_no=None, fraction=0.0)
        bar, card = self.bar(nav), self.card(nav)
        self.assertEqual((bar["step"], bar["fraction"], bar["percent"]), (card["stepLine"], 0.25, "25 %"))

    def test_an_update_says_what_its_progress_card_line_says(self):
        nav = self.nav()
        nav.setup_state = {"t5dr": running()}
        line = nav.view()["progressCard"]["lines"][0]
        bar = self.bar(nav)
        self.assertEqual(line["text"], "T5DR · Download 45 % · 82/181 MB · 1 min")
        self.assertEqual((bar["name"], bar["step"], bar["percent"], bar["eta"]), ("T5DR", "Download", "45 %", "1 min"))
        self.assertEqual(bar["fraction"], line["fraction"])
        nav.setup_state["t5dr"].update(step="swap", done=0, total=0)     # the exchange: no percentage, as on the card
        line, bar = nav.view()["progressCard"]["lines"][0], self.bar(nav)
        self.assertEqual(line["text"], "T5DR · Installing, please wait")
        self.assertEqual((bar["step"], bar["percent"], bar["fraction"]), ("Installing, please wait", "", -1.0))

    def test_there_is_no_second_progress_source(self):
        """The bar asks the adapter for nothing the card does not ask for, and never while no build runs."""
        nav = self.nav()
        asked = []
        real = self.t4.build_state
        self.t4.build_state = lambda: asked.append(1) or real()
        self.bar(nav)
        self.assertEqual(asked, [])
        nav.header_progress_view()
        self.assertEqual(asked, [])
        self.assertFalse(hasattr(nav, "header_progress_state"))

    def test_two_jobs_show_the_first_and_count_the_other(self):
        nav = self.nav()
        self.start_build(nav)
        nav.setup_state = {"t5dr": running()}
        bar = self.bar(nav)
        self.assertEqual((bar["id"], bar["more"]), ("t4", "+1 more"))
        self.end_build(nav, result="@t4.build_finished")
        bar = self.bar(nav)
        self.assertEqual((bar["id"], bar["more"]), ("t5dr", ""))

    def test_every_language_has_the_bars_texts(self):
        for code in i18n.LANGUAGES:
            nav = self.nav(code)
            self.start_build(nav)
            nav.setup_state = {"t5dr": running()}
            bar = self.bar(nav)
            self.assertEqual(bar["percent"], "62 %", code)
            self.assertIn("1", bar["more"], code)
            for key in ("header_progress.percent", "header_progress.more"):
                self.assertIn(key, i18n.catalog(code), (code, key))
            self.assertNotIn("@", " ".join(str(bar[k]) for k in ("name", "title", "step", "percent", "eta", "more", "open")), code)


class Disappears(Env):
    def test_gone_after_success(self):
        nav = self.nav()
        self.start_build(nav)
        self.assertTrue(self.bar(nav)["show"])
        self.end_build(nav, result="@t4.build_finished")
        self.assertEqual(self.bar(nav), dict(show=False))

    def test_gone_after_failure(self):
        nav = self.nav()
        self.start_build(nav)
        self.end_build(nav, failed="build", result="@t4.build_incomplete")
        self.assertEqual(self.bar(nav), dict(show=False))

    def test_gone_after_cancel(self):
        nav = self.nav()
        self.start_build(nav)
        self.end_build(nav, result="@t4.build_cancelled")
        self.assertEqual(self.bar(nav), dict(show=False))

    def test_gone_at_once_even_before_the_next_poll(self):
        nav = self.nav()
        self.start_build(nav)
        self.t4.state.update(running=False, result="@t4.build_cancelled")
        self.assertFalse(self.bar(nav)["show"])

    def test_a_second_build_shows_again(self):
        nav = self.nav()
        self.start_build(nav)
        self.end_build(nav, failed="build", result="@t4.build_incomplete")
        self.start_build(nav, fraction=0.1, step_no=(1, 7), title=STEPS[0])
        self.assertEqual(self.bar(nav)["percent"], "10 %")

    def test_an_update_is_gone_after_success_failure_and_cancel(self):
        for phase in ("updated", "ready", "error", "cancelled"):
            nav = self.nav()
            nav.setup_state = {"t5dr": running()}
            self.assertTrue(self.bar(nav)["show"])
            nav.setup_state["t5dr"].update(phase=phase)
            self.assertEqual(self.bar(nav), dict(show=False), phase)

    def test_the_launcher_update_is_gone_when_it_ends(self):
        for phase in ("ready", "error", "cancelled", "idle"):
            nav = self.nav()
            nav.update_state = dict(phase="installing", version="v1", step="download", done=1, total=2, speed=0, left=0,
                                    can_cancel=True, cancelling=False, reason="")
            self.assertTrue(self.bar(nav)["show"])
            nav.update_state = dict(nav.update_state, phase=phase)
            self.assertEqual(self.bar(nav), dict(show=False), phase)


class OpensTheCard(Env):
    def test_a_click_opens_the_build_card_from_anywhere(self):
        nav = self.nav()
        self.start_build(nav)
        places = [("start", None, None), ("hub", "t5dr", "play"), ("hub", "t4", "settings"), ("launcher", None, None)]
        for screen, gid, section in places:
            nav.overlay, nav.screen = None, "hub"
            if gid:
                nav._select_game(next(g for g in nav.games if g.id == gid))
                nav.sec[gid] = section
            if screen == "launcher":
                nav.open_launcher_settings()
            else:
                nav.screen = screen
            self.assertTrue(nav.header_progress_open(), (screen, gid, section))
            self.assertEqual((nav.screen, nav.game.id, nav.section(), nav.overlay), ("hub", "t4", "build", None))
            view = nav.view()
            main = view["build"]["main"]
            self.assertTrue(view["build"]["show"])
            self.assertEqual((main["title"], main["stepLine"], main["progress"]), ("Build running", "Step 5 of 7: Compile", 0.62))
            self.assertTrue(main["button"]["focused"])            # Confirm asks whether to cancel, as on the card

    def test_a_click_opens_the_update_window(self):
        nav = self.nav()
        nav.setup_state = {"t5dr": running()}
        nav.screen = "hub"
        self.assertTrue(nav.header_progress_open())
        self.assertEqual((nav.overlay, nav.confirm_kind, nav.setup_game), ("dialog", "setup_progress", "t5dr"))
        self.assertTrue(self.bar(nav)["show"])                    # the job still runs: the bar stays
        self.assertEqual(self.setup.calls, [])                    # opening starts and cancels nothing

    def test_a_click_opens_the_launcher_update_window(self):
        nav = self.nav()
        nav.update_state = dict(phase="installing", version="v1", step="download", done=1, total=2, speed=0, left=0,
                                can_cancel=True, cancelling=False, reason="")
        self.assertTrue(nav.header_progress_open())
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "update_progress"))

    def test_nothing_opens_behind_a_window_or_without_a_job(self):
        nav = self.nav()
        self.assertFalse(nav.header_progress_open())
        self.start_build(nav)
        nav._ask("exit")
        before = (nav.screen, nav.game.id, nav.overlay, nav.confirm_kind)
        self.assertFalse(nav.header_progress_open())
        self.assertEqual((nav.screen, nav.game.id, nav.overlay, nav.confirm_kind), before)

    def test_opening_never_starts_or_cancels_a_build(self):
        nav = self.nav()
        self.start_build(nav)
        nav.header_progress_open()
        self.assertEqual(self.t4.calls, [])

    def test_the_keyboard_shortcut_and_the_pad_drawer_reach_the_build_card(self):
        nav = self.nav()
        nav.device = "kb"
        self.assertNotIn("progress", [p["action"] for p in nav.view()["prompts"]])
        self.start_build(nav)
        self.assertIn(("progress", "Show progress"), [(p["action"], p["label"]) for p in nav.view()["prompts"]])
        nav.act("progress", device="kb")
        self.assertEqual((nav.screen, nav.game.id, nav.section()), ("hub", "t4", "build"))
        self.assertNotIn("progress", [p["action"] for p in nav.view()["prompts"]])      # already on its page
        nav._select_game(nav.games[1])
        nav.sec["t5dr"] = "play"
        nav.act("social", device="xbox")
        rows = [r["id"] for r in nav._drawer_items()]
        self.assertIn("progress", rows)
        nav.drawer_focus = rows.index("progress")
        nav.act("confirm", device="xbox")
        self.assertEqual((nav.overlay, nav.game.id, nav.section()), (None, "t4", "build"))


class Scene(unittest.TestCase):
    """The real top bar, offscreen, with the fake job."""

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        from openrecomp.app import UI_DIR
        cls.app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        for font in (Path(UI_DIR) / "fonts").glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font))

    def scene(self, language="en"):
        from PySide6.QtCore import QUrl, Slot
        from PySide6.QtQml import QQmlApplicationEngine
        from openrecomp.app import UI_DIR
        from test_ui_loads import FakeBackend, wait_pages

        class Backend(FakeBackend):
            opened = 0

            @Slot()
            def openHeaderProgress(self):
                self.opened += 1
                self.nav.header_progress_open()
                self.refresh()

        env = Env()
        nav = env.nav(language)
        nav.dry = True
        backend = Backend(nav)
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
        engine.setInitialProperties(dict(backend=backend, wantFull=False))
        engine.load(QUrl.fromLocalFile(os.path.join(UI_DIR, "Main.qml")))
        self.assertTrue(engine.rootObjects(), warnings)
        window = engine.rootObjects()[0]
        window.show()
        wait_pages(window)

        def close(engine=engine):                                 # the engine lives until its window is closed
            window.setProperty("allowClose", True)
            window.close()
        self.addCleanup(close)
        return env, nav, backend, engine, window, warnings

    def item(self, window, name):
        from PySide6.QtCore import QObject
        return window.findChild(QObject, name)

    def click(self, window, item):
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        from test_ui_loads import spin
        centre = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, centre)
        spin(30)

    def test_the_bar_is_in_the_top_bar_only_while_a_job_runs_and_a_click_opens_the_card(self):
        from PySide6.QtCore import QRectF
        from test_ui_loads import spin, wait_pages
        env, nav, backend, _engine, window, warnings = self.scene()
        bar = self.item(window, "headerProgress")
        self.assertIsNotNone(bar)
        self.assertFalse(bar.isVisible())
        env.start_build(nav)
        backend.refresh()
        spin(30)
        self.assertTrue(bar.isVisible())
        top = self.item(window, "topBar")
        self.assertIs(bar.parentItem(), top)
        identity, actions = self.item(window, "topIdentity"), self.item(window, "topActions")
        self.assertGreaterEqual(bar.x(), identity.x() + identity.width() + 16)
        self.assertLessEqual(bar.x() + bar.width() + 16, actions.x())
        self.assertGreaterEqual(bar.mapRectToScene(QRectF(0, 0, bar.width(), bar.height())).height(), 44 * window.width() / 1920 - .1)
        words = self.item(window, "headerProgressText").property("text")
        figures = self.item(window, "headerProgressFigures").property("text")
        card = env.card(nav)
        self.assertIn(card["stepLine"], words)
        self.assertIn("62 %", figures)
        self.assertIn(card["eta"], figures)
        fill, track = self.item(window, "headerProgressFill"), self.item(window, "headerProgressTrack")
        self.assertAlmostEqual(fill.width() / track.width(), 0.62, places=2)
        for screen in ("start", "hub", "launcher"):               # every screen keeps it
            nav.overlay = None
            if screen == "launcher":
                nav.open_launcher_settings()
            else:
                nav.screen = screen
            backend.refresh()
            wait_pages(window)
            self.assertTrue(bar.isVisible(), screen)
        nav.overlay, nav.screen = None, "start"
        backend.refresh()
        wait_pages(window)
        self.click(window, bar)
        self.assertEqual(backend.opened, 1)
        self.assertEqual((nav.screen, nav.game.id, nav.section()), ("hub", "t4", "build"))
        wait_pages(window)
        self.assertEqual(self.item(window, "buildStepLine").property("text"), card["stepLine"])
        for result in (dict(result="@t4.build_finished"), dict(failed="build", result="@t4.build_incomplete"),
                       dict(result="@t4.build_cancelled")):
            env.start_build(nav)
            backend.refresh()
            spin(30)
            self.assertTrue(bar.isVisible(), result)
            env.end_build(nav, **dict(dict(failed=""), **result))
            backend.refresh()
            spin(30)
            self.assertFalse(bar.isVisible(), result)
        self.assertEqual(warnings, [])

    def test_the_bar_fits_between_identity_and_actions_in_every_language_and_text_size(self):
        from test_ui_loads import spin
        env, nav, backend, _engine, window, warnings = self.scene()
        env.start_build(nav)
        nav.setup_state = {"t5dr": running()}
        for screen in ("start", "hub"):
            nav.screen = screen
            for language in i18n.LANGUAGES:
                for percent in (100, 130):
                    with self.subTest(screen=screen, language=language, text=percent):
                        nav.language, nav.text_size = language, percent
                        backend.refresh()
                        spin(10)
                        bar = self.item(window, "headerProgress")
                        identity, actions = self.item(window, "topIdentity"), self.item(window, "topActions")
                        self.assertLessEqual(identity.x() + identity.width() + 16, actions.x())
                        if bar.isVisible():
                            self.assertGreaterEqual(bar.x(), identity.x() + identity.width() + 16)
                            self.assertLessEqual(bar.x() + bar.width() + 16, actions.x())
                            figures = self.item(window, "headerProgressFigures")
                            self.assertLessEqual(figures.x() + figures.width(), bar.width())
                            self.assertLessEqual(bar.height(), self.item(window, "topBar").height())
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
