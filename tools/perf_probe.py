"""Offline, offscreen launcher probe. Results and isolated homes stay under build/.

Run with the launcher's Python: tools/perf_probe.py --label before --runs 3.
CPU is process CPU / elapsed time (100% means one core). No player installs,
physical controllers, network, game launches, screenshots or builds are used.
"""
import time

BOOT = time.perf_counter()
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def synthetic_asset():
    """A plain colour swatch, never game art; generated only in the parent."""
    import struct
    import zlib

    target = ROOT / "build/perf-assets/swatch.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    target.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1024, 1024, 8, 2, 0, 0, 0))
                       + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x30\x40\x50" * 1024) * 1024))
                       + chunk(b"IEND", b""))


def counters():
    from ctypes import wintypes

    class Memory(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "peak", "working_set", "pool_peak", "pool", "nonpool_peak", "nonpool", "page", "page_peak")]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes")]

    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    ctypes.windll.kernel32.GetProcessIoCounters.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    memory, io = Memory(), IO()
    memory.cb = ctypes.sizeof(memory)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
        raise ctypes.WinError()
    if not ctypes.windll.kernel32.GetProcessIoCounters(handle, ctypes.byref(io)):
        raise ctypes.WinError()
    return dict(working_set_mib=round(memory.working_set / 1048576, 2),
                read_operations=io.reads, read_bytes=io.read_bytes)


def child(args):
    global BOOT
    BOOT = args.started_at if args.started_at is not None else BOOT
    home = ROOT / "build" / "tmp-home" / (args.label + "-" + str(args.child))
    home.mkdir(parents=True, exist_ok=True)
    for key in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        os.environ[key] = str(home)
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                      QT_QUICK_CONTROLS_STYLE="Basic", QML_DISABLE_DISK_CACHE="1",
                      OPENRECOMP_NO_GAME_CHECKS="1", OPENRECOMP_PAD_ALWAYS="1",
                      OPENRECOMP_STALL_LOG=str(home / "stalls.txt"), OPENRECOMP_STALL_MS="50")
    (home / "config.json").write_text('{"language":"en","fullscreen":false}', encoding="utf-8")
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
    from unittest import mock
    import socket
    opened = []

    def audit(event, values):
        if event == "open" and isinstance(values[0], str) and not values[2] & (os.O_WRONLY | os.O_RDWR):
            path = Path(values[0])
            if path.is_absolute() and path.is_relative_to(ROOT) and path.is_file():
                opened.append((path.relative_to(ROOT).as_posix(), path.stat().st_size))
        if event in ("socket.connect", "socket.bind", "subprocess.Popen"):
            raise AssertionError("External operation in offline probe")

    sys.addaudithook(audit)
    from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent
    from openrecomp import app
    from openrecomp.nav import Game
    from test_nav import Fake, manifest
    from test_online_nav import Lobby
    from test_online_page import lobby_snapshot

    class Reader:
        kind = "xbox"
        def read(self):
            return set()

    def forbidden(*a, **kw):
        raise AssertionError("External operation in offline probe")

    def spin(ms):
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def ready():
        return all(not loader.property("active") or loader.property("progress") == 1
                   and loader.property("item") is not None
                   for loader in backend.window.findChildren(QObject, "pageLoader"))

    def settle():
        deadline = time.perf_counter() + 5
        while not ready() and time.perf_counter() < deadline:
            spin(5)
        if not ready():
            raise RuntimeError("A page did not load")
        count = len(frames)
        backend.window.update()
        while len(frames) == count and time.perf_counter() < deadline:
            spin(5)
        if len(frames) == count:
            raise RuntimeError("A page did not render")

    gui = QGuiApplication([])
    lobby = Lobby()
    lobby.snapshot.update(lobby_snapshot())
    games = [Game(lobby.m, lobby)]
    games += [Game(m, Fake(m)) for m in (manifest("probe"), manifest("direct", adapter="t4"))]
    asset = str(ROOT / "build/perf-assets/swatch.png")
    for game in games:
        game.a.hero = lambda: asset
        game.a.rank_plate = lambda tier: asset
        game.a.fighter_image = lambda fighter: asset
    lobby.snapshot["me"]["main"] = "synthetic"
    lobby.snapshot["players"][0].update(main="synthetic", tier=12)
    with mock.patch.object(app, "load_games", return_value=(games, [])), \
            mock.patch.object(app, "XInputReader", Reader), \
            mock.patch.object(app, "WinMMPlayStationReader", Reader), \
            mock.patch.object(app.UpdateService, "check"), \
            mock.patch.object(socket, "socket", forbidden):
        backend = app.Backend(windowed=True)
        backend._setup_started = True
        engine = app.make_engine(backend, False)
        report = dict(scene_ms=round((time.perf_counter() - BOOT) * 1000, 2))
        frames = []
        backend.window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
        spin(1)
        deadline = time.perf_counter() + 5
        while not frames and time.perf_counter() < deadline:
            spin(5)
        if not frames:
            raise RuntimeError("No first frame")
        settle()
        report["first_frame_ms"] = round((frames[-1] - BOOT) * 1000, 2)
        backend.nav.act("confirm", device="xbox")
        backend.refresh()
        previous_frames = len(frames)
        deadline = time.perf_counter() + 5
        while len(frames) == previous_frames and time.perf_counter() < deadline:
            spin(5)
        if backend.view["screen"] != "hub" or len(frames) == previous_frames:
            raise RuntimeError("Hub did not render")
        settle()
        report["interactive_ms"] = round((time.perf_counter() - BOOT) * 1000, 2)
        report["startup_io"] = counters()
        report["startup_python_files"] = [dict(file=p, bytes=s) for p, s in sorted(set(opened))]
        spin(1000)
        report["idle_memory_mib"] = counters()["working_set_mib"]
        ticks = [0]
        backend.timer.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
        # The watchdog is diagnostic overhead, so exclude it from the idle CPU interval.
        if backend.stall:
            backend._heart.stop()
            backend.stall.stop()
        cpu, wall = time.process_time(), time.perf_counter()
        spin(int(args.idle_seconds * 1000))
        elapsed = time.perf_counter() - wall
        report["idle_seconds"] = round(elapsed, 2)
        report["idle_cpu_percent"] = round(100 * (time.process_time() - cpu) / elapsed, 3)
        report["idle_tick_count"] = ticks[0]
        import threading
        report["background_threads"] = [t.name for t in threading.enumerate()]
        report["timers"] = [dict(interval_ms=t.interval(), active=t.isActive()) for t in backend.findChildren(QTimer)]
        if backend.stall:
            # Use a fresh watch; the stopped worker must not race a restarted one.
            backend._heart.timeout.disconnect(backend.stall.beat)
            backend.stall = app.stall.from_env()
            backend._heart.timeout.connect(backend.stall.beat)
            backend._heart.start()
        cpu, wall = time.process_time(), time.perf_counter()
        pages = set()
        page_times = {}
        image_modes = set()
        actions = (["next", "down", "up"] * 5 + ["switchGame"]) * len(games)
        actions += ["social", "right", "back", "back", "confirm"]
        for action in actions:
            start = time.perf_counter()
            backend.nav.act(action, device="xbox")
            backend.nav.release(action)
            backend.refresh()
            settle()
            for obj in backend.window.findChildren(QObject):
                if obj.metaObject().className() == "QQuickImage":
                    image_modes.add((bool(obj.property("asynchronous")), bool(obj.property("cache"))))
            page = backend.nav.section() if backend.nav.screen == "hub" else "shelf"
            page_times.setdefault(page, round((time.perf_counter() - start) * 1000, 3))
            spin(100)
            pages.add(backend.nav.section() if backend.nav.screen == "hub" else "shelf")
        # Exercise the login and status card too, without asking the fake to log in or search.
        while backend.nav.game is not games[0]:
            backend.nav.act("switchGame", device="xbox")
        while backend.nav.section() != "online":
            backend.nav.act("next", device="xbox")
        for phase in ("offline", "connecting", "logged_in"):
            lobby.snapshot["phase"] = phase
            backend.refresh()
            spin(100)
            pages.add("online:" + backend.view["online"]["layout"])
        report["navigation_cpu_percent"] = round(100 * (time.process_time() - cpu) / (time.perf_counter() - wall), 3)
        report["pages"] = sorted(pages)
        report["page_first_render_ms"] = page_times
        report["image_async_cache_modes"] = sorted(image_modes)
        report["visited_memory_mib"] = counters()["working_set_mib"]
        report["stalls_after_start"] = backend.stall.summary() if backend.stall else None
        report["qml_compile_ms"] = {}
        for path in sorted((ROOT / "openrecomp/ui").glob("*.qml")):
            start = time.perf_counter()
            component = QQmlComponent(engine, QUrl.fromLocalFile(str(path)))
            report["qml_compile_ms"][path.name] = round((time.perf_counter() - start) * 1000, 3)
            if component.isError():
                raise RuntimeError(str(component.errors()))
        report["asset_files"] = [dict(file=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size)
                                 for p in sorted((ROOT / "openrecomp/ui").rglob("*"))
                                 if p.suffix in (".svg", ".ttf", ".ico")]
        report["measurement_limits"] = [
            "Fresh processes and disabled QML disk cache; OS file cache is not flushed.",
            "Startup I/O is process logical read counters, not physical disk traffic.",
            "Python file inventory excludes native Qt reads; asset inventory lists available files.",
            "QML compilation timings are a warm post-navigation diagnostic, not page creation timings.",
            "A synthetic 1024px colour swatch exercises image loading/cache; exact decode time/thread attribution requires a Qt profiler."]
        if backend.stall:
            backend.stall.stop()
        backend.timer.stop()
        backend.window.hide()
        del engine
    print("PERF_RESULT " + json.dumps(report))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="probe")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--idle-seconds", type=float, default=60)
    parser.add_argument("--child", type=int)
    parser.add_argument("--started-at", type=float)
    args = parser.parse_args()
    if not args.label.replace("-", "").isalnum():
        parser.error("label must be alphanumeric")
    if args.child is not None:
        child(args)
        return
    target = ROOT / "build/perf" / args.label
    target.mkdir(parents=True, exist_ok=True)
    synthetic_asset()
    reports = []
    for run in range(args.runs):
        result = subprocess.run([sys.executable, "-X", "importtime", __file__, "--child", str(run),
                                 "--label", args.label, "--idle-seconds", str(args.idle_seconds),
                                 "--started-at", str(time.perf_counter())],
                                cwd=ROOT, capture_output=True, text=True, timeout=args.idle_seconds + 60)
        # Import timings contain module names only; omit Qt diagnostics/local paths.
        (target / (str(run) + "-importtime.txt")).write_text(
            "\n".join(line for line in result.stderr.splitlines() if line.startswith("import time:")), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        report = json.loads(result.stdout.split("PERF_RESULT ", 1)[1].splitlines()[0])
        reports.append(report)
        (target / "results.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
        print(json.dumps({k: report[k] for k in ("interactive_ms", "first_frame_ms", "idle_cpu_percent", "visited_memory_mib")} ), flush=True)


if __name__ == "__main__":
    main()
