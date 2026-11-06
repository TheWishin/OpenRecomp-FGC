"""0.1.4: a game release names the launcher it needs (min_launcher), Update all, the test-version hint, progress with
MB / speed / time left, the language row in Settings, logged-in is not busy."""
import os
import sys
import unittest

from openrecomp import game_releases as gr
from openrecomp import game_setup as gs
from openrecomp import i18n

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_game_setup_nav as base  # noqa: E402
from test_game_setup_nav import Game5, text  # noqa: E402


class MinLauncher(unittest.TestCase):
    def test_marker_line_in_the_notes(self):
        for body, want in (("**Needs OpenRecomp-FGC 0.1.3 or newer** (0.1.4 recommended).", "0.1.3"),
                           ("<!-- min_launcher: 0.1.4 -->\nText", "0.1.4"), ("Nothing about it", None)):
            m = gr.RE_MIN_LAUNCHER.search(body)
            self.assertEqual(m.group(1) if m else None, want)

    def test_launcher_too_old(self):
        self.assertEqual(gr.launcher_too_old(dict(min_launcher="0.1.4"), "0.1.3"), "0.1.4")
        self.assertEqual(gr.launcher_too_old(dict(min_launcher="0.1.4"), "0.1.4"), "")
        self.assertEqual(gr.launcher_too_old(dict(min_launcher="0.1.4"), "0.1.10"), "")
        self.assertEqual(gr.launcher_too_old(dict(min_launcher=""), "0.1.2"), "")
        self.assertEqual(gr.launcher_too_old(dict(min_launcher="0.1.4"), ""), "")      # source checkout: never blocked

    def test_notes_hide_the_marker_comment(self):
        self.assertNotIn("min_launcher", gr.release_notes("<!-- min_launcher: 0.1.4 -->\nFaster builds."))

    def test_setup_state_says_needs_launcher_and_refuses_to_start(self):
        setup = gs.GameSetup({}, launcher="0.1.3", latest=lambda src, ch: None)
        offer = dict(version="0.1.5", tag="v0.1.5", prerelease=False, name="v0.1.5", notes="", min_launcher="0.1.4",
                     zip=dict(size=10, name="x.zip", url="u", sha256=None))
        setup.github["t4"] = offer
        setup._st("t4")["installed"] = "0.1.3"
        setup._apply("t4")
        self.assertEqual(setup.state["t4"]["needs_launcher"], "0.1.4")
        self.assertFalse(setup.update("t4", "C:/T4"))
        self.assertFalse(setup.install("t4", "C:/"))
        self.assertEqual(setup.view("t4")["offer"]["min_launcher"], "0.1.4")
        setup.launcher = "0.1.4"
        setup._apply("t4")
        self.assertEqual(setup.state["t4"]["needs_launcher"], "")

    def test_progress_reports_speed_and_time_left(self):
        clock = [100.0]
        setup = gs.GameSetup({}, now=lambda: clock[0], launcher="0.1.4")
        report = setup._progress("t4")
        report("download", 0, 100_000_000)
        clock[0] += 2
        report("download", 20_000_000, 100_000_000)
        st = setup.state["t4"]
        self.assertEqual(st["speed"], 10_000_000)
        self.assertEqual(st["left"], 8)


class Nav014(unittest.TestCase):
    nav = base.SetupNav.nav
    ready_state = base.SetupNav.ready_state

    def test_update_row_says_update_all_and_the_dialog_names_both_versions(self):
        nav = self.nav(Game5("t4"))
        self.ready_state(nav, gid="t4", installed="0.1.3", latest="0.1.5", available=True, needs_launcher="0.1.4",
                         launcher="0.1.3")
        nav.screen, nav.sec["t4"] = "hub", "build"
        row = nav.items()[0]
        self.assertEqual(text(nav, row["verb"]), "Update all")
        self.assertIn("0.1.4", text(nav, row["hint"]))
        nav.setup_offer_update(nav.games[0])
        dialog = text(nav, nav.view()["dialog"])
        self.assertIn("needs OpenRecomp-FGC 0.1.4 (you have 0.1.3)", dialog["text"])
        self.assertEqual([o["label"] for o in dialog["options"]], ["Cancel", "Update all"])
        nav.exit_focus = 1
        nav.act("confirm")
        self.assertIn(("update_all", "t4", "0.1.4"), self.setup.calls)

    def test_progress_line_has_mb_speed_and_time_left(self):
        nav = self.nav(Game5("t4"))
        line = text(nav, nav._setup_progress_text(dict(step="download", done=120_000_000, total=274_000_000,
                                                       speed=8_300_000, left=75)))
        self.assertEqual(line, "Downloading 43 % · 120 of 274 MB · 8.3 MB/s · 1 min 15 s left")
        self.assertEqual(text(nav, nav._setup_progress_text(dict(step="check"))), "Checking")

    def test_up_to_date_names_the_test_version(self):
        nav = self.nav(Game5("t4"))
        nav.on_update_check = lambda: None
        nav.update_state = dict(phase="current", version="", test_version="v0.1.4")
        row = next(item for item in nav._drawer_items() if item["id"] == "updates")
        self.assertEqual(row["value"], "v0.1.4")
        self.assertIn("Test version v0.1.4 is available", text(nav, row["hint"]))
        taken = []
        nav.on_update_test = lambda: taken.append(True) or False
        nav._check_update()
        self.assertEqual(taken, [True])

    def test_logged_in_is_not_busy(self):
        nav = self.nav(Game5("t4"))
        nav.games[0].a.online_state = lambda: dict(phase="logged_in", busy=False)
        self.assertFalse(nav._update_busy())
        nav.games[0].a.online_state = lambda: dict(phase="matched", busy=False)
        self.assertTrue(nav._update_busy())

    def test_language_is_a_settings_row(self):
        nav = self.nav(Game5("t4"))
        changed = []
        nav.on_language = changed.append
        out = nav._settings_groups(nav.games[0], [dict(kind="info", id="none", label="x")])
        row = next(item for item in out if item.get("id") == "language")
        row["set"]("de")
        self.assertEqual((nav.language, changed), ("de", ["de"]))


if __name__ == "__main__":
    unittest.main()
