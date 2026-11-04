"""Allowlisted public lobby metadata for cards; no client requests or file access."""
from ..player_main import choose_main


def players(value, known=()):
    if not isinstance(value, (list, tuple)):
        return []
    lookup = {}
    for p in known:
        if isinstance(p, dict):
            pid = str(p.get("id"))
            lookup[pid] = dict(lookup.get(pid, {}), **p)
    out = []
    for item in value[:200]:
        source = dict(lookup.get(str(item.get("id")), {}), **item) if isinstance(item, dict) else lookup.get(str(item), {})
        row = {key: str(source[key])[:limit] for key, limit in (("id", 80), ("name", 64), ("main", 40))
               if isinstance(source.get(key), (str, int)) and not isinstance(source.get(key), bool)}
        if row:
            row["main"] = choose_main(source)
        if source.get("state") in ("playing", "ready", "away"):
            row["state"] = source["state"]
        if row:
            out.append(row)
    return out


def score(value):
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 10 ** 7 for n in value)):
        return list(value)
    return []


def match(source, known=()):
    info = source.get("match") if isinstance(source.get("match"), dict) else {}
    people = players(info.get("players") or source.get("match_players") or source.get("players"), known)
    if len(people) > 2:
        people = [p for p in people if p.get("state") == "playing"]
    result = {}
    if len(people) == 2:
        result["players"] = people
    set_info = source.get("set") if isinstance(source.get("set"), dict) else {}
    wins = score(info.get("score") or source.get("score") or set_info.get("wins"))
    if wins:
        result["score"] = wins
    return result
