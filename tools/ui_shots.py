"""Capture synthetic launcher scenes, without discovering or loading any installed game.

    python tools/ui_shots.py before --ui-dir build/tmp-home/ui-before/ui
    python tools/ui_shots.py after

Every picture uses the test adapter boundary, empty image fields and a private home.
The real Backend, input readers and game adapters are never instantiated.
"""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
HOME = ROOT / "build" / "tmp-home"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QColor, QRawFont  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from openrecomp import i18n  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_nav import Fake, manifest  # noqa: E402
from test_online_nav import Lobby  # noqa: E402
from test_online_page import lobby_snapshot  # noqa: E402
from test_ui_loads import FakeBackend, spin, wait_pages  # noqa: E402


SCENES = ("shelf", "shelf_build_needed", "shelf_update", "shelf_update_required", "play", "replays", "replays_empty", "settings",
          "controls", "controls_empty", "support", "support_loading", "support_error",
          "build", "build_loading", "online", "login", "login_error", "drawer",
          "confirm", "info", "error", "keyboard", "fighters",
          "playtime_tile", "playtime_game", "playtime_profile")


def configure_environment():
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(HOME)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"


class Synthetic(Lobby):
    """Only literal sample values; inherited test methods just record calls."""

    native_label = ""

    def __init__(self):
        super().__init__()
        self.m.update(title="Sample Arena", short="Sample Arena", accent="#BE7449")
        self.empty_replays = False
        self.empty_controls = False
        self.support = dict(running=False, operation="", checked=False, findings=[],
                            report="", error="", note="", contact="", send_available=True,
                            check_available=False)
        self.progress = dict(super().build_state())

    def status(self):
        return dict(status="@ready" if self.is_ready else "@build_first", version="1.0",
                    players="", last="2026-10-28", detail="@start_hint")

    def playtime(self):
        return dict(getattr(self, "playtime_stats", {}))

    def settings(self):
        specs = (("resolution", "@settings_ui.group.display", "1920 × 1080", "@settings_ui.note.display", "display"),
                 ("vsync", "VSync", "@on", "@settings_ui.note.display", "display"),
                 ("mute", "@settings_ui.group.audio", "@off", "@settings_ui.note.audio", "audio"),
                 ("practice", "@settings_ui.group.offline", "@on", "@settings_ui.note.offline", "offline"),
                 ("replays", "@section.replays", "@on", "@settings_ui.note.replays", "replays"))
        return [dict(id=sid, label=label, options=[("sample", value), ("other", "@off")],
                     value="sample", hint=hint, lead=hint, group=group)
                for sid, label, value, hint, group in specs]

    def quick_settings(self):
        return ["resolution", "practice"]

    def replays(self):
        if self.empty_replays:
            return []
        return [dict(id=str(n), label=f"Player {n + 1} · Player {n + 2}", when=f"18:{n:02}",
                     date="2026-10-28", group="2026-10-28", opponent=f"Player {n + 2}",
                     fighters="Fighter A / Fighter B", length="02:14", netcode="Rollback",
                     result="3–1", images=[]) for n in range(8)]

    def controls_supported(self):
        return True

    def controls(self):
        if self.empty_controls:
            return []
        return [dict(id="pad1", label="Sample controller · P1", port=1,
                     slots=[dict(id=slot, label="@controls.slot." + slot, value=value)
                            for slot, value in (("1", "A"), ("2", "B"), ("3", "X"),
                                                ("4", "Y"), ("START", "Start"), ("SELECT", "Back"))])]

    def support_available(self):
        return True

    def support_send_info(self):
        return dict(available=True)

    def support_state(self):
        return dict(self.support)

    def build_state(self):
        return dict(self.progress)


def scene(name, language):
    if name == "playtime_profile":
        from tools.online_shots import scene as online_scene
        nav = online_scene("t5", "profile", language)
        nav.game.a.playtime_stats = dict(offline_seconds=30 * 3600, online_seconds=12 * 3600,
                                         last_played=date.today().isoformat(), sessions=54)
        nav.game.a.snapshot["profile"]["self"] = True
        other = Fake(manifest("t4", short="T4"), is_ready=True)
        other.playtime = lambda: dict(offline_seconds=6 * 3600, online_seconds=0,
                                      last_played=date.today().isoformat(), sessions=8)
        nav.games.append(Game(other.m, other))
        return nav
    adapter = Synthetic()
    other = Fake(manifest("sample2", title="Sample Circuit", accent="#65979F"), is_ready=False)
    if name in ("playtime_tile", "playtime_game"):
        adapter.playtime_stats = dict(offline_seconds=10 * 3600, online_seconds=2 * 3600 + 30 * 60,
                                      last_played=date.today().isoformat(), sessions=18)
        name = "shelf" if name == "playtime_tile" else "play"
    nav = Nav([Game(adapter.m, adapter), Game(other.m, other)], language=language)
    nav.dry = True
    nav.device = nav.pad_kind = "xbox"
    nav.reduced_motion = True
    if name.startswith("shelf"):
        if name == "shelf_build_needed":
            nav.start_focus = 1
        elif name.startswith("shelf_update"):
            adapter.m["adapter"] = "t5dr"
            nav.on_setup = lambda *_: None
            nav.setup_state = {nav.game.id: dict(available=True, required=name.endswith("required"),
                                                installed="1.0", latest="1.1", size=100_000_000)}
        return nav
    nav.screen = "hub"
    section = name.split("_")[0]
    nav.sec[nav.game.id] = section if section in nav.sections() else "play"
    if name == "replays_empty":
        adapter.empty_replays = True
    elif name == "controls_empty":
        adapter.empty_controls = True
    elif name == "support_loading":
        adapter.support.update(running=True, operation="send")
    elif name == "support_error":
        adapter.support.update(error="@support.error")
        nav.focus[nav.key()] = 4
    elif name == "build_loading":
        adapter.progress.update(running=True, fraction=.55, title="@build_game", line="@support.running",
                                steps=[dict(k="@build_game", v="55%")])
    elif name == "online":
        nav.sec[nav.game.id] = "online"
        adapter.snapshot.update(lobby_snapshot())
    elif name in ("login", "login_error"):
        nav.sec[nav.game.id] = "online"
        if name == "login_error":
            adapter.snapshot.update(phase="error", message="@online.disconnected")
    elif name == "drawer":
        nav.overlay = "drawer"
    elif name in ("confirm", "info", "error"):
        nav._ask("exit" if name == "confirm" else "support_report")
    elif name == "keyboard":
        nav._open_osk("support_note")
    elif name == "fighters":
        nav._open_fighters()
    return nav


def snapshot(nav, name):
    view = nav.view()
    if name in ("info", "error"):
        view["dialog"] = dict(title=i18n.localize("@support.error" if name == "error" else "@support.report_ready", nav.language),
                              text=i18n.localize("@support.check.hint" if name == "error" else "@support.local_only", nav.language),
                              options=[dict(label=i18n.localize("@confirm", nav.language), index=0, focused=True)])
    # Never allow a future test fixture to bring game art into captures.
    def no_art(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("hero", "image", "art", "wordmark", "face", "plate", "portrait", "background"):
                    value[key] = ""
                elif key in ("images", "mosaic"):
                    value[key] = []
                else:
                    no_art(child)
        elif isinstance(value, list):
            for child in value:
                no_art(child)
    no_art(view)
    return view


def descendants(item):
    for child in item.childItems():
        yield child
        yield from descendants(child)


def geometry(window):
    """Use the same clipping and dense-row audit as the expanded Online fixtures."""
    from tools.online_shots import geometry as online_geometry
    return online_geometry(window)[0]


def font_coverage_details():
    """Check every printable catalog character against the available Qt fallback fonts."""
    faces = [QRawFont.fromFont(QFont(family)) for family in QFontDatabase.families()]
    catalogs = {language: {char for value in i18n.catalog(language).values() for char in value
                           if char.isprintable() and not char.isspace()}
                for language in i18n.LANGUAGES}
    supported = {char: any(face.supportsCharacter(ord(char)) for face in faces)
                 for char in set().union(*catalogs.values())}
    result = {}
    for language, characters in catalogs.items():
        missing = sorted(char for char in characters if not supported[char])
        result[language] = dict(covered=not missing, tested_characters=len(characters),
                                missing_characters="".join(missing),
                                missing_codepoints=[f"U+{ord(char):04X}" for char in missing])
    return result


def font_coverage():
    return {language: detail["covered"] for language, detail in font_coverage_details().items()}


def main(argv=None):
    configure_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after", "probe", "playtime"))
    parser.add_argument("--ui-dir", type=Path, default=ROOT / "openrecomp" / "ui")
    parser.add_argument("--languages", nargs="+", default=list(i18n.LANGUAGES))
    parser.add_argument("--scenes", nargs="+", choices=SCENES, default=list(SCENES))
    args = parser.parse_args(argv)
    HOME.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    for font in (args.ui_dir / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font.resolve()))
    warnings = []
    backend = FakeBackend(scene("shelf", "en"))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda messages: warnings.extend(w.toString() for w in messages))
    engine.setInitialProperties(dict(backend=backend, wantFull=False))
    engine.load(QUrl.fromLocalFile(str((args.ui_dir / "Main.qml").resolve())))
    if not engine.rootObjects():
        raise RuntimeError("\n".join(warnings))
    window = engine.rootObjects()[0]
    window.show()
    records = []
    for language in args.languages:
        for name in args.scenes:
            backend.nav = scene(name, language)
            backend._v = snapshot(backend.nav, name)
            backend.viewChanged.emit()
            wait_pages(window)
            spin(70)
            for width, height in ((1920, 1080), (1280, 720)):
                window.setWidth(width)
                window.setHeight(height)
                spin(25)
                path = ROOT / "build" / "shots" / args.phase / language / f"{width}x{height}" / f"{name}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                if not window.grabWindow().save(str(path)):
                    raise RuntimeError("Capture failed: " + str(path))
                from tools.online_shots import geometry as online_geometry, layout_geometry, layout_problems
                overflow, elided = online_geometry(window)
                layout = layout_geometry(window)
                records.append(dict(language=language, scene=name, size=f"{width}x{height}",
                                    path=path.relative_to(ROOT).as_posix(), overflow=overflow, elided=elided,
                                    layout=layout, collisions=layout_problems(layout)))
        print(f"{args.phase}: {language}: {len(args.scenes) * 2} synthetic captures", flush=True)
    out = ROOT / "build" / "shots" / args.phase
    coverage_details = font_coverage_details()
    coverage = {language: detail["covered"] for language, detail in coverage_details.items()}
    limitations = [f"{language}: catalog characters are missing from the offscreen font database; glyph layout is unverified"
                   for language, covered in coverage.items() if not covered]
    from tools.online_shots import DECORATIVE_CLIPPING
    (out / "report.json").write_text(json.dumps(dict(captures=records, qml_warnings=warnings,
                                                    font_coverage=coverage, font_coverage_details=coverage_details,
                                                    limitations=limitations,
                                                    geometry_exclusions=dict(art_free_background_numerals=DECORATIVE_CLIPPING)),
                                              ensure_ascii=False, indent=2), encoding="utf-8")
    # Small contact sheets make it practical to inspect every page, language and size.
    for language in args.languages:
        for width, height in ((1920, 1080), (1280, 720)):
            thumb_w, thumb_h, columns = 480, 270, 4
            rows = (len(args.scenes) + columns - 1) // columns
            sheet = QImage(columns * thumb_w, rows * (thumb_h + 28), QImage.Format_RGB32)
            sheet.fill(QColor("#08090A"))
            painter = QPainter(sheet)
            painter.setPen(QColor("#ECE9E1"))
            for index, name in enumerate(args.scenes):
                x, y = index % columns * thumb_w, index // columns * (thumb_h + 28)
                capture = QImage(str(out / language / f"{width}x{height}" / f"{name}.png"))
                painter.drawImage(x, y + 28, capture.scaled(thumb_w, thumb_h))
                painter.drawText(x + 8, y + 20, f"{language} · {name} · {width}×{height}")
            painter.end()
            sheet.save(str(out / f"contact-{language}-{width}x{height}.png"))
    window.setProperty("allowClose", True)
    window.close()
    if warnings:
        print("QML warnings:\n" + "\n".join(sorted(set(warnings))), file=sys.stderr)
        return 1
    print(f"Saved {len(records)} synthetic captures to build/shots/{args.phase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
