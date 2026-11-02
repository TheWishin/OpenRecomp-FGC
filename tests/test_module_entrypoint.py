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
    def run_profile(self, contents=None, *, directory=False):
        with tempfile.TemporaryDirectory(prefix=".module-test-", dir=ROOT) as home:
            config = Path(home, "config.json")
            if directory:
                config.mkdir()
            elif contents is not None:
                config.write_bytes(contents)
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic", QML_DISABLE_DISK_CACHE="1",
                       OPENRECOMP_HOME=home, OPENRECOMP_PAD_ALWAYS="1")
            result = subprocess.run(
                [sys.executable, "-B", str(Path(__file__).resolve()), "--module-child"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(COMPLETE, result.stdout, result.stdout + result.stderr)
            report = json.loads(result.stdout.split(COMPLETE, 1)[1].splitlines()[0])
            self.assertEqual(report["entry"], "openrecomp.__main__")
            self.assertEqual(report["adapters"], ["Missing", "Missing"])
            self.assertTrue(report["quit"])
            if directory:
                self.assertTrue(config.is_dir())
                self.assertEqual(list(config.iterdir()), [])
            elif contents is not None:
                self.assertEqual(config.read_bytes(), contents)
            else:
                saved = json.loads(config.read_text(encoding="utf-8"))
                self.assertEqual(saved["last_game"], "t5dr")
                self.assertFalse(saved["fullscreen"])
                self.assertTrue(saved["reduced_motion"])

    def test_clean_profile_starts_and_saves_controller_preferences(self):
        self.run_profile(None)

    def test_malformed_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(b"{invalid configuration\n")

    def test_nonobject_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(b"[]\n")

    def test_unwritable_profile_keeps_selection_preferences_and_quit_usable(self):
        self.run_profile(directory=True)


def run_child():
    from contextlib import ExitStack
    import runpy
    import traceback
    from unittest import mock

    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QEventLoop, QTimer, QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication, QWindow
    from openrecomp import app, i18n
    from openrecomp.adapters import t4, t5dr
    from openrecomp.adapters.base import Missing

    failures, warnings, forbidden, report = [], [], [], {}
    config = Path(os.environ["OPENRECOMP_HOME"], "config.json")
    malformed = config.exists()

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
        buttons = dict(confirm="A", back="B", social="Y", right="DRIGHT", down="DDOWN")

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
            if malformed:
                check(backend.view["toast"] == i18n.text(nav.language, "preferences.save_failed"),
                      "An unsaved preference needs localized feedback")

        check(QGuiApplication.platformName() == "offscreen", "Visible platform selected")
        check(isinstance(window, QWindow) and window.isVisible(), "Real window did not start")
        check(window.property("wantFull") is False, "--windowed was not honored")
        check(nav.screen == "start" and not nav.overlay, "First-run shelf did not load")
        check([g.id for g in nav.games] == ["t4", "t5dr"], "Built-in discovery did not run")
        check(all(isinstance(g.a, Missing) for g in nav.games), "Real Missing adapters were not used")
        check(all(not tile["hero"] for tile in backend.view["shelf"]["tiles"]), "Unexpected artwork")
        report.update(entry="openrecomp.__main__", adapters=[type(g.a).__name__ for g in nav.games])
        backend._tick()  # Release the initial pad suppression.
        press("right")
        press("confirm")
        check(nav.game.id == "t5dr" and nav.overlay == "picker", "Game selection did not open onboarding")
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
            patches.enter_context(mock.patch.object(t4, "find_root", return_value=None))
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
