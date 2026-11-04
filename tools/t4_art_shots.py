"""Review explicitly supplied local T4 portrait PNGs in offline launcher fixtures.

    python tools/t4_art_shots.py --cache <OPENRECOMP_HOME>/art/t4/fighters

No installed game, launcher backend, account or network is opened. Captures contain
the supplied private art and stay in ignored build/shots/t4art.
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


SCENES = {"lobby": "lobby_dense", "vs": "matched", "profile": "profile"}


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


def scene(name, pictures):
    nav = online_shots.scene("t4", SCENES[name], "en")
    adapter = nav.game.a
    keys = list(pictures)
    preferred = [key for key in ("jin", "kazuya") if key in pictures]
    keys = preferred + [key for key in keys if key not in preferred]
    adapter.fighter_image = lambda key: pictures.get(key, "")
    adapter.fighters = lambda: [dict(key=key, name=key.replace("_", " ").title(), image=path)
                               for key, path in pictures.items()]
    adapter.snapshot["me"]["main"] = keys[0]
    for index, player in enumerate(adapter.snapshot["players"]):
        player["main"] = keys[(index + 1) % len(keys)]
    adapter.snapshot["profile"].update(main=keys[0],
        ranked_chars=[dict(char=keys[0], games=40, wins=22, losses=18)],
        history=[dict(opponent="Rival", ranked=False, result="win", status="confirmed",
                      score=[3, 1], you_char=keys[0], opp_char=keys[1])])
    return nav


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
    parser.add_argument("--cache", required=True, type=Path)
    args = parser.parse_args(argv)
    from openrecomp import t4_art
    pictures = load_cache(args.cache, t4_art.FIGHTER_PORTRAITS)
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
    ui = ROOT / "openrecomp" / "ui"
    for font in (ui / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    warnings = []
    backend = FakeBackend(scene("lobby", pictures))
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
        backend.nav = scene(name, pictures)
        backend._v = backend.nav.view()
        backend.viewChanged.emit()
        wait_pages(window)
        for width, height in online_shots.SIZES:
            window.setWidth(width)
            window.setHeight(height)
            visible = wait_pictures(window, spin)
            path = OUT / f"{width}x{height}" / (name + ".png")
            path.parent.mkdir(parents=True, exist_ok=True)
            if not window.grabWindow().save(str(path)):
                raise RuntimeError("A review capture failed")
            overflow, elided = online_shots.geometry(window)
            records.append(dict(scene=name, size=f"{width}x{height}",
                path=path.relative_to(ROOT).as_posix(), visible_portraits=visible,
                overflow=overflow, elided=elided))
    window.setProperty("allowClose", True)
    window.close()
    (OUT / "report.json").write_text(json.dumps(dict(captures=records, qml_warnings=warnings), indent=2), encoding="utf-8")
    print(f"Saved {len(records)} local-art review captures to build/shots/t4art")
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
