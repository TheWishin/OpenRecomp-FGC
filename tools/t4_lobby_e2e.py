r"""T4 lobby end to end on this PC: a local T4 lobby server and two real launchers, driven like a pad.

    python tools\t4_lobby_e2e.py --lobby <T4 lobby folder> --t4-root <built T4 install> --iso <your ISO>
                                 --out <scratch folder> [--stub <t4_stub_game.py>] [--real]

The server is the T4 port's own lobby (`<lobby>\run.py server`, 127.0.0.1 only, an in-memory database, free
ports). Each player is a separate process running the launcher's real `python -m openrecomp` offscreen: its own
OPENRECOMP_HOME, the T4 install's real adapter, Nav and QML, the vendored lobby client, NAT and relay code. The
players are driven only through pad presses (and keyboard text in the on-screen keyboard); the return chord is the
same action the launcher sends for View + Menu held two seconds.

Two players on one PC need three test-only allowances, all named here: each player gets its own TEMP (the
launcher's one-T4-per-PC reservation lives there), the "another T4 is already running" process check answers
"no" (the other player's game is a ps2EntryRunner.exe too), and the lobby client binds 127.0.0.1
(T5_NET_BIND). With --stub the game process is the T4 lobby's stand-in game instead of ps2EntryRunner.exe;
without it (--real) both players start the real T4 build: a heavy run, take the PC's heavy-run lock first.

Nothing leaves 127.0.0.1. Prints one JSON line per player and exits 0 when every step passed.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DONE = "T4_E2E_REPORT "
CHILD_TIMEOUT = 900


def free_port():
    while True:
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind(("127.0.0.1", 0))
        port = tcp.getsockname()[1]
        tcp.close()
        try:
            for extra in (0, 1):
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    udp.bind(("127.0.0.1", port + extra))
                finally:
                    udp.close()
            return port
        except OSError:
            continue


# ---------------------------------------------------------------------------------------------- parent
def parent(args):
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("--out must be a new or empty folder")
    out.mkdir(parents=True, exist_ok=True)
    lobby = Path(args.lobby).resolve()
    if not (lobby / "run.py").is_file() or not (lobby / "t4lobby" / "server").is_dir():
        raise SystemExit("--lobby must be the T4 lobby folder (run.py, t4lobby/server)")
    port = free_port()
    server_env = dict(os.environ, T5L_STATUS_PORT="0", T5L_LOG_LEVEL="INFO", T5L_PAIR_COOLDOWN="0",
                      T5L_MIN_MATCH_SECONDS="0", T5_NET_BIND="127.0.0.1", T5_PORTMAP="0")
    if args.relay:
        server_env["T5L_FORCE_RELAY"] = "1"
    flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    server_log = open(out / "server.log", "wb")
    # -B: the lobby folder is read only for this test.
    server = subprocess.Popen([sys.executable, "-I", "-B", str(lobby / "run.py"), "server", "--host", "127.0.0.1",
                               "--port", str(port), "--udp-port", str(port), "--udp-port2", str(port + 1),
                               "--db", ":memory:"], env=server_env, stdout=server_log, stderr=subprocess.STDOUT,
                              creationflags=flags)
    deadline = time.monotonic() + 15
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            break
        except OSError:
            if server.poll() is not None or time.monotonic() > deadline:
                raise SystemExit("the lobby server did not start; see " + str(out / "server.log"))
            time.sleep(0.2)
    children = []
    try:
        for who in ("Alice", "Bob"):
            home = out / who
            (home / "tmp").mkdir(parents=True)
            env = {key: value for key, value in os.environ.items() if not key.startswith(("TEKKEN4_", "QT_"))}
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic",
                       QML_DISABLE_DISK_CACHE="1", OPENRECOMP_HOME=str(home), OPENRECOMP_PAD_ALWAYS="1",
                       OPENRECOMP_T4_ROOT=str(Path(args.t4_root).resolve()),
                       OPENRECOMP_T4_SERVER="127.0.0.1:" + str(port),
                       TEMP=str(home / "tmp"), TMP=str(home / "tmp"),
                       T5_NET_BIND="127.0.0.1", T5_PORTMAP="0", PYTHONIOENCODING="utf-8")
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", who, "--out", str(out),
                       "--iso", str(Path(args.iso).resolve())]
            if args.stub:
                command += ["--stub", str(Path(args.stub).resolve())]
            if args.real:
                command.append("--real")
            log = open(out / (who + ".log"), "wb")
            children.append((who, subprocess.Popen(command, cwd=str(ROOT), env=env, stdout=log,
                                                   stderr=subprocess.STDOUT, creationflags=flags), log))
        reports = {}
        for who, proc, log in children:
            try:
                proc.wait(CHILD_TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            log.close()
            text = (out / (who + ".log")).read_text(encoding="utf-8", errors="replace")
            line = next((row for row in text.splitlines() if row.startswith(DONE)), None)
            reports[who] = json.loads(line[len(DONE):]) if line else dict(ok=False, exit=proc.returncode,
                                                                         tail=text.splitlines()[-25:])
    finally:
        for _who, proc, _log in children:
            if proc.poll() is None:
                proc.kill()
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()
    for who in ("Alice", "Bob"):
        print(who, json.dumps(reports[who], ensure_ascii=False))
    ok = all(report.get("ok") for report in reports.values())
    print("PASS" if ok else "FAIL", "-- logs in", out)
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------- child
def child(args):
    from contextlib import ExitStack
    import runpy
    import traceback
    from unittest import mock

    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QEventLoop, QTimer, Qt
    from PySide6.QtGui import QGuiApplication
    from openrecomp import app, manifest as mf
    from openrecomp.adapters import t4_source
    from openrecomp.pad import SOURCES

    who, other = args.child, "Bob" if args.child == "Alice" else "Alice"
    out = Path(args.out)
    steps, failures = [], []
    report = dict(player=who, steps=steps, ok=False)

    class Reader:
        kind = "xbox"
        held = set()

        def read(self):
            return set(self.held)

    reader = Reader()
    buttons = {action: name for name, action in SOURCES}

    def mark(name):
        (out / (who + "." + name)).write_text(str(time.time()), encoding="utf-8")

    def spin(ms=20):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def drive(backend):
        nav = backend.nav
        game = next(g for g in nav.games if g.id == "t4")
        adapter = game.a
        started = time.monotonic()

        def step(label, **facts):
            steps.append(dict(step=label, t=round(time.monotonic() - started, 1), **facts))
            print("STEP", who, label, json.dumps(facts, ensure_ascii=False), flush=True)

        def state():
            return adapter.online_state()

        def press(action):
            reader.held = {buttons[action]}
            backend._tick()
            reader.held = set()
            backend._tick()
            spin()

        seen = [None]

        def transitions():
            current = state()
            now = (current.get("phase"), current.get("message"))
            if now != seen[0]:
                seen[0] = now
                print("PHASE", who, round(time.monotonic() - started, 2), now[0], now[1],
                      "busy" if adapter._online_busy else "", flush=True)

        def wait(condition, seconds, what):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                backend._tick()
                spin(40)
                transitions()
                value = condition()
                if value:
                    return value
            current = state()
            raise AssertionError("timed out waiting for %s (phase %s, message %s)"
                                 % (what, current.get("phase"), current.get("message")))

        def wait_other(name, seconds=120):
            wait(lambda: (out / (other + "." + name)).is_file(), seconds, other + " " + name)

        def ids():
            return [item.get("id") for item in nav.items()]

        def focus(match, activate=False, seconds=10):
            """Move the focus with the d-pad to the first row whose id matches; never jump to it directly."""
            test = match if callable(match) else (lambda iid: iid == match)
            deadline = time.monotonic() + seconds
            while True:
                items = nav.items()
                if any(test(item.get("id") or "") for item in items):
                    break
                if time.monotonic() > deadline:
                    raise AssertionError("no row %s; rows %s" % (match, ids()))
                backend._tick()
                spin(40)
            for direction in ("up", "down"):
                for _ in range(len(nav.items()) + 2):
                    items = nav.items()
                    if test(items[nav.focus_index(items)].get("id") or ""):
                        if activate:
                            press("confirm")
                        return items[nav.focus_index(items)].get("id")
                    press(direction)
            raise AssertionError("the pad could not reach " + str(match))

        def type_into(field, text):
            focus(field, activate=True)
            if nav.overlay != "osk":
                raise AssertionError("the on-screen keyboard did not open for " + field)
            for _ in range(64):
                backend.keyDown(int(Qt.Key.Key_Backspace), "", False)
            for char in text:
                backend.keyDown(int(Qt.Key.Key_A), char, False)
            press("play")
            if nav.overlay == "osk" or adapter.text_value(field) != text:
                raise AssertionError("the keyboard did not save " + field)

        def phase_is(*phases):
            return lambda: state().get("phase") in phases

        def chat_has(text):
            return lambda: any(line.get("text") == text for line in state().get("chat") or [])

        def player_row(name):
            players = {p["id"]: p["name"] for p in state().get("players") or []}
            return lambda iid: iid.startswith("challenge:") and players.get(iid.split(":", 1)[1]) == name

        def play_match(result_action):
            before = dict(phase=state().get("phase"), busy=adapter._online_busy)
            focus("start_match", activate=True)
            step("ready", message=state().get("message"), before=before, after=state().get("phase"),
                 busy=adapter._online_busy)
            wait(phase_is("playing"), 120, "the game start")
            run = getattr(adapter, "_online_owned_run", None)
            step("game_started", path=getattr(adapter._online_ticket, "path", ""),
                 role=getattr(adapter._online_ticket, "role", ""), pid=getattr(getattr(run, "proc", None), "pid", 0))
            if args.real:
                wait(lambda: getattr(adapter, "_online_playing_sent", False), 240, "the games playing (NETSUMMARY)")
                step("games_connected_and_playing", evidence=dict(adapter._online_evidence))
                mark("playing")
                wait_other("playing", 240)
                time.sleep(3)
                nav.act("returnGame", device="xbox")     # what View + Menu held for two seconds sends
                step("return_chord")
            wait(phase_is("result"), 180, "the result prompt")
            step("result_prompt", message=state().get("message"), evidence=dict(adapter._online_evidence))
            focus(result_action, activate=True)
            wait(phase_is("result_sent"), 60, "the result reply")
            wait(lambda: state().get("message") != "@online.result_sent", 30, "the lobby's verdict")
            step("result", message=state().get("message"))
            focus("return_lobby", activate=True)
            wait(phase_is("logged_in"), 20, "the lobby")
            step("back_in_lobby")

        # Shelf -> T4 -> Online, by pad.
        backend._tick()
        spin()
        for _ in nav.tile_ids():
            if nav.tile_ids()[nav.start_focus] == "t4":
                break
            press("right")
        press("confirm")
        if nav.screen != "hub" or nav.game.id != "t4":
            raise AssertionError("the T4 page did not open")
        for _ in nav.sections():
            if nav.section() == "online":
                break
            press("next")
        if nav.section() != "online":
            raise AssertionError("the pad could not reach Online")
        rows = ids()
        if "login_guest" not in rows or "host" in rows or "mode_direct" not in rows:
            raise AssertionError("the T4 lobby screen is not shown: " + str(rows))
        step("lobby_screen", server=adapter.text_value("online_server"), message=state().get("message"))
        type_into("online_name", who)
        focus("login_guest", activate=True)
        wait(phase_is("logged_in"), 30, "the login")
        step("logged_in", name=state().get("name"))
        mark("login")
        wait_other("login")
        for _ in range(40):
            focus("refresh_players", activate=True)
            try:
                wait(lambda: any(player_row(other)(iid or "") for iid in ids()), 3, other + " in the list")
                break
            except AssertionError:
                continue
        step("player_list", players=[p["name"] for p in state().get("players") or []])
        mark("players")
        wait_other("players")

        # Lobby chat both ways.
        line = "hi from " + who
        if who == "Alice":
            type_into("online_chat", line)
            focus("send_chat", activate=True)
            wait(chat_has("hi from Bob"), 30, "Bob's chat line")
        else:
            wait(chat_has("hi from Alice"), 30, "Alice's chat line")
            type_into("online_chat", line)
            focus("send_chat", activate=True)
        step("chat", lines=[(c.get("name"), c.get("text")) for c in state().get("chat") or []])
        mark("chat")
        wait_other("chat")

        if not args.real:
            # A challenge Bob declines, then one Alice accepts (Bob challenges).
            if who == "Alice":
                focus(player_row("Bob"), activate=True)
                step("challenge_sent")
                wait_other("declined", 60)
                wait(lambda: not state().get("challenge"), 10, "the declined challenge to close")
                step("challenge_declined_seen", message=state().get("message"), phase=state().get("phase"))
            else:
                wait(lambda: "decline_challenge" in ids(), 60, "Alice's challenge")
                step("challenge_received", challenger=state().get("challenge", {}).get("name"))
                focus("decline_challenge", activate=True)
                wait(lambda: not state().get("challenge"), 10, "the challenge to close")
                mark("declined")
                step("challenge_declined")
            mark("after_decline")
            wait_other("after_decline")

        # Quick match.
        focus("search_casual", activate=True)
        step("searching", message=state().get("message"))
        wait(phase_is("matched"), 60, "a quick match")
        step("matched", opponent=state().get("match", {}).get("opponent"))
        play_match("result_win" if who == "Alice" else "result_loss")
        mark("quick_done")
        wait_other("quick_done", 300)

        if not args.real:
            if who == "Bob":
                focus(player_row("Alice"), activate=True)
                step("challenge_sent")
            else:
                wait(lambda: "accept_challenge" in ids(), 60, "Bob's challenge")
                step("challenge_received", challenger=state().get("challenge", {}).get("name"))
                focus("accept_challenge", activate=True)
            wait(phase_is("matched"), 60, "the accepted challenge")
            step("matched", opponent=state().get("match", {}).get("opponent"))
            play_match("result_loss" if who == "Alice" else "result_win")
            mark("challenge_done")
            wait_other("challenge_done", 300)

        focus("logout", activate=True)
        wait(phase_is("offline"), 15, "the logout")
        step("logged_out")
        report["ok"] = True

    def finish(ok):
        QGuiApplication.exit(0 if ok else 1)

    real_make_engine = app.make_engine

    def start_scene(backend, full):
        engine = real_make_engine(backend, full)

        def walk():
            try:
                drive(backend)
                finish(True)
            except BaseException:
                failures.append(traceback.format_exc())
                finish(False)
        QTimer.singleShot(0, walk)
        return engine

    def only_t4(*a, **k):
        manifests, problems = real_load_all(*a, **k)
        return [m for m in manifests if m.get("adapter") == "t4"], problems

    real_load_all = mf.load_all
    real_popen = t4_source.subprocess.Popen

    def stub_popen(command, *a, **k):
        # The T4 lobby's stand-in game, started exactly where the launcher starts ps2EntryRunner.exe.
        if isinstance(command, (list, tuple)) and str(command[0]).lower().endswith("ps2entryrunner.exe"):
            command = [sys.executable, "-I", "-B", args.stub]
        return real_popen(command, *a, **k)

    # Settings a player has after picking their ISO in the launcher (the source core keeps them per launcher home).
    root = os.environ["OPENRECOMP_T4_ROOT"]
    core = t4_source.SourceCore(root)
    settings = core.load_settings()
    settings.update(iso=args.iso, sound=False)
    core.save_settings(settings)
    code = 1
    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(app, "XInputReader", return_value=reader))
        patches.enter_context(mock.patch.object(app, "WinMMPlayStationReader", return_value=Reader()))
        patches.enter_context(mock.patch.object(app, "PlayStationReader", return_value=Reader()))
        patches.enter_context(mock.patch.object(app, "make_engine", side_effect=start_scene))
        patches.enter_context(mock.patch.object(app.mf, "load_all", side_effect=only_t4))
        patches.enter_context(mock.patch.object(app.UpdateService, "check"))
        patches.enter_context(mock.patch.object(app.updater, "confirm_startup", return_value=False))
        patches.enter_context(mock.patch.object(app.updater, "update_result", return_value=None))
        # One PC, two players: the other player's game is not "another T4 already running".
        patches.enter_context(mock.patch("openrecomp.adapters.t4.game_process_running", return_value=False))
        patches.enter_context(mock.patch("openrecomp.adapters.t4_online.game_process_running", return_value=False))
        if args.stub:
            patches.enter_context(mock.patch.object(t4_source.subprocess, "Popen", side_effect=stub_popen))
        with mock.patch.object(sys, "argv", ["openrecomp", "--windowed"]):
            try:
                runpy.run_module("openrecomp", run_name="__main__")
            except SystemExit as exit_result:
                code = exit_result.code
    report["exit"] = code
    report["ok"] = bool(report["ok"] and code == 0 and not failures)
    if failures:
        report["error"] = failures[-1].strip().splitlines()[-3:]
        print(failures[-1], flush=True)
    print(DONE + json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lobby")
    parser.add_argument("--t4-root")
    parser.add_argument("--iso", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--stub")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--relay", action="store_true", help="the server relays every match (T5L_FORCE_RELAY)")
    parser.add_argument("--child")
    args = parser.parse_args()
    if args.child:
        return child(args)
    if bool(args.stub) == bool(args.real) or not args.lobby or not args.t4_root:
        parser.error("give --lobby, --t4-root and exactly one of --stub / --real")
    return parent(args)


if __name__ == "__main__":
    sys.exit(main())
