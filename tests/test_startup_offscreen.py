"""Real module/Qt/QML startup and T4 controller walk, isolated from player installs.

The child has a hard timeout. Only the adapter and physical input boundaries
are synthetic: no disc is read, build/game started, connection or log made.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
COMPLETE = "OFFSCREEN_T4_COMPLETE "


class StartupOffscreen(unittest.TestCase):
    def test_real_main_and_t4_controller_flow_without_qml_warnings(self):
        with tempfile.TemporaryDirectory(prefix=".startup-test-", dir=ROOT) as home:
            Path(home, "config.json").write_text(
                json.dumps(dict(language="en", fullscreen=False)), encoding="utf-8")
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic", QML_DISABLE_DISK_CACHE="1",
                       OPENRECOMP_HOME=home, OPENRECOMP_PAD_ALWAYS="1")
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--offscreen-child"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=55)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(COMPLETE, result.stdout, result.stdout + result.stderr)
        report = json.loads(result.stdout.split(COMPLETE, 1)[1].splitlines()[0])
        self.assertEqual(set(report["screens"]), {
            "shelf", "tools", "iso", "picker", "build", "build_progress", "cancel_dialog",
            "built", "host", "join", "address_keyboard", "logs", "settings", "drawer", "quit_dialog"})
        self.assertEqual(set(report["languages"]), {"en", "de", "es", "fr", "ja", "ko", "pt-BR"})


def run_child():
    # Import Qt only in the child, after the parent has selected offscreen.
    from contextlib import ExitStack
    import runpy
    import traceback
    from unittest import mock

    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QEventLoop, QTimer, QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication, QWindow
    from openrecomp import app, i18n
    from openrecomp.adapters.base import Adapter
    from openrecomp.pad import SOURCES

    failures, qml_warnings, screens, languages, forbidden = [], [], set(), set(), []

    def check(condition, message):
        if not condition:
            raise AssertionError(message)

    def prohibited(*args, **kwargs):
        forbidden.append(str(args[:1]))
        raise AssertionError("The smoke test requested a real external operation")

    class Reader:
        kind = "xbox"
        held = set()

        def read(self):
            return set(self.held)

    class TestGame(Adapter):
        def __init__(self, manifest, config):
            super().__init__(manifest, config)
            self.built = False
            self.accepted = False
            self.build = super().build_state()
            self.source = super().source_state()
            self.online = dict(phase="offline", role="host", busy=False, message="@t4.direct_hint",
                               capabilities=dict(direct_ip=True), checks=[],
                               build_id="synthetic-build", compiler="Synthetic compiler")
            self.address = ""
            self.calls = []

        def found(self):
            return self.m["id"] == "t4"

        def ready(self):
            return self.built

        def prerequisites(self):
            return [dict(id="git", label="Git", value="@missing", ok=False,
                         command="winget install --id Git.Git --exact --source winget")]

        def refresh_prerequisites(self):
            self.calls.append("tools")

        def sources(self):
            return [dict(id="iso", label="@game_iso", value="@missing", ok=self.accepted,
                         kind="file", exts=[".iso"], dirs=[], hint="@iso.choose_first")]

        def set_source(self, sid, path):
            check((sid, path) == ("iso", "synthetic-choice.iso"), "Unexpected source selection")
            self.calls.append("iso")
            self.accepted = True
            self.source.update(id=sid, result="@iso.confirmed", ok=True)
            return "@iso.confirmed"

        def source_state(self):
            return dict(self.source)

        def build_ready(self):
            return "" if self.accepted else "@iso.choose_first"

        def build_state(self):
            return dict(self.build)

        def online_state(self):
            return dict(self.online)

        def online_action(self, action):
            self.calls.append(action)
            if action in ("host", "join"):
                self.online["role"] = action
            elif action == "collect_logs":
                self.online.update(log_path="synthetic-diagnostics.zip", message="Synthetic log result")
            elif action != "disconnect":
                prohibited(action)

        def text_value(self, tid):
            return self.address if tid == "online_address" else ""

        def set_text_value(self, tid, value):
            check(tid == "online_address", "Unexpected text field")
            self.address = value

        start = build_start = build_cancel = open_native = prohibited

    reader = Reader()
    games = {}

    def make_adapter(manifest, config):
        game = TestGame(manifest, config)
        games[manifest["id"]] = game
        return game

    def spin():
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()

    def drive(backend):
        nav, game = backend.nav, games["t4"]
        buttons = {action: name for name, action in SOURCES}

        def press(action):
            reader.held = {buttons[action]}
            backend._tick()
            reader.held = set()
            backend._tick()
            spin()
            check(not forbidden, "External operation requested")
            check(not failures, "Exception in a Qt callback: " + "\n".join(failures))
            check(not qml_warnings, "QML warnings: " + "\n".join(qml_warnings))

        def focus(iid, activate=False):
            for _ in range(len(nav.items()) + 1):
                if nav.items()[nav.focus_index(nav.items())].get("id") == iid:
                    if activate:
                        press("confirm")
                    return
                press("up")
            for _ in range(len(nav.items()) + 1):
                if nav.items()[nav.focus_index(nav.items())].get("id") == iid:
                    if activate:
                        press("confirm")
                    return
                press("down")
            raise AssertionError("Controller could not reach " + iid)

        def section(name):
            for _ in nav.sections():
                if nav.section() == name:
                    return
                press("next")
            raise AssertionError("Controller could not reach section " + name)

        check(QGuiApplication.platformName() == "offscreen", "A visible platform was selected")
        # Startup suppresses held buttons until the first released input sample.
        backend._tick()
        spin()
        check(nav.screen == "start", "main did not start at the shelf")
        screens.add("shelf")
        for _ in nav.tile_ids():
            if nav.tile_ids()[nav.start_focus] == "t4":
                break
            press("right")
        check(nav.tile_ids()[nav.start_focus] == "t4", "Controller could not reach the T4 tile")
        press("confirm")
        check(nav.screen == "hub" and nav.game.id == "t4", "T4 page did not open")
        section("build")
        check(not any(str(row.get("id", "")).startswith(("tool:", "tool_copy:")) for row in nav.items()),
              "Build tools are listed one by one again")
        check(not any(str(row.get("id", "")).startswith("tools") for row in nav.items()),
              "Missing build tools are a row again: Build installs them itself")
        tools_card = next(card for card in backend.view["build"]["cards"] if card["id"] == "tools")
        check(tools_card["status"] == "wait" and not tools_card["actions"], "The tools card must be one line")
        check(backend.view["build"]["show"], "The Build page did not show its cards")
        screens.add("tools")
        focus("iso")
        screens.add("iso")
        press("confirm")
        check(nav.overlay == "picker", "ISO picker did not open")
        screens.add("picker")
        press("back")
        focus("build", activate=True)
        check(not game.accepted and not forbidden, "Missing ISO must block a build")
        screens.add("build")
        focus("iso", activate=True)
        press("confirm")
        check(game.accepted and "iso" in game.calls, "Synthetic ISO was not selected")
        focus("build")
        # Present adapter snapshots; never call build_start or create game data.
        game.build.update(running=True, fraction=.5, title="Synthetic step", line="Synthetic progress",
                          steps=[dict(k="Synthetic stage", v="Running")])
        backend.refresh()
        spin()
        check(backend.view["detail"]["progress"] == .5, "Progress screen did not update")
        screens.add("build_progress")
        press("confirm")
        check(nav.overlay == "dialog" and nav.confirm_kind == "cancel_build", "Cancel dialog did not open")
        screens.add("cancel_dialog")
        press("back")
        game.build.update(running=False, fraction=1, result="@build_finished")
        game.built = True
        backend.refresh()
        spin()
        focus("build")
        screens.add("built")
        focus("online_setup", activate=True)
        check(nav.section() == "online", "Built page did not reach online setup")
        focus("host", activate=True)
        check(game.online["role"] == "host", "Host was not selected")
        screens.add("host")
        focus("join", activate=True)
        check(game.online["role"] == "join", "Join was not selected")
        screens.add("join")
        focus("online_address", activate=True)
        check(nav.overlay == "osk", "Address keyboard did not open")
        screens.add("address_keyboard")
        # A real pad edits and saves one character; no connection check is pressed.
        press("confirm")
        press("play")
        check(bool(game.address), "Controller keyboard did not save the address")
        focus("check")
        for name in ("firewall", "forward", "tailscale", "check"):
            focus("network:" + name)
        focus("collect_logs", activate=True)
        focus("direct:log_path")
        check("collect_logs" in game.calls, "Log screen did not reach the synthetic adapter")
        screens.add("logs")
        section("settings")
        screens.add("settings")
        press("social")
        check(nav.overlay == "drawer", "Quick access did not open")
        screens.add("drawer")
        for _ in i18n.LANGUAGES:
            languages.add(nav.language)
            press("right")
        check(languages == set(i18n.LANGUAGES), "Not every language rendered")
        press("down")
        press("confirm")
        press("confirm")
        press("down")
        press("confirm")
        press("confirm")
        press("back")
        press("back")
        check(nav.screen == "start", "Back did not return to the shelf")
        press("back")
        check(nav.overlay == "dialog" and nav.confirm_kind == "exit", "Quit dialog did not open")
        screens.add("quit_dialog")
        check(not forbidden, "A build, game or connection was requested")
        press("right")
        press("confirm")

    def on_exception(kind, value, tb):
        failures.append("".join(traceback.format_exception(kind, value, tb)))
        QGuiApplication.exit(1)

    def qt_message(kind, context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if ".qml" in message or "qml" in str(getattr(context, "category", "")).lower():
                qml_warnings.append(message)

    real_engine, real_make_engine = app.QQmlApplicationEngine, app.make_engine

    def create_engine():
        engine = real_engine()
        engine.warnings.connect(lambda warnings: qml_warnings.extend(w.toString() for w in warnings))
        return engine

    def start_scene(backend, full):
        engine = real_make_engine(backend, full)
        check(engine.rootObjects(), "make_engine did not load the real QML")
        check(isinstance(backend.window, QWindow), "The scene root is not a window")
        check(backend.window.isVisible(), "The launcher window was never shown")
        check(not backend.window.property("wantFull"), "--windowed was not applied")

        def walk():
            try:
                drive(backend)
            except BaseException:
                on_exception(*sys.exc_info())

        QTimer.singleShot(0, walk)
        QTimer.singleShot(45000, lambda: on_exception(AssertionError, AssertionError("Smoke test watchdog"), None))
        return engine

    old_hook, sys.excepthook = sys.excepthook, on_exception
    old_handler = qInstallMessageHandler(qt_message)
    try:
        with ExitStack() as patches:
            patches.enter_context(mock.patch.object(app.adapters, "make", side_effect=make_adapter))
            patches.enter_context(mock.patch.object(app, "XInputReader", return_value=reader))
            patches.enter_context(mock.patch.object(app, "WinMMPlayStationReader", return_value=Reader()))
            patches.enter_context(mock.patch.object(app, "PlayStationReader", side_effect=prohibited))
            patches.enter_context(mock.patch.object(app, "QQmlApplicationEngine", side_effect=create_engine))
            patches.enter_context(mock.patch.object(app, "make_engine", side_effect=start_scene))
            patches.enter_context(mock.patch.object(app.Nav, "_picker_entries", return_value=[
                dict(kind="file", name="synthetic-choice.iso", path="synthetic-choice.iso")]))
            patches.enter_context(mock.patch.object(app.UpdateService, "check"))
            patches.enter_context(mock.patch.object(app.updater, "confirm_startup", return_value=False))
            patches.enter_context(mock.patch.object(app.updater, "update_result", return_value=None))
            patches.enter_context(mock.patch("socket.socket", side_effect=prohibited))
            patches.enter_context(mock.patch("subprocess.Popen", side_effect=prohibited))
            with mock.patch.object(sys, "argv", ["openrecomp", "--windowed"]):
                try:
                    runpy.run_module("openrecomp", run_name="__main__")
                except SystemExit as exit_result:
                    code = exit_result.code
                else:
                    raise AssertionError("The module entry did not return an exit status")
        check(code == 0, "main failed: " + "\n".join(failures))
        check(not failures, "\n".join(failures))
        check(not qml_warnings, "QML warnings: " + "\n".join(qml_warnings))
        check(not forbidden, "An external operation was requested")
        print(COMPLETE + json.dumps(dict(
            screens=sorted(screens), languages=sorted(languages), unreachable=[
                "Real install discovery/import and disc verification", "Tool installation and real builds",
                "Game launch and return from gameplay", "Connection checks, remote Host/Join and matches",
                "Real diagnostic archives and physical controller hardware"])))
    finally:
        qInstallMessageHandler(old_handler)
        sys.excepthook = old_hook


if __name__ == "__main__":
    if sys.argv[1:] == ["--offscreen-child"]:
        run_child()
    else:
        unittest.main()
