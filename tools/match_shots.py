"""Review compact match cards using explicitly supplied read-only picture caches.

Only synthetic adapters are used. No install discovery, game code or network is
loaded; private pictures and reports stay in ignored build/shots/withart.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from tools import online_shots

SCENES = ("home", "lobby_dense", "matched", "starting", "profile")


def pictures(game, cache, renders=None):
    """Read named PNGs only; never run a decoder or write beside supplied art."""
    from PySide6.QtGui import QImageReader
    from openrecomp.t4_art import FIGHTER_PORTRAITS
    cache = Path(cache).resolve(strict=True)
    renders = Path(renders).resolve(strict=True) if renders else cache
    keys = {f"f{i}": f"face_{i:02d}" for i in range(35)} if game == "t5" else {
        key: key for key in FIGHTER_PORTRAITS}

    def picture(folder, stem):
        path = folder / (stem + ".png")
        if not path.is_file():
            return ""
        if path.resolve().parent != folder:
            raise ValueError("Pictures must stay inside the supplied cache")
        reader = QImageReader(str(path))
        size = reader.size()
        if bytes(reader.format()) != b"png" or not (0 < size.width() <= 2048 and 0 < size.height() <= 2048):
            raise ValueError("Expected a PNG of at most 2048 pixels per side")
        if reader.read().isNull():
            raise ValueError("A review picture could not be decoded")
        return str(path)

    faces = {key: picture(cache, stem) for key, stem in keys.items()}
    large = {}
    for key in keys:
        if game == "t5":
            index = int(key[1:])
            large[key] = {side: picture(renders, f"render_{index:02d}_{'p2' if side else 'p1'}")
                          for side in (False, True)}
        else:
            large[key] = {side: picture(renders, key + ("_render_p2" if side else "_render_p1"))
                          for side in (False, True)}
    if sum(bool(path) for path in faces.values()) < 2:
        raise ValueError("At least two named portraits are required")
    return faces, large


def scene(game, chapter, language, faces, renders):
    nav = online_shots.scene(game, "matched" if chapter == "starting" else chapter, language)
    adapter, snapshot = nav.game.a, nav.game.a.snapshot
    if chapter == "starting":
        snapshot.update(phase="starting", message="@online.starting")
    left, right = ("f9", "f0") if game == "t5" else ("jin", "kazuya")
    adapter.fighter_image = lambda key: faces.get(key, "")
    adapter.fighter_render = lambda key, mirrored=False: renders.get(key, {}).get(mirrored, "")
    adapter.fighter_name = lambda key: {left: "Jin", right: "Paul" if game == "t5" else "Kazuya"}.get(key, key.title())
    adapter.fighter_label = adapter.fighter_name
    adapter.chosen_fighter = lambda: left
    adapter.main_fighter = lambda: "Jin"
    adapter.fighters = lambda: [dict(key=key, name=adapter.fighter_name(key), image=path)
                               for key, path in faces.items() if path]
    snapshot["me"]["main"] = left
    for index, player in enumerate(snapshot["players"]):
        player["main"] = right if index % 2 == 0 else left
    snapshot["profile"].update(main=left, ranked_chars=[dict(char=left, games=40, wins=22, losses=18)])
    if snapshot.get("match"):
        snapshot["match"].update(you_char=left, opp_char=right)
        if chapter == "starting":
            snapshot["match"]["opponent_ready"] = True
    assert nav.dry and not adapter.calls
    return nav


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t5-cache", type=Path, required=True)
    parser.add_argument("--t5-renders", type=Path)
    parser.add_argument("--t4-cache", type=Path, required=True)
    parser.add_argument("--t4-renders", type=Path)
    args = parser.parse_args(argv)
    private = ROOT / "build/tmp-home/match-shots"
    private.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(private)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QFontDatabase
    from PySide6.QtQml import QQmlApplicationEngine
    from test_ui_loads import FakeBackend, spin, wait_pages
    app = QGuiApplication.instance() or QGuiApplication([])
    art = {game: pictures(game, cache, renders) for game, cache, renders in (
        ("t5", args.t5_cache, args.t5_renders), ("t4", args.t4_cache, args.t4_renders))}
    ui = ROOT / "openrecomp/ui"
    for font in (ui / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    backend = FakeBackend(scene("t5", "matched", "en", *art["t5"]))
    engine, warnings = QQmlApplicationEngine(), []
    engine.warnings.connect(lambda messages: warnings.extend(w.toString() for w in messages))
    engine.setInitialProperties(dict(backend=backend, wantFull=False))
    engine.load(QUrl.fromLocalFile(str(ui / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("Review UI failed to load")
    window = engine.rootObjects()[0]
    window.show()
    out = ROOT / "build/shots/withart"
    records = []
    for language in ("en", "de"):
        for game in ("t5", "t4"):
            for width, height in online_shots.SIZES:
                window.setWidth(width)
                window.setHeight(height)
                for chapter in SCENES:
                    backend.nav = scene(game, chapter, language, *art[game])
                    backend.refresh()
                    wait_pages(window)
                    spin(180)
                    path = out / language / game / f"{width}x{height}" / (chapter + ".png")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not window.grabWindow().save(str(path)):
                        raise RuntimeError("Review capture failed")
                    overflow, elided = online_shots.geometry(window)
                    records.append(dict(game=game, language=language, scene=chapter,
                                        size=f"{width}x{height}", overflow=overflow, elided=elided))
                    print(game, language, f"{width}x{height}", chapter, "overflow", len(overflow), flush=True)
    online_shots.contact_sheets(out, ("en", "de"), ("t5", "t4"), SCENES)
    from PySide6.QtGui import QImageReader
    coverage = {game: dict(portraits=sum(bool(p) for p in faces.values()),
                          full_height_portraits=sum(QImageReader(p).size().height() > QImageReader(p).size().width()
                                                    for p in faces.values() if p),
                          large_renders=sum(bool(p) for sides in renders.values() for p in sides.values()))
                for game, (faces, renders) in art.items()}
    limitations = []
    if not coverage["t5"]["large_renders"]:
        limitations.append("T5DR uses the supplied face cache; native large VS crops were unavailable and their quality is unverified.")
    if not coverage["t4"]["large_renders"]:
        limitations.append("T4 uses supplied portraits with P2 mirrored by QML; separate side-specific render caches were unavailable.")
    (out / "compact-report.json").write_text(json.dumps(dict(captures=records,
        art_coverage=coverage, limitations=limitations, qml_warnings=warnings), indent=2), encoding="utf-8")
    window.setProperty("allowClose", True)
    window.close()
    return int(bool(warnings or any(record["overflow"] for record in records)))


if __name__ == "__main__":
    raise SystemExit(main())
