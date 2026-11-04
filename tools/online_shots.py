"""Render art-free Online fixtures; never instantiate a launcher backend or game adapter.

    python tools/online_shots.py before --ui-dir build/tmp-home/online-before/ui
    python tools/online_shots.py after
    python tools/online_shots.py after --batch arcade --languages en
    python tools/online_shots.py after --batch community
    python tools/online_shots.py after --batch final --languages en de

The default after batch includes every state. Community selects the expanded input,
chat, challenge and match phase fixtures. Final selects the owner's review screens
under build/shots/final; other captures stay under build/shots/online. Every batch
renders both reference sizes and writes a report, overview sheets and six-scene
contact pages named contact-{language}-{game}-{size}-pageNN.png.
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
COMMUNITY_SCENES = ("lobby_dense", "lobby_guest", "lobby_long_names", "player_busy", "player_self", "private_chat",
                    "mentions", "chat_history", "native_composer", "pad_composer", "pad_osk",
                    "challenge_incoming", "challenge_sent", "challenge_waiting", "challenge_cancelled",
                    "challenge_declined", "challenge_expired", "searching", "cancelling", "matched",
                    "matched_picks", "starting", "playing", "result", "reporting", "disconnect_retry", "rooms_create",
                    "community_room", "controls")
OFFER_SCENES = ("offer_shelf", "offer_home", "offer_settings")
ACTIVITY_SCENES = ("activity_rooms", "activity_home")
PORTRAIT_SCENES = ("matched", "matched_picks", "searching", "result", "lobby_dense", "profile", "friends", "leaderboard", "challenge_incoming")
FINAL_SCENES = ("home", "lobby_dense", "lobby_long_names", "lobby_guest", "arcade_selected", "mentions",
                "private_chat", "rooms", "rooms_create", "community_room", "ranked", "ranked_select",
                "challenge_incoming", "challenge_waiting", "challenge_declined", "challenge_expired",
                "matched", "starting", "playing", "result", "reporting", "searching", "cancelling", "disconnect_retry", "leaderboard", "profile", "settings", "controls") + OFFER_SCENES + ACTIVITY_SCENES
SCENES = BASELINE_SCENES + ("home", "ranked", "ranked_select", "settings", "feedback") + ARCADE_SCENES + COMMUNITY_SCENES + OFFER_SCENES + ACTIVITY_SCENES
SIZES = ((1920, 1080), (1280, 720))
ART_FIELDS = {"hero", "image", "art", "render", "selfArt", "wordmark", "face", "plate", "portrait", "background"}
ART_LISTS = {"images", "mosaic"}
DECORATIVE_CLIPPING = ("shelfDecoration", "buildDecoration")
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
                      title="Tekken 4" if game == "t4" else "Tekken 5: Dark Resurrection",
                      short="T4" if game == "t4" else "T5DR", accent="#BE7449")
        # Deliberately share the presentation capabilities, as T4 does at runtime.
        self.snapshot.update(lobby_snapshot())
        self.snapshot["capabilities"].update(
            ranked=game != "t4", t4_lobby=game == "t4", private_rooms=True, friends=True,
            profiles=True, leaderboard=True, community_stats=True, community=True,
            room_tables=True, tournaments=True, spectating=True, account_tools=True,
            account_blocks=True, strict=game != "t4", online_feel=game != "t4")
        self.snapshot["netext"] = dict(online_feel="balanced")
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
                         history=[dict(opponent="Rival", ranked=True, result="win", status="confirmed", score=[3, 1],
                                       you_char="f3", opp_char="f1")]),
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
        self.empty_controls = False

    def settings(self):
        from tools.ui_shots import Synthetic
        return Synthetic.settings(self) + [dict(id="input_delay", label="@input_delay",
            options=[("auto", "@resolution.auto")] + [(str(n), str(n)) for n in range(5)],
            value=self.values.get("input_delay", "auto"), hint="@input_delay.hint", lead="@input_delay.lead")]

    def playtime(self):
        return dict(getattr(self, "playtime_stats", {}))

    def controls_supported(self):
        return True

    def controls(self):
        from tools.ui_shots import Synthetic
        return Synthetic.controls(self)

    def support_available(self):
        return True


def scene(game, chapter, language, nav_type=Nav, text_size=100, high_contrast=False):
    adapter = SyntheticOnline(game)
    requested = chapter
    arcade_scene = chapter if chapter in ARCADE_SCENES or chapter in COMMUNITY_SCENES else ""
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
        if requested == "lobby_dense":
            adapter.snapshot["players"] += [dict(id=f"p{n}",
                name=f"Player {n:02}" if n % 7 else f"Long community player name {n:02}",
                rank=("Beginner", "2nd Dan", "Warrior", "")[n % 4],
                **({"rating": 1200 + n * 17} if n % 5 else {}), main="f1" if n % 6 else "",
                status=("idle", "playing", "searching", "in_room")[n % 4],
                **({"ping": 20 + n * 4, "ping_measured": True} if n % 3 else {}))
                for n in range(7, 40)]
        chapter = "lobby"
    adapter.snapshot["capabilities"].update(private_chat=True, mentions=True, challenge_preferences=True)
    if requested == "lobby_guest":
        adapter.snapshot["account"] = False
        adapter.snapshot["me"]["guest"] = True
    adapter.snapshot["challenge_preferences"] = dict(first_to=2)
    adapter.texts.update(online_private_chat="", online_private_report_reason="")
    if requested in ("private_chat", "mentions", "chat_history", "native_composer", "pad_composer", "pad_osk"):
        adapter.snapshot["private_chat"] = dict(selected="p1" if requested == "private_chat" else "", unread=2,
            threads=[dict(id="p1", name="Rival", unread=0 if requested == "private_chat" else 2,
                messages=[dict(id="private-1", name="Rival", text="Ready for a practice set?"),
                          dict(id="private-2", name="Me", text="Yes, after this match.")]),
                     dict(id="p6", name="Player 6", unread=1, messages=[])])
        adapter.snapshot["chat"] = [dict(name="Rival", text="Hello @Me, ready for a set?", mentioned=True),
                                     dict(name="Me", text="Welcome!"),
                                     dict(name="Player 6", text="<b>Plain text</b> & a friendly lobby.")]
    if requested == "chat_history":
        adapter.snapshot["chat"] = [dict(name="Rival", text=f"Practice message {n + 1}") for n in range(48)]
    if requested == "lobby_long_names":
        adapter.snapshot["players"][0]["name"] = "A very long community player name"
        adapter.snapshot["players"][0].update(area="Central Europe", language="Deutsch / Français")
    if requested in ("rooms_create", "community_room"):
        chapter = "rooms"
    if requested == "community_room":
        adapter.snapshot["community"]["room"] = dict(id="r1", name="Evening practice", size=4, mode="line",
            lock="none", rotation="queue", in_line=True, host=False, line=["p1", "me", "p6"],
            members=[dict(id="p1", name="Rival"), dict(id="me", name="Me"), dict(id="p6", name="Player 6")],
            tables=[dict(id="1", players=["p1", "me"], wins=[1, 0], playing=True)])
    phase = {"searching": "searching", "activity_rooms": "searching", "activity_home": "searching", "cancelling": "cancelling", "matched": "matched", "matched_picks": "matched", "starting": "starting",
             "playing": "playing", "result": "result", "reporting": "result_sent", "disconnect_retry": "error"}.get(requested)
    if phase:
        adapter.snapshot.update(phase=phase, message={"searching": "@online.searching_casual",
            "cancelling": "@feedback.cancelling", "matched": "@online.match_found", "starting": "@online.starting",
            "playing": "@online.match_active", "result": "@online.result", "result_sent": "@online.result",
            "error": "@online.disconnected"}[phase],
            match=dict(opponent="Rival", ping=42, ping_measured=True, ranked=False))
        if phase in ("matched", "starting"):
            adapter.snapshot["match"].update(id="sample-match", seconds=27, delay=dict(auto=True, frames=2),
                first_to=2, rounds=3, ping_path="direct", opponent_ready=phase == "starting", mode="casual")
        if requested == "matched_picks":
            adapter.snapshot["match"].update(you_char="f4", opp_char="f2")
    if requested == "challenge_incoming":
        adapter.snapshot["challenge"] = dict(id="sample-incoming", name="Rival", player="p1", ping=42, ping_measured=True)
        adapter.snapshot["challenge_preferences"]["incoming"] = dict(id="sample-incoming", first_to=2, delay=dict(auto=True))
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
    from openrecomp import nav_feedback
    nav_feedback.observe_offers(nav, nav.game, adapter.snapshot)
    if requested in ACTIVITY_SCENES:
        if requested == "activity_home":
            nav.open_main_menu()
        else:
            nav.click_chapter("rooms")
        return nav
    if requested in OFFER_SCENES:
        from openrecomp import nav_feedback
        adapter.snapshot["challenge"] = dict(id="global-sample", name="Rival", player="p1", rank="2nd Dan", ping=42, ping_measured=True, seconds=24)
        adapter.snapshot["challenge_preferences"]["incoming"] = dict(id="global-sample", first_to=2, delay=dict(auto=True))
        if requested == "offer_shelf":
            nav.screen = "start"
        elif requested == "offer_home":
            nav.open_main_menu()
        else:
            nav.sec[game] = "settings"
        nav_feedback.observe_offers(nav, nav.game, adapter.snapshot)
        return nav
    if arcade_scene:
        if phase:
            return nav
        if requested == "controls":
            nav.sec[game] = "controls"
            return nav
        nav.click_chapter(chapter)
        if requested == "rooms_create":
            adapter.snapshot["community"]["first_to"] = True
            adapter.snapshot["community"]["preferences"]["first_to"] = 2
            nav.open_room_flow(nav.game, "create", "arcade_create_room")
        if arcade_scene == "arcade_options":
            nav.arcade_options = {game: True}
        elif arcade_scene == "arcade_cabinet":
            nav.arcade_more = {game: True}
        if requested.startswith("challenge_") and requested != "challenge_incoming":
            from openrecomp import nav_feedback
            terminal = requested.removeprefix("challenge_")
            kind = "pending" if terminal == "sent" else "waiting" if terminal == "waiting" else terminal
            receipt = dict(kind=kind, text="@feedback.sending" if kind == "pending" else
                "@online.challenge_sent" if kind == "waiting" else "@feedback." + terminal,
                age=12, name="Rival", action="challenge:p1", challenge="sample-offer", left=5)
            nav_feedback.records(nav, game)["challenge:p1"] = receipt
            if terminal in ("cancelled", "declined", "expired"):
                nav_feedback.finish(nav, receipt, kind, receipt["text"])
            if terminal == "waiting":
                adapter.snapshot["open_challenges"] = [dict(id="sample-offer", player="p1", name="Rival",
                    first_to=2, ping=42, ping_measured=True)]
        selected = {"arcade_selected": "challenge:p1", "arcade_cabinet": "arcade_watch:spec_watch_room:r1",
                    "player_busy": "challenge:p2", "player_self": "online_status", "private_chat": "online_private_chat",
                    "native_composer": "online_chat", "pad_composer": "online_chat", "pad_osk": "online_chat",
                    "rooms_create": "online_room_name", "community_room": "refresh_rooms"}.get(
            arcade_scene, "search_casual")
        items = nav.items()
        nav.focus[nav.key()] = next((n for n, item in enumerate(items) if item.get("id") == selected), 0)
        if requested == "native_composer":
            adapter.texts["online_chat"] = "Hello @Rival"
            nav.begin_edit("online_chat")
        elif requested == "pad_osk":
            nav._open_osk("online_chat")
        return nav
    if chapter == "home":
        nav.open_main_menu()
        return nav
    if chapter == "settings":
        nav.sec[game] = "settings"
        return nav
    if chapter in ("ranked", "ranked_select"):
        nav.open_ranked(nav.game)
        if chapter == "ranked_select":
            nav._open_fighters()
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
        if item.objectName() in DECORATIVE_CLIPPING:
            continue  # Intentionally cropped, non-interactive artwork-free background numerals.
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
        horizontal_scroll = False
        while parent:
            if parent.objectName() == "arcadePlayer":
                top = item.mapToItem(parent, QPointF(0, 0))
                bottom = item.mapToItem(parent, QPointF(item.width(), item.height()))
                if clip_reason(top.x(), top.y(), bottom.x(), bottom.y(), parent.width(), parent.height()):
                    problems.append(dict(record, reason="player-row-overflow", ancestor=parent.objectName()))
                    break
            if parent.clip():
                vertical_scroll = vertical_scroll or (
                    parent.property("contentHeight") is not None and
                    parent.property("contentY") is not None and
                    parent.property("contentHeight") > parent.height())
                top = item.mapToItem(parent, QPointF(0, 0))
                bottom = item.mapToItem(parent, QPointF(item.width(), item.height()))
                if (parent.objectName() in ("rankingCompactControls", "onlineChapters", "chatTabsViewport", "findOptionsViewport") and
                        parent.property("contentX") is not None and
                        parent.property("contentWidth") is not None and
                        parent.property("contentWidth") > parent.width()):
                    offset = parent.property("contentX")
                    if top.x() + offset < -2 or bottom.x() + offset > parent.property("contentWidth") + 2:
                        problems.append(dict(record, reason="scroll-content-overflow", ancestor=parent.objectName()))
                        break
                    horizontal_scroll = True
                reason = clip_reason(top.x(), top.y(), bottom.x(), bottom.y(),
                                     parent.width(), parent.height(), vertical_scroll, horizontal_scroll)
                if reason:
                    problems.append(dict(record, reason=reason, ancestor=parent.objectName()))
                    break
            parent = parent.parentItem()
    return problems, elided


def clip_reason(left, top, right, bottom, width, height, vertical_scroll=False, horizontal_scroll=False):
    if not horizontal_scroll and (left < -2 or right > width + 2):
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
                # Six scenes per page preserve readable review scale in ordinary image viewers.
                for start in range(0, len(scenes), 6):
                    selected = scenes[start:start + 6]
                    page = QImage(columns * tw, ((len(selected) + 1) // columns) * (th + 28), QImage.Format_RGB32)
                    page.fill(QColor("#08090A"))
                    painter = QPainter(page)
                    painter.setPen(QColor("#ECE9E1"))
                    for index, chapter in enumerate(selected):
                        x, y = index % columns * tw, index // columns * (th + 28)
                        capture = QImage(str(out / language / game / f"{width}x{height}" / f"{chapter}.png"))
                        painter.drawImage(x, y + 28, capture.scaled(tw, th))
                        painter.drawText(x + 8, y + 20, f"{language} / {game} / {chapter} / {width}x{height}")
                    painter.end()
                    page.save(str(out / f"contact-{language}-{game}-{width}x{height}-page{start // 6 + 1:02}.png"))


def capture_home(phase, text_size, high_contrast=False, batch=None, platform="offscreen"):
    profile = "-".join((phase, text_size, "contrast" if high_contrast else "standard", batch or "default", platform))
    return ROOT / "build" / "tmp-home" / "uipolish5" / ("online-" + profile)


def merge_captures(previous, current):
    """Replace recaptured scene records without losing the other reviewed scenes."""
    def key(record):
        return tuple(record[field] for field in ("language", "game", "scene", "size"))
    records = {key(record): record for record in previous}
    records.update((key(record), record) for record in current)
    return list(records.values())


def main(argv=None):
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--ui-dir", type=Path)
    parser.add_argument("--languages", nargs="+", choices=list(i18n.LANGUAGES), default=list(i18n.LANGUAGES))
    parser.add_argument("--games", nargs="+", choices=("t5", "t4"), default=["t5", "t4"])
    parser.add_argument("--scenes", nargs="+", choices=SCENES)
    parser.add_argument("--text-size", choices=("normal", "large", "larger"), default="normal")
    parser.add_argument("--high-contrast", action="store_true")
    parser.add_argument("--batch", choices=("presentation", "arcade", "community", "final", "portraits"))
    parser.add_argument("--merge-report", action="store_true", help="Refresh selected scenes and retain the complete report and contact sheets")
    parser.add_argument("--platform", choices=("offscreen", "windows"), default="offscreen")
    args = parser.parse_args(argv)
    home = capture_home(args.phase, args.text_size, args.high_contrast, args.batch, args.platform)
    home.mkdir(parents=True, exist_ok=True)
    for name in ("OPENRECOMP_HOME", "APPDATA", "LOCALAPPDATA", "TMP", "TEMP"):
        os.environ[name] = str(home)
    if args.scenes is None:
        args.scenes = list(PORTRAIT_SCENES if args.batch == "portraits" else
                           ARCADE_SCENES if args.batch == "arcade" else
                           COMMUNITY_SCENES if args.batch == "community" else
                           FINAL_SCENES if args.batch == "final" else
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
    from tools.ui_shots import font_coverage_details

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
    if args.batch == "final":
        out = ROOT / "build" / "shots" / "final" / phase
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
                    layout = layout_geometry(window)
                    records.append(dict(language=language, game=game, scene=chapter, size=f"{width}x{height}",
                                        path=path.relative_to(ROOT).as_posix(), overflow=overflow, elided=elided,
                                        layout=layout, visible_player_rows=sum(row.get("fullyVisible", False) for row in layout if row["name"] == "arcadePlayer"),
                                        collisions=layout_problems(layout)))
            print(f"{args.phase}: {language} / {game}: {len(args.scenes) * 2} synthetic captures", flush=True)
    coverage_details = font_coverage_details()
    coverage = {language: detail["covered"] for language, detail in coverage_details.items()}
    limitations = [f"{lang}: catalog glyph coverage incomplete; actual glyph layout remains unverified"
                   for lang, covered in coverage.items() if not covered]
    if args.merge_report and (out / "report.json").exists():
        previous = json.loads((out / "report.json").read_text(encoding="utf-8"))
        records = merge_captures(previous.get("captures", []), records)
        warnings = list(dict.fromkeys(previous.get("qml_warnings", []) + warnings))
    (out / "report.json").write_text(json.dumps(dict(captures=records, qml_warnings=warnings,
        font_coverage=coverage, font_coverage_details=coverage_details, limitations=limitations,
        geometry_exclusions=dict(art_free_background_numerals=DECORATIVE_CLIPPING)), ensure_ascii=False, indent=2), encoding="utf-8")
    sheet_scenes = [name for name in (FINAL_SCENES if args.batch == "final" else SCENES)
                    if any(record["scene"] == name for record in records)] if args.merge_report else args.scenes
    contact_sheets(out, args.languages, args.games, sheet_scenes)
    window.setProperty("allowClose", True)
    window.close()
    print(f"Saved {len(records)} synthetic captures to {out.relative_to(ROOT).as_posix()}")
    if warnings:
        print("QML warnings:\n" + "\n".join(sorted(set(warnings))), file=sys.stderr)
        return 1
    return 0


def layout_geometry(window):
    """Record actual rendered bounds for the community panes and fixed-height rows."""
    from PySide6.QtCore import QPointF

    records = []
    def visit(item):
        for child in item.childItems():
            if child.isVisible() and child.opacity() > 0 and child.width() > 0 and child.height() > 0:
                name = child.objectName()
                if name in ("lobbyPlayersPane", "lobbyChatPane", "lobbyNotice", "arcadePlayer", "editableField",
                            "lobbyLivePane", "lobbyRoomsPane", "onlineProfile", "onlineFind", "onlineChapters",
                            "onlineRankedAction", "onlineCasualAction", "arcadePlayerPortrait", "playerInlineActions"):
                    top = child.mapToScene(QPointF(0, 0))
                    bottom = child.mapToScene(QPointF(child.width(), child.height()))
                    record = dict(name=name, x=round(top.x(), 2), y=round(top.y(), 2),
                        width=round(bottom.x() - top.x(), 2), height=round(bottom.y() - top.y(), 2))
                    if name == "arcadePlayer":
                        fully_visible = True
                        ancestor = child.parentItem()
                        while ancestor:
                            if ancestor.clip():
                                left = child.mapToItem(ancestor, QPointF(0, 0))
                                right = child.mapToItem(ancestor, QPointF(child.width(), child.height()))
                                fully_visible = fully_visible and left.x() >= -.1 and left.y() >= -.1 and right.x() <= ancestor.width() + .1 and right.y() <= ancestor.height() + .1
                            ancestor = ancestor.parentItem()
                        record["fullyVisible"] = fully_visible
                    records.append(record)
                visit(child)
    visit(window.contentItem())
    return records


def layout_problems(records):
    """A notice and either permanent pane must never occupy the same output pixels."""
    names = ("lobbyPlayersPane", "lobbyChatPane", "lobbyNotice", "lobbyLivePane", "lobbyRoomsPane",
             "onlineProfile", "onlineFind", "onlineChapters")
    panes = [row for row in records if row["name"] in names]
    problems = []
    for index, first in enumerate(panes):
        for second in panes[index + 1:]:
            width = min(first["x"] + first["width"], second["x"] + second["width"]) - max(first["x"], second["x"])
            height = min(first["y"] + first["height"], second["y"] + second["height"]) - max(first["y"], second["y"])
            if width > 1 and height > 1:
                problems.append(dict(reason="pane-overlap", first=first["name"], second=second["name"],
                                     width=round(width, 2), height=round(height, 2)))
    return problems


if __name__ == "__main__":
    raise SystemExit(main())
