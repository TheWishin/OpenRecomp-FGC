"""The install / update progress window is modal, can be hidden, and a card shows the running jobs (0.1.5)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrecomp import i18n  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_game_setup_nav import Setup  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402


def text(nav, value):
    return i18n.localize(value, nav.language)


class T4(Fake):
    def __init__(self):
        super().__init__(manifest("t4", adapter="t4", short="Tekken 4"), is_ready=True)


class Game5(Fake):
    def __init__(self):
        super().__init__(manifest("t5dr", adapter="t5dr", short="Tekken 5 DR"), is_ready=True)
        self.root = "C:/games/T5DR-Online-1.2.0"


def running(**kw):
    st = dict(phase="updating", installed="1.2.0", latest="1.2.1", step="download", done=82_000_000, total=181_000_000,
              speed=4_000_000, left=60, can_cancel=True, offer=dict(version="1.2.1", size=181_000_000, name="v",
                                                                    prerelease=False, notes=""))
    st.update(kw)
    return st


class Env(unittest.TestCase):
    def nav(self, *adapters):
        self.setup = Setup()
        self.cancels = []
        games = [Game(a.m, a) for a in (adapters or (Game5(),))]
        nav = Nav(games, language="en", on_setup=self.setup)
        nav.on_update_cancel = lambda: self.cancels.append(1) or True
        return nav

    def open_progress(self, nav, gid="t5dr", **kw):
        nav.setup_state = dict(nav.setup_state or {})
        nav.setup_state[gid] = running(**kw)
        nav.setup_game = gid
        nav._ask("setup_progress")

    def labels(self, nav):
        return [o["label"] for o in text(nav, nav.view()["dialog"])["options"]]


class Modal(Env):
    def test_nothing_behind_the_window_reacts(self):
        nav = self.nav(Game5(), T4())
        self.open_progress(nav)
        nav.act("confirm", device="xbox")                 # focus is on Hide: closes only the window
        self.assertIsNone(nav.overlay)
        self.open_progress(nav)
        before = (nav.screen, nav.game.id, dict(nav.sec), dict(nav.focus), nav.overlay, nav.confirm_kind)
        quits = []
        nav.on_quit = lambda: quits.append(1)
        for action in ("up", "down", "prev", "next", "x", "social", "play", "switchGame", "discord", "returnGame",
                       "returnActivity", "launcherSettings", "home", "chapterNext", "offers", "progress"):
            nav.act(action, device="kb")
            self.assertEqual((nav.screen, nav.game.id, dict(nav.sec), dict(nav.focus), nav.overlay, nav.confirm_kind),
                             before, action)
        nav.act("quit", device="kb")
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_progress"))
        self.assertEqual(quits, [])
        self.assertEqual(self.setup.calls, [])

    def test_mouse_clicks_behind_the_window_do_nothing(self):
        nav = self.nav(Game5(), T4())
        self.open_progress(nav)
        nav.click_tile(1)
        nav.click_row(0)
        nav.click_tab("play")
        nav.click_primary()
        nav.click_main_entry(0)
        self.assertEqual((nav.overlay, nav.confirm_kind, nav.game.id), ("dialog", "setup_progress", "t5dr"))
        nav.click_entry(0)                                # the window's own Hide button
        self.assertIsNone(nav.overlay)

    def test_a_global_offer_cannot_be_answered_through_the_window(self):
        from openrecomp import nav_feedback
        nav = self.nav()
        self.open_progress(nav)
        self.assertEqual(nav.view()["globalOffers"], [])
        self.assertFalse(nav_feedback.click_global(nav, "x", True))
        self.assertFalse(nav_feedback.global_action(nav, "confirm"))

    def test_hide_is_the_default_and_back_hides_too(self):
        nav = self.nav()
        self.open_progress(nav)
        self.assertEqual(self.labels(nav), ["Hide", "Cancel"])
        self.assertEqual(nav.exit_focus, 0)
        nav.act("back", device="xbox")
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.setup.calls, [])            # Back never cancels the work

    def test_cancel_needs_a_deliberate_move_and_is_asked_once(self):
        nav = self.nav()
        self.open_progress(nav)
        nav.act("right", device="xbox")
        nav.act("confirm", device="xbox")
        self.assertEqual(self.setup.calls[-1], ("cancel", "t5dr", None))
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_progress"))
        self.assertIn("Cancelling", text(nav, nav.view()["dialog"])["text"])
        self.assertEqual(self.labels(nav), ["Hide"])
        nav.act("confirm", device="xbox")                 # now Hide
        self.assertIsNone(nav.overlay)
        self.assertEqual([c for c in self.setup.calls if c[0] == "cancel"], [("cancel", "t5dr", None)])


class CancelOnlyWhenSafe(Env):
    def test_download_and_verify_offer_cancel(self):
        nav = self.nav()
        for step in ("download", "check"):
            self.open_progress(nav, step=step)
            self.assertEqual(self.labels(nav), ["Hide", "Cancel"], step)

    def test_unpack_is_cancellable_until_it_is_complete(self):
        nav = self.nav()
        self.open_progress(nav, step="unpack", done=100, total=388)
        self.assertEqual(self.labels(nav), ["Hide", "Cancel"])
        self.open_progress(nav, step="unpack", done=388, total=388)
        self.assertEqual(self.labels(nav), ["Hide"])

    def test_the_install_step_says_installing_and_has_no_cancel(self):
        nav = self.nav()
        for kw in (dict(step="swap", done=0, total=0), dict(step="download", can_cancel=False),
                   dict(step="unpack", done=388_000_000, total=388_000_000)):
            self.open_progress(nav, **kw)
            view = text(nav, nav.view()["dialog"])
            self.assertEqual(view["title"].lower(), "installing, please wait", kw)
            self.assertIn("do not close the launcher", view["text"])
            self.assertEqual([o["label"] for o in view["options"]], ["Hide"])
            nav.act("right", device="xbox")
            nav.act("confirm", device="xbox")             # the only action is Hide
            self.assertIsNone(nav.overlay)
            self.assertNotIn("cancel", [c[0] for c in self.setup.calls])

    def test_the_launcher_update_follows_the_same_rule(self):
        nav = self.nav()
        nav.update_state = dict(phase="installing", version="v1.2.3", step="download", done=5, total=50, speed=0, left=0,
                                can_cancel=True, cancelling=False, reason="")
        nav._ask("update_progress")
        self.assertEqual(self.labels(nav), ["Hide", "Cancel"])
        nav.update_state = dict(nav.update_state, step="prepare", done=0, total=0)
        self.assertEqual(self.labels(nav), ["Hide"])
        nav.update_state = dict(nav.update_state, step="restart", can_cancel=False)
        self.assertEqual(self.labels(nav), ["Hide"])
        nav.act("confirm", device="xbox")
        self.assertIsNone(nav.overlay)
        self.assertEqual(self.cancels, [])


class HideAndReopen(Env):
    def test_the_card_appears_when_hidden_and_reopens_the_window(self):
        nav = self.nav()
        self.open_progress(nav)
        self.assertFalse(nav.view()["progressCard"]["show"])      # the window itself shows it
        nav.act("confirm", device="xbox")                         # Hide
        card = nav.view()["progressCard"]
        self.assertTrue(card["show"])
        self.assertEqual(text(nav, card["lines"][0]["text"]), "Tekken 5 DR · Download 45 % · 82/181 MB · 1 min")
        nav.act("progress", device="kb")                          # the shortcut
        self.assertEqual((nav.overlay, nav.confirm_kind, nav.setup_game), ("dialog", "setup_progress", "t5dr"))
        self.assertFalse(nav.view()["progressCard"]["show"])
        nav.act("confirm", device="kb")
        nav.progress_open("t5dr")                            # a click on the line
        self.assertEqual(nav.confirm_kind, "setup_progress")

    def test_the_work_continues_hidden_and_the_card_follows_it(self):
        nav = self.nav()
        self.open_progress(nav)
        nav.act("back", device="xbox")
        nav.setup_state["t5dr"].update(done=181_000_000 // 2)
        self.assertIn("Download 50 %", text(nav, nav.view()["progressCard"]["lines"][0]["text"]))
        nav.setup_state["t5dr"].update(step="swap", done=0, total=0)
        line = nav.view()["progressCard"]["lines"][0]
        self.assertEqual(text(nav, line["text"]), "Tekken 5 DR · Installing, please wait")
        self.assertEqual(line["fraction"], -1.0)

    def test_pages_stay_usable_once_hidden(self):
        nav = self.nav(Game5(), T4())
        self.open_progress(nav)
        nav.act("back", device="xbox")
        nav.act("confirm", device="kb")                           # not blocked: opens a game
        self.assertNotEqual((nav.screen, nav.overlay), ("start", None))

    def test_the_footer_names_the_shortcut_only_when_the_card_shows(self):
        nav = self.nav()
        nav.device = "kb"
        self.assertNotIn("progress", [p["action"] for p in nav.view()["prompts"]])
        self.open_progress(nav)
        nav.act("back", device="kb")
        prompts = nav.view()["prompts"]
        self.assertIn(("progress", "Show progress", "F7"), [(p["action"], text(nav, p["label"]), p["g"]["text"]) for p in prompts])

    def test_an_ended_job_stays_a_few_seconds_then_goes(self):
        nav = self.nav()
        self.open_progress(nav)
        nav.act("back", device="xbox")
        nav.setup_state["t5dr"].update(phase="updated")
        nav.poll_setup([("t5dr", "update", dict(version="1.2.1", rebuild=False, restart=False), None)])
        lines = nav.view()["progressCard"]["lines"]
        self.assertEqual([(l["state"], text(nav, l["text"])) for l in lines], [("done", "Tekken 5 DR · Done")])
        nav.tick(3)
        self.assertTrue(nav.view()["progressCard"]["show"])
        nav.tick(4)
        self.assertFalse(nav.view()["progressCard"]["show"])

    def test_cancelled_goes_too_but_a_failure_stays_until_it_is_opened(self):
        nav = self.nav(Game5(), T4())
        nav.setup_state = {"t5dr": running(phase="ready"), "t4": running(phase="ready")}
        nav.poll_setup([("t5dr", "update", None, ("@setup.cancelled", "")),
                        ("t4", "update", None, ("@setup.err_space", ""))])
        states = {l["id"]: l["state"] for l in nav.view()["progressCard"]["lines"]}
        self.assertEqual(states, {"t5dr": "cancelled", "t4": "failed"})
        nav.tick(60)
        self.assertEqual([l["id"] for l in nav.view()["progressCard"]["lines"]], ["t4"])
        nav.act("progress", device="kb")                          # opens the failure: says why, then it is gone
        self.assertIn("Not enough free space", text(nav, nav.toast))
        self.assertFalse(nav.view()["progressCard"]["show"])

    def test_the_launcher_update_ends_on_the_card_too(self):
        nav = self.nav()
        nav.update_state = dict(phase="installing", version="v1.2.3", step="download", done=5, total=50, speed=0, left=0,
                                can_cancel=True, cancelling=False, reason="")
        nav.poll_update()
        self.assertTrue(nav.view()["progressCard"]["show"])
        nav.update_state = dict(nav.update_state, phase="error", step="", reason="network")
        nav.poll_update()
        line = nav.view()["progressCard"]["lines"][0]
        self.assertEqual(line["state"], "failed")
        nav.act("progress", device="kb")
        self.assertIn("internet", text(nav, nav.toast).lower())


class TwoJobs(Env):
    def test_both_games_and_the_launcher_have_a_line_each(self):
        nav = self.nav(Game5(), T4())
        nav.setup_state = {"t5dr": running(), "t4": running(step="unpack", done=100_000_000, total=388_000_000, left=0)}
        nav.update_state = dict(phase="installing", version="v1.2.3", step="download", done=10, total=50, speed=0,
                                left=0, can_cancel=True, cancelling=False, reason="")
        card = nav.view()["progressCard"]
        self.assertEqual([l["id"] for l in card["lines"]], ["t5dr", "t4", "launcher"])
        lines = [text(nav, l["text"]) for l in card["lines"]]
        self.assertTrue(lines[0].startswith("Tekken 5 DR · Download 45 %"))
        self.assertTrue(lines[1].startswith("Tekken 4 · Unpacking 25 %"))
        self.assertTrue(lines[2].startswith("Launcher · Download"))
        self.assertEqual(round(card["lines"][0]["fraction"], 2), 0.45)

    def test_the_open_window_leaves_the_other_job_on_the_card(self):
        nav = self.nav(Game5(), T4())
        nav.setup_state = {"t5dr": running(), "t4": running()}
        nav.setup_game = "t5dr"
        nav._ask("setup_progress")
        self.assertFalse(nav.view()["progressCard"]["show"])      # no card behind a window
        nav.act("back", device="kb")
        self.assertEqual([l["id"] for l in nav.view()["progressCard"]["lines"]], ["t5dr", "t4"])
        nav.progress_open("t4")
        self.assertEqual((nav.confirm_kind, nav.setup_game), ("setup_progress", "t4"))
        self.assertFalse(nav.view()["progressCard"]["show"])
        nav.act("back", device="kb")
        nav.progress_open()                                       # the shortcut walks through the jobs
        first = nav.setup_game
        nav.act("back", device="kb")
        nav.progress_open()
        self.assertNotEqual(nav.setup_game, first)

    def test_one_game_finishing_does_not_close_the_others_window(self):
        nav = self.nav(Game5(), T4())
        nav.setup_state = {"t5dr": running(), "t4": running()}
        nav.setup_game = "t5dr"
        nav._ask("setup_progress")
        nav.setup_state["t4"].update(phase="updated")
        nav.poll_setup([("t4", "update", dict(version="1", rebuild=False, restart=False), None)])
        self.assertEqual((nav.overlay, nav.setup_game), ("dialog", "t5dr"))


class FooterBelongsToTheWindow(Env):
    def test_the_progress_window_has_its_own_hint_and_prompts(self):
        nav = self.nav()
        nav.screen, nav.sec["t5dr"] = "hub", "build"
        before = nav.view()
        self.open_progress(nav)
        view = nav.view()
        self.assertNotEqual(view["hint"], "@dialog_hint")
        hint = text(nav, view["hint"])
        self.assertNotIn("No is preselected", hint)
        self.assertIn("Hide", hint)
        prompts = [(p["action"], text(nav, p["label"])) for p in view["prompts"]]
        self.assertEqual(prompts, [("confirm", "Hide"), ("right", "Switch"), ("back", "Hide")])
        self.assertNotEqual(before["prompts"], view["prompts"])
        nav.act("right", device="xbox")
        self.assertEqual(text(nav, nav.view()["prompts"][0]["label"]), "Cancel")

    def test_the_install_phase_hint_says_it_cannot_be_cancelled(self):
        nav = self.nav()
        self.open_progress(nav, step="swap", done=0, total=0)
        view = nav.view()
        self.assertIn("can no longer be cancelled", text(nav, view["hint"]))
        self.assertEqual([(p["action"], text(nav, p["label"])) for p in view["prompts"]],
                         [("confirm", "Hide"), ("back", "Hide")])

    def test_every_dialog_sets_its_own_footer(self):
        """No dialog kind may leave the page's hint or prompts (or the generic confirm text) behind."""
        nav = self.nav()
        nav.screen, nav.sec["t5dr"] = "hub", "build"
        page = nav.view()
        for kind in ("exit", "stop_game", "rebuild", "controls_reset"):
            nav._ask(kind)
            view = nav.view()
            self.assertEqual(view["overlay"], "dialog")
            self.assertNotEqual(view["prompts"], page["prompts"], kind)
            nav.overlay = None
        self.open_progress(nav)
        self.assertNotEqual(nav.view()["hint"], page["hint"])


class UpdateRunning(Env):
    def test_play_build_and_online_say_update_running_and_start_nothing(self):
        game = Game5()
        nav = self.nav(game)
        nav.setup_state = {"t5dr": running()}
        nav.screen = "hub"
        for section in ("play", "build", "online"):
            if section not in nav.sections():
                continue
            nav.sec["t5dr"] = section
            for item in nav.items():
                if item.get("kind") in ("action", "hold") and item.get("id") not in ("game_setup", "game_update"):
                    self.assertTrue(item.get("disabled"), (section, item.get("id")))
                    self.assertIsNone(item.get("run"))
                    self.assertEqual(text(nav, item["hint"]), "Update running")
        nav.sec["t5dr"] = "play"
        start = next(i for i in nav.items() if i["id"] == "start")
        self.assertEqual(text(nav, start["value"]), "Update running")
        nav.focus[nav.key()] = nav.items().index(start)
        nav.act("confirm", device="xbox")
        self.assertEqual(game.calls, [])
        self.assertIn("Update running", text(nav, nav.toast))
        nav.start_game(nav.games[0])
        nav._start_build(nav.games[0])
        self.assertEqual(game.calls, [])

    def test_the_other_game_is_not_locked_and_it_unlocks_when_the_update_ends(self):
        nav = self.nav(Game5(), T4())
        nav.setup_state = {"t5dr": running()}
        t4 = nav.games[1]
        nav._select_game(t4)
        nav.screen, nav.sec["t4"] = "hub", "play"
        start = next(i for i in nav.items() if i["id"] == "start")
        self.assertFalse(start.get("disabled"))
        nav._select_game(nav.games[0])
        nav.sec["t5dr"] = "play"
        self.assertTrue(next(i for i in nav.items() if i["id"] == "start")["disabled"])
        nav.setup_state["t5dr"]["phase"] = "ready"
        self.assertFalse(next(i for i in nav.items() if i["id"] == "start").get("disabled"))


class Catalogs(unittest.TestCase):
    def test_every_new_text_is_in_all_catalogs(self):
        keys = [k for k in i18n.catalog("en") if k.startswith("progress.")]
        self.assertGreaterEqual(len(keys), 18)
        for code in i18n.LANGUAGES:
            for key in keys:
                self.assertIn(key, i18n.catalog(code), (code, key))


if __name__ == "__main__":
    unittest.main()


class RunningRow(Env):
    def test_the_update_row_shows_the_job_and_opens_the_window_never_a_second_start(self):
        nav = self.nav(Game5())
        nav.setup_state = {"t5dr": running()}
        nav.screen, nav.sec["t5dr"] = "hub", "play"
        row = nav.items()[0]
        self.assertEqual(row["id"], "game_update")
        self.assertEqual(text(nav, row["value"]), "Updating · 45 %")
        nav.act("confirm", device="xbox")
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "setup_progress"))
        self.assertEqual([c for c in self.setup.calls if c[0] in ("update", "install", "check")], [])

    def test_the_locked_play_row_keeps_its_normal_label(self):
        nav = self.nav(Game5())
        nav.setup_state = {"t5dr": running()}
        nav.screen, nav.sec["t5dr"] = "hub", "play"
        start = next(i for i in nav.items() if i["id"] == "start")
        self.assertEqual(text(nav, start["label"]), "Start game")
        self.assertEqual(text(nav, start["value"]), "Update running")

    def test_a_disabled_play_row_is_not_drawn_as_the_primary_button(self):
        nav = self.nav(Game5())
        nav.setup_state = {"t5dr": running()}
        v = dict()
        nav._view_session_page(v, nav.game, "play", nav.items(), 0)
        self.assertFalse(next(r for r in v["sessionPage"]["rows"] if r["id"] == "start")["primary"])
        nav.setup_state = {}
        nav._view_session_page(v, nav.game, "play", nav.items(), 0)
        self.assertTrue(next(r for r in v["sessionPage"]["rows"] if r["id"] == "start")["primary"])
