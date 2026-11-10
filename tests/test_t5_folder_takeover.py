"""A T5DR folder set up by T5DR's own launcher can be built from OpenRecomp, and both launchers keep using it.

Owner decision 2026-11-05: a one-time notice, then the build with the folder's own Python; the T5DR launcher's own
files and checks are not changed (docs/T5DR_COEXISTENCE.md "Building a folder from the T5DR launcher"). Everything here
is synthetic: an inert core, a fake build that writes what T5DR's build writes, mocked processes. One extra check runs the
real T5DR launcher's own core.py read-only when OPENRECOMP_TEST_T5DR_ROOT names an install (a developer PC).
"""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from openrecomp import i18n
from openrecomp.adapters import t5_buildlock, t5dr
from openrecomp.adapters.t5dr import T5DR
from openrecomp.nav import Game, Nav
from test_build_page import Page
from test_nav import manifest

REAL_INSTALL_PROBE = T5DR.build_install_problem
MANIFEST = dict(id="t5dr", adapter="t5dr", locations=[])
STAMP = {"code_id": "synthetic-code", "built": "2026-11-05T10:00:00"}


class NativeSettings(dict):
    """The T5DR launcher's Settings contract: launcher.json beside the install, never written by reading it."""

    def __init__(self):
        super().__init__(display="window", pkg="", rap="", low_priority=False)
        self.path = str(NativeSettings.root / "launcher.json")
        try:
            self.update(json.loads(Path(self.path).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    def save(self):
        Path(self.path).write_text(json.dumps(self), encoding="utf-8")

    @property
    def out_dir(self):
        return self.get("out_dir") or str(NativeSettings.root / "native")

    @property
    def replay_dir(self):
        return str(NativeSettings.root / "native" / "replays")

    def env_overrides(self):
        return {}


class FakeBuild:
    """build_game.py's visible result: the output tree T5DR's own BUILD GAME leaves, then the exit-code log line."""

    def __init__(self, out, lines=(), code=0):
        self.out, self.code = Path(out), code
        self.events = queue.Queue()
        self.log_path = str(self.out / "build.log")
        self.cmd = ["python.exe", "build_game.py"]
        self.lines = lines

    def start(self):
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "build.log").write_text("# T5DR Online build log\n", encoding="utf-8")
        for line in self.lines:
            self.events.put(("line", line))
        if self.code == 0:
            (self.out / "build").mkdir(exist_ok=True)
            (self.out / "build" / "t5dr_build.json").write_text(json.dumps(STAMP), encoding="utf-8")
            (self.out / "game").mkdir(exist_ok=True)
            (self.out / "game" / "EBOOT.elf").write_bytes(b"synthetic program")
            (self.out / "t5dr.exe").write_bytes(b"synthetic runtime")
        with open(self.out / "build.log", "a", encoding="utf-8") as log:
            log.write("# exit code %d\n" % self.code)
        self.events.put(("end", self.code))

    def cancel(self):
        pass


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file()}


class Folder(unittest.TestCase):
    """A synthetic folder as T5DR's own launcher leaves it (no OpenRecomp marker), plus an OpenRecomp home."""

    def setUp(self):
        self.temp = Path(self.enterContext(tempfile.TemporaryDirectory(dir=Path(__file__).parent)))
        self.root = self.temp / "T5DR-Online-1.2.1"
        for name in ("launcher", "python", "tools", "toolchain", "deps/ps3recomp"):
            (self.root / name).mkdir(parents=True)
        for name in ("T5DR Online.exe", "python/python.exe", "tools/build_game.py", "launcher/core.py"):
            (self.root / name).write_bytes(b"synthetic")
        (self.root / "release.json").write_text(json.dumps(dict(version="1.2.1", code_id="synthetic-code")), encoding="utf-8")
        (self.root / "launcher.json").write_text(json.dumps(dict(display="window1440", future={"keep": True})), encoding="utf-8")
        (self.root / "native").mkdir()
        NativeSettings.root = self.root
        self.home = self.temp / "openrecomp-home"
        self.enterContext(mock.patch.dict(os.environ, OPENRECOMP_HOME=str(self.home), OPENRECOMP_T5DR_ROOT=""))
        self.enterContext(mock.patch.object(T5DR, "build_install_problem", return_value=""))
        self.runs = []
        self.core = SimpleNamespace(Settings=NativeSettings, DEFAULTS={"display": "window", "pkg": "", "rap": ""},
                                    STEP_TITLES={"deps": "Recompiler", "unpack": "Unpack"},
                                    BuildRun=self.build_run, game_state=self.game_state,
                                    install_warnings=self.install_warnings)

    def build_run(self, pkg, rap, out, force=False, low_priority=False):
        run = FakeBuild(out, code=getattr(self, "exit_code", 0), lines=getattr(self, "log_lines", ()))
        run.args = (pkg, rap, out, force)
        self.runs.append(run)
        return run

    # T5DR core.py's own checks, written the way the real ones read the folder (game_state / install_warnings)
    def game_state(self, out):
        stamp = Path(out) / "build" / "t5dr_build.json"
        if not (Path(out) / "t5dr.exe").exists():
            return dict(built=False, ok=False, needs_rebuild=False)
        info = json.loads(stamp.read_text(encoding="utf-8")) if stamp.exists() else {}
        ok = (Path(out) / "game" / "EBOOT.elf").exists() and info.get("code_id") == "synthetic-code"
        return dict(built=True, ok=ok, needs_rebuild=not ok)

    def install_warnings(self, root):
        return [name for name in ("python", "tools", "toolchain", "launcher") if not (Path(root) / name).is_dir()]

    def adapter(self):
        a = T5DR(MANIFEST, {}, str(self.root), core=self.core, replays_mod=SimpleNamespace())
        a.s["pkg"], a.s["rap"] = "synthetic.pkg", "synthetic.rap"
        return a

    def finish(self, adapter):
        deadline = time.monotonic() + 5
        while adapter.build is not None and time.monotonic() < deadline:
            adapter.build_state()


class Building(Folder):
    def test_a_folder_without_the_openrecomp_marker_is_buildable_and_is_not_marked(self):
        a = self.adapter()
        self.assertFalse(a.managed)
        self.assertTrue(a.coexistence_state()["can_build"])
        self.assertEqual(a.build_ready(), "")
        self.assertFalse((self.root / "openrecomp-release.json").exists())

    def test_the_build_leaves_the_folder_as_the_t5dr_launcher_would_after_its_own_build(self):
        before = snapshot(self.root)
        a = self.adapter()
        warnings_before = self.core.install_warnings(self.root)
        a.build_start()
        self.finish(a)
        self.assertEqual(a.build_state()["result"], "@build_finished")
        after = snapshot(self.root)
        changed = {name for name in after if before.get(name) != after[name]} | (set(before) - set(after))
        self.assertTrue(changed, "the build wrote nothing")
        # Only the output folder changes: not launcher.json (its settings), release.json, the Python, tools, the .exe.
        self.assertTrue(all(name.startswith("native/") for name in changed), sorted(changed))
        for name in ("launcher.json", "release.json", "T5DR Online.exe", "python/python.exe", "tools/build_game.py"):
            self.assertEqual(after[name], before[name], name)
        self.assertFalse((self.root / "openrecomp-release.json").exists())
        self.assertFalse((self.root / t5_buildlock.LOCK_NAME).exists())
        self.assertEqual(self.runs[0].args, ("synthetic.pkg", "synthetic.rap", str(self.root / "native"), False))
        # The T5DR launcher's own checks: its settings still read as they were, the build counts as ready, the folder
        # still passes its install checks.
        settings = NativeSettings()
        self.assertEqual((settings["display"], settings["future"]), ("window1440", {"keep": True}))
        self.assertEqual(settings["pkg"], "")                       # the package choice stayed in OpenRecomp's home
        self.assertTrue(self.core.game_state(settings.out_dir)["ok"])
        self.assertEqual(self.core.install_warnings(self.root), warnings_before)

    def test_package_choices_are_kept_in_the_openrecomp_home_not_in_launcher_json(self):
        a = self.adapter()
        original = (self.root / "launcher.json").read_bytes()
        self.assertEqual(a.set_source("pkg", "other.pkg"), "")
        self.assertEqual((self.root / "launcher.json").read_bytes(), original)
        self.assertEqual(a.s["pkg"], "other.pkg")
        self.assertTrue(any(self.home.rglob("settings.json")))

    def test_an_openrecomp_install_is_unchanged_by_this(self):
        (self.root / "openrecomp-release.json").write_text(json.dumps(dict(
            game="t5dr", installed_by="OpenRecomp-FGC", version="0.0.0", tag="v0.0.0")), encoding="utf-8")
        a = self.adapter()
        self.assertTrue(a.managed)
        self.assertFalse(a.foreign_notice_pending())


REAL_SCAN = t5_buildlock._scan


class OneBuildAtATime(Folder):
    def setUp(self):
        super().setUp()
        t5_buildlock.forget_scan()
        self.addCleanup(t5_buildlock.forget_scan)
        self.addCleanup(t5_buildlock._ANYWAY.clear)
        self.processes = []                     # what the process list holds; None = cannot be read
        self.enterContext(mock.patch.object(t5_buildlock, "_scan", lambda: self.processes))

    def adapter(self):
        t5_buildlock.forget_scan()              # (the scan is cached for a few seconds; the tests change what it sees)
        return super().adapter()

    def build_line(self):
        return r'"%s\python\python.exe" "%s\tools\build_game.py" --pkg a.pkg --out "%s"' % (
            self.root, self.root, self.root / "native")

    def start_foreign_build(self, age=5, last="# step"):
        log = self.root / "native" / "build.log"
        log.write_text("# T5DR Online build log\n" + last + "\n", encoding="utf-8")
        stamp = time.time() - age
        os.utime(log, (stamp, stamp))

    def test_a_running_t5dr_launcher_build_stops_this_one_with_a_clear_message(self):
        self.start_foreign_build()
        self.processes = [(4242, self.build_line())]
        a = self.adapter()
        self.assertEqual(a.build_ready(), "@t5.build_locked_t5dr")
        with self.assertRaisesRegex(RuntimeError, "t5.build_locked_t5dr"):
            a.build_start()
        self.assertEqual(self.runs, [])
        self.assertFalse((self.root / t5_buildlock.LOCK_NAME).exists())

    def test_a_compiler_of_that_folder_counts_as_the_build_too(self):
        self.start_foreign_build(age=900)       # a quiet compile step: the log is old, the compiler is there
        self.processes = [(77, r'"%s\toolchain\llvm\bin\clang-cl.exe" /c x.c' % self.root)]
        self.assertEqual(self.adapter().build_ready(), "@t5.build_locked_t5dr")

    def test_a_cut_off_build_with_no_process_does_not_block(self):
        # OpenRecomp or T5DR's launcher closed mid-build: build.log changed seconds ago, no exit line, nothing running.
        self.start_foreign_build(age=3)
        for processes in ([], [(5, "python.exe other.py")], [(6, self.build_line().replace(str(self.root), r"D:\Other"))]):
            with self.subTest(processes=processes):
                self.processes = processes
                t5_buildlock.forget_scan()
                self.assertEqual(self.adapter().build_ready(), "")
        self.adapter().build_start()
        self.assertEqual(len(self.runs), 1)

    def test_when_the_processes_cannot_be_read_the_log_decides_with_a_short_window(self):
        self.processes = None
        for age, blocked in ((5, True), (t5_buildlock.BLIND_SECONDS - 20, True), (t5_buildlock.BLIND_SECONDS + 20, False),
                             (t5_buildlock.RUNNING_SECONDS - 20, False)):
            with self.subTest(age=age):
                self.start_foreign_build(age)
                self.assertEqual(self.adapter().build_ready(), "@t5.build_locked_t5dr" if blocked else "")
        self.start_foreign_build(5, "# exit code 1")
        self.assertEqual(self.adapter().build_ready(), "")

    @unittest.skipUnless(os.name == "nt", "the process list is read on Windows")
    def test_the_real_process_scan_sees_a_live_fake_build_and_not_a_dead_one(self):
        fake = self.root / "tools" / "build_game.py"
        fake.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        process = subprocess.Popen([sys.executable, str(fake), "--out", str(self.root / "native")], stdin=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        # A process that was started this instant has no readable command line yet: look again. Where some other
        # Python or compiler on the PC cannot be read (another account, a sandbox) the strict scan answers "could
        # not look" (None) by design; what it could read is then taken from the same scan without that rule.
        def scan():
            from openrecomp.adapters import other_launchers
            strict = REAL_SCAN()
            return other_launchers._command_lines(t5_buildlock._wanted) if strict is None else strict
        deadline = time.monotonic() + 10
        while True:
            lines = [l for l in scan() if l[0] == process.pid]
            if lines or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        self.assertEqual(len(lines), 1)
        self.assertTrue(t5_buildlock.t5dr_build_process(str(self.root / "native"), str(self.root), lines))
        self.assertFalse(t5_buildlock.t5dr_build_process(str(self.temp / "other" / "native"), str(self.temp / "other"), lines))
        process.kill()
        process.wait()
        self.assertFalse(t5_buildlock.t5dr_build_process(str(self.root / "native"), str(self.root), [l for l in scan() if l[0] == process.pid]))

    @unittest.skipUnless(os.name == "nt", "the process list is read on Windows")
    def test_a_process_with_a_very_long_command_line_is_still_read(self):
        """Over about 4,000 characters the command line did not fit the buffer: the process counted as unreadable
        and the strict scan answered "could not look" for the whole PC."""
        from openrecomp.adapters import other_launchers
        fake = self.root / "tools" / "build_game.py"
        fake.write_text("import time" + chr(10) + "time.sleep(60)" + chr(10), encoding="utf-8")
        long = "x" * 20000
        process = subprocess.Popen([sys.executable, str(fake), "--out", str(self.root / "native"), long],
                                   stdin=subprocess.DEVNULL)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        mine = lambda name: name.startswith("python")      # noqa: E731
        deadline = time.monotonic() + 10
        while True:
            found = [line for pid, line in other_launchers._command_lines(mine) if long in line]
            if found or time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        self.assertTrue(found)
        self.assertGreater(len(found[0]), 20000)
        self.assertTrue(t5_buildlock._is_build(found[0], [t5_buildlock._norm(str(self.root)).lower()]))

    def test_build_anyway_skips_the_t5dr_check_once(self):
        self.start_foreign_build()
        self.processes = [(4242, self.build_line())]
        a = self.adapter()
        self.assertEqual(a.build_ready(), "@t5.build_locked_t5dr")
        a.build_anyway()
        self.assertEqual(a.build_ready(), "")
        a.build_start()
        self.finish(a)
        self.assertEqual(len(self.runs), 1)
        self.start_foreign_build()
        self.assertEqual(a.build_ready(), "@t5.build_locked_t5dr", "the override was for that one build")

    def test_the_build_page_offers_build_anyway_and_asks_before_it(self):
        class LockedPage(Page):
            def __init__(self):
                super().__init__(adapter="t5dr", checks=[], sources=[
                    dict(id="pkg", label="@package", value="@found", ok=True, kind="file", exts=[".pkg"], dirs=[], hint="@package.hint"),
                    dict(id="rap", label="@license", value="@found", ok=True, kind="file", exts=[".rap"], dirs=[], hint="@license.hint")])
                self.locked = True

            def build_ready(self):
                return "@t5.build_locked_t5dr" if self.locked else ""

            def build_install_problem(self):
                return ""

            def build_anyway(self):
                self.locked = False
                self.calls.append(("anyway",))

        adapter = LockedPage()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["t5dr"] = "build"
        items = nav.items()
        build = next(i for i, it in enumerate(items) if it.get("id") == "build")
        self.assertEqual(i18n.localize(items[build]["verb"], "en"), "Build anyway")
        self.assertFalse(items[build].get("blocked"))
        nav.focus["t5dr:build"] = build
        nav.act("confirm", device="kb")
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "build_anyway"))
        self.assertEqual(adapter.calls, [], "asks first")
        nav.act("confirm", device="kb")                     # default answer: No
        self.assertEqual(adapter.calls, [])
        nav.focus["t5dr:build"] = build
        nav.act("confirm", device="kb")
        nav.act("right", device="kb")
        nav.act("confirm", device="kb")
        self.assertEqual(adapter.calls, [("anyway",), ("build", False)])

    def test_a_finished_or_old_t5dr_build_log_does_not_block(self):
        self.processes = [(4242, self.build_line())]
        for age, last in ((5, "# exit code 0"), (5, "# exit code 1")):
            with self.subTest(age=age, last=last):
                self.start_foreign_build(age, last)
                self.assertEqual(self.adapter().build_ready(), "")
        self.processes = None
        self.start_foreign_build(t5_buildlock.RUNNING_SECONDS + 60, "# step")
        self.assertEqual(self.adapter().build_ready(), "")

    def test_a_lock_whose_process_is_dead_is_replaced(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        lock = self.root / t5_buildlock.LOCK_NAME
        lock.write_text(json.dumps(dict(pid=dead.pid)), encoding="utf-8")
        a = self.adapter()
        self.assertEqual(a.build_ready(), "")
        a.build_start()
        self.assertEqual(json.loads(lock.read_text(encoding="utf-8"))["pid"], os.getpid())
        self.finish(a)
        self.assertFalse(lock.exists())

    def test_our_own_lock_is_held_during_the_build_and_removed_at_its_end(self):
        a = self.adapter()
        a.build_start = a.build_start      # (the real method)
        with mock.patch.object(self, "build_run", wraps=self.build_run):
            lock = self.root / t5_buildlock.LOCK_NAME
            real = FakeBuild.start
            seen = []

            def start(run):
                seen.append(lock.is_file())          # the lock exists while the build runs
                real(run)

            with mock.patch.object(FakeBuild, "start", start):
                a.build_start()
                self.finish(a)
        self.assertEqual(seen, [True])
        self.assertFalse(lock.exists())

    def test_another_running_openrecomp_process_stops_the_build(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL)
        self.addCleanup(other.wait)
        self.addCleanup(other.kill)
        (self.root / t5_buildlock.LOCK_NAME).write_text(json.dumps(dict(pid=other.pid)), encoding="utf-8")
        a = self.adapter()
        self.assertEqual(a.build_ready(), "@t5.build_locked_openrecomp")
        with self.assertRaisesRegex(RuntimeError, "t5.build_locked_openrecomp"):
            a.build_start()
        self.assertEqual(self.runs, [])
        self.assertTrue((self.root / t5_buildlock.LOCK_NAME).exists(), "someone else's lock is never removed")
        other.kill()
        other.wait()
        self.assertEqual(a.build_ready(), "")          # its process is gone: the lock is stale

    def test_a_failed_start_gives_the_lock_back(self):
        a = self.adapter()
        with mock.patch.object(a.core, "BuildRun", side_effect=OSError("synthetic")):
            with self.assertRaises(OSError):
                a.build_start()
        self.assertFalse((self.root / t5_buildlock.LOCK_NAME).exists())

    def test_a_cancelled_or_failed_build_gives_the_lock_back(self):
        for code in (1, -1):
            with self.subTest(code=code):
                self.exit_code = code
                a = self.adapter()
                a.build_start()
                self.finish(a)
                self.assertFalse((self.root / t5_buildlock.LOCK_NAME).exists())


class NoticeOnce(Folder):
    def test_the_notice_is_pending_once_per_folder_and_kept_in_the_config_only(self):
        a = self.adapter()
        before = snapshot(self.root)
        self.assertTrue(a.foreign_notice_pending())
        a.foreign_notice_done()
        self.assertFalse(a.foreign_notice_pending())
        self.assertTrue(a.config["t5dr_folder_notice"])
        self.assertEqual(snapshot(self.root), before)
        other = self.temp / "T5DR-Online-1.2.2"
        other.mkdir()
        b = self.adapter()
        b.root = str(other)
        self.assertTrue(b.foreign_notice_pending(), "another folder is told again")

    def test_the_build_button_asks_once_then_builds(self):
        class FolderPage(Page):
            def __init__(self):
                super().__init__(adapter="t5dr", checks=[], sources=[
                    dict(id="pkg", label="@package", value="@found", ok=True, kind="file", exts=[".pkg"], dirs=[], hint="@package.hint"),
                    dict(id="rap", label="@license", value="@found", ok=True, kind="file", exts=[".rap"], dirs=[], hint="@license.hint")])
                self.pending, self.told = True, 0

            def foreign_notice_pending(self):
                return self.pending

            def foreign_notice_done(self):
                self.pending, self.told = False, self.told + 1

            def coexistence_state(self):
                return dict(active=True, source="C:/T5DR-Online-1.2.1", build="unknown", can_build=True)

            def build_install_problem(self):
                return ""

        adapter = FolderPage()
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["t5dr"] = "build"
        saved = []
        nav.on_adapter_config = lambda: saved.append(True)

        def press_build():
            items = nav.items()
            nav.focus["t5dr:build"] = next(i for i, it in enumerate(items) if it.get("id") == "build")
            nav.act("confirm", device="kb")

        press_build()
        self.assertEqual((nav.overlay, nav.confirm_kind), ("dialog", "t5_folder"))
        self.assertEqual(adapter.calls, [], "nothing builds before the notice is answered")
        dialog = nav.view()["dialog"]
        text = i18n.localize(dialog["text"], "en")
        self.assertIn("set up by the T5DR launcher", text)
        self.assertIn("keeps working", text)
        nav.act("right", device="kb")
        nav.act("confirm", device="kb")
        self.assertEqual(adapter.calls, [("build", False)])
        self.assertEqual((adapter.told, saved), (1, [True]))
        press_build()
        self.assertIsNone(nav.overlay)
        self.assertEqual(adapter.calls, [("build", False), ("build", False)], "told once, then it just builds")

    def test_declining_the_notice_builds_nothing_and_asks_again_next_time(self):
        class FolderPage(Page):
            told = 0

            def foreign_notice_pending(self):
                return True

            def coexistence_state(self):
                return dict(active=True, source="C:/T5DR-Online-1.2.1", build="unknown", can_build=True)

            def build_install_problem(self):
                return ""

        adapter = FolderPage(adapter="t5dr", checks=[])
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["t5dr"] = "build"
        items = nav.items()
        nav.focus["t5dr:build"] = next(i for i, it in enumerate(items) if it.get("id") == "build")
        nav.act("confirm", device="kb")
        self.assertEqual(nav.confirm_kind, "t5_folder")
        nav.act("confirm", device="kb")                # focus is on No
        self.assertEqual(adapter.calls, [])
        nav.act("confirm", device="kb")
        self.assertEqual(nav.confirm_kind, "t5_folder")


class PathTooLong(Folder):
    def test_a_long_path_breaking_the_crypto_import_says_move_the_folder_not_reinstall(self):
        error = subprocess.CalledProcessError(1, ["python.exe"], stderr=b"OSError: [WinError 206] The filename or extension is too long")
        with mock.patch.object(T5DR, "build_install_problem", REAL_INSTALL_PROBE), \
                mock.patch.object(t5dr.subprocess, "run", side_effect=error), \
                mock.patch.object(t5dr.os, "stat", side_effect=lambda p, *a, **k: SimpleNamespace(
                    st_mtime_ns=1, st_size=1)):
            a = self.adapter()
            self.assertEqual(a.build_install_problem(), "@t5.install_path_too_long")
            text = i18n.localize("@t5.install_path_too_long", "en")
        self.assertIn("too long", text)
        self.assertIn(r"C:\Games\T5DR", text)
        self.assertNotIn("einstall", text)

    def test_other_import_failures_still_say_the_install_is_incomplete(self):
        error = subprocess.CalledProcessError(1, ["python.exe"], stderr=b"ModuleNotFoundError: No module named 'Crypto'")
        with mock.patch.object(T5DR, "build_install_problem", REAL_INSTALL_PROBE), \
                mock.patch.object(t5dr.subprocess, "run", side_effect=error), \
                mock.patch.object(t5dr.os, "stat", side_effect=lambda p, *a, **k: SimpleNamespace(
                    st_mtime_ns=1, st_size=1)):
            self.assertEqual(self.adapter().build_install_problem(), "@t5.install_incomplete_python")

    def test_a_build_that_fails_on_winerror_206_says_the_path_is_too_long(self):
        self.exit_code = 1
        self.log_lines = ("[unpack]", "OSError: [WinError 206] The filename or extension is too long: 'C:\\\\very\\\\long'",
                          "ERROR: unpack failed")
        a = self.adapter()
        a.build_start()
        self.finish(a)
        state = a.build_state()
        self.assertEqual(state["result"], "@t5.build_path_too_long")
        self.assertEqual(state["failed"], "build")
        self.assertNotIn("einstall", i18n.localize(state["result"], "en"))

    def test_a_failure_without_that_error_keeps_the_log_message(self):
        self.exit_code = 1
        a = self.adapter()
        a.build_start()
        self.finish(a)
        self.assertEqual(a.build_state()["result"]["_text"], "build_failed")

    def test_the_build_page_offers_choosing_the_moved_folder_not_a_reinstall(self):
        class Long(Page):
            def build_install_problem(self):
                return "@t5.install_path_too_long"

        adapter = Long(adapter="t5dr", checks=[])
        nav = Nav([Game(adapter.m, adapter)], language="en")
        nav.screen = "hub"
        nav.sec["t5dr"] = "build"
        ids = [it.get("id") for it in nav.items()]
        self.assertIn("build_choose_install", ids)
        self.assertNotIn("build_reinstall", ids)


class Texts(unittest.TestCase):
    KEYS = ("dialog.t5_folder.title", "dialog.t5_folder.text", "t5.build_locked_openrecomp", "t5.build_locked_t5dr", "t5.build_anyway", "dialog.build_anyway.title", "dialog.build_anyway.text",
            "t5.build_lock_failed", "t5.install_path_too_long", "t5.build_path_too_long", "t5.coexist.build_differs")

    def test_every_text_exists_in_all_seven_languages_and_is_translated(self):
        english = i18n.catalog("en")
        for language in i18n.LANGUAGES:
            for key in self.KEYS:
                with self.subTest(language=language, key=key):
                    text = i18n.catalog(language)[key]
                    self.assertTrue(text.strip())
                    if language != "en":
                        self.assertNotEqual(text, english[key])
                    if key.endswith("too_long"):
                        self.assertIn(r"C:\Games\T5DR", text)

    def test_the_old_wording_that_the_t5dr_launcher_alone_rebuilds_is_gone(self):
        for language in i18n.LANGUAGES:
            self.assertNotIn("im eigenen Launcher", i18n.catalog(language)["t5.coexist.build_differs"])
        self.assertNotIn("in its own launcher", i18n.catalog("en")["t5.coexist.build_differs"])


@unittest.skipUnless(os.environ.get("OPENRECOMP_TEST_T5DR_ROOT"), "set OPENRECOMP_TEST_T5DR_ROOT to a T5DR install (read only)")
class RealT5drCore(unittest.TestCase):
    """The real T5DR launcher core.py, imported read-only: its own checks read the folder the same before and after."""

    def test_the_real_checks_see_the_same_folder_after_an_openrecomp_attach(self):
        root = os.path.realpath(os.environ["OPENRECOMP_TEST_T5DR_ROOT"])
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, OPENRECOMP_HOME=home, OPENRECOMP_T5DR_ROOT=""):
            sys.dont_write_bytecode = True
            for name in ("core", "replays"):
                sys.modules.pop(name, None)
            try:
                for name in ("lobby", "tools", "launcher"):
                    t5dr.add_path(os.path.join(root, name))
                core = t5dr.load_runtime(root, "core")
                before = snapshot(root)
                warnings = core.install_warnings(root)
                settings = core.Settings(os.path.join(root, "launcher.json"))
                values = dict(settings)
                with mock.patch.object(T5DR, "build_install_problem", return_value=""):
                    a = T5DR(MANIFEST, {}, root, core=core, replays_mod=SimpleNamespace())
                    self.assertTrue(a.foreign_notice_pending())
                    self.assertEqual(a.build_ready() in ("", "@choose_package_license"), True)
                self.assertEqual(snapshot(root), before)
                self.assertEqual(core.install_warnings(root), warnings)
                self.assertEqual(dict(core.Settings(os.path.join(root, "launcher.json"))), values)
            finally:
                for name in ("core", "replays"):
                    sys.modules.pop(name, None)


if __name__ == "__main__":
    unittest.main()
