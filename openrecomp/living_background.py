"""Small, main-first runtime art projection. No Qt, decoding or file access here."""
import time

from .nav_common import uri
from .player_main import choose_main

ROTATE_SECONDS = 18
ROSTER_SECONDS = 30


def _optional(adapter, method, *args):
    try:
        return getattr(adapter, method)(*args)
    except Exception:  # noqa: BLE001 -- decorative art must never stop navigation
        return ""


def background_view(adapter, theme, main="", reduced_motion=False, now=None):
    """Request one installed render per rotation; never eagerly decode the roster.

    The adapter owns decoding and its local cache. Missing images are retried only
    once a second while its worker runs. Reduced motion also stops fighter cycling.
    """
    result = dict(theme=theme, source="", fighter="", slot=0, hasArt=False,
                  interval=ROTATE_SECONDS)
    if theme not in ("t4", "t5dr"):
        return result
    now = time.monotonic() if now is None else now
    if not main:
        state = _optional(adapter, "online_state")
        main = choose_main(state.get("me")) if isinstance(state, dict) else ""
    identity = (theme, main)
    cache = getattr(adapter, "_living_background", None)
    if not isinstance(cache, dict) or cache.get("identity") != identity:
        cache = dict(identity=identity, started=now, roster_at=float("-inf"),
                     roster=[], key=None, retry=float("-inf"), source="", complete=False)
        adapter._living_background = cache
    if now - cache["roster_at"] >= (ROSTER_SECONDS if cache["roster"] else 5):
        roster = _optional(adapter, "fighters")
        roster = roster if isinstance(roster, (list, tuple)) else []
        roster = [row for row in roster if isinstance(row, dict) and row.get("key")]
        choice = main or _optional(adapter, "main_fighter")
        first = next((row for row in roster if choice in (row.get("key"), row.get("name"))), None)
        cache["roster"] = ([first] if first else []) + [row for row in roster if row is not first]
        cache["roster_at"] = now
    roster = cache["roster"]
    slot = 0 if reduced_motion or not roster else int(max(0, now - cache["started"]) // ROTATE_SECONDS) % len(roster)
    row = roster[slot] if roster else {}
    key = row.get("key", "")
    if cache["key"] != key or not cache["complete"] and now >= cache["retry"]:
        picture = _optional(adapter, "fighter_render", key) if key else ""
        complete = bool(picture)
        if not picture and key:
            picture = _optional(adapter, "fighter_image", key)
        if not picture:
            picture = _optional(adapter, "hero")
            complete = not key and bool(picture)
        try:
            source = uri(picture) if isinstance(picture, str) else ""
        except (ValueError, TypeError):
            source = ""
        cache.update(key=key, source=source, retry=now + 1, complete=complete and bool(source))
    result.update(source=cache["source"], fighter=row.get("name", ""),
                  slot=slot, hasArt=bool(cache["source"]))
    return result
