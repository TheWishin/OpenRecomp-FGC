"""Review explicitly supplied local T4 art in offline launcher fixtures.

    python tools/t4_art_shots.py --cache <OPENRECOMP_HOME>/art/t4/fighters

The optional --source reads verified disc data without loading installed code.
No launcher backend, account or network is opened. Captures contain the supplied
private art and stay in ignored build/shots.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "shots" / "t4art"
HOME = ROOT / "build" / "tmp-home" / "t4art-shots"
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from PySide6.QtGui import QImageReader  # noqa: E402
from tools import online_shots  # noqa: E402


SCENES = {"lobby": "lobby_dense", "vs": "matched", "profile": "profile",
          "challenge": "challenge_incoming"}


def extract_source(source):
    """Write only to the private review home; never modify the supplied disc files."""
    from openrecomp import t4_art
    cache = HOME / "fighters"
    pictures, renders = {}, {}
    for key in t4_art.FIGHTER_PORTRAITS:
        path = cache / (key + ".png")
        pictures[key] = t4_art.make_fighter(str(source), key, str(path))
        renders[key] = {}
        for mirrored, side in ((False, "p1"), (True, "p2")):
            path = cache / (key + "-" + side + ".png")
            renders[key][mirrored] = t4_art.make_fighter_render(str(source), key, str(path), mirrored)
    return pictures, renders


def load_cache(directory, known):
    """Read only named, square PNGs inside the explicitly supplied directory."""
    directory = Path(directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("The portrait cache must be a directory")
    pictures = {}
    for key in known:
        path = directory / (key + ".png")
        if not path.is_file():
            continue
        if path.resolve().parent != directory:
            raise ValueError("Portraits must stay inside the supplied cache")
        reader = QImageReader(str(path))
        size = reader.size()
        if bytes(reader.format()) != b"png" or not 1 <= size.width() <= 1024 or size.width() != size.height():
            raise ValueError("Portraits must be square PNGs of at most 1024 pixels")
        if reader.read().isNull():
            raise ValueError("A portrait PNG could not be decoded")
        pictures[key] = str(path)
    if len(pictures) < 2:
        raise ValueError("At least two known T4 portrait PNGs are required")
    return pictures


def scene(name, pictures, renders=None):
    nav = online_shots.scene("t4", SCENES[name], "en")
    adapter = nav.game.a
    keys = list(pictures)
    preferred = [key for key in ("jin", "kazuya") if key in pictures]
    keys = preferred + [key for key in keys if key not in preferred]
    adapter.fighter_image = lambda key: pictures.get(key, "")
    renders = renders or {}
    adapter.fighter_render = lambda key, mirrored=False: renders.get(key, {}).get(mirrored, "")
    adapter.fighters = lambda: [dict(key=key, name=key.replace("_", " ").title(), image=path)
                               for key, path in pictures.items()]
    adapter.snapshot["me"]["main"] = keys[0]
    for index, player in enumerate(adapter.snapshot["players"]):
        player["main"] = keys[(index + 1) % len(keys)]
    adapter.snapshot["profile"].update(main=keys[0],
        ranked_chars=[dict(char=keys[0], games=40, wins=22, losses=18)],
        history=[dict(opponent="Rival", ranked=False, result="win", status="confirmed",
                      score=[3, 1], you_char=keys[0], opp_char=keys[1])])
    if name == "challenge":
        adapter.snapshot["challenge"]["main"] = keys[1]
    return nav


def portrait_sheet(pictures, path):
    """Label every verified portrait at native review size, including offscreen rows."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    columns, width, height = 6, 264, 288
    sheet = QImage(columns * width, ((len(pictures) + columns - 1) // columns) * height,
                   QImage.Format_RGB32)
    sheet.fill(QColor("#101318"))
    painter = QPainter(sheet)
    painter.setPen(QColor("#eeeeee"))
    painter.setFont(QFont("IBM Plex Sans", 14))
    for index, (key, picture) in enumerate(pictures.items()):
        x, y = index % columns * width, index // columns * height
        image = QImage(picture).scaled(248, 248, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawImage(x + (width - image.width()) // 2, y + 4, image)
        painter.drawText(x + 8, y + 276, key.replace("_", " ").title())
    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not sheet.save(str(path)):
        raise RuntimeError("The portrait review sheet could not be saved")


def descendants(item):
    for child in item.childItems():
        yield child
        yield from descendants(child)


def wait_pictures(window, spin):
    for _ in range(100):
        spin(10)
        pictures = [item for item in descendants(window.contentItem())
                    if item.objectName() == "fighterPicture" and item.parentItem().isVisible()
                    and item.property("source").toString()]
        if pictures and all(item.isVisible() for item in pictures):
            return sum(item.isVisible() for item in pictures)
    raise RuntimeError("The fixture portraits did not finish loading")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--cache", type=Path)
    inputs.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    from openrecomp import t4_art
    out = args.out.resolve()
    out.relative_to((ROOT / "build" / "shots").resolve())
    HOME.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(HOME)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from test_ui_loads import FakeBackend, spin, wait_pages

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    pictures, renders = extract_source(args.source) if args.source else (load_cache(args.cache, t4_art.FIGHTER_PORTRAITS), {})
    ui = ROOT / "openrecomp" / "ui"
    for font in (ui / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    warnings = []
    backend = FakeBackend(scene("lobby", pictures, renders))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda messages: warnings.extend(message.toString() for message in messages))
    engine.setInitialProperties(dict(backend=backend, wantFull=False))
    engine.load(QUrl.fromLocalFile(str(ui / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("The review UI could not load")
    window = engine.rootObjects()[0]
    window.show()
    records = []
    for name in SCENES:
        backend.nav = scene(name, pictures, renders)
        backend._v = backend.nav.view()
        backend.viewChanged.emit()
        wait_pages(window)
        for width, height in online_shots.SIZES:
            window.setWidth(width)
            window.setHeight(height)
            visible = wait_pictures(window, spin)
            path = out / f"{width}x{height}" / (name + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(path)):
                raise RuntimeError("A review capture failed")
            overflow, elided = online_shots.geometry(window)
            records.append(dict(scene=name, size=f"{width}x{height}",
                path=path.relative_to(ROOT).as_posix(), visible_portraits=visible,
                overflow=overflow, elided=elided))
    window.setProperty("allowClose", True)
    window.close()
    portrait_sheet(pictures, out / "all-portraits.png")
    (out / "report.json").write_text(json.dumps(dict(captures=records, qml_warnings=warnings,
        portrait_keys=list(pictures)), indent=2), encoding="utf-8")
    print(f"Saved {len(records)} local-art review captures to {out.relative_to(ROOT)}")
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
