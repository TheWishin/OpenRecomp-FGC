"""The real module, Backend and QML with no install, hardware or network access."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
COMPLETE = "MODULE_ENTRY_COMPLETE "


class ModuleEntrypoint(unittest.TestCase):
    def run_profile(self, contents=None, *, directory=False, saved=False, generic=False,
                    last_run=None, t4=False, expected_last="@never"):
        with tempfile.TemporaryDirectory(prefix=".module-test-", dir=ROOT) as home:
            config = Path(home, "config.json")
            if directory:
                config.mkdir()
            elif contents is not None:
                config.write_bytes(contents)
            if generic:
                games = Path(home, "games")
                games.mkdir()
                games.joinpath("example.json").write_text(json.dumps(dict(
                    schema_version=1, id="example", title="Example", numeral="E", accent="#123ABC",
                    adapter="generic", platform="PC", author="Example author", repository="example/recomp",
                    exe="bin/example.exe", license="MIT", credits=["Example author"],
                    requirements=[dict(id="input", label="Input", kind="file", version="1", sha256="0" * 64)])),
                    encoding="utf-8")
            refused = directory or (contents is not None and not saved)
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic", QML_DISABLE_DISK_CACHE="1",
                       OPENRECOMP_HOME=home, OPENRECOMP_PAD_ALWAYS="1",
                       OPENRECOMP_TEST_SCENARIO=json.dumps(dict(refused=refused, generic=generic,
                           t4=t4, last_run=last_run, expected_last=expected_last)))
            result = subprocess.run(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--module-child"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(COMPLETE, result.stdout, result.stdout + result.stderr)
            report = json.loads(result.stdout.split(COMPLETE, 1)[1].splitlines()[0])
            self.assertEqual(report["entry"], "openrecomp.__main__")
            self.assertEqual(report["adapters"], ["T4" if t4 else "Missing", "Missing"] +
                             (["Generic"] if generic else []))
            self.assertTrue(report["quit"])
            self.assertEqual(list(Path(home).glob(".config-*.tmp")), [])
            if generic:
                self.assertTrue(report["generic_onboarding"])
            if directory:
                self.assertTrue(config.is_dir())
                self.assertEqual(list(config.iterdir()), [])
            elif refused:
                self.assertEqual(config.read_bytes(), contents)
            else:
                actual = json.loads(config.read_text(encoding="utf-8"))
                self.assertEqual(actual["last_game"], "t5dr")
                self.assertFalse(actual["fullscreen"])
                self.assertTrue(actual["reduced_motion"])
                if contents is not None:
                    original = json.loads(contents)
                    for key in set(original) - {"last_game", "language", "fullscreen", "reduced_motion"}:
                        self.assertEqual(actual[key], original[key], key)

    def test_clean_profile_starts_and_saves_controller_preferences(self):
        self.run_profile(None)

    def test_malformed_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(b"{invalid configuration\n")

    def test_nonobject_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(b"[]\n")

    def test_unwritable_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(directory=True)

    def test_deep_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(b'{"unknown":' + b'[' * 10000 + b'0' + b']' * 10000 + b'}')

    def test_deep_profile_preserves_bytes_when_preferences_cannot_serialize(self):
        self.run_profile(b'{"unknown":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}')

    def test_malformed_generic_roots_keep_onboarding_and_quit_usable(self):
        for roots in ("invalid", ["invalid"], {"example": ["invalid"]}, {"example": {"bad": "path"}},
                      {"example": True}, {"example": 7}, {"example": "bad\x00path"}):
            with self.subTest(roots=roots):
                self.run_profile(json.dumps(dict(roots=roots, unknown={"keep": "unchanged"})).encode(),
                                 saved=True, generic=True)

    def test_malformed_generic_sources_keep_onboarding_and_quit_usable(self):
        for sources in ("invalid", ["invalid"], {"example": "invalid"}, {"example": ["invalid"]},
                        {"example": {"input": True}}, {"example": {"input": ["invalid"]}},
                        {"example": {"input": {"path": ["invalid"], "sha256": "0" * 64}}}):
            with self.subTest(sources=sources):
                self.run_profile(json.dumps(dict(generic_sources=sources, unknown={"keep": "unchanged"})).encode(),
                                 saved=True, generic=True)

    def test_malformed_t4_last_run_keeps_shelf_preferences_and_quit_usable(self):
        for last in ("invalid", ["invalid"], True, 7, {"time": True}, {"time": ["invalid"]},
                     {"time": {"bad": "time"}}):
            with self.subTest(last_run=last):
                self.run_profile(t4=True, last_run=last)

    def test_valid_t4_last_run_remains_visible_through_module_startup(self):
        self.run_profile(t4=True, last_run={"time": "2026-10-30 02:06:42", "ok": True},
                         expected_last="30.10., 02:06")


def run_child():
    from contextlib import ExitStack
    import runpy
    import traceback
    from unittest import mock
    from types import SimpleNamespace

    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QEventLoop, QTimer, QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication, QWindow
    from openrecomp import app, i18n
    from openrecomp.adapters import t4, t5dr

    failures, warnings, forbidden, report = [], [], [], {}
    config = Path(os.environ["OPENRECOMP_HOME"], "config.json")
    scenario = json.loads(os.environ["OPENRECOMP_TEST_SCENARIO"])

    def check(condition, message):
        if not condition:
            raise AssertionError(message)

    def prohibited(*args, **kwargs):
        forbidden.append(True)
        raise AssertionError("Module smoke test requested an external operation")

    class Reader:
        kind = "xbox"
        held = set()

        def read(self):
            return set(self.held)

    reader = Reader()

    def spin():
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()

    def drive(backend):
        nav, window = backend.nav, backend.window
        buttons = dict(confirm="A", back="B", social="Y", right="DRIGHT", left="DLEFT", down="DDOWN")

        def press(action):
            reader.held = {buttons[action]}
            backend._tick()
            reader.held = set()
            backend._tick()
            spin()
            check(not failures, "Qt callback failed: " + "\n".join(failures))
            check(not warnings, "QML warnings: " + "\n".join(warnings))
            check(not forbidden, "External operation requested")

        def save_feedback():
            if scenario["refused"]:
                # Preferences coalesce before writing; feedback follows that write.
                for _ in range(200):
                    if not backend._save_timer.isActive():
                        break
                    spin()
                check(backend.view["toast"] == i18n.text(nav.language, "preferences.save_failed"),
                      "An unsaved preference needs localized feedback")

        check(QGuiApplication.platformName() == "offscreen", "Visible platform selected")
        check(isinstance(window, QWindow) and window.isVisible(), "Real window did not start")
        check(window.property("wantFull") is False, "--windowed was not honored")
        check(nav.screen == "start" and not nav.overlay, "First-run shelf did not load")
        check([g.id for g in nav.games] == ["t4", "t5dr"] +
              (["example"] if scenario["generic"] else []), "Real manifest discovery did not run")
        check([type(g.a).__name__ for g in nav.games] ==
              (["T4" if scenario["t4"] else "Missing", "Missing"] +
               (["Generic"] if scenario["generic"] else [])), "Real adapters were not used")
        check(all(not tile["hero"] for tile in backend.view["shelf"]["tiles"]), "Unexpected artwork")
        report.update(entry="openrecomp.__main__", adapters=[type(g.a).__name__ for g in nav.games])
        if scenario["t4"]:
            check(nav.games[0].a.status()["last"] == scenario["expected_last"],
                  "Last-run shelf time did not match the expected value")
            check(backend.view["shelf"]["tiles"][0]["rows"][-1]["v"] ==
                  i18n.localize(scenario["expected_last"], nav.language),
                  "Last-run time did not reach the real shelf view")
        backend._tick()  # Release the initial pad suppression.
        if scenario["generic"]:
            press("right")
            press("right")
            press("confirm")
            check(nav.game.id == "example" and nav.overlay == "picker", "Generic onboarding did not open")
            check(nav.picker is not None, "Generic recovery picker is missing")
            report["generic_onboarding"] = True
            press("back")
            press("left")
            press("left")
        press("right")
        press("confirm")
        # T5DR not found: its Build section with Install (download) first and Choose folder after it
        check(nav.game.id == "t5dr" and nav.screen == "hub" and nav.sec.get("t5dr") == "build"
              and nav.items()[0]["id"] == "game_setup", "Game selection did not open onboarding")
        save_feedback()
        press("back")
        press("social")
        check(nav.overlay == "drawer", "Controller did not open quick access")
        previous = nav.language
        press("right")
        check(nav.language != previous and backend.config["language"] == nav.language,
              "Language did not change for this session")
        save_feedback()
        press("down")
        press("confirm")
        check(nav.fullscreen and window.property("wantFull"), "Fullscreen preference did not reach the real window")
        save_feedback()
        press("confirm")
        check(not nav.fullscreen and not window.property("wantFull"), "Windowed preference did not reach the real window")
        save_feedback()
        press("down")
        press("confirm")
        check(nav.reduced_motion and window.property("reducedMotion"), "Reduced motion did not reach QML")
        save_feedback()
        press("back")
        press("back")
        check(nav.overlay == "dialog" and nav.confirm_kind == "exit", "Controller quit dialog did not open")
        press("right")
        press("confirm")
        check(window.property("allowClose"), "Controller quit did not reach the real backend")
        report["quit"] = True

    def on_exception(kind, value, tb):
        failures.append("".join(traceback.format_exception(kind, value, tb)))
        QGuiApplication.exit(1)

    def qt_message(kind, context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if ".qml" in message or "qml" in str(getattr(context, "category", "")).lower():
                warnings.append(message)

    real_engine, real_make_engine = app.QQmlApplicationEngine, app.make_engine

    def create_engine():
        engine = real_engine()
        engine.warnings.connect(lambda items: warnings.extend(item.toString() for item in items))
        return engine

    def start_scene(backend, full):
        engine = real_make_engine(backend, full)
        check(engine.rootObjects(), "Real QML did not load")

        def walk():
            try:
                drive(backend)
            except BaseException:
                on_exception(*sys.exc_info())

        QTimer.singleShot(0, walk)
        QTimer.singleShot(25000, lambda: on_exception(
            AssertionError, AssertionError("Module smoke watchdog"), None))
        return engine

    previous_hook, sys.excepthook = sys.excepthook, on_exception
    previous_handler = qInstallMessageHandler(qt_message)
    try:
        with ExitStack() as patches:
            # Keep manifest loading, adapter construction, Backend and QML real.
            patches.enter_context(mock.patch.object(t4, "find_root", return_value=
                str(config.parent) if scenario["t4"] else None))
            patches.enter_context(mock.patch.object(t4, "load_core", return_value=SimpleNamespace(
                load_settings=lambda: {"last_run": scenario["last_run"]}, play_problems=lambda _: [],
                STEPS=(), find_runtime=lambda _: (None, ""))))
            patches.enter_context(mock.patch.object(t5dr, "find_root", return_value=None))
            patches.enter_context(mock.patch.object(app, "XInputReader", return_value=reader))
            patches.enter_context(mock.patch.object(app, "WinMMPlayStationReader", return_value=Reader()))
            patches.enter_context(mock.patch.object(app, "PlayStationReader", side_effect=prohibited))
            patches.enter_context(mock.patch.object(app.Nav, "_picker_entries", return_value=[]))
            patches.enter_context(mock.patch.object(app.UpdateService, "check"))
            patches.enter_context(mock.patch.object(app.updater, "confirm_startup", return_value=False))
            patches.enter_context(mock.patch.object(app.updater, "update_result", return_value=None))
            patches.enter_context(mock.patch.object(app, "QQmlApplicationEngine", side_effect=create_engine))
            patches.enter_context(mock.patch.object(app, "make_engine", side_effect=start_scene))
            patches.enter_context(mock.patch("socket.socket", side_effect=prohibited))
            patches.enter_context(mock.patch("subprocess.Popen", side_effect=prohibited))
            sys.argv = ["openrecomp", "--windowed"]
            # Embedded CPython ignores PYTHONPATH/sitecustomize. runpy uses the
            # actual __main__ after installing the test-only safety boundaries.
            try:
                runpy.run_module("openrecomp", run_name="__main__")
            except SystemExit as result:
                check(result.code == 0, "Module exited unsuccessfully: " + "\n".join(failures))
            else:
                raise AssertionError("Module did not return an exit status")
        check(report.get("quit"), "Module did not finish its controller walk")
        check(not failures, "\n".join(failures))
        check(not warnings, "QML warnings: " + "\n".join(warnings))
        check(not forbidden, "External operation requested")
        print(COMPLETE + json.dumps(report), flush=True)
    finally:
        qInstallMessageHandler(previous_handler)
        sys.excepthook = previous_hook


if __name__ == "__main__":
    if sys.argv[1:] == ["--module-child"]:
        run_child()
    else:
        unittest.main()
