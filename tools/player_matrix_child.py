"""Private subprocess driver for player_matrix; never imports the development launcher.

The portable interpreter runs this file, then the packaged module entry point. Only
the release transport and safety boundaries are instrumented; adapters and QML are real.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import threading
import time


_JOB = None


def contain_process_tree():
    """A timeout killing this driver must also kill every descendant it started."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class Limits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
                    ("processes", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("limits", Limits), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not handle:
        raise OSError(ctypes.get_last_error(), "cannot create matrix process job")
    if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel.CloseHandle(handle)
        raise OSError(ctypes.get_last_error(), "cannot limit matrix process job")
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle)
        raise OSError(ctypes.get_last_error(), "cannot contain matrix descendants")
    global _JOB
    _JOB = handle  # Keep open until process exit; closing it kills this process too.


class BoundaryStop(RuntimeError):
    pass


def same_path(first, second):
    return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def local_address(address):
    if isinstance(address, (str, bytes)):
        return False
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except (ValueError, TypeError, IndexError):
        return False


def local_host(host):
    if host in ("localhost", b"localhost"):
        return True
    try:
        return ipaddress.ip_address(host.decode() if isinstance(host, bytes) else host).is_loopback
    except (ValueError, TypeError):
        return False


def seed_keys(inputs, root):
    """T5DR's first build step downloads the public key data from github.com. The offline gate hands the build the
    keys file the owner already has (config `t5dr_keys`, read only) at the place the step looks, inside the case."""
    source = inputs.get("t5dr_keys")
    if not source or not root:
        return False
    target = Path(root) / "native" / "keys" / "ps3.keys"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(source).read_bytes())
    return True


def event(path, kind, **values):
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(kind=kind, **values), ensure_ascii=False) + "\n")


def safety(events, *, full=False, worker=False, expected_python=None, extra_roots=()):
    """Fail closed for sockets and commands that can escape the offline test.

    Python build subprocesses enter this same driver so the socket guard follows
    them. Shell build pipelines cannot inherit a Python audit hook and are refused.
    """
    original_popen = subprocess.Popen
    compilers = {"cl", "clang", "clang++", "clang-cl", "gcc", "g++", "ninja", "cmake", "msbuild", "make"}
    network = {"git", "curl", "wget", "winget", "msiexec", "bitsadmin", "certutil"}
    shells = {"powershell", "pwsh", "cmd", "wscript", "cscript"}
    pending = threading.local()
    owned_pids = set()
    scratch = Path(events).resolve().parent
    roots = [scratch, *(Path(r).resolve() for r in extra_roots)]

    def writable(path):
        if isinstance(path, int):  # Already-open standard streams and anonymous pipes.
            return
        if os.fsdecode(path).casefold() in (os.devnull.casefold(), "nul", "/dev/null"):
            return  # subprocess.DEVNULL; the launcher's own probes use it
        try:
            target = Path(os.fsdecode(path)).resolve()
        except TypeError:
            raise PermissionError("player matrix refused a write outside its isolated case") from None
        if not any(target.is_relative_to(root) for root in roots):
            raise PermissionError("player matrix refused a write outside its isolated case")

    def audit(name, args):
        if name == "open":
            flags = args[2]
            if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                writable(args[0])
        elif name in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "shutil.rmtree"):
            writable(args[0])
        elif name in ("os.rename", "os.link", "os.symlink"):
            writable(args[0])
            writable(args[1])
        elif name in ("socket.connect", "socket.sendto"):
            address = args[1] if name == "socket.connect" else args[-1]
            if not local_address(address):
                event(events, "network_denied", address=str(address))
                raise PermissionError("player matrix permits loopback connections only")
        elif name in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"):
            if not local_host(args[0]):
                event(events, "network_denied", address=str(args[0]))
                raise PermissionError("player matrix refuses external DNS lookups")
        elif name in ("os.system", "os.exec", "os.spawn", "os.posix_spawn"):
            event(events, "unsafe_process", command=str(args))
            raise PermissionError("player matrix refuses process creation outside its guard")
        elif name == "subprocess.Popen":
            approved = getattr(pending, "command", None)
            # CPython converts an argv list to a native command string before
            # raising this audit event on Windows. Compare with that exact string.
            wanted = subprocess.list2cmdline(approved) if approved and os.name == "nt" else approved
            if approved is None or args[1] != wanted or args[0] not in (None, approved[0]):
                event(events, "unsafe_process", command=str(args[1]))
                raise PermissionError("player matrix refused an unaudited process")

    sys.addaudithook(audit)

    def popen(command, *args, **kwargs):
        if isinstance(command, (str, bytes)) or kwargs.get("shell"):
            event(events, "unsafe_process", command=str(command))
            raise PermissionError("player matrix refuses shell command strings")
        command = [os.fspath(part) for part in command]
        name = Path(command[0]).stem.casefold()
        event(events, "command", command=command)
        probe = len(command) == 2 and command[1].casefold() in ("--version", "-version", "/?")
        if name in network | shells and not probe:
            event(events, "unsafe_process", command=command)
            raise PermissionError("offline matrix cannot safely run an installer or shell pipeline")
        if worker and name in compilers and not probe:
            if full:
                event(events, "unsafe_process", command=command)
                raise PermissionError("full native compilation needs an offline process sandbox; Python audit cannot contain native network access")
            event(events, "compile_boundary", command=command)
            raise BoundaryStop("player matrix stopped before compilation")
        is_python = name.startswith("python")
        if is_python and not probe:
            # Crypto readiness probes are a fixed import and never start a build.
            crypto_probe = command[1:] == ["-I", "-c", "from Crypto.Cipher import AES"]
            if not crypto_probe:
                own = sys.executable if worker else expected_python() if expected_python else None
                if not own or not same_path(command[0], own):
                    event(events, "foreign_python", command=command)
                    raise PermissionError("build attempted a Python outside the game's own install")
                flags = []
                for part in command[1:]:
                    if part not in ("-B", "-u", "-I", "-E", "-s"):
                        break
                    flags.append(part)
                command = [command[0], *flags, "-B", str(Path(__file__).resolve()), "--build-worker", events,
                           *(["--full"] if full else []), "--", *command[1:]]
        if worker and not is_python and name not in compilers and not probe:
            event(events, "unsafe_process", command=command)
            raise PermissionError("offline matrix cannot audit this build subprocess")
        readonly = name in {"tasklist", "where", "vswhere"}
        stop = False
        if name == "taskkill" and "/PID" in command and "/T" in command:
            try:
                stop = int(command[command.index("/PID") + 1]) in owned_pids
            except (ValueError, IndexError):
                pass
        if not (is_python or readonly or stop or probe and name in compilers | network
                or worker and full and name in compilers):
            event(events, "unsafe_process", command=command)
            raise PermissionError("offline matrix cannot audit this subprocess")
        if kwargs.get("executable") is not None and not same_path(kwargs["executable"], command[0]):
            raise PermissionError("player matrix refuses an executable override")
        if os.name == "nt":
            kwargs["creationflags"] = kwargs.get("creationflags", 0) | 0x08000000 | 0x00004000
        pending.command = command
        try:
            process = original_popen(command, *args, **kwargs)
            owned_pids.add(process.pid)
            return process
        finally:
            pending.command = None

    subprocess.Popen = popen
    return original_popen


def build_worker(events, argv, full):
    safety(events, full=full, worker=True)
    argv = list(argv)
    while argv and argv[0] in ("-B", "-u", "-I", "-E", "-s"):
        argv.pop(0)
    try:
        if not argv:
            raise ValueError("Python build command has no program")
        if argv[0] == "-c":
            sys.argv = ["-c", *argv[2:]]
            exec(compile(argv[1], "<player-matrix-python-command>", "exec"), {"__name__": "__main__"})
        elif argv[0] == "-m":
            sys.argv = argv[1:]
            runpy.run_module(argv[1], run_name="__main__", alter_sys=True)
        else:
            script = str(Path(argv[0]).resolve())
            sys.path.insert(0, str(Path(script).parent))
            sys.argv = [script, *argv[1:]]
            runpy.run_path(script, run_name="__main__")
    except BoundaryStop:
        return 86
    return 0


def read_events(path):
    try:
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    except FileNotFoundError:
        return []


def run_case(request):
    launcher = Path(request["launcher"]).resolve()
    home = Path(request["home"]).resolve()
    events = str(home / "safety.jsonl")
    case = request["case"]
    inputs = request.get("inputs", {})
    gid = case.get("game", "t5dr")
    evidence = dict(packaged_python=sys.executable, imported_launcher="", root="", build_python="",
                    commands=[], first_steps=[], build_started=False, repair_message="", guidance="",
                    offered_existing=False, second_copy=False, qml_loaded=False, network_denied=[], error="")
    result = dict(id=case["id"], status="FAIL", reason="launcher did not finish the case", evidence=evidence)
    if not same_path(sys.executable, launcher / "portable" / "pythonw.exe"):
        result["reason"] = "case did not use the package's portable/pythonw.exe"
        return result
    # Embedded Python ignores PYTHONPATH; insert exactly the package explicitly.
    repository = Path(__file__).resolve().parents[1]
    sys.path[:] = [str(launcher)] + [p for p in sys.path if p and not same_path(p, repository)
                                    and not same_path(p, repository / "tools")]
    sys.dont_write_bytecode = True
    # Tekken 4 has no Python of its own: its ISO import and build run on the package's portable Python (-I -B), which
    # the foreign-python / no-python cases keep honest. T5DR builds with python/python.exe inside the game folder.
    own_python = [sys.executable if case.get("game") == "t4" else None]
    # The game copy sits under the profile, except in the long-profile case where it is a sibling folder inside the
    # same case; only copies made by the matrix count, never the read-only inputs.
    case_dir = home.parent if case.get("id") == "unicode-long-path" else home
    copies = [Path(inputs[key]).resolve() for key in ("t5dr_existing", "t4_root") if inputs.get(key)]
    safety(events, full=request.get("full", False), expected_python=lambda: own_python[0],
           extra_roots=[c for c in copies if c.is_relative_to(case_dir)])
    from PySide6.QtCore import QTimer, QtMsgType, qInstallMessageHandler
    from PySide6.QtGui import QGuiApplication
    from openrecomp import app
    evidence["imported_launcher"] = str(Path(app.__file__).resolve())
    if not same_path(Path(app.__file__).resolve().parents[1], launcher):
        raise RuntimeError("imported launcher from outside the tested package")

    backend_ref = []
    started_at = time.monotonic()
    phase = "start"
    selected_sources = False
    blocked_since = None
    finished = False
    drive_timer = None

    def finish(status, reason):
        nonlocal finished
        if finished:
            return
        finished = True
        result.update(status=status, reason=reason)
        if evidence.get("qml_warnings"):
            result.update(status="FAIL", reason="packaged QML emitted warnings")
        if backend_ref:
            backend = backend_ref[0]
            game = backend.nav.game_by_id(gid)
            try:
                if game:
                    game.a.build_cancel()
            finally:
                backend._quit()
        else:
            QGuiApplication.quit()

    def press(backend, action):
        backend.nav.act(action)
        backend.refresh()

    def focus(backend, iid):
        nav = backend.nav
        for direction in ("up", "down"):
            for _ in range(len(nav.items()) + 2):
                rows = nav.items()
                row = rows[nav.focus_index(rows)]
                if row.get("id") == iid:
                    return row
                press(backend, direction)
        raise AssertionError("controller cannot reach " + iid + "; rows: " + ", ".join(
            str(row.get("id")) for row in nav.items()) + "; section " + str(nav.section()))

    def pick(backend, target, path):
        # Seed the picker at the supplied player's path, then confirm the actual
        # entry through the same controller action and _picked validation as UI.
        nav = backend.nav
        folder = os.path.isdir(path)
        nav._open_list_picker("source:" + target, "Player matrix", [], "folder" if folder else "file",
                              path if folder else os.path.dirname(path))
        entries = nav._picker_entries()
        wanted = next((i for i, entry in enumerate(entries)
                       if entry["kind"] in ("pick", "file") and same_path(entry["path"], path)), None)
        if wanted is None:
            raise AssertionError("chosen path is absent from the real controller picker")
        for _ in range(len(entries) + 1):
            if nav.picker["focus"] == wanted:
                press(backend, "confirm")
                return
            press(backend, "up" if nav.picker["focus"] > wanted else "down")
        raise AssertionError("controller picker could not select the supplied path")

    def configure_transport(backend):
        folder = inputs.get(gid + "_release")
        if not folder:
            return False
        from openrecomp import bundled_games, game_releases
        offer = bundled_games.offer(gid, folder)
        backend.setup.latest = lambda source, channel: offer if source == game_releases.SOURCES[gid] else None
        backend.setup.install_fn = lambda game, offer, parent, **kwargs: game_releases.install_fresh(
            game, offer, parent, opener=bundled_games.opener(folder), **kwargs)
        return True

    def step():
        nonlocal phase, selected_sources, blocked_since
        if finished:
            return
        backend = backend_ref[0]
        nav = backend.nav
        game = nav.game_by_id(gid)
        try:
            if time.monotonic() - started_at > request.get("timeout", 120):
                finish("FAIL", "case timed out before successful build steps (phase " + phase + (
                       "; " + str(nav.overlay) + "/" + str(getattr(nav, "confirm_kind", "")) + "; " + str(backend.setup.view(gid))[:300]
                       if phase == "install" else "") + ")")
                return
            if game is None:
                finish("FAIL", "packaged launcher has no " + gid + " tile")
                return
            if phase == "start":
                if QGuiApplication.platformName() != "offscreen":
                    raise AssertionError("launcher did not use offscreen Qt")
                for _ in nav.tile_ids():
                    if nav.tile_ids()[nav.start_focus] == gid:
                        break
                    press(backend, "right")
                press(backend, "confirm")
                for _ in nav.sections():
                    if nav.section() == "build":
                        break
                    press(backend, "next")
                if case["id"] == "fresh-t5dr":
                    if game.a.found():
                        raise AssertionError("fresh home already discovers a game install")
                    if not configure_transport(backend):
                        finish("BLOCKED", "fresh install needs signed local T5DR release files")
                        return
                    nav.setup_parent = str(home / "games")
                    Path(nav.setup_parent).mkdir(exist_ok=True)
                    focus(backend, "game_setup")
                    press(backend, "confirm")
                    phase = "install"
                    return
                if case["id"] == "discover-old-t5dr":
                    if not inputs.get("t5dr_existing"):
                        finish("BLOCKED", "old-launcher T5DR folder fixture is missing")
                        return
                    evidence["offered_existing"] = bool(game.a.found())
                    evidence["second_copy"] = any(row.get("id") == "game_setup" for row in nav.items())
                    if not evidence["offered_existing"] or evidence["second_copy"]:
                        raise AssertionError("launcher offers a second install instead of the old folder")
                selection = case.get("selection")
                if selection:
                    pick(backend, "folder", selection)
                phase = "sources"
                return
            if phase == "install":
                if nav.overlay == "dialog" and nav.confirm_kind == "setup_existing":
                    # The launcher looks through drive roots, the registry and recent files: a development PC has
                    # T5DR installs of its own. A fresh install says "no, install a new copy" and never touches them.
                    if nav.exit_focus != 1:
                        press(backend, "right")
                    press(backend, "confirm")
                    return
                if nav.overlay == "dialog" and nav.confirm_kind == "setup_install":
                    if nav.exit_focus != 1:
                        press(backend, "right")
                    press(backend, "confirm")
                state = backend.setup.view(gid)
                if state.get("error"):
                    raise AssertionError("fresh installation failed: " + state["error"])
                if game.a.found() and state.get("phase") == "installed":
                    phase = "sources"
                return
            if phase == "sources":
                if game.a.source_state().get("running"):
                    return
                evidence["root"] = getattr(game.a, "root", "") or ""
                evidence["expected_root"] = inputs.get("expected_root", "")
                if not game.a.found():
                    if not inputs.get("t4_root" if gid == "t4" else "t5dr_existing"):
                        finish("BLOCKED", "existing game folder fixture is missing")
                        return
                    raise AssertionError("launcher did not find the chosen game's root")
                expected = inputs.get("expected_root")
                if expected and not same_path(evidence["root"], expected):
                    raise AssertionError("launcher selected a different game root")
                if case["id"] in ("missing-python", "missing-crypto"):
                    problem = game.a.build_install_problem()
                    rows = nav.items()
                    repairs = [row for row in rows if row.get("install_problem") == problem]
                    if not problem or not repairs or not any(row.get("id") == "build_reinstall" for row in repairs):
                        raise AssertionError("incomplete game Python has no visible repair action")
                    from openrecomp import i18n
                    evidence["repair_message"] = i18n.localize(problem, "en")
                    finish("PASS", "incomplete game Python shows repair and cannot start a build")
                    return
                problem = game.a.build_install_problem()
                if problem:
                    from openrecomp import i18n
                    evidence["install_problem"] = i18n.localize(problem, "en")
                    raise AssertionError("the game install is not buildable: " + evidence["install_problem"])
                if gid != "t4":
                    seed_keys(inputs, evidence["root"])
                required = ("iso",) if gid == "t4" else ("pkg", "rap")
                if not selected_sources:
                    for sid in required:
                        value = inputs.get(gid + "_" + sid)
                        if not value:
                            finish("BLOCKED", "read-only owner input is missing: " + gid + "_" + sid)
                            return
                        pick(backend, sid, value)
                    selected_sources = True
                    return
                if game.a.source_state().get("running"):
                    return
                row = focus(backend, "build")
                if row.get("first_play"):
                    raise AssertionError("scratch fixture already built; this case would launch a game")
                if row.get("disabled") or row.get("blocked"):
                    # The launcher checks a chosen disc image / package on its own thread: the first tick
                    # after the pick still shows "choose the image first". Only a block that stays is a failure.
                    blocked_since = blocked_since or time.monotonic()
                    if time.monotonic() - blocked_since < 45:
                        return
                    raise AssertionError("launcher blocks Build: " + str(row.get("hint", "")) + " (" + str(nav.toast) + "; " + str(game.a.source_state()) + ")")
                blocked_since = None
                if gid != "t4":
                    own_python[0] = str(Path(evidence["root"]) / "python" / "python.exe")
                press(backend, "confirm")
                build = getattr(game.a, "build", None)
                if build is not None:
                    evidence["build_started"] = True
                    command = getattr(build, "cmd", None)
                    if command:
                        evidence["build_python"] = command[0]
                phase = "build"
                return
            state = game.a.build_state()
            build = getattr(game.a, "build", None)
            command = getattr(build, "cmd", None)
            if command:
                evidence["build_python"] = command[0]
                own = Path(sys.executable) if gid == "t4" else Path(evidence["root"]) / "python" / "python.exe"
                if not same_path(command[0], own):
                    raise AssertionError("build selected a Python outside the game install")
            evidence["build_started"] = evidence["build_started"] or bool(state.get("running") and build)
            evidence["first_steps"] = [row.get("k", "") for row in state.get("steps", [])
                                       if row.get("v") == "@osk.done"]
            records = read_events(events)
            boundaries = [record for record in records if record["kind"] == "compile_boundary"]
            unsafe = [record for record in records if record["kind"] == "unsafe_process"]
            if boundaries:
                if evidence["build_started"] and evidence["build_python"] and evidence["first_steps"]:
                    finish("PASS", "build's first steps succeeded; stopped before compilation")
                else:
                    finish("FAIL", "compile boundary reached without successful first-step evidence")
            elif unsafe:
                finish("BLOCKED", "offline safety guard refused an unauditable installer or build subprocess")
            elif not state.get("running"):
                if request.get("full") and state.get("result") in ("@build_finished", "@t4.build_finished"):
                    finish("PASS", "full build completed")
                elif case["id"] == "no-winget" and state.get("failed") == "tools":
                    from openrecomp import i18n
                    evidence["guidance"] = i18n.localize(state.get("result") or "", "en")
                    help_rows = [row for row in nav.items() if "help" in str(row.get("id", ""))]
                    finish("PASS" if evidence["guidance"] and help_rows else "FAIL",
                           "no-winget build tools guidance" if help_rows else "no actionable build tools guidance")
                elif phase == "build":
                    raise AssertionError("build failed before first steps: " + str(state.get("result") or nav.toast))
        except Exception as error:
            evidence["error"] = str(error)
            finish("FAIL", str(error))

    original_make_engine = app.make_engine

    def make_engine(backend, full):
        nonlocal drive_timer
        backend_ref.append(backend)
        engine = original_make_engine(backend, full)
        evidence["qml_loaded"] = bool(engine.rootObjects())
        drive_timer = QTimer(backend)
        drive_timer.setInterval(50)
        drive_timer.timeout.connect(step)
        drive_timer.start()
        return engine

    app.make_engine = make_engine
    sys.argv = ["openrecomp", "--windowed"]
    evidence["qml_warnings"] = []

    def qt_message(kind, context, message):
        if kind in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            if ".qml" in message or "qml" in str(getattr(context, "category", "")).casefold():
                evidence["qml_warnings"].append(message)

    def callback_error(kind, error, tb):
        evidence["error"] = str(error)
        finish("FAIL", "unhandled launcher callback: " + str(error))

    old_handler = qInstallMessageHandler(qt_message)
    old_hook, sys.excepthook = sys.excepthook, callback_error
    try:
        runpy.run_module("openrecomp", run_name="__main__")
    except SystemExit as error:
        if error.code not in (None, 0):
            result.update(status="FAIL", reason="packaged launcher exited with " + str(error.code))
    finally:
        qInstallMessageHandler(old_handler)
        sys.excepthook = old_hook
        records = read_events(events)
        evidence["commands"] = [record["command"] for record in records if record["kind"] == "command"]
        evidence["network_denied"] = [record for record in records if record["kind"] == "network_denied"]
        evidence["foreign_python_used"] = any(record["kind"] == "foreign_python" for record in records)
        if evidence["qml_warnings"]:
            result.update(status="FAIL", reason="packaged launcher produced QML warnings")
        if evidence["network_denied"]:
            result.update(status="FAIL", reason="launcher or build attempted a non-loopback connection")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request")
    parser.add_argument("--result")
    parser.add_argument("--build-worker")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.build_worker:
        return build_worker(args.build_worker, args.command[1:] if args.command[:1] == ["--"] else args.command,
                            args.full)
    result = dict(status="FAIL", reason="child did not run", evidence={})
    try:
        contain_process_tree()
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        result = run_case(request)
    except Exception as error:
        result.update(status="FAIL", reason=str(error))
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
