"""Render art-free Online fixtures; never instantiate a launcher backend or game adapter.

    python tools/online_shots.py before --ui-dir build/tmp-home/online-before/ui
    python tools/online_shots.py after
    python tools/online_shots.py after --batch arcade --languages en

All captures, contact sheets and geometry reports stay under build/shots/online.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from openrecomp import i18n  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402
from test_online_nav import Lobby  # noqa: E402
from test_online_page import lobby_snapshot  # noqa: E402


CHAPTERS = ("lobby", "rooms", "friends", "leaderboard", "stats", "profile", "tournaments", "spectating", "account")
BASELINE_SCENES = CHAPTERS + ("rooms_empty",)
ARCADE_SCENES = ("arcade_floor", "arcade_selected", "arcade_cabinet", "arcade_options")
SCENES = BASELINE_SCENES + ("home", "ranked", "settings", "feedback") + ARCADE_SCENES
SIZES = ((1920, 1080), (1280, 720))
ART_FIELDS = {"hero", "image", "art", "wordmark", "face", "plate", "portrait", "background"}
ART_LISTS = {"images", "mosaic"}
BASELINE = ROOT / "build" / "tmp-home" / "online-before"


def baseline_nav(source=BASELINE / "nav_online_layout.py"):
    """Use the preserved launcher projection together with the preserved before QML."""
    source = Path(source).resolve()
    source.relative_to(ROOT)
    spec = importlib.util.spec_from_file_location("openrecomp._online_shots_baseline", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return type("BaselineNav", (module.OnlineLayout, Nav), {})


class SyntheticOnline(Lobby):
    """Literal UI samples at the adapter boundary; no install discovery or external code."""

    def __init__(self, game):
        super().__init__()
        self.m.update(id=game, adapter="t4" if game == "t4" else "t5dr",
                      title="Sample Arena", short="Sample Arena", accent="#BE7449")
        # Deliberately share the presentation capabilities, as T4 does at runtime.
        self.snapshot.update(lobby_snapshot())
        self.snapshot["capabilities"].update(
            ranked=game != "t4", t4_lobby=game == "t4", private_rooms=True, friends=True,
            profiles=True, leaderboard=True, community_stats=True, community=True,
            room_tables=True, tournaments=True, spectating=True, account_tools=True,
            account_blocks=True, strict=game != "t4")
        self.snapshot.update(
            rooms=[dict(id="r1", name="Evening practice", host="Rival", status="open", size=4,
                        players=2, members=[dict(id="p1"), dict(id="p2")], maximum=4,
                        mode="line", rotation="winner", lock="none", ping=42, ping_measured=True),
                   dict(id="r2", name="Friends room", host="Player 2", status="open", size=8,
                        players=3, maximum=8, mode="tables", rotation="queue", lock="password",
                        ping=78, ping_measured=True)],
            friends=[dict(name="Rival", status="online", invite=True),
                     dict(name="Player 2", status="in_match", invite=True)],
            friend_incoming=[dict(name="Player 3", status="online")],
            community=dict(maximum=8, preferences=dict(size=4, rotation="winner", access="none",
                                                      hidden=False, mode="line")),
            leaderboard=dict(sort="place", rows=[dict(name=f"Player {n}", place=n, rating=1800 - n * 50,
                                                       rank="3rd Dan", ranked_wins=12 + n,
                                                       ranked_losses=n, casual_wins=6, casual_losses=3)
                                                 for n in range(1, 5)]),
            community_stats=dict(accounts=240, players=12, matches=1820, ranked=1240,
                                 matches_24h=56, players_24h=28,
                                 fighters=[dict(char="Fighter A", ranked=[40, 22, 1], casual=[20, 11, 0]),
                                           dict(char="Fighter B", ranked=[50, 25, 0], casual=[25, 13, 1])]),
            profile=dict(name="Me", rank="3rd Dan", rating=1610, record=[19, 42, 0],
                         stats=dict(ranked=dict(games=61, wins=19, losses=42, draws=0)),
                         ranked_chars=[dict(char="Fighter A", games=40, wins=22, losses=18)],
                         history=[dict(opponent="Rival", ranked=True, result="win", status="confirmed", score=[3, 1])]),
            tournaments=dict(rows=[dict(id="t1", name="Weekend bracket", state="signup", organizer="Player 1",
                                         players=12, max_players=16, set_wins=2)],
                             can_create=True, options=dict(format="single", set_wins=2,
                                 start_minutes=30, max_players=16, checkin_minutes=10, seeding="random")),
            spectating=dict(targets=[dict(kind="room", id="spec_watch_room:r1", name="Evening practice"),
                                    dict(kind="friend", id="spec_watch_friend:p2", name="Player 2")], count=3),
            blocks=[dict(name="Player 4")])
        self.texts.update(online_room_name="Evening practice", online_room_password="",
                          online_room_code="", online_friend_name="", online_profile_name="",
                          online_tour_name="Weekend bracket", online_tour_clock="", online_block_name="")

    def settings(self):
        from tools.ui_shots import Synthetic
        return Synthetic.settings(self)

    def controls_supported(self):
        return True

    def support_available(self):
        return True


def scene(game, chapter, language, nav_type=Nav, text_size=100, high_contrast=False):
    adapter = SyntheticOnline(game)
    arcade_scene = chapter if chapter in ARCADE_SCENES else ""
    if arcade_scene:
        adapter.snapshot["me"]["main"] = "f3"
        adapter.snapshot["players"] = [
            dict(id="p1", name="Rival", rank="2nd Dan", rating=1580, main="f1",
                 status="idle", ping=42, ping_measured=True),
            dict(id="p2", name="Busy", rank="3rd Dan", rating=1620, main="f2",
                 status="playing", opponent="Player 3", ping=78, ping_measured=True),
            dict(id="p3", name="Player 3", rank="2nd Dan", rating=1550, main="f4",
                 status="playing", opponent="Busy", ping=69, ping_measured=True),
            dict(id="p4", name="Player 4", rank="1st Dan", rating=1500, main="f5",
                 status="searching", ping=53, ping_measured=True),
            dict(id="p5", name="Player 5", rank="Beginner", rating=1320, main="f6",
                 status="in_room", room="r2", ping=94, ping_measured=True),
            dict(id="p6", name="Player 6", rank="3rd Dan", rating=1610, main="f7",
                 status="idle", ping=35, ping_measured=True)]
        adapter.snapshot["spectating"]["targets"][0].update(
            players=[dict(id="p2", name="Busy", main="f2"),
                     dict(id="p3", name="Player 3", main="f4")], score=[2, 1])
        chapter = "lobby"
    if chapter == "rooms_empty":
        adapter.snapshot["rooms"] = []
    chapter = chapter.removesuffix("_empty")
    nav = nav_type([Game(adapter.m, adapter)], language=language, text_size=text_size,
                   high_contrast=high_contrast)
    nav.dry = True
    nav.device = nav.pad_kind = "xbox"
    nav.reduced_motion = True
    nav.screen = "hub"
    nav.sec[game] = "online"
    nav.main_menu_visited = {game}
    if arcade_scene:
        nav.click_chapter("lobby")
        if arcade_scene == "arcade_options":
            nav.arcade_options = {game: True}
        selected = {"arcade_selected": "challenge:p1", "arcade_cabinet": "arcade_watch:spec_watch_room:r1"}.get(
            arcade_scene, "search_casual")
        items = nav.items()
        nav.focus[nav.key()] = next(n for n, item in enumerate(items) if item.get("id") == selected)
        return nav
    if chapter == "home":
        nav.open_main_menu()
        return nav
    if chapter == "settings":
        nav.sec[game] = "settings"
        return nav
    if chapter == "ranked":
        nav.open_ranked(nav.game)
        return nav
    if chapter == "feedback":
        from openrecomp import nav_feedback
        adapter.snapshot["capabilities"]["challenge_preferences"] = True
        adapter.snapshot["challenge_preferences"] = {}
        adapter.snapshot["open_challenges"] = [dict(id="sample-offer", player="p1", name="Rival")]
        nav_feedback.records(nav, game)["challenge:p1"] = dict(kind="waiting", text="@online.challenge_sent",
            age=3, name="Rival", action="challenge:p1", challenge="sample-offer", seconds=27)
        nav.click_chapter("lobby")
        items = nav.items()
        nav.focus[nav.key()] = next(n for n, it in enumerate(items) if it.get("id") == "challenge:p1")
        return nav
    if chapter in ("profile", "leaderboard", "stats"):
        nav._t5_profile_pages = {game: chapter}
    nav.click_chapter(chapter)
    return nav


def strip_art(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ART_FIELDS:
                value[key] = ""
            elif key in ART_LISTS:
                value[key] = []
            else:
                strip_art(child)
    elif isinstance(value, list):
        for child in value:
            strip_art(child)


def snapshot(nav):
    view = nav.view()
    strip_art(view)
    return view


def geometry(window):
    """Report overflow and elision while allowing vertically scrollable content outside its viewport."""
    from PySide6.QtCore import QPointF

    problems, elided = [], []
    def descendants(item):
        for child in item.childItems():
            yield child
            yield from descendants(child)

    for item in descendants(window.contentItem()):
        if not item.isVisible() or item.opacity() <= 0 or item.width() <= 0 or item.height() <= 0:
            continue
        if item.property("text") is None or item.property("contentHeight") is None:
            continue
        record = dict(name=item.objectName(), text=str(item.property("text"))[:100])
        if item.property("truncated"):
            elided.append(record)
        if item.property("contentHeight") > item.height() + 3 and not item.property("truncated"):
            problems.append(dict(record, reason="text-height", height=round(item.height(), 1),
                                 content=round(item.property("contentHeight"), 1)))
        if (item.property("contentWidth") is not None and
                item.property("contentWidth") > item.width() + 3 and not item.property("truncated")):
            problems.append(dict(record, reason="text-width", width=round(item.width(), 1),
                                 content=round(item.property("contentWidth"), 1)))
        parent = item.parentItem()
        vertical_scroll = False
        while parent:
            if parent.clip():
                vertical_scroll = vertical_scroll or (
                    parent.property("contentHeight") is not None and
                    parent.property("contentY") is not None and
                    parent.property("contentHeight") > parent.height())
                top = item.mapToItem(parent, QPointF(0, 0))
                bottom = item.mapToItem(parent, QPointF(item.width(), item.height()))
                reason = clip_reason(top.x(), top.y(), bottom.x(), bottom.y(),
                                     parent.width(), parent.height(), vertical_scroll)
                if reason:
                    problems.append(dict(record, reason=reason, ancestor=parent.objectName()))
                    break
            parent = parent.parentItem()
    return problems, elided


def clip_reason(left, top, right, bottom, width, height, vertical_scroll=False):
    if left < -2 or right > width + 2:
        return "horizontal-clip"
    if not vertical_scroll and (top < -2 or bottom > height + 2):
        return "vertical-clip"
    return ""


def contact_sheets(out, languages, games, scenes):
    from PySide6.QtGui import QColor, QImage, QPainter

    for language in languages:
        for game in games:
            for width, height in SIZES:
                tw, th, columns = 640, 360, 2
                rows = (len(scenes) + columns - 1) // columns
                sheet = QImage(columns * tw, rows * (th + 28), QImage.Format_RGB32)
                sheet.fill(QColor("#08090A"))
                painter = QPainter(sheet)
                painter.setPen(QColor("#ECE9E1"))
                for index, chapter in enumerate(scenes):
                    x, y = index % columns * tw, index // columns * (th + 28)
                    capture = QImage(str(out / language / game / f"{width}x{height}" / f"{chapter}.png"))
                    painter.drawImage(x, y + 28, capture.scaled(tw, th))
                    painter.drawText(x + 8, y + 20, f"{language} / {game} / {chapter} / {width}x{height}")
                painter.end()
                sheet.save(str(out / f"contact-{language}-{game}-{width}x{height}.png"))


def main(argv=None):
    home = ROOT / "build" / "tmp-home" / "online"
    home.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(home)
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--ui-dir", type=Path)
    parser.add_argument("--languages", nargs="+", choices=list(i18n.LANGUAGES), default=list(i18n.LANGUAGES))
    parser.add_argument("--games", nargs="+", choices=("t5", "t4"), default=["t5", "t4"])
    parser.add_argument("--scenes", nargs="+", choices=SCENES)
    parser.add_argument("--text-size", choices=("normal", "large", "larger"), default="normal")
    parser.add_argument("--high-contrast", action="store_true")
    parser.add_argument("--batch", choices=("presentation", "arcade"))
    parser.add_argument("--platform", choices=("offscreen", "windows"), default="offscreen")
    args = parser.parse_args(argv)
    if args.scenes is None:
        args.scenes = list(ARCADE_SCENES if args.batch == "arcade" else
                           BASELINE_SCENES if args.phase == "before" else SCENES)
    if args.phase == "before" and any(scene not in BASELINE_SCENES for scene in args.scenes):
        parser.error("The preserved baseline supports only the original Online scenes.")
    text_size = {"normal": 100, "large": 115, "larger": 130}[args.text_size]
    if args.ui_dir is None:
        args.ui_dir = BASELINE / "ui" if args.phase == "before" else ROOT / "openrecomp" / "ui"
    nav_type = baseline_nav() if args.phase == "before" else Nav
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QFontDatabase, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError:
        parser.exit(2, "PySide6 is required for captures; install the existing requirements.txt dependency first.\n")
    from test_ui_loads import FakeBackend, spin, wait_pages
    from tools.ui_shots import font_coverage

    os.environ["QT_QPA_PLATFORM"] = args.platform
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    for font in (args.ui_dir / "fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font.resolve()))
    warnings = []
    backend = FakeBackend(scene("t5", "lobby", "en", nav_type=nav_type))
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda messages: warnings.extend(w.toString() for w in messages))
    engine.setInitialProperties(dict(backend=backend, wantFull=False))
    engine.load(QUrl.fromLocalFile(str((args.ui_dir / "Main.qml").resolve())))
    if not engine.rootObjects():
        raise RuntimeError("\n".join(warnings))
    window = engine.rootObjects()[0]
    window.show()
    suffix = ("-" + args.text_size if args.text_size != "normal" else "") + ("-high-contrast" if args.high_contrast else "")
    if args.batch:
        suffix += "-" + args.batch
    if args.platform != "offscreen":
        suffix += "-" + args.platform
    phase = args.phase + suffix
    out = ROOT / "build" / "shots" / "online" / phase
    records = []
    for language in args.languages:
        for game in args.games:
            for chapter in args.scenes:
                backend.nav = scene(game, chapter, language, nav_type=nav_type,
                                    text_size=text_size, high_contrast=args.high_contrast)
                backend._v = snapshot(backend.nav)
                backend.viewChanged.emit()
                wait_pages(window)
                spin(50)
                for width, height in SIZES:
                    window.setWidth(width)
                    window.setHeight(height)
                    spin(20)
                    path = out / language / game / f"{width}x{height}" / f"{chapter}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if not window.grabWindow().save(str(path)):
                        raise RuntimeError("Capture failed: " + str(path))
                    overflow, elided = geometry(window)
                    records.append(dict(language=language, game=game, scene=chapter, size=f"{width}x{height}",
                                        path=path.relative_to(ROOT).as_posix(), overflow=overflow, elided=elided))
            print(f"{args.phase}: {language} / {game}: {len(args.scenes) * 2} synthetic captures", flush=True)
    coverage = font_coverage()
    limitations = [f"{lang}: CJK glyph coverage unavailable; actual glyph layout remains unverified"
                   for lang, covered in coverage.items() if not covered]
    (out / "report.json").write_text(json.dumps(dict(captures=records, qml_warnings=warnings,
        font_coverage=coverage, limitations=limitations), ensure_ascii=False, indent=2), encoding="utf-8")
    contact_sheets(out, args.languages, args.games, args.scenes)
    window.setProperty("allowClose", True)
    window.close()
    print(f"Saved {len(records)} synthetic captures to build/shots/online/{phase}")
    if warnings:
        print("QML warnings:\n" + "\n".join(sorted(set(warnings))), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
