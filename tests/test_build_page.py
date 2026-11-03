"""Owner (2026-11-04): the Build page as cards -- one big button, the step's name, a time estimate, a log that opens on
request -- and the build tools never as a list: Build installs missing ones itself ("Installing build tools (x of y)")
and only a failed install shows a clear error with Try again / Help. A restart Windows asks for continues the build."""
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters import t4 as t4_module
from openrecomp.adapters import t4_prerequisites as tools
from openrecomp.adapters.base import Adapter
from openrecomp.adapters.t4 import T4
from openrecomp.nav import Game, Nav
from test_nav import manifest
from test_t4 import MANIFEST, FakeCore

VERSIONS = [("python", "3.12.10"), ("git", "2.55.0"), ("cmake", "4.4.4"), ("ninja", "1.13.2"),
            ("vs2022", "17.14.3"), ("msvc", "14.44.35207")]
STEPS = ["Unpack", "Toolchain", "Recompile", "Configure", "Compile", "Link", "Check"]


def rows(missing=(), busy=False):
    return [dict(id=sid, label="@t4.tools." + sid, value="@t4.tools.checking" if busy else ("@t4.tools.missing" if sid in missing else v),
                 ok=False if busy else sid not in missing, busy=busy, command=tools.COMMANDS[sid]) for sid, v in VERSIONS]


class Page(Adapter):
    """A game's Build page in one state."""

    def __init__(self, adapter="t4", found=True, ready=False, sources=None, checks=None, problem="", state=None,
                 options=None):
        super().__init__(manifest(adapter, adapter=adapter) if adapter == "t4" else manifest(adapter))
        self.m = dict(self.m, adapter=adapter)
        self._found, self._ready, self.problem_text = found, ready, problem
        self.src = sources if sources is not None else [dict(id="iso", label="@game_iso", value="T4.iso", ok=True, kind="file",
                                                             exts=[".iso"], dirs=[], hint="@iso.hint")]
        self.checks = checks if checks is not None else rows()
        self.state = dict(dict(running=False, fraction=0.0, title="", steps=[], result="", line=""), **(state or {}))
        self.options = options or []
        self.calls = []
        self.resume = False

    def found(self):
        return self._found

    def ready(self):
        return self._ready

    def status(self):
        return dict(status="@not_built", version="v1", players="@no", last="@never", detail="@build_hint")

    def sources(self):
        return [dict(s) for s in self.src]

    def set_source(self, sid, path):
        self.calls.append(("source", sid))
        for s in self.src:
            if s["id"] == sid:
                s.update(ok=True, value="@found")
        return ""

    def prerequisites(self):
        return [dict(r) for r in self.checks]

    def build_ready(self):
        return self.problem_text

    def build_prepares(self):
        return ("@t4.tools.required",)

    def build_start(self, force=False):
        self.calls.append(("build", force))

    def build_state(self):
        return dict(self.state)

    def build_options(self):
        return self.options

    def build_resume_pending(self):
        return self.resume

    def build_resume(self):
        self.calls.append(("resume",))
        self.resume = False


def page(adapter, language="en"):
    nav = Nav([Game(adapter.m, adapter)], language=language)
    nav.screen = "hub"
    nav.sec[adapter.m["id"]] = "build"
    return nav


def cards(view):
    return {c["id"]: c for c in view["build"]["cards"]}


def flat(value):
    return json.dumps(value, ensure_ascii=False)


class Cards(unittest.TestCase):
    def test_build_section_is_the_card_page_with_one_big_button(self):
        nav = page(Page(problem="@iso.choose_first", sources=[dict(id="iso", label="@game_iso", value="@missing", ok=False,
                                                                   kind="file", exts=[".iso"], dirs=[], hint="@iso.hint")]))
        v = nav.view()
        self.assertTrue(v["build"]["show"])
        self.assertEqual(list(cards(v)), ["files", "tools"])
        self.assertEqual(cards(v)["files"]["status"], "todo")
        self.assertEqual(cards(v)["files"]["actions"][0]["label"], "Game ISO")
        main = v["build"]["main"]
        self.assertEqual(main["title"], "Build game")
        self.assertTrue(main["button"]["blocked"], "files missing: the button says so")
        self.assertEqual(main["lead"], i18n.text("en", "iso.choose_first"))

    def test_other_sections_keep_the_list(self):
        nav = page(Page())
        nav.sec["t4"] = "settings"
        self.assertFalse(nav.view()["build"]["show"])

    def test_tools_are_never_listed_on_the_page(self):
        for checks in (rows(), rows(("git", "vs2022", "msvc")), rows(busy=True)):
            nav = page(Page(checks=checks, problem="@t4.tools.required"))
            v = nav.view()
            text = flat(v["build"]) + flat(v["rows"]) + v["hint"]
            for sid, version in VERSIONS:
                with self.subTest(tool=sid):
                    self.assertNotIn(version, text)
                    self.assertNotIn(i18n.text("en", "t4.tools." + sid), text)
            self.assertFalse(any(str(it.get("id", "")).startswith("tools:") for it in nav.items()), "no tool rows to focus")

    def test_tools_card_says_one_line_per_state(self):
        expect = [(rows(), "done", "build.tools_ready"), (rows(busy=True), "work", "build.tools_checking"),
                  (rows(("git",)), "wait", "build.tools_auto")]
        for checks, status, key in expect:
            with self.subTest(status=status):
                tools_card = cards(page(Page(checks=checks)).view())["tools"]
                self.assertEqual((tools_card["status"], tools_card["text"]), (status, i18n.text("en", key)))
                self.assertEqual(tools_card["actions"], [])

    def test_missing_tools_do_not_block_build_it_installs_them(self):
        adapter = Page(checks=rows(("git", "vs2022", "msvc")), problem="@t4.tools.required")
        nav = page(adapter)
        v = nav.view()
        self.assertFalse(v["build"]["main"]["button"]["blocked"])
        self.assertEqual(v["build"]["main"]["lead"], i18n.text("en", "build.lead_tools"))
        nav.focus["t4:build"] = v["build"]["main"]["button"]["index"]
        nav.act("confirm", device="xbox")
        self.assertEqual(adapter.calls, [("build", False)])

    def test_installing_tools_is_one_line_x_of_y(self):
        adapter = Page(checks=rows(("git", "vs2022", "msvc")), problem="@t4.tools.required",
                       state=dict(running=True, phase="tools", tools=dict(done=1, total=2)))
        v = page(adapter).view()
        line = i18n.text("en", "build.tools_installing", done=2, total=2)
        self.assertEqual(cards(v)["tools"]["text"], line)
        self.assertEqual(v["build"]["main"]["stepLine"], line)
        self.assertEqual(v["build"]["main"]["progress"], -1.0, "no fake percentage while winget runs")
        self.assertEqual(v["build"]["main"]["button"]["label"], i18n.text("en", "cancel"))

    def test_failed_install_is_a_clear_error_with_try_again_and_help(self):
        error = dict(_text="t4.tools.not_installed", _values=dict(name="@t4.tools.vs2022"))
        adapter = Page(checks=rows(("vs2022", "msvc")), problem="@t4.tools.required", state=dict(failed="tools", result=error))
        nav = page(adapter)
        v = nav.view()
        tools_card = cards(v)["tools"]
        self.assertEqual(tools_card["status"], "error")
        self.assertIn("could not be installed", tools_card["text"])
        self.assertEqual([a["label"] for a in tools_card["actions"]], ["Help"])
        self.assertEqual(v["build"]["main"]["button"]["label"], "Try again")
        nav.focus["t4:build"] = tools_card["actions"][0]["index"]
        nav.act("confirm", device="kb")
        dialog = nav.view()["dialog"]
        self.assertEqual([o["label"] for o in dialog["options"]], ["Close", "Copy commands"])
        self.assertIn("Visual Studio 2022", dialog["text"])
        nav.act("right", device="kb")
        nav.act("confirm", device="kb")
        self.assertEqual(nav.pending_clipboard, tools.COMMANDS["vs2022"], "VS and MSVC: one installer, one command")
        nav.focus["t4:build"] = v["build"]["main"]["button"]["index"]
        nav.act("confirm", device="kb")
        self.assertEqual(adapter.calls, [("build", False)], "Try again builds (and installs) again")

    def test_running_build_shows_step_name_elapsed_and_estimate(self):
        state = dict(running=True, phase="build", fraction=0.5, title="compile", step_no=[5, 7], line="x",
                     steps=[dict(k=n, v="@pending") for n in STEPS])
        adapter = Page(state=state)
        nav = page(adapter)
        now = [100.0]
        nav.clock = lambda: now[0]
        nav.view()
        now[0] += 125
        main = nav.view()["build"]["main"]
        self.assertEqual(main["stepLine"], "Step 5 of 7: Compile")
        self.assertEqual(main["elapsed"], "2:05 so far")
        self.assertEqual(main["eta"], "About 3 min left", "125 s for half the build: about 2 more minutes")
        self.assertEqual(main["progress"], 0.5)

    def test_estimate_before_any_progress_is_the_usual_range(self):
        adapter = Page(state=dict(running=True, phase="build", fraction=0.0, title="unpack", step_no=[1, 7], line=""))
        nav = page(adapter)
        nav.clock = lambda: 50.0
        self.assertEqual(nav.view()["build"]["main"]["eta"], "Usually 10-30 min")

    def test_last_builds_step_times_give_the_estimate_and_a_finished_build_is_remembered(self):
        adapter = Page(state=dict(running=True, phase="build", fraction=0.0, title="unpack", line="a"))
        nav = page(adapter)
        saved = []
        nav.on_build_history = lambda gid, history: saved.append((gid, history))
        now = [0.0]
        nav.clock = lambda: now[0]
        nav.view()
        now[0] = 60.0
        adapter.state.update(title="compile", line="b")
        nav.view()
        now[0] = 360.0
        adapter.state.update(running=False, phase="", result="@t4.build_finished")
        nav.view()
        self.assertEqual(saved, [("t4", dict(steps=[["build:unpack", 60.0], ["build:compile", 300.0]], total=360.0))])
        adapter.state.update(running=True, phase="build", title="unpack", result="", line="c")
        now[0] = 1000.0
        nav.view()
        now[0] = 1030.0
        self.assertEqual(nav.view()["build"]["main"]["eta"], "About 6 min left", "30 s of unpack left + 300 s compile")
        nav.dry = True
        adapter.state.update(running=False, result="@t4.build_finished")
        nav.view()
        self.assertEqual(len(saved), 1, "a dry run writes nothing")

    def test_long_silence_names_the_running_step(self):
        adapter = Page(adapter="t5dr", sources=[], checks=[],
                       state=dict(running=True, phase="build", fraction=0.3, title="Translate code", line="lifting", step_no=[5, 7],
                                  steps=[dict(k=n, v="@pending") for n in STEPS]))
        nav = page(adapter)
        now = [0.0]
        nav.clock = lambda: now[0]
        nav.view()
        now[0] = 100.0
        self.assertEqual(nav.view()["build"]["main"]["quiet"], "")
        now[0] = 250.0
        quiet = nav.view()["build"]["main"]["quiet"]
        self.assertIn("Translate code", quiet)
        self.assertIn("4 min", quiet)
        adapter.state["line"] = "lifting chunk 10"
        self.assertEqual(nav.view()["build"]["main"]["quiet"], "", "new output: quiet again")

    def test_log_opens_with_x_and_shows_the_last_lines(self):
        lines = ["line %d" % i for i in range(14)]
        adapter = Page(state=dict(running=True, phase="build", fraction=0.2, title="t", line=lines[-1], lines=lines))
        nav = page(adapter)
        v = nav.view()
        self.assertTrue(v["build"]["main"]["canLog"])
        self.assertFalse(v["build"]["main"]["logOpen"])
        self.assertEqual(v["build"]["main"]["logLines"], [])
        self.assertIn("Show log", [p["label"] for p in v["prompts"]])
        nav.act("x", device="xbox")
        v = nav.view()
        self.assertTrue(v["build"]["main"]["logOpen"])
        self.assertEqual(v["build"]["main"]["logLines"], lines[-8:])
        self.assertIn("Hide log", [p["label"] for p in v["prompts"]])
        nav.act("x", device="xbox")
        self.assertFalse(nav.view()["build"]["main"]["logOpen"])

    def test_failed_build_shows_its_error_and_try_again(self):
        error = dict(_text="t4.build_failed", _values=dict(name="compile", error="C1083"))
        nav = page(Page(state=dict(failed="build", result=error, lines=["a", "C1083"])))
        main = nav.view()["build"]["main"]
        self.assertEqual(main["tone"], "error")
        self.assertIn("C1083", main["error"])
        self.assertEqual(main["button"]["label"], "Try again")

    def test_finished_build_offers_play_for_both_games(self):
        for adapter in ("t4", "t5dr"):
            with self.subTest(adapter=adapter):
                result = "@t4.build_finished" if adapter == "t4" else "@build_finished"
                nav = page(Page(adapter=adapter, ready=True, checks=[], state=dict(result=result)))
                main = nav.view()["build"]["main"]
                self.assertEqual((main["tone"], main["button"]["label"]), ("done", "Play"))

    def test_not_installed_game_card_and_install_button(self):
        adapter = Page(found=False, sources=[dict(id="folder", label="@t4.game_folder", value="@missing", ok=False,
                                                  kind="file_or_folder", exts=[".zip"], dirs=[], hint="@folder_hint")])
        nav = page(adapter)
        nav.on_setup = lambda *a: None
        v = nav.view()
        self.assertEqual(list(cards(v)), ["game"])
        self.assertEqual([a["label"] for a in cards(v)["game"]["actions"]],
                         [i18n.text("en", "t4.game_folder"), i18n.text("en", "picker.have_zip")])
        self.assertEqual(v["build"]["main"]["button"]["label"], i18n.text("en", "setup.install"))

    def test_choosing_files_moves_on_to_the_next_missing_then_to_build(self):
        missing = dict(value="@missing", ok=False, kind="file", dirs=[], hint="h")
        adapter = Page(adapter="t5dr", checks=[], problem="@choose_package_license",
                       sources=[dict(missing, id="pkg", label="@package", exts=[".pkg"]),
                                dict(missing, id="rap", label="@license", exts=[".rap"])])
        nav = page(adapter)
        items = nav.items()
        self.assertEqual(items[nav.focus_index(items)]["id"], "pkg")
        nav._picked("source:pkg", "C:/x.pkg")
        items = nav.items()
        self.assertEqual(items[nav.focus_index(items)]["id"], "rap")
        adapter.problem_text = ""
        nav._picked("source:rap", "C:/x.rap")
        items = nav.items()
        self.assertEqual(items[nav.focus_index(items)]["id"], "build")

    def test_every_language_resolves_every_text(self):
        error = dict(_text="t4.tools.not_installed", _values=dict(name="@t4.tools.git"))
        states = [dict(running=True, phase="tools", tools=dict(done=0, total=3)),
                  dict(running=True, phase="build", fraction=0.4, title="x", step_no=[2, 7], line="l", lines=["l"]),
                  dict(failed="tools", result=error)]
        for code in i18n.LANGUAGES:
            for state in states:
                with self.subTest(language=code, state=state.get("phase") or state.get("failed")):
                    nav = page(Page(checks=rows(("git",)), problem="@t4.tools.required", state=state), code)
                    nav.clock = lambda: 0.0
                    text = flat(nav.view()["build"])
                    self.assertNotIn('"@', text)
                    self.assertNotIn("{", text.replace('{"', "").replace("{}", ""))

    def test_rebuild_everything_only_once_there_was_a_build(self):
        nav = page(Page())
        self.assertNotIn("rebuild", [it.get("id") for it in nav.items()], "nothing to redo before the first build")
        for adapter in (Page(ready=True), Page(state=dict(failed="build", result="@t4.no_build_output"))):
            self.assertIn("rebuild", [it.get("id") for it in page(adapter).items()])

    def test_install_dialog_names_space_in_gb(self):
        nav = page(Page(found=False))
        nav.setup_game = "t4"
        nav.setup_space = dict(need=3_400_000_000, free=1_673_464_000_000, target="D:/Games/T4")
        nav.setup_state = {"t4": dict(phase="ready", latest="v0.1.0", offer=dict(version="0.1.0", size=106_000_000))}
        nav._ask("setup_install")
        text = nav.view()["dialog"]["text"]
        self.assertIn("3.4 GB", text)
        self.assertIn("1673.5 GB", text)
        self.assertNotIn("1673464", text)

    def test_mouse_reaches_every_card_action(self):
        adapter = Page(adapter="t5dr", checks=[], options=[dict(id="low_priority", label="@responsive",
                                                                  options=[(False, "@off"), (True, "@on")], value=False)])
        adapter.set_setting = mock.Mock()
        nav = page(adapter)
        v = nav.view()
        index = v["build"]["more"][0]["index"]
        nav.click_row(index)
        adapter.set_setting.assert_called_once_with("low_priority", True)


class Resume(unittest.TestCase):
    def test_a_pending_resume_continues_once_after_the_tool_check(self):
        adapter = Page(checks=rows(busy=True))
        adapter.resume = True
        nav = page(adapter)
        self.assertFalse(nav.poll_build(1.0) and ("resume",) in adapter.calls)
        self.assertNotIn(("resume",), adapter.calls, "waits for the tool check")
        adapter.checks = rows()
        nav.poll_build(1.0)
        self.assertEqual(adapter.calls, [("resume",)])
        self.assertEqual(nav.toast, "@build.resumed")
        adapter.resume = True
        nav.poll_build(1.0)
        self.assertEqual(adapter.calls, [("resume",)], "once per launcher start")

    def test_dry_run_never_resumes(self):
        adapter = Page()
        adapter.resume = True
        nav = page(adapter)
        nav.dry = True
        nav.poll_build(1.0)
        self.assertEqual(adapter.calls, [])


class Core(FakeCore):
    source_only = True
    STEPS = [("unpack", "Unpack"), ("compile", "Compile")]

    def __init__(self):
        super().__init__()
        self.iso = ""

    def effective_iso(self, settings):
        return settings.get("iso", "")

    def build_command(self, iso):
        return ["builder", iso]

    def build_env(self):
        return {}


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(t4_module.T4, "refresh_prerequisites", return_value=True))
        # The adapter never writes config.json itself (the launcher does, on config_dirty).
        self.enterContext(mock.patch.object(t4_module, "save_config", side_effect=AssertionError("adapter wrote the config")))
        self.config = {}
        self.adapter = T4(MANIFEST, self.config, "fake-root", core=Core())
        self.adapter.s["iso"] = "game.iso"
        self.adapter._verified_iso = ("game.iso", 1, 2)
        self.enterContext(mock.patch.object(self.adapter, "_iso_stamp", return_value=("game.iso", 1, 2)))
        self.adapter._prerequisite_rows = [dict(r, busy=False) for r in rows(("git", "vs2022", "msvc"))]
        self.process = self.enterContext(mock.patch.object(t4_module, "ProcessBuild"))
        self.process.return_value.running.return_value = True
        self.enterContext(mock.patch.object(tools.shutil, "which", return_value="C:/winget.exe"))
        self.enterContext(mock.patch.object(tools, "refresh_path"))

    def run_pipeline(self, codes, after):
        calls = []

        def run(args, **kw):
            calls.append(args)
            snapshot = self.adapter.build_state()
            self.assertEqual(snapshot["phase"], "tools")
            self.assertTrue(snapshot["running"])
            return SimpleNamespace(returncode=codes[len(calls) - 1])
        self.adapter._tools_then_build(False, run=run, check=lambda: after)
        return calls

    def start_and_wait(self):
        self.assertEqual(self.adapter.build_ready(), "@t4.tools.required")
        with mock.patch.object(t4_module.threading, "Thread") as thread:
            self.adapter.build_start()       # the worker is run below by hand, with fake installers
        self.assertIn(self.adapter._tools_then_build, [c.kwargs.get("target") for c in thread.call_args_list])
        self.assertTrue(self.adapter.build_state()["running"])
        self.assertEqual(self.adapter.build_state()["phase"], "tools")

    def test_build_installs_the_missing_tools_then_builds(self):
        self.start_and_wait()
        calls = self.run_pipeline([0, 0], [dict(r, busy=False) for r in rows()])
        self.assertEqual(len(calls), 2, "git, then Visual Studio (with MSVC): one installer each")
        self.assertIn("--silent", calls[0])
        self.process.assert_called_once()
        state = self.adapter.build_state()
        self.assertEqual((state["phase"], state["failed"]), ("build", ""))

    def test_a_tool_that_will_not_install_stops_with_its_name(self):
        self.start_and_wait()
        self.run_pipeline([0, 1], [dict(r, busy=False) for r in rows(("vs2022", "msvc"))])
        self.process.assert_not_called()
        state = self.adapter.build_state()
        self.assertFalse(state["running"])
        self.assertEqual(state["failed"], "tools")
        self.assertEqual(state["result"]["_text"], "t4.tools.not_installed")
        self.assertEqual(state["result"]["_values"]["name"], "@t4.tools.vs2022")

    def test_restart_needed_is_remembered_and_continues_after_it(self):
        self.start_and_wait()
        self.run_pipeline([0, 0x8A150109], [dict(r, busy=False) for r in rows(("vs2022", "msvc"))])
        state = self.adapter.build_state()          # into the config on the window's thread
        self.assertEqual(state["result"], "@t4.tools.reboot")
        self.assertTrue(self.adapter.config_dirty)
        self.assertIn("t4", self.config["build_resume"])
        again = T4(MANIFEST, json.loads(json.dumps(self.config)), "fake-root", core=Core())
        again._prerequisite_rows = [dict(r, busy=False) for r in rows()]
        self.assertTrue(again.build_resume_pending())
        again._verified_iso = None
        with mock.patch.object(again, "build_start") as start:
            again.build_resume()
        start.assert_called_once_with()
        self.assertNotIn("build_resume", again.config, "the marker is gone once the build continues")
        self.assertTrue(again.config_dirty)

    def test_an_old_resume_marker_is_ignored(self):
        old = T4(MANIFEST, dict(build_resume=dict(t4=int(time.time()) - 30 * 86400)), "fake-root", core=Core())
        old._prerequisite_rows = [dict(r, busy=False) for r in rows()]
        self.assertFalse(old.build_resume_pending())

    def test_no_winget_is_said_and_nothing_runs(self):
        self.start_and_wait()
        with mock.patch.object(tools.shutil, "which", return_value=None):
            self.adapter._tools_then_build(False, run=mock.Mock(), check=lambda: rows(("git",)))
        self.assertEqual(self.adapter.build_state()["result"], "@t4.tools.no_winget")
        self.process.assert_not_called()

    def test_cancel_stops_after_the_running_installer(self):
        self.start_and_wait()

        def run(args, **kw):
            self.adapter.build_cancel()
            return SimpleNamespace(returncode=0)
        self.adapter._tools_then_build(False, run=run, check=lambda: [dict(r, busy=False) for r in rows(("vs2022", "msvc"))])
        self.process.assert_not_called()
        self.assertEqual(self.adapter.build_state()["result"], "@t4.build_cancelled")

    def test_all_tools_there_builds_at_once(self):
        self.adapter._prerequisite_rows = [dict(r, busy=False) for r in rows()]
        self.adapter.build_start()
        self.process.assert_called_once()


class IsoRemembered(unittest.TestCase):
    def test_a_verified_iso_stays_verified_after_a_restart(self):
        config = {}
        # 2026-11-04: a test's adapter wrote the player's real config.json. The adapter only marks it dirty now.
        with mock.patch.object(t4_module, "save_config", side_effect=AssertionError("adapter wrote the config")), \
                mock.patch("openrecomp.manifest.save_config", side_effect=AssertionError("adapter wrote the config")):
            adapter = T4(MANIFEST, config, "fake-root", core=Core())
            adapter.s["iso"] = __file__
            adapter.core.verify_iso = lambda path: (True, "")
            adapter.region_problem = lambda: ""
            adapter._check_iso(__file__)
            adapter.source_state()                   # the window's thread keeps it in the config
            adapter.build_state()
        self.assertTrue(adapter.config_dirty, "the launcher saves it")
        self.assertIn(os.path.normcase(os.path.abspath("fake-root")), config["t4_iso_verified"])
        again = T4(MANIFEST, config, "fake-root", core=Core())
        again.s["iso"] = __file__
        again._verified_iso = again._remembered_iso()
        again._prerequisite_rows = [dict(r, busy=False) for r in rows()]
        self.assertEqual(again.build_ready(), "")

    def test_the_launcher_writes_what_an_adapter_marked(self):
        from openrecomp.app import Backend
        adapter = Page()
        adapter.config_dirty = True
        backend = SimpleNamespace(_was_running=False, window=None, _was_building=False, _was_sourcing=False,
                                  _last_hero={}, nav=SimpleNamespace(games=[Game(adapter.m, adapter)]),
                                  _save_config=mock.Mock())
        Backend._slow_changes(backend, False)
        backend._save_config.assert_called_once_with()
        self.assertFalse(adapter.config_dirty)
        Backend._slow_changes(backend, False)
        backend._save_config.assert_called_once_with()

    def test_a_changed_iso_is_checked_again(self):
        stamp = [os.path.normcase(os.path.abspath(__file__)), 1, 2]
        config = dict(t4_iso_verified={os.path.normcase(os.path.abspath("fake-root")): stamp})
        adapter = T4(MANIFEST, config, "fake-root", core=Core())
        adapter.s["iso"] = __file__
        self.assertIsNone(adapter._remembered_iso())


class T5Fraction(unittest.TestCase):
    def test_the_steps_own_progress_moves_the_bar(self):
        from openrecomp.adapters.t5dr import T5DR
        adapter = T5DR.__new__(T5DR)
        adapter.core = SimpleNamespace(STEP_TITLES={"a": "A", "b": "B"})
        adapter.build = SimpleNamespace(events=SimpleNamespace(get_nowait=mock.Mock(side_effect=__import__("queue").Empty)))
        adapter.build_steps = {"a": "@osk.done", "b": "@running"}
        adapter.build_step = "b"
        adapter.build_fraction = 0.5
        adapter.build_line = "x"
        adapter.build_lines = ["x"]
        adapter.last_result = ""
        state = adapter.build_state()
        self.assertEqual(state["fraction"], 0.75)
        self.assertEqual(state["step_no"], [2, 2])
        self.assertEqual(state["lines"], ["x"])

    def test_the_end_of_a_build_is_read_once_without_touching_the_finished_run(self):
        # QA run (fresh T5DR install built from the launcher): the "end" event set self.build = None and the loop
        # read self.build.events again -> AttributeError in the window's tick at the end of every build.
        import queue
        from openrecomp.adapters.t5dr import T5DR
        adapter = T5DR.__new__(T5DR)
        adapter.core = SimpleNamespace(STEP_TITLES={"a": "A"})
        events = queue.Queue()
        events.put(("step", "a"))
        events.put(("end", 0))
        adapter.build = SimpleNamespace(events=events, log_path="build.log")
        adapter.build_steps, adapter.build_step, adapter.build_fraction = {}, "", 0.0
        adapter.build_line, adapter.build_lines, adapter.last_result = "", [], ""
        state = adapter.build_state()
        self.assertFalse(state["running"])
        self.assertEqual(state["result"], "@build_finished")


if __name__ == "__main__":
    unittest.main()
