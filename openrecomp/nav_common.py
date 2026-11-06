"""Shared navigation constants and plain helpers. No Qt."""
import pathlib

SECTION_TITLES = {"play": "section.play", "online": "section.online", "build": "section.build", "replays": "section.replays", "settings": "section.settings", "controls": "section.controls", "support": "section.support"}
GLYPHS = {
    "xbox": dict(confirm="A", back="B", x="X", social="Y", prev="LB", next="RB", play="Start", switchGame="View", right="‹ ›",
                 chapterPrev="LT", chapterNext="RT", chapters="LT RT", progress="F7"),
    "ps": dict(confirm="✕", back="○", x="□", social="△", prev="L1", next="R1", play="Options", switchGame="Share", right="‹ ›",
               chapterPrev="L2", chapterNext="R2", chapters="L2 R2", progress="F7"),
    "kb": dict(confirm="Enter", back="Esc", x="X", social="F", prev="Q", next="E", play="Space", switchGame="G", right="← →",
               chapterPrev="PgUp", chapterNext="PgDn", chapters="PgUp PgDn", progress="F7"),
}
TRAIL = dict(up="↑", down="↓", left="←", right="→", confirm="A", back="B", x="X", social="Y", prev="LB", next="RB", play="St", switchGame="Vw",
             chapterPrev="LT", chapterNext="RT")
DEVICE_LABEL = dict(xbox="device.xbox", ps="device.ps", kb="device.kb")
OSK = ("1234567890", "QWERTYUIOP", "ASDFGHJKL-", "ZXCVBNM_.,")
OSK_ACTIONS = (("space", "osk.space"), ("del", "osk.delete"), ("done", "osk.done"))
ROWS_VISIBLE = 9
PICKER_VISIBLE = 11
SCREEN_W = 1920
WIDE, SPINE_GAME, SPINE_SLOT, GAP = 1040, 260, 140, 2
GRID_COLS = 9
HOLD_SECONDS = 1.5
FRIENDLY_RESULT = {"W": True, "L": False}


def uri(path):
    return pathlib.Path(path).as_uri() if path else ""


def window(count, focus, size):
    """First visible index so that `focus` stays in a list of `size` rows."""
    if count <= size:
        return 0
    return max(0, min(count - size, focus - size // 2))


def badge(g):
    """What kind of recomp a game is, from its manifest: PS3 RECOMP."""
    platform = g.m.get("platform", "")
    return f"{platform} RECOMP".upper() if platform else ""


PROVISIONAL_GAMES = 3        # "provisional" / placement is for a player's first 3 ranked matches only (0.1.5)


def ranked_count(p):
    """How many ranked matches this player (lobby row, profile, leaderboard row) has played, or None when the data
    does not say. The server's own provisional flag follows rating uncertainty and stays on for many matches."""
    placement = p.get("placement")
    if isinstance(placement, (list, tuple)) and placement:
        return placement[0]
    games = p.get("ranked_games")
    if isinstance(games, int) and not isinstance(games, bool):
        return games
    won, lost = p.get("ranked_wins"), p.get("ranked_losses")
    if all(isinstance(n, int) and not isinstance(n, bool) for n in (won, lost)):
        return won + lost
    return None


def provisional(p):
    """True only while the first PROVISIONAL_GAMES ranked matches are not played yet."""
    count = ranked_count(p)
    return bool(p.get("provisional") or p.get("placement")) and count is not None and count < PROVISIONAL_GAMES


def placing(p):
    """The (done, total) placement of a player who is still inside the first matches, else None."""
    placement = p.get("placement")
    return tuple(placement) if placement and placement[0] < PROVISIONAL_GAMES else None
