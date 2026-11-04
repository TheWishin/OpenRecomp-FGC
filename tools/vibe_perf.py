"""Measure synthetic launcher drawing and idle CPU, without games or captures.

CPU is process CPU / elapsed time: 100 percent means one core. The software
offscreen renderer is a useful upper-bound diagnostic, not a desktop GPU test.
All generated inputs and results stay in ignored build/shots/vibe.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def distribution(values):
    """Nearest-rank statistics retain spikes instead of averaging them away."""
    values = sorted(values)
    if not values:
        return dict(count=0, p50=None, p95=None, maximum=None)
    return dict(count=len(values), p50=round(values[math.ceil(len(values) * .50) - 1], 3),
                p95=round(values[math.ceil(len(values) * .95) - 1], 3),
                maximum=round(values[-1], 3))


def full_backend_samples(asset, out, seconds):
    """Include real timers/model polling, replacing only external boundaries."""
    from unittest import mock

    from PySide6.QtCore import QObject, Qt
    from openrecomp import app
    from openrecomp.nav import Game
    from openrecomp.pad import Pads
    from test_ui_loads import spin, wait_pages
    from tools.online_shots import SyntheticOnline

    records, warnings = [], []

    def forbidden(*args, **kwargs):
        raise AssertionError("External operation in synthetic backend performance probe")

    for kind in ("t4", "t5"):
        adapter = SyntheticOnline(kind)
        adapter.snapshot["me"]["main"] = "f3"
        available = [False]
        adapter.fighter_render = lambda *args, **kwargs: str(asset) if available[0] else ""
        adapter.fighter_image = lambda *args, **kwargs: str(asset) if available[0] else ""
        adapter.hero = lambda: ""
        with mock.patch.object(app.mf, "load_config", return_value=dict(language="en", fullscreen=False, ui_sounds=False)), \
                mock.patch.object(app, "load_games", return_value=([Game(adapter.m, adapter)], [])), \
                mock.patch.object(app.Backend, "_load_pads", lambda backend, games: setattr(backend, "pads", Pads([]))), \
                mock.patch.object(app, "system_reduced_motion", return_value=False), \
                mock.patch.object(app.UpdateService, "check", side_effect=forbidden), \
                mock.patch.dict(os.environ, OPENRECOMP_NO_GAME_CHECKS="1", OPENRECOMP_STALL_LOG=""):
            backend = app.Backend(windowed=True)
            backend.nav.open_main_menu()
            backend.refresh()
            engine = app.make_engine(backend, False)
            engine.warnings.connect(lambda rows: warnings.extend(row.toString() for row in rows))
            window = backend.window
            window.resize(1920, 1080)
            window.requestActivate()
            wait_pages(window)
            spin(1000)
            backend._sync_timers()
            if not window.property("motionActive") or not backend.timer.isActive():
                raise RuntimeError("Combined probe needs both active backdrop and real Backend timer")
            backgrounds = window.findChildren(QObject, "livingBackground")
            timer = next((background.findChild(QObject, "backgroundDriftTimer") for background in backgrounds
                          if background.isVisible()), None)
            if timer is None or not timer.property("running"):
                raise RuntimeError("Combined probe background timer did not run")
            frames, durations, started, ticks = [], [], [None], [0]
            window.beforeRendering.connect(lambda: started.__setitem__(0, time.perf_counter()), Qt.DirectConnection)

            def rendered():
                if started[0] is not None:
                    durations.append((time.perf_counter() - started[0]) * 1000)
                    started[0] = None

            window.afterRendering.connect(rendered, Qt.DirectConnection)
            window.frameSwapped.connect(lambda: frames.append(time.perf_counter()), Qt.DirectConnection)
            backend.timer.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
            for art in (False, True):
                available[0] = art
                # A changed fixture source is published through the normal model.
                adapter.__dict__.pop("_living_background", None)
                backend.refresh()
                spin(1000)
                frames.clear()
                durations.clear()
                ticks[0] = 0
                wall, cpu = time.perf_counter(), time.process_time()
                spin(round(seconds * 1000))
                elapsed = time.perf_counter() - wall
                record = dict(game=adapter.m["adapter"], width=1920, height=1080,
                              synthetic_art=art, elapsed_seconds=round(elapsed, 3),
                              cpu_percent_one_core=round(100 * (time.process_time() - cpu) / elapsed, 3),
                              backend_tick_count=ticks[0], backend_interval_ms=backend.timer.interval(),
                              motion_active=window.property("motionActive"),
                              background_interval_ms=timer.property("interval"), ambient_frames=len(frames),
                              render_ms=distribution(durations))
                records.append(record)
                print(json.dumps(record), flush=True)
                if not window.property("motionActive") or not backend.timer.isActive():
                    raise RuntimeError("Combined sample lost the active launcher")
            window.setProperty("allowClose", True)
            window.visibilityChanged.disconnect(backend._sync_timers)
            window.activeChanged.disconnect(backend._sync_timers)
            window.hide()
            backend.timer.stop()
            backend._background_timer.stop()
            backend._save_timer.stop()
            backend.sounds.close()
            del engine
            backend.window = None
            backend.deleteLater()
            del backend
            spin(50)
    report = dict(platform="offscreen", renderer="software", real_backend=True,
                  records=records, qml_warnings=warnings,
                  limitations=["Real Backend timers/model polling with synthetic adapters and empty controller readers.",
                               "No game installation, player data, network, recording, or actual hardware-controller polling.",
                               "Synthetic solid-colour art; desktop GPU and weak-PC results may differ.",
                               "Animation preference is supplied by the fixture; no Windows setting is changed."])
    (out / "backend-perf.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if warnings:
        raise RuntimeError("QML warnings during combined backend performance probe")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--backend", action="store_true", help="include real Backend timers and model polling")
    args = parser.parse_args(argv)
    if not 1 <= args.seconds <= 30:
        parser.error("seconds must be between 1 and 30")
    out = ROOT / "build/shots/vibe"
    home = ROOT / "build/tmp-home/vibe-perf"
    out.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(home)
    os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                      QML_DISABLE_DISK_CACHE="1", OPENRECOMP_UI_SOUND="0")
    sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

    from PySide6.QtCore import QObject, QTimer, QUrl, Qt
    from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QImage
    from PySide6.QtQml import QQmlApplicationEngine
    from test_ui_loads import FakeBackend, spin, wait_pages
    from tools.online_shots import scene

    gui = QGuiApplication.instance() or QGuiApplication([])
    asset = out / "synthetic-swatch.png"
    picture = QImage(1024, 1024, QImage.Format_RGB32)
    picture.fill(QColor("#90A0B0"))
    if not picture.save(str(asset)):
        raise RuntimeError("Cannot create synthetic probe input")
    if args.backend:
        full_backend_samples(asset, out, args.seconds)
        return
    ui = ROOT / "openrecomp/ui"
    for font in (ui / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    nav = scene("t5", "home", "en")
    adapter = nav.game.a
    adapter.fighter_render = lambda *args, **kwargs: str(asset)
    adapter.fighter_image = lambda *args, **kwargs: str(asset)
    adapter.hero = lambda: ""
    backend = FakeBackend(nav)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda rows: warnings.extend(row.toString() for row in rows))
    engine.setInitialProperties(dict(backend=backend, wantFull=False))
    engine.load(QUrl.fromLocalFile(str(ui / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Synthetic scene failed to load")
    window = engine.rootObjects()[0]
    window.show()
    wait_pages(window)
    spin(600)

    timestamps, durations, began = [], [], [None]
    window.beforeRendering.connect(lambda: began.__setitem__(0, time.perf_counter()), Qt.DirectConnection)

    def rendered():
        if began[0] is not None:
            durations.append((time.perf_counter() - began[0]) * 1000)
            began[0] = None

    window.afterRendering.connect(rendered, Qt.DirectConnection)
    window.frameSwapped.connect(lambda: timestamps.append(time.perf_counter()), Qt.DirectConnection)
    records = []
    backgrounds = window.findChildren(QObject, "livingBackground")
    if not backgrounds:
        raise RuntimeError("Missing background under measurement")

    def measure(mode, width, height, art):
        for background in backgrounds:
            background.setProperty("motionActive", mode != "inactive")
            background.setProperty("reducedMotion", mode == "reduced")
            background.setProperty("scene", dict(theme="t5dr", source=QUrl.fromLocalFile(str(asset)).toString() if art else ""))
        window.setWidth(width)
        window.setHeight(height)
        spin(600)
        timestamps.clear()
        durations.clear()
        wall, cpu = time.perf_counter(), time.process_time()
        spin(round(args.seconds * 1000))
        elapsed = time.perf_counter() - wall
        row = dict(mode=mode, width=width, height=height, synthetic_art=art,
                   elapsed_seconds=round(elapsed, 3),
                   cpu_percent_one_core=round(100 * (time.process_time() - cpu) / elapsed, 3),
                   render_ms=distribution(durations),
                   frame_interval_ms=distribution([(b - a) * 1000 for a, b in zip(timestamps, timestamps[1:])]))
        records.append(row)
        print(json.dumps(row), flush=True)

    for width, height in ((1280, 720), (1920, 1080)):
        for art in (False, True):
            for mode in ("ambient", "inactive", "reduced"):
                measure(mode, width, height, art)

    # Short transitions deliberately run at the animation driver's cadence.
    # This separates frame budget evidence from the backdrop's capped idle rate.
    for background in backgrounds:
        background.setProperty("motionActive", False)
    page = window.findChildren(QObject, "pageLoader")
    loader = next((item for item in page if item.property("active") and item.property("item") is not None), None)
    if loader is not None:
        from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation
        animation = QParallelAnimationGroup()
        for name, start, end in ((b"opacity", .65, 1), (b"entryOffset", 16, 0)):
            part = QPropertyAnimation(loader, name)
            part.setDuration(150)
            part.setStartValue(start)
            part.setEndValue(end)
            part.setEasingCurve(QEasingCurve.OutCubic)
            animation.addAnimation(part)
        pulse = QTimer()
        pulse.setInterval(300)
        pulse.timeout.connect(animation.start)
        timestamps.clear()
        durations.clear()
        pulse.start()
        spin(round(args.seconds * 1000))
        pulse.stop()
        animation.stop()
        gaps = [(b - a) * 1000 for a, b in zip(timestamps, timestamps[1:])]
        records.append(dict(mode="short_transition", width=window.width(), height=window.height(),
                            render_ms=distribution(durations),
                            active_frame_interval_ms=distribution([gap for gap in gaps if gap < 75]),
                            all_frame_interval_ms=distribution(gaps)))
    for background in backgrounds:
        background.setProperty("motionActive", False)
    window.setProperty("allowClose", True)
    window.hide()
    report = dict(platform="offscreen", renderer="software", records=records, qml_warnings=warnings,
                  limitations=["Synthetic colour inputs only; no game files or live backend.",
                               "Software offscreen timings do not establish desktop GPU or weak-PC performance.",
                               "Ambient updates cap at 2 Hz in software and 10 Hz on GPU; transitions target 60 Hz.",
                               "Process CPU includes Python, QML, and software drawing, but excludes real controllers and backend polling."])
    (out / "perf.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if warnings:
        raise RuntimeError("QML warnings during synthetic performance probe")


if __name__ == "__main__":
    main()
