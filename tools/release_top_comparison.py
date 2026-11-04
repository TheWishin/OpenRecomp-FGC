"""Compare the release Online composition and current art-free synthetic lobby.

Only read-only git source is extracted, under build/tmp-home. No installed game,
real backend, network request or game-derived image participates in the capture.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
SOURCE = "343b01c"
HOME = ROOT / "build/tmp-home/round7-comparison"
OUT = ROOT / "build/shots/round7-comparison"


def release_sources():
    """The current shell renders the original release OnlineHub without a second dock."""
    destination = HOME / "ui"
    destination.mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "openrecomp/ui").iterdir():
        if source.suffix == ".qml" or source.name == "qmldir":
            shutil.copyfile(source, destination / source.name)
    original = subprocess.check_output(
        ["git", "-c", "safe.directory=" + ROOT.as_posix(), "show", SOURCE + ":openrecomp/ui/OnlineHub.qml"],
        cwd=ROOT).decode("utf-8")
    (destination / "OnlineHub.qml").write_text(original, encoding="utf-8")
    shell = (destination / "Main.qml").read_text(encoding="utf-8")
    shell = re.sub(r"readonly property bool chatDocked: [^\n]+", "readonly property bool chatDocked: false", shell)
    (destination / "Main.qml").write_text(shell, encoding="utf-8")
    return destination


def main():
    HOME.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(HOME)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    from PySide6.QtCore import QRectF, QUrl
    from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter
    from PySide6.QtQml import QQmlApplicationEngine
    from test_ui_loads import FakeBackend, spin, wait_pages
    from tools import online_shots
    app = QGuiApplication.instance() or QGuiApplication([])
    for font in (ROOT / "openrecomp/ui/fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font))
    baseline = release_sources()
    warnings, records = [], []
    for language in ("en", "de"):
        for width, height in online_shots.SIZES:
            pictures, layouts = [], []
            for release, ui in ((True, baseline), (False, ROOT / "openrecomp/ui")):
                nav = online_shots.scene("t5", "lobby_dense", language)
                backend = FakeBackend(nav)
                backend._v = online_shots.snapshot(nav)
                if release:
                    backend._v["online"]["chatOpen"] = True
                engine = QQmlApplicationEngine()
                engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
                engine.setInitialProperties(dict(backend=backend, wantFull=False))
                engine.load(QUrl.fromLocalFile(str(ui / "Main.qml")))
                if not engine.rootObjects():
                    raise RuntimeError("Comparison scene failed to load")
                window = engine.rootObjects()[0]
                window.setWidth(width); window.setHeight(height); window.show()
                wait_pages(window); spin(180)
                picture = window.grabWindow()
                label = "release-0.1.0" if release else "round7"
                filename = f"{label}-{language}-{width}x{height}.png"
                if not picture.save(str(OUT / filename)):
                    raise RuntimeError("Comparison capture failed")
                pictures.append(picture)
                layout = online_shots.layout_geometry(window)
                layouts.append(dict(source=label, panes=[row for row in layout if row["name"] in (
                    "onlineProfile", "onlineFind", "lobbyPlayersPane", "lobbyRoomsPane", "lobbyLivePane", "lobbyChatPane")]))
                if nav.game.a.calls:
                    raise AssertionError("Synthetic comparison executed an adapter action")
                window.setProperty("allowClose", True); window.close()
                del window
                del engine
            comparison = QImage(width * 2, height + 40, QImage.Format_RGB32)
            comparison.fill(QColor("#0E0F11"))
            painter = QPainter(comparison)
            painter.setPen(QColor("#E8E4DD")); painter.setFont(QFont("IBM Plex Sans", 16))
            for index, (title, picture) in enumerate(zip(("v0.1.0 source / same synthetic identity", "Round 7 / same synthetic identity"), pictures)):
                painter.drawText(QRectF(index * width + 16, 0, width - 32, 40), title)
                painter.drawImage(index * width, 40, picture)
            painter.end()
            comparison.save(str(OUT / f"comparison-{language}-{width}x{height}.png"))
            records.append(dict(language=language, size=f"{width}x{height}", layouts=layouts))
    report = dict(source=SOURCE, release_top_stage_height=226, captures=records,
                  qml_warnings=warnings,
                  limitations=["Release QML is rendered with the current synthetic projection and shell; this is a composition comparison, not a historical runtime capture."])
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Synthetic release comparison: " + OUT.relative_to(ROOT).as_posix())
    if warnings:
        print("\n".join(sorted(set(warnings))))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
