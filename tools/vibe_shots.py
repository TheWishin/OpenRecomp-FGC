"""Capture offline vibe fixtures from explicitly supplied read-only picture caches.

No launcher backend, install discovery, decoder, game or network is used. Private
PNGs, a 12-second GIF per game and timing reports stay in build/shots/vibe.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")


def _gif_pixels(pixels):
    """Small original GIF LZW encoder; bounded dictionaries keep codes at 9 bits."""
    codes, table, current, following = [256], {bytes([n]): n for n in range(256)}, b"", 258
    for pixel in pixels:
        token = bytes([pixel])
        phrase = current + token
        if phrase in table:
            current = phrase
            continue
        codes.append(table[current])
        if following < 510:
            table[phrase] = following
            following += 1
        else:
            codes.append(256)
            table, following = {bytes([n]): n for n in range(256)}, 258
        current = token
    if current:
        codes.append(table[current])
    codes.append(257)
    packed, accumulator, count = bytearray(), 0, 0
    for code in codes:
        accumulator |= code << count
        count += 9
        while count >= 8:
            packed.append(accumulator & 255)
            accumulator >>= 8
            count -= 8
    if count:
        packed.append(accumulator & 255)
    return bytes(packed)


def _gif_palette(frames):
    """Median-cut samples retain dark menu shades and natural portrait colours."""
    from PySide6.QtGui import qRgb
    colours = collections.Counter()
    for image in frames[::max(1, len(frames) // 6)]:
        sample = image.scaled(96, 54)
        for y in range(sample.height()):
            for x in range(sample.width()):
                colour = sample.pixelColor(x, y)
                colours[(colour.red(), colour.green(), colour.blue())] += 1
    boxes = [list(colours)]

    def spread(box):
        ranges = [max(colour[channel] for colour in box) - min(colour[channel] for colour in box)
                  for channel in range(3)]
        return max(ranges), ranges.index(max(ranges))

    while len(boxes) < 256:
        candidates = [(spread(box)[0] * sum(colours[c] for c in box) ** .5, index)
                      for index, box in enumerate(boxes) if len(box) > 1]
        if not candidates:
            break
        _, index = max(candidates)
        box = boxes.pop(index)
        channel = spread(box)[1]
        box.sort(key=lambda colour: colour[channel])
        halfway, cumulative, cut = sum(colours[c] for c in box) / 2, 0, 1
        for cut, colour in enumerate(box[:-1], 1):
            cumulative += colours[colour]
            if cumulative >= halfway:
                break
        boxes.extend((box[:cut], box[cut:]))
    palette = [qRgb(*(round(sum(colour[channel] * colours[colour] for colour in box) /
                            sum(colours[colour] for colour in box)) for channel in range(3)))
               for box in boxes]
    return palette + [palette[-1]] * (256 - len(palette))


def write_gif(path, frames, delay_ms=100):
    """Write QImages without an optional imaging/video dependency."""
    from PySide6.QtGui import QImage
    if not frames:
        raise ValueError("A recording needs at least one frame")
    width, height = frames[0].width(), frames[0].height()
    palette = _gif_palette(frames)
    with Path(path).open("wb") as stream:
        stream.write(b"GIF89a" + struct.pack("<HHBBB", width, height, 0xF7, 0, 0))
        stream.write(bytes(channel for colour in palette for channel in
                           ((colour >> 16) & 255, (colour >> 8) & 255, colour & 255)))
        stream.write(b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00")
        for image in frames:
            if (image.width(), image.height()) != (width, height):
                raise ValueError("Recording frames must share a size")
            indexed = image.convertToFormat(QImage.Format_Indexed8, palette)
            raw = bytes(indexed.constBits())
            pixels = b"".join(raw[row * indexed.bytesPerLine():row * indexed.bytesPerLine() + width]
                              for row in range(height))
            stream.write(b"\x21\xf9\x04\x04" + struct.pack("<H", max(1, round(delay_ms / 10))) + b"\x00\x00")
            stream.write(b"\x2c" + struct.pack("<HHHHB", 0, 0, width, height, 0) + b"\x08")
            compressed = _gif_pixels(pixels)
            for offset in range(0, len(compressed), 255):
                block = compressed[offset:offset + 255]
                stream.write(bytes([len(block)]) + block)
            stream.write(b"\x00")
        stream.write(b"\x3b")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t5-cache", type=Path, required=True)
    parser.add_argument("--t4-cache", type=Path, required=True)
    args = parser.parse_args(argv)
    out = ROOT / "build/shots/vibe"
    private = ROOT / "build/tmp-home/vibe-shots"
    private.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(private)
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from test_ui_loads import FakeBackend, spin, wait_pages
    from tools import match_shots, online_shots
    app = QGuiApplication.instance() or QGuiApplication([])
    art = {game: match_shots.pictures(game, cache)
           for game, cache in (("t5", args.t5_cache), ("t4", args.t4_cache))}
    ui = ROOT / "openrecomp/ui"
    for font in (ui / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))

    def scene(game, chapter, language="en"):
        nav = match_shots.scene(game, chapter, language, *art[game])
        nav.reduced_motion = False
        nav.game.a.playtime_stats = dict(offline_seconds=14400, online_seconds=28800,
                                        sessions=12, last_played="2026-11-05")
        label = nav.game.a.fighter_label
        known = {"f0": "Paul", "f1": "Law", "f3": "King", "f9": "Jin"} if game == "t5" else {}
        nav.game.a.fighter_label = lambda key: known.get(key, label(key))
        nav.game.a.fighter_name = nav.game.a.fighter_label
        return nav

    backend = FakeBackend(scene("t5", "home"))
    engine, warnings = QQmlApplicationEngine(), []
    engine.warnings.connect(lambda messages: warnings.extend(w.toString() for w in messages))
    engine.setInitialProperties(dict(backend=backend, wantFull=False))
    engine.load(QUrl.fromLocalFile(str(ui / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Review UI failed to load")
    window = engine.rootObjects()[0]
    window.setWidth(1280); window.setHeight(720); window.show(); window.requestActivate(); spin(30)
    records, performance = [], {}
    try:
        for game in ("t5", "t4"):
            for language in ("en", "de"):
                for chapter in ("home", "lobby_dense", "matched", "result"):
                    backend.nav = scene(game, chapter, language)
                    backend.refresh(); wait_pages(window); spin(220)
                    filename = f"{game}-{language}-{chapter}.png"
                    if not window.grabWindow().save(str(out / filename)):
                        raise RuntimeError("Review capture failed")
                    overflow, elided = online_shots.geometry(window)
                    records.append(dict(game=game, language=language, scene=chapter,
                                        file=filename, overflow=overflow, elided=elided))
            frames, grab_times, drift_samples = [], [], []
            for frame in range(120):
                started = time.perf_counter()
                if frame % 40 == 0:
                    backend.nav = scene(game, ("home", "lobby_dense", "matched")[frame // 40])
                    if frame == 80:
                        for clock in backend.nav._global_offer_clock.values():
                            clock.update(seconds=6, age=0)
                    backend.refresh(); wait_pages(window)
                if frame in (12, 22, 32, 52, 62, 72):
                    backend.nav.act("down", device="xbox")
                    backend.refresh()
                if frame >= 80:
                    from openrecomp import nav_feedback
                    nav_feedback.tick(backend.nav, .1)
                    backend.refresh()
                grab_started = time.perf_counter()
                image = window.grabWindow()
                grab_times.append((time.perf_counter() - grab_started) * 1000)
                frames.append(image.scaled(768, 432, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if frame % 20 == 0:
                    from PySide6.QtCore import QObject
                    drift_samples.append([item.property("drift") for item in window.findChildren(QObject, "livingBackground")])
                spin(max(1, round(100 - (time.perf_counter() - started) * 1000)))
            write_gif(out / f"{game}-navigation.gif", frames)
            del frames
            backend.nav = scene(game, "home")
            backend.refresh(); wait_pages(window); spin(250)
            wall, cpu = time.perf_counter(), time.process_time()
            spin(3000)
            idle_wall = time.perf_counter() - wall
            idle_cpu = time.process_time() - cpu
            ordered = sorted(grab_times)
            performance[game] = dict(renderer="Qt Quick software/offscreen", size="1280x720",
                gif_size="768x432", gif_seconds=12, gif_fps=10,
                window_active=window.isActive(), drift_samples=drift_samples,
                grab_ms_median=ordered[len(ordered) // 2], grab_ms_p95=ordered[int(len(ordered) * .95)],
                idle_seconds=idle_wall, idle_one_core_percent=100 * idle_cpu / idle_wall)
            print(game, "captures and 12s recording complete", flush=True)
        report = dict(captures=records, performance=performance, qml_warnings=warnings,
            limitations=["Synthetic offline adapters with explicitly supplied private portraits; no game or online session.",
                         "No native large T5DR renders were supplied. Cached faces cannot establish full-resolution key-art quality.",
                         "GIF playback is 10 fps. grabWindow timings include software rendering and readback; they do not establish GPU 60 fps or weak-PC performance.",
                         "Idle CPU is this machine's process CPU divided by elapsed time, as a percentage of one core."])
        (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    finally:
        window.setProperty("allowClose", True)
        window.close()
    return int(bool(warnings or any(record["overflow"] for record in records)))


if __name__ == "__main__":
    raise SystemExit(main())
