"""Choose a player's main from public usage counts, without Qt or game access."""
from datetime import datetime, timezone
import math


def _number(value):
    try:
        return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else 0
    except OverflowError:
        return 0


def _recent(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()
        except (ValueError, OverflowError, OSError):
            return 0
    return _number(value)


def _key(value):
    return value if (isinstance(value, str) and 0 < len(value) <= 80 and value.isprintable()
                     and value.casefold() not in ("random", "none")) else ""


def _rows(value):
    if isinstance(value, dict):
        return [dict(row, char=key) if isinstance(row, dict) else
                dict(char=key, games=row[0], wins=row[1], last_played=row[2] if len(row) > 2 else 0)
                for key, row in list(value.items())[:200]
                if isinstance(row, dict) or isinstance(row, (list, tuple)) and len(row) >= 2]
    return value[:200] if isinstance(value, (list, tuple)) else []


def _counts(rows):
    counts = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _key(row.get("char") or row.get("character") or row.get("fighter"))
        if not key:
            continue
        games = row.get("games", row.get("matches", row.get("played")))
        wins = row.get("wins")
        if games is None:
            modes = [row[mode] for mode in ("ranked", "casual") if isinstance(row.get(mode), (list, tuple)) and len(row[mode]) >= 2]
            games = sum(_number(mode[0]) for mode in modes) if modes else sum(_number(row.get(field)) for field in ("wins", "losses", "draws"))
            if wins is None and modes:
                wins = sum(_number(mode[1]) for mode in modes)
        recent = max((_recent(row.get(field)) for field in ("last_played", "last_used", "last", "time", "recent", "last_played_at", "last_match")), default=0)
        total = counts.setdefault(key, [0, 0, 0])
        total[0] += _number(games)
        total[1] += _number(wins)
        total[2] = max(total[2], recent)
    return counts


def _winner(counts):
    candidates = [key for key, values in counts.items() if values[0] > 0]
    return max(sorted(candidates), key=lambda key: tuple(counts[key])) if candidates else ""


def _zero_games(source):
    record = source.get("record")
    if (isinstance(record, (list, tuple)) and 2 <= len(record) <= 3
            and all(type(value) in (int, float) and value == 0 for value in record)):
        return True
    return any(type(source.get(field)) in (int, float) and source[field] == 0 for field in ("games", "matches"))


def choose_main(source, history=None):
    """Most games, then wins, then latest play; an old server's Main is its summary.

    All-mode usage takes precedence over ranked-only profile tables. A local history
    is a fallback only; other players' partial history is never inferred as usage.
    """
    source = source if isinstance(source, dict) else {}
    has_usage = any(field in source for field in ("char_usage", "chars", "ranked_chars", "casual_chars"))
    if "char_usage" in source:
        rows = _rows(source["char_usage"])
    elif "chars" in source:
        rows = _rows(source["chars"])
    else:
        rows = _rows(source.get("ranked_chars")) + _rows(source.get("casual_chars"))
    main = _winner(_counts(rows))
    if not main and not has_usage and not _zero_games(source):
        main = _key(source.get("main"))
    if main or not isinstance(history, (list, tuple)):
        return main
    rows = []
    for index, row in enumerate(history):
        if not isinstance(row, dict) or row.get("status") in ("void", "training"):
            continue
        key = _key(row.get("you_char") or row.get("char"))
        if key:
            rows.append(dict(char=key, games=1, wins=int(row.get("result") in ("win", "won") or row.get("won") is True),
                             last_played=row.get("time", row.get("when", len(history) - index))))
    return _winner(_counts(rows))


def local_main(owner):
    """Local match history only; no current character preference or default art."""
    profile = getattr(owner, "_t5_profile", {})
    own = (isinstance(profile, dict) and profile.get("self") is True
           and isinstance(profile.get("name"), str)
           and profile["name"].casefold() == str(getattr(owner, "_online_name", "")).casefold())
    main = (choose_main(dict(main=profile.get("main"), record=profile.get("record"))) or choose_main(profile)) if own else ""
    if main:
        return main
    history = profile.get("history", []) if own else []
    entries = getattr(owner, "replay_entries", None)
    table = getattr(owner, "_fighter_table", None)
    if not callable(entries) or not callable(table):
        return choose_main({}, history)
    try:
        keys = {row["id"]: row["key"] for row in table() if "id" in row and "key" in row}
        local_history = [dict(you_char=keys.get(entry.p1 if entry.slot == 0 else entry.p2, ""),
                        won=entry.won, when=entry.when) for entry in entries() if entry.complete]
        return choose_main({}, local_history) or choose_main({}, history)
    except (OSError, ValueError, TypeError, AttributeError):
        return choose_main({}, history)
