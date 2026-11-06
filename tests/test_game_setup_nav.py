"""The launcher's install / update rows, dialogs and tile badge for T5DR Online and T4 (Nav only, no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrecomp import i18n  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402


class Game5(Fake):
    def __init__(self, gid="t5dr", found=True):
        super().__init__(manifest(gid, adapter=gid), is_ready=found)
        self.is_found = found
        self.root = "C:/games/T5DR-Online-1.2.0" if found else None

    def found(self):
        return self.is_found


class Setup:
    """Stands in for the backend's GameSetup + app actions."""

    def __init__(self):
        self.calls = []
        self.answers = dict(default_parent="D:/Games", space=dict(problem="", need=3_000_000_000, free=50_000_000_000,
                                                                 target="D:/Games/T5DR-Online-1.2.1"),
                            install=True, update=True, check=True)

    def __call__(self, action, gid, arg):
        self.calls.append((action, gid, arg))
        return self.answers.get(action, True)


def text(nav, value):
    return i18n.localize(value, nav.language)


class SetupNav(unittest.TestCase):
    def nav(self, *adapters, prereleases=False):
        self.setup = Setup()
        nav = Nav([Game(a.m, a) for a in adapters], language="en", on_setup=self.setup, game_prereleases=prereleases,
                  on_prereleases=lambda on: self.setup.calls.append(("prereleases", "", on)))
        return nav

    def ready_state(self, nav, gid="t5dr", **kw):
        state = dict(phase="ready", installed="", latest="1.2.1", required=False, available=False, size=95_000_000,
                     step="", done=0, total=0, offer=dict(version="1.2.1", size=95_000_000, name="v1.2.1",
                                                          prerelease=False, notes="Fixes"))
        state.update(kw)
        nav.setup_state = {gid: state}

    def test_missing_game_tile_leads_to_install_and_the_install_row_is_first(self):
        nav = self.nav(Game5(found=False))
        tile = nav.view()["shelf"]["tiles"][0]
        self.assertEqual(text(nav, tile["bar"]), "Install or choose folder")
        nav.act("confirm", device="xbox")
        self.assertEqual((nav.screen, nav.sec["t5dr"]), ("hub", "build"))
        first = nav.items()[0]
        self.assertEqual((first["id"], text(nav, first["label"])), ("game_setup", "Install Tekken 5 DR Online"))
        self.assertEqual(text(nav, first["detail"]["rows"][0]["v"]), "TheWishin/T5DROnline")

    def test_install_by_controller_asks_where_then_downloads_and_reports_progress(self):
        nav = self.nav(Game5(found=False))
        nav.act("confirm", device="xbox")                 # tile -> Build
        nav.act("confirm", device="xbox")                 # Install: looks up the release first
        self.assertEqual(self.setup.calls[-1], ("check", "t5dr", True))
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_loading"))
        self.ready_state(nav)
        nav.poll_setup([("t5dr", "check", dict(offer=None), None)])
        self.assertEqual(nav.confirm_kind, "setup_install")
        dialog = text(nav, nav.view()["dialog"])
        self.assertIn("D:/Games/T5DR-Online-1.2.1", dialog["text"])
        self.assertEqual([o["label"] for o in dialog["options"]], ["Other folder", "Install here"])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("install", "t5dr", "D:/Games"))
        self.assertEqual(nav.confirm_kind, "setup_progress")
        nav.setup_state["t5dr"].update(phase="installing", step="download", done=47_500_000, total=95_000_000)
        self.assertIn("Downloading 50 %", text(nav, nav.view()["dialog"])["text"])
        nav.poll_setup([("t5dr", "install", "D:/Games/T5DR-Online-1.2.1", None)])
        self.assertEqual(self.setup.calls[-1], ("attach", "t5dr", "D:/Games/T5DR-Online-1.2.1"))
        self.assertIsNone(nav.overlay)

    def test_other_folder_opens_the_folder_picker_and_a_space_problem_is_said(self):
        nav = self.nav(Game5(found=False))
        self.ready_state(nav)
        nav.setup_begin(nav.games[0])
        self.assertEqual(nav.confirm_kind, "setup_install")
        nav.act("confirm", device="xbox")                 # focus 0 = Other folder
        self.assertEqual(nav.overlay, "picker")
        self.setup.answers["space"] = dict(problem="@setup.err_space", need=9, free=1, target="E:/x/T5DR-Online-1.2.1")
        nav.setup_folder_picked("E:/x")
        self.assertIn("Not enough free space", text(nav, nav.view()["dialog"])["text"])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertNotIn("install", [c[0] for c in self.setup.calls])

    def test_update_needed_badge_hint_and_x_button_on_the_tile(self):
        nav = self.nav(Game5())
        self.ready_state(nav, installed="1.2.0", required=True, available=True)
        view = nav.view()
        self.assertEqual(text(nav, view["shelf"]["tiles"][0]["update"]), "UPDATE NEEDED")
        self.assertEqual(text(nav, view["hint"]), "An update is needed to play online. Offline play still works.")
        self.assertIn(("x", "Update"), [(p["action"], text(nav, p["label"])) for p in view["prompts"]])
        nav.act("x", device="xbox")
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_update"))
        dialog = text(nav, nav.view()["dialog"])
        self.assertIn("from 1.2.0 to 1.2.1", dialog["text"])
        self.assertEqual(nav.exit_focus, 0)               # No is preselected
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("update", "t5dr", None))

    def test_update_row_in_play_and_online_sections_and_offline_play_stays(self):
        nav = self.nav(Game5())
        self.ready_state(nav, installed="1.2.0", required=True, available=True)
        nav.screen = "hub"
        for section in ("play", "online"):
            nav.sec["t5dr"] = section
            row = nav.items()[0]
            self.assertEqual((row["id"], text(nav, row["label"])), ("game_update", "Update needed for online"))
        nav.sec["t5dr"] = "play"
        self.assertIn("start", [r.get("id") for r in nav.items()])

    def test_no_update_no_row_and_a_newer_version_is_only_available(self):
        nav = self.nav(Game5())
        self.ready_state(nav, installed="1.2.1")
        nav.screen, nav.sec["t5dr"] = "hub", "play"
        self.assertNotIn("game_update", [r.get("id") for r in nav.items()])
        nav.screen = "start"
        self.assertNotIn("update", nav.view()["shelf"]["tiles"][0])
        self.ready_state(nav, installed="1.2.0", available=True)
        self.assertEqual(text(nav, nav.view()["shelf"]["tiles"][0]["update"]), "UPDATE")

    def start_update(self, nav):
        self.ready_state(nav, installed="1.2.0", available=True)
        nav.setup_offer_update(nav.games[0])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        nav.setup_state["t5dr"].update(phase="updating", step="download", done=0, total=0)
        self.assertEqual(nav.confirm_kind, "setup_progress")

    def test_quit_during_an_update_is_refused_and_shows_the_progress(self):
        nav = self.nav(Game5())
        quits = []
        nav.on_quit = lambda: quits.append(1)
        self.start_update(nav)
        nav.overlay = None                                 # even with the dialog gone (window close, quit key)
        self.assertFalse(nav.request_quit())
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_progress"))
        self.assertIn("installed or updated", text(nav, nav.toast))
        nav.act("quit", device="kb")
        self.assertEqual(nav.confirm_kind, "setup_progress")
        self.assertEqual(quits, [])
        nav.setup_state["t5dr"].update(phase="updated")
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=False, restart=False), None)])
        self.assertTrue(nav.request_quit())                # finished: quitting asks as usual
        self.assertEqual(nav.confirm_kind, "exit")

    def test_cancel_keeps_the_dialog_until_the_worker_has_stopped(self):
        nav = self.nav(Game5())
        self.start_update(nav)
        nav.act("back", device="xbox")                    # Back hides the window; the update goes on
        self.assertIsNone(nav.overlay)
        self.assertNotIn("cancel", [c[0] for c in self.setup.calls])
        nav.setup_offer_update(nav.games[0])              # shown again
        nav.act("right", device="xbox")                   # Hide -> Cancel
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("cancel", "t5dr", None))
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_progress"))   # Play/Build stay blocked
        self.assertIn("Cancelling", text(nav, nav.view()["dialog"])["text"])
        nav.act("confirm", device="xbox")                 # only Hide is left now
        self.assertEqual([c for c in self.setup.calls if c[0] == "cancel"], [("cancel", "t5dr", None)])  # asked once
        nav.setup_offer_update(nav.games[0])
        nav.setup_state["t5dr"].update(phase="ready", error="@setup.cancelled")
        nav.poll_setup([("t5dr", "update", None, ("@setup.cancelled", ""))])
        self.assertIsNone(nav.overlay)

    def test_t5dr_update_asks_to_restart_the_launcher(self):
        nav = self.nav(Game5())
        self.ready_state(nav, installed="1.2.0", available=True)
        nav.setup_offer_update(nav.games[0])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=False, restart=True), None)])
        self.assertEqual(nav.confirm_kind, "setup_restart")
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("restart", "t5dr", None))

    def test_an_unknown_installed_version_reads_as_own_version(self):
        nav = self.nav(Game5("t4"))
        self.ready_state(nav, gid="t4", installed="", latest="0.1.1", available=True)
        nav.screen, nav.sec["t4"] = "hub", "build"
        row = nav.items()[0]
        self.assertEqual((row["id"], text(nav, row["value"])), ("game_update", "own version → 0.1.1"))
        nav.setup_offer_update(nav.games[0])
        self.assertIn("from own version to 0.1.1", text(nav, nav.view()["dialog"])["text"])

    def test_t4_update_reloads_and_says_build_again(self):
        nav = self.nav(Game5("t4"))
        self.ready_state(nav, gid="t4", installed="0.1.0-beta.1", available=True)
        nav.setup_offer_update(nav.games[0])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        nav.poll_setup([("t4", "update", dict(version="0.1.0-beta.2", rebuild=True, restart=False), None)])
        self.assertEqual(self.setup.calls[-1][0], "reload")
        # 0.1.5: a changed game is built by itself (the update line said so), not left to a second click
        self.assertIn("The build is starting.", text(nav, nav.toast))

    def test_quick_access_checks_game_updates_and_switches_test_versions(self):
        nav = self.nav(Game5())
        nav.act("social", device="xbox")
        rows = [text(nav, r["label"]) for r in nav.view()["drawer"]["rows"]]
        self.assertIn("Check game updates", rows)
        self.assertIn("Test versions", rows)
        nav.drawer_focus = rows.index("Test versions")
        nav.act("right", device="xbox")
        self.assertTrue(nav.game_prereleases)
        self.assertEqual(self.setup.calls[-1], ("prereleases", "", True))
        nav.drawer_focus = rows.index("Check game updates")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("check_all", "", True))

    def test_without_the_backend_nothing_is_offered(self):
        nav = Nav([Game(Game5(found=False).m, Game5(found=False))], language="en")
        self.assertNotEqual(nav.view()["shelf"]["tiles"][0].get("bar"), "@setup.tile_bar")
        nav.act("social", device="xbox")
        self.assertNotIn("@setup.check", [r["label"] for r in nav.view()["drawer"]["rows"]])

    def test_nothing_published_offers_the_game_folder_the_player_has(self):
        """Setup.exe alone, no T4 release yet: say so and open the folder chooser instead of a failing download."""
        game = Game5("t4", found=False)
        game.sources = lambda: [dict(id="folder", label="Folder", title="@t4.choose_game_folder", value="@missing",
                                     ok=False, kind="file_or_folder", exts=[".zip"], dirs=[], hint="h")]
        nav = self.nav(game)
        nav.setup_begin(nav.games[0])
        nav.setup_state = {"t4": dict(phase="ready", installed="", latest="", offer=None)}
        nav.poll_setup([("t4", "check", dict(offer=None), None)])
        self.assertEqual(nav.confirm_kind, "setup_none")
        dialog = text(nav, nav.view()["dialog"])
        self.assertIn("Tekken 4 is not published yet", dialog["text"])
        self.assertEqual([o["label"] for o in dialog["options"]], ["Close", "Choose your Tekken 4 game folder"])
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual((nav.overlay, nav.picker["target"]), ("picker", "source:folder"))
        self.assertFalse(any(call[0] == "install" for call in self.setup.calls))

    def test_nothing_published_without_a_folder_row_just_says_so(self):
        nav = self.nav(Game5(found=False))
        nav.setup_begin(nav.games[0])
        nav.setup_state = {"t5dr": dict(phase="ready", installed="", latest="", offer=None)}
        nav.poll_setup([("t5dr", "check", dict(offer=None), None)])
        dialog = text(nav, nav.view()["dialog"])
        self.assertEqual([o["label"] for o in dialog["options"]], ["Close"])
        nav.act("confirm", device="xbox")
        self.assertIsNone(nav.overlay)

    def test_every_view_text_exists_in_every_language(self):
        nav = self.nav(Game5(found=False))
        self.ready_state(nav)
        nav.setup_begin(nav.games[0])
        for code in i18n.LANGUAGES:
            nav.language = code
            rendered = repr(i18n.localize(nav.view(), code))
            self.assertNotIn("@setup.", rendered, code)


if __name__ == "__main__":
    unittest.main()
