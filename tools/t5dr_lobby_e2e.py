r"""T5DR lobby end to end on this PC: a local T5DR lobby server and two real launchers with the REAL game.

    python tools\t5dr_lobby_e2e.py --build --root <T5DR folder> --pkg <.pkg> --rap <.rap> --out <scratch folder>
                                   [--keys <ps3.keys>]
    python tools\t5dr_lobby_e2e.py --lobby <T5DR lobby folder> --root-a <built T5DR folder> --root-b <another copy>
                                   --out <scratch folder> [--match-seconds S]

--build: the launcher builds a T5DR folder the T5DR launcher set up (no OpenRecomp marker) through the real Build page
(notice, Yes, the whole build with the folder's own Python) and checks that the T5DR launcher's files are untouched and the
game then counts as built. Do this once, then copy the built folder for the second player.

The server is the T5DR lobby (`<lobby>\run.py server`, 127.0.0.1 only, a database file in --out, free ports). Each
player is a separate process running the launcher's real `python -m openrecomp` offscreen: its own OPENRECOMP_HOME,
its own copy of the built T5DR folder (two games never share a folder), the real T5DR adapter, Nav, QML and the
installed lobby client, NAT and match driver. Alice registers an account, Bob logs in as a guest. The players are
driven only through pad presses. Steps (each one is a line "STEP"): both log in, Alice challenges Bob, Bob accepts,
both press Start, the games start, each game plays a scripted mash to the end of the match, both launchers show the
game's own result and the lobby confirms it, both press Rematch, the second match starts, then both leave to the
lobby and log out. Pictures of the launcher at each step go to --out/shots (never commit them).

Test-only allowances, all named here: each player has its own TEMP (the launcher's one-game-per-PC reservation lives
there), the "another T5DR game is running" process check answers "no" (the other player's game is a t5dr.exe too), the
lobby client binds 127.0.0.1 (T5_NET_BIND), games are muted and run in the background (PS3_AUDIO_MUTE,
PS3_WINDOW_BACKGROUND) at below-normal priority, and each match gets a mash script as its pad input (T5_NET_SCRIPT).
This is a HEAVY run (two games): take two of the PC's heavy-run locks first.

Nothing leaves 127.0.0.1. Prints one JSON line per player and exits 0 when every step passed.
"""
import argparse
import json
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DONE = "T5_E2E_REPORT "
CHILD_TIMEOUT = 3600


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


def wait_listening(port, proc, log):
    deadline = time.monotonic() + 30
    while True:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return
        except OSError:
            if proc.poll() is not None or time.monotonic() > deadline:
                raise SystemExit("the lobby server did not start; see " + str(log))
            time.sleep(0.2)


def mash_script(path, seed, frames=200000, gap=12):
    """Face buttons and directions for a game's pad (the same masks as T5DR's own fight_flow_test, no START)."""
    rnd = random.Random(seed)
    buttons = [0x4000, 0x2000, 0x8000, 0x1000, 0x4000 | 0x2000, 0x8000 | 0x1000, 0x10, 0x20, 0x40, 0x80, 0x20, 0x80]
    out, frame = [], 30
    while frame < frames:
        n = rnd.randint(1, 4)
        out.append("%d %d %#x" % (frame, n, rnd.choice(buttons)))
        frame += n + rnd.randint(1, gap)
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------------------------- parent
def parent(args):
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("--out must be a new or empty folder")
    (out / "shots").mkdir(parents=True, exist_ok=True)
    lobby = Path(args.lobby).resolve()
    if not (lobby / "run.py").is_file() or not (lobby / "t5lobby" / "server").is_dir():
        raise SystemExit("--lobby must be the T5DR lobby folder (run.py, t5lobby/server)")
    roots = {"Alice": Path(args.root_a).resolve(), "Bob": Path(args.root_b).resolve()}
    if roots["Alice"] == roots["Bob"]:
        raise SystemExit("two players need two copies of the T5DR folder")
    port = free_port()
    server_env = dict(os.environ, T5L_STATUS_PORT="0", T5L_LOG_LEVEL="INFO", T5L_PAIR_COOLDOWN="0",
                      T5L_MIN_MATCH_SECONDS="0", T5L_RANKED_SAME_IP="1", T5_NET_BIND="127.0.0.1", T5_PORTMAP="0",
                      T5L_SCRYPT_N=str(1 << 12), PYTHONDONTWRITEBYTECODE="1")
    if args.relay:
        server_env["T5L_FORCE_RELAY"] = "1"
    flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    log_server = open(out / "server.log", "wb")
    server = subprocess.Popen([sys.executable, "-I", "-B", str(lobby / "run.py"), "server", "--host", "127.0.0.1",
                               "--port", str(port), "--udp-port", str(port), "--udp-port2", str(port + 1),
                               "--db", str(out / "lobby.db")], env=server_env, stdout=log_server,
                              stderr=subprocess.STDOUT, creationflags=flags)
    children = []
    try:
        wait_listening(port, server, out / "server.log")
        for who in ("Alice", "Bob"):
            home = out / who
            (home / "tmp").mkdir(parents=True)
            env = {key: value for key, value in os.environ.items() if not key.startswith(("T5_", "PS3_", "QT_", "OPENRECOMP_"))}
            env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic",
                       QML_DISABLE_DISK_CACHE="1", OPENRECOMP_HOME=str(home), OPENRECOMP_PAD_ALWAYS="1",
                       OPENRECOMP_T5DR_ROOT=str(roots[who]), OPENRECOMP_T5_SERVER="127.0.0.1:" + str(port),
                       OPENRECOMP_NO_GAME_CHECKS="1", OPENRECOMP_UI_SOUND="0", OPENRECOMP_NATIVE_PICKER="0",
                       TEMP=str(home / "tmp"), TMP=str(home / "tmp"), T5_NET_BIND="127.0.0.1", T5_PORTMAP="0",
                       PS3_AUDIO_MUTE="1", PS3_WINDOW_BACKGROUND="1", PYTHONIOENCODING="utf-8",
                       PYTHONDONTWRITEBYTECODE="1")
            command = [sys.executable, "-B", str(Path(__file__).resolve()), "--child", who, "--out", str(out),
                       "--match-seconds", str(args.match_seconds)]
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
        log_server.close()
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
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QGuiApplication
    from openrecomp import app, manifest as mf
    from openrecomp.pad import SOURCES

    who, other = args.child, "Bob" if args.child == "Alice" else "Alice"
    out = Path(args.out)
    steps, failures = [], []
    report = dict(player=who, steps=steps, ok=False)
    engines = []

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
        game = next(g for g in nav.games if g.id == "t5dr")
        adapter = game.a
        started = time.monotonic()
        shot_no = [0]

        def step(label, **facts):
            steps.append(dict(step=label, t=round(time.monotonic() - started, 1), **facts))
            print("STEP", who, label, json.dumps(facts, ensure_ascii=False, default=str), flush=True)

        def shot(name):
            """The launcher window as it looks now (kept in --out/shots; never committed)."""
            try:
                shot_no[0] += 1
                for engine in engines:
                    for window in engine.rootObjects():
                        window.grabWindow().save(str(out / "shots" / ("%s-%02d-%s.png" % (who, shot_no[0], name))))
                        return
            except Exception as error:  # noqa: BLE001 -- a missing picture never fails the run
                print("SHOT failed", name, error, flush=True)

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

        def wait_other(name, seconds=300):
            wait(lambda: (out / (other + "." + name)).is_file(), seconds, other + " " + name)

        def ids():
            return [item.get("id") for item in nav.items()]

        def focus(match, activate=False, seconds=20):
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

        def phase_is(*phases):
            return lambda: state().get("phase") in phases

        def player_row(name):
            players = {p["id"]: p["name"] for p in state().get("players") or []}
            return lambda iid: iid.startswith("challenge:") and players.get(iid.split(":", 1)[1]) == name

        def play_to_the_end(label):
            focus("start_match", activate=True)
            step(label + "_ready", message=state().get("message"), phase=state().get("phase"))
            wait(phase_is("starting", "playing", "result", "result_sent"), 180, "the start of the game")
            shot(label + "-starting")
            wait(phase_is("playing", "result", "result_sent"), 300, "the game start")
            run = getattr(adapter, "_online_owned_run", None) or adapter.game
            step(label + "_game_started", pid=getattr(getattr(run, "proc", None), "pid", 0))
            wait(lambda: getattr(adapter, "_online_playing_sent", False), 300, "the games connected and playing")
            step(label + "_playing", evidence=dict(getattr(adapter, "_online_evidence", {}) or {}))
            shot(label + "-playing")
            mark(label + "_playing")
            wait_other(label + "_playing", 300)
            # The game plays its scripted mash to the end of the match and writes its own result.
            wait(phase_is("result_sent", "result"), args.match_seconds, "the game's own result")
            shot(label + "-result")
            wait(lambda: state().get("message") not in ("@online.result_sent",), 90, "the lobby's verdict")
            step(label + "_result", message=state().get("message"), phase=state().get("phase"))
            if state().get("message") != "@online.result_confirmed":
                raise AssertionError("the lobby did not confirm the game's result: %s" % state().get("message"))
            mark(label + "_result")
            wait_other(label + "_result", 120)

        # Shelf -> T5DR -> Online, by pad.
        backend._tick()
        spin()
        for _ in nav.tile_ids():
            if nav.tile_ids()[nav.start_focus] == "t5dr":
                break
            press("right")
        press("confirm")
        if nav.screen != "hub" or nav.game.id != "t5dr":
            raise AssertionError("the T5DR page did not open")
        # The folder is the T5DR launcher's own: no OpenRecomp marker, so OpenRecomp attaches (coexistence).
        step("folder", root=adapter.root, managed=bool(getattr(adapter, "managed", None)),
             ready=bool(adapter.ready()), coexistence=adapter.coexistence_state())
        for _ in nav.sections():
            if nav.section() == "online":
                break
            press("next")
        if nav.section() != "online":
            raise AssertionError("the pad could not reach Online")
        step("lobby_screen", server=adapter.text_value("online_server").split("#")[0],
             message=state().get("message"), rows=ids()[:12])
        shot("lobby-screen")
        if who == "Alice":
            adapter.set_text_value("online_name", "Alice")
            adapter.set_text_value("online_password", "e2e-" + "%08x" % random.getrandbits(32))
            focus("login_register", activate=True)
            wait(phase_is("logged_in", "registration"), 30, "the registration")
            if state().get("recovery_codes"):
                focus("acknowledge_recovery", activate=True)
        else:
            adapter.set_text_value("online_name", "Bob")
            focus("login_guest", activate=True)
        wait(phase_is("logged_in"), 30, "the login")
        step("logged_in", name=state().get("name"), account=bool(state().get("account")))
        shot("logged-in")
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

        # Alice challenges Bob; Bob accepts.
        if who == "Alice":
            focus(player_row("Bob"), activate=True)
            step("challenge_sent")
            shot("challenge-sent")
        else:
            wait(lambda: "accept_challenge" in ids(), 60, "Alice's challenge")
            step("challenge_received", challenger=state().get("challenge", {}).get("name"))
            shot("challenge-received")
            focus("accept_challenge", activate=True)
        wait(phase_is("matched"), 60, "the accepted challenge")
        step("matched", opponent=state().get("match", {}).get("opponent"))
        shot("matched")
        play_to_the_end("match1")

        # Rematch: both press it; the second match starts in the same game.
        wait(lambda: (state().get("capabilities") or {}).get("rematch"), 30, "the rematch offer")
        shot("rematch-offered")
        focus("rematch", activate=True)
        step("rematch_pressed")
        wait(phase_is("matched", "starting", "playing"), 180, "the rematch")
        if state().get("phase") == "matched":
            focus("start_match", activate=True)
        wait(phase_is("playing"), 300, "the rematch game")
        step("rematch_playing", message=state().get("message"))
        shot("rematch-playing")
        mark("rematch_playing")
        wait_other("rematch_playing", 300)
        # Leave: the rematch plays to the end if it can within --match-seconds, else it is left.
        try:
            wait(phase_is("result_sent", "result"), args.match_seconds, "the rematch result")
            wait(lambda: state().get("message") not in ("@online.result_sent",), 90, "the lobby's verdict")
            step("rematch_result", message=state().get("message"))
        except AssertionError as error:
            step("rematch_left_unfinished", why=str(error))
            focus("stop_match", activate=True)
        mark("rematch_done")
        wait_other("rematch_done", 600)
        focus("return_lobby", activate=True)
        wait(phase_is("logged_in"), 60, "the lobby")
        step("back_in_lobby")
        shot("back-in-lobby")
        focus("logout", activate=True)
        wait(phase_is("offline"), 15, "the logout")
        step("logged_out")
        report["ok"] = True

    def finish(ok):
        QGuiApplication.exit(0 if ok else 1)

    real_make_engine = app.make_engine

    def start_scene(backend, full):
        engine = real_make_engine(backend, full)
        engines.append(engine)

        def walk():
            try:
                drive(backend)
                finish(True)
            except BaseException:
                failures.append(traceback.format_exc())
                finish(False)
        QTimer.singleShot(0, walk)
        return engine

    real_load_all = mf.load_all

    def only_t5dr(*a, **k):
        manifests, problems = real_load_all(*a, **k)
        return [m for m in manifests if m.get("adapter") == "t5dr"], problems

    code = 1
    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(app, "XInputReader", return_value=reader))
        patches.enter_context(mock.patch.object(app, "WinMMPlayStationReader", return_value=Reader()))
        patches.enter_context(mock.patch.object(app, "PlayStationReader", return_value=Reader()))
        patches.enter_context(mock.patch.object(app, "make_engine", side_effect=start_scene))
        patches.enter_context(mock.patch.object(app.mf, "load_all", side_effect=only_t5dr))
        patches.enter_context(mock.patch.object(app.UpdateService, "check"))
        patches.enter_context(mock.patch.object(app.updater, "confirm_startup", return_value=False))
        patches.enter_context(mock.patch.object(app.updater, "update_result", return_value=None))
        # One PC, two players: the other player's game is not "another T5DR already running".
        patches.enter_context(mock.patch("openrecomp.adapters.t5dr.game_process_running", return_value=False))
        patches.enter_context(mock.patch("openrecomp.adapters.t5_online.game_process_running", return_value=False))
        # Every match its own presses: the match driver hands the game its environment; add the mash script.
        from openrecomp.adapters import t5dr as t5dr_adapter
        original_start = t5dr_adapter.T5DR.start

        def start(self, extra_env=None):
            env = dict(extra_env or {})
            if "T5_NET_SCRIPT" not in env and env.get("T5_NET_MODE", "").lower() in ("host", "join"):
                seed = 1000 + sum(map(ord, who)) + sum(map(ord, str(env.get("T5_NET_MATCH", ""))))
                env["T5_NET_SCRIPT"] = mash_script(out / (who + "-mash-%s.txt" % env.get("T5_NET_MATCH", "x")), seed)
            return original_start(self, extra_env=env)

        patches.enter_context(mock.patch.object(t5dr_adapter.T5DR, "start", start))
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
    print(DONE + json.dumps(report, ensure_ascii=False, default=str), flush=True)
    return 0 if report["ok"] else 1


def build_child(args):
    """The Build page on a folder T5DR's launcher set up: notice, Yes, the full build, then the T5DR files are checked."""
    from contextlib import ExitStack
    import hashlib
    import runpy
    import traceback
    from unittest import mock

    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QGuiApplication
    from openrecomp import app, manifest as mf
    from openrecomp.pad import SOURCES

    root = Path(args.root).resolve()
    steps, failures = [], []
    report = dict(player="builder", steps=steps, ok=False)

    class Reader:
        kind = "xbox"
        held = set()

        def read(self):
            return set(self.held)

    reader = Reader()
    buttons = {action: name for name, action in SOURCES}

    def spin(ms=20):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def files():
        names = ["launcher.json", "release.json", "T5DR Online.exe", "launcher/core.py", "python/python.exe",
                 "tools/build_game.py", "openrecomp-release.json"]
        return {n: (hashlib.sha256((root / n).read_bytes()).hexdigest() if (root / n).is_file() else None) for n in names}

    def drive(backend):
        nav = backend.nav
        adapter = next(g for g in nav.games if g.id == "t5dr").a
        started = time.monotonic()

        def step(label, **facts):
            steps.append(dict(step=label, t=round(time.monotonic() - started, 1), **facts))
            print("STEP", label, json.dumps(facts, ensure_ascii=False, default=str), flush=True)

        def press(action):
            reader.held = {buttons[action]}
            backend._tick()
            reader.held = set()
            backend._tick()
            spin()

        def wait(condition, seconds, what):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                backend._tick()
                spin(50)
                value = condition()
                if value:
                    return value
            raise AssertionError("timed out waiting for " + what)

        before = files()
        backend._tick()
        spin()
        for _ in nav.tile_ids():
            if nav.tile_ids()[nav.start_focus] == "t5dr":
                break
            press("right")
        press("confirm")
        for _ in nav.sections():
            if nav.section() == "build":
                break
            press("next")
        if nav.section() != "build":
            raise AssertionError("the pad could not reach Build")
        step("folder", root=str(root), managed=bool(adapter.managed), coexistence=adapter.coexistence_state(),
             notice_pending=adapter.foreign_notice_pending(), ready=bool(adapter.ready()))
        if adapter.managed or not adapter.foreign_notice_pending():
            raise AssertionError("this folder is not one the T5DR launcher set up")
        adapter.set_source("pkg", args.pkg)
        adapter.set_source("rap", args.rap)
        wait(lambda: not adapter.source_state().get("running"), 120, "the package check")
        problem = adapter.build_ready()
        step("build_ready", problem=problem)
        if problem:
            raise AssertionError("Build is blocked: " + str(problem))

        def focus_build():
            for direction in ("up", "down"):
                for _ in range(len(nav.items()) + 2):
                    items = nav.items()
                    if (items[nav.focus_index(items)].get("id") or "") == "build":
                        return
                    press(direction)
            raise AssertionError("the pad could not reach Build")

        focus_build()
        press("confirm")
        if (nav.overlay, nav.confirm_kind) != ("dialog", "t5_folder"):
            raise AssertionError("the one-time notice did not come: %s %s" % (nav.overlay, nav.confirm_kind))
        from openrecomp import i18n
        step("notice", text=i18n.localize(nav.view()["dialog"]["text"], "en"))
        if nav.exit_focus != 1:
            press("right")
        press("confirm")
        wait(lambda: adapter.build is not None or adapter.build_state().get("result"), 60, "the build to start")
        step("build_started", lock=(root / "openrecomp-build.lock").is_file(),
             cmd0=(adapter.build.cmd[0] if adapter.build else ""))
        last = [None]

        def finished():
            state = adapter.build_state()
            label = (state.get("title"), round(state.get("fraction") or 0, 2))
            if label != last[0]:
                last[0] = label
                print("BUILD", round(time.monotonic() - started), label, flush=True)
            return not state["running"] and state.get("result")

        result = wait(finished, args.build_seconds, "the build to finish")
        step("build_result", result=str(result), lock_left=(root / "openrecomp-build.lock").is_file())
        after = files()
        changed = sorted(n for n in before if before[n] != after[n])
        step("t5dr_files", changed=changed)
        if result != "@build_finished":
            raise AssertionError("the build did not finish: %s" % (result,))
        if changed:
            raise AssertionError("the build changed files the T5DR launcher relies on: %s" % changed)
        state = adapter.state(fresh=True)
        step("game_state", built=state.get("built"), ok=state.get("ok"), text=str(state.get("text"))[:120])
        if not state.get("ok"):
            raise AssertionError("the game does not count as ready after the build")
        report["ok"] = True

    real_make_engine = app.make_engine

    def start_scene(backend, full):
        engine = real_make_engine(backend, full)

        def walk():
            try:
                drive(backend)
                QGuiApplication.exit(0)
            except BaseException:
                failures.append(traceback.format_exc())
                QGuiApplication.exit(1)
        QTimer.singleShot(0, walk)
        return engine

    real_load_all = mf.load_all

    def only_t5dr(*a, **k):
        manifests, problems = real_load_all(*a, **k)
        return [m for m in manifests if m.get("adapter") == "t5dr"], problems

    if args.keys:
        keys = root / "native" / "keys"
        keys.mkdir(parents=True, exist_ok=True)
        (keys / "ps3.keys").write_bytes(Path(args.keys).read_bytes())
    code = 1
    with ExitStack() as patches:
        patches.enter_context(mock.patch.object(app, "XInputReader", return_value=reader))
        patches.enter_context(mock.patch.object(app, "WinMMPlayStationReader", return_value=Reader()))
        patches.enter_context(mock.patch.object(app, "PlayStationReader", return_value=Reader()))
        patches.enter_context(mock.patch.object(app, "make_engine", side_effect=start_scene))
        patches.enter_context(mock.patch.object(app.mf, "load_all", side_effect=only_t5dr))
        patches.enter_context(mock.patch.object(app.UpdateService, "check"))
        patches.enter_context(mock.patch.object(app.updater, "confirm_startup", return_value=False))
        patches.enter_context(mock.patch.object(app.updater, "update_result", return_value=None))
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
    print(DONE + json.dumps(report, ensure_ascii=False, default=str), flush=True)
    return 0 if report["ok"] else 1


def build_parent(args):
    """Run build_child in its own process with its own OPENRECOMP_HOME under --out (never the owner's)."""
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("--out must be a new or empty folder")
    (out / "home" / "tmp").mkdir(parents=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith(("T5_", "PS3_", "QT_", "OPENRECOMP_"))}
    env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_QUICK_CONTROLS_STYLE="Basic",
               QML_DISABLE_DISK_CACHE="1", OPENRECOMP_HOME=str(out / "home"), OPENRECOMP_PAD_ALWAYS="1",
               OPENRECOMP_T5DR_ROOT=str(Path(args.root).resolve()), OPENRECOMP_NO_GAME_CHECKS="1",
               OPENRECOMP_UI_SOUND="0", OPENRECOMP_NATIVE_PICKER="0", TEMP=str(out / "home" / "tmp"),
               TMP=str(out / "home" / "tmp"), PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--build-child", "--root", args.root,
               "--pkg", args.pkg, "--rap", args.rap, "--out", str(out), "--build-seconds", str(args.build_seconds)]
    if args.keys:
        command += ["--keys", args.keys]
    with open(out / "build-child.log", "wb") as log:
        code = subprocess.run(command, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)).returncode
    text = (out / "build-child.log").read_text(encoding="utf-8", errors="replace")
    line = next((row for row in text.splitlines() if row.startswith(DONE)), None)
    print(line[len(DONE):] if line else json.dumps(dict(ok=False, exit=code, tail=text.splitlines()[-25:])))
    print("PASS" if code == 0 else "FAIL", "-- log", out / "build-child.log")
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lobby")
    parser.add_argument("--root-a")
    parser.add_argument("--root-b")
    parser.add_argument("--out", required=True)
    parser.add_argument("--match-seconds", type=int, default=900, help="how long a match may take to end")
    parser.add_argument("--relay", action="store_true", help="the server relays every match (T5L_FORCE_RELAY)")
    parser.add_argument("--child")
    parser.add_argument("--build", action="store_true", help="build the folder --root through the Build page first")
    parser.add_argument("--build-child", action="store_true")
    parser.add_argument("--root")
    parser.add_argument("--pkg")
    parser.add_argument("--rap")
    parser.add_argument("--keys", help="an offline ps3.keys copied into the folder's native/keys before the build")
    parser.add_argument("--build-seconds", type=int, default=2400)
    args = parser.parse_args()
    if args.build_child:
        return build_child(args)
    if args.build:
        if not (args.root and args.pkg and args.rap):
            parser.error("--build needs --root, --pkg and --rap")
        return build_parent(args)
    if args.child:
        return child(args)
    if not (args.lobby and args.root_a and args.root_b):
        parser.error("give --lobby, --root-a and --root-b")
    return parent(args)


if __name__ == "__main__":
    sys.exit(main())
