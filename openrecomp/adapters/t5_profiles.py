"""Read-only profile, leaderboard and community views through the installed client."""
import copy
import math
import time

from ..player_main import choose_main, local_main


PAGE = 20
MODES = ("all", "ranked", "casual")
SORTS = ("matches", "winrate", "fighter")
BOARD_SORTS = ("place", "name", "rating", "ranked_wins", "ranked_losses", "casual_wins", "casual_losses", "rank", "main")
PREFIX = "feature_profile:"


def init(owner):
    if not hasattr(owner, "_t5_profile"):
        owner._t5_profile = {}
        owner._t5_profile_target = None
        owner._t5_profile_offset = 0
        owner._t5_board = dict(rows=[], offset=0, has_next=False, sort="place", descending=False)
        owner._t5_stats = dict(mode="all", sort="matches", fighters=[])
    owner._online_fields.setdefault("online_profile_name", "")


def reset(owner):
    if hasattr(owner, "_t5_profile"):
        del owner._t5_profile
    init(owner)
    owner._online_fields["online_profile_name"] = ""


def _number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _fields(source, texts=(), numbers=(), flags=()):
    if not isinstance(source, dict):
        return {}
    out = {key: source[key][:160] for key in texts if isinstance(source.get(key), str)}
    out.update({key: source[key] for key in numbers if _number(source.get(key))})
    out.update({key: source[key] for key in flags if isinstance(source.get(key), bool)})
    return out


def _counts(source):
    out = _fields(source, numbers=("games", "wins", "losses", "draws", "win_rate"))
    return {key: max(0, value) for key, value in out.items()}


def _history(rows):
    out = []
    for source in rows[:PAGE] if isinstance(rows, list) else ():
        row = _fields(source, texts=("opponent", "you_char", "opp_char"), numbers=("time", "delta"), flags=("ranked",))
        if not row:
            continue
        for key, values in (("result", ("win", "loss", "draw", "none", "won", "lost")),
                            ("status", ("confirmed", "onesided", "forfeit", "resolved", "disputed", "void", "training")),
                            ("reason", ("desync", "too_short", "disputed", "crash", "early_quit", "quit", "disconnect",
                                        "connection", "no_report", "both_left", "timeout", "crash_repeat", "early_quit_repeat",
                                        "no_report_repeat", "score_mismatch", "no_result", "set_restart", "no_return"))):
            if source.get(key) in values:
                row[key] = source[key]
        score = source.get("score")
        if isinstance(score, (list, tuple)) and len(score) == 2 and all(_number(n) for n in score):
            row["score"] = list(score)
        info = source.get("set")
        if isinstance(info, dict):
            row["set"] = _fields(info, numbers=("game", "best_of", "first_to"), flags=("ended",))
            if isinstance(info.get("wins"), (list, tuple)) and len(info["wins"]) == 2 and all(_number(n) for n in info["wins"]):
                row["set"]["wins"] = list(info["wins"])
        out.append(row)
    return out


def _profile(source):
    out = _fields(source, texts=("name", "rank", "main", "peak_rank"),
                  numbers=("rating", "rd", "place", "ranked_games", "voids_24h"), flags=("account", "self", "provisional"))
    if not isinstance(source, dict):
        return out
    if source.get("badge") == "dev":
        out["badge"] = "dev"
    if source.get("self") is True and _number(source.get("recovery_codes_left")):
        out["recovery_codes_left"] = source["recovery_codes_left"]
    rec = source.get("record")
    if isinstance(rec, (list, tuple)) and len(rec) <= 3 and all(_number(n) for n in rec):
        out["record"] = list(rec)
    stats = source.get("stats")
    if isinstance(stats, dict):
        out["stats"] = {mode: _counts(stats[mode]) for mode in ("ranked", "casual") if isinstance(stats.get(mode), dict)}
    for key in ("chars", "ranked_chars"):
        if isinstance(source.get(key), list):
            out[key] = [dict(char=row["char"][:80], **_counts(row)) for row in source[key][:100]
                        if isinstance(row, dict) and isinstance(row.get("char"), str)]
    out["history"] = _history(source.get("history"))
    out["main"] = choose_main(source)
    return out


def _link_replays(owner):
    profile = owner._t5_profile
    if not (profile.get("self") and str(profile.get("name", "")).casefold() == owner._online_name.casefold()):
        return
    match = getattr(getattr(owner, "rp", None), "for_history", None)
    if not callable(match) or not callable(getattr(owner, "replay_entries", None)):
        return
    try:
        entries = owner.replay_entries()
        ids = {row["key"]: row["id"] for row in owner._fighter_table() if "key" in row and "id" in row}
        for row in profile.get("history") or []:
            entry = match(entries, row.get("time"), mine=ids.get(row.get("you_char")),
                          theirs=ids.get(row.get("opp_char")), opponent=row.get("opponent"), score=row.get("score"))
            if entry is not None:
                index = next((index for index, candidate in enumerate(entries) if candidate is entry), None)
                if index is not None:
                    row["replay_id"] = str(index)
    except (OSError, ValueError, TypeError, AttributeError):
        # An older replay module cannot prevent the server profile being read.
        return

def _board(rows):
    out = []
    for source in rows[:PAGE] if isinstance(rows, list) else ():
        row = _fields(source, texts=("name", "rank", "main"),
                      numbers=("place", "rating", "tier", "wins", "losses", "ranked_wins", "ranked_losses", "casual_wins", "casual_losses"),
                      flags=("online", "provisional"))
        if row.get("name"):
            row["main"] = choose_main(source)
            if source.get("badge") == "dev":
                row["badge"] = "dev"
            out.append(row)
    return out


def _stats(source):
    out = _fields(source, numbers=("made", "accounts", "players", "matches", "ranked", "matches_24h", "players_24h"))
    out["fighters"] = []
    for source_row in source.get("fighters", [])[:100] if isinstance(source, dict) and isinstance(source.get("fighters"), list) else ():
        if not isinstance(source_row, dict) or not isinstance(source_row.get("char"), str):
            continue
        row = dict(char=source_row["char"][:80])
        for mode in ("ranked", "casual"):
            counts = source_row.get(mode)
            if isinstance(counts, (list, tuple)) and len(counts) == 3 and all(_number(n) and n >= 0 for n in counts):
                row[mode] = list(counts)
        if "ranked" in row and "casual" in row:
            out["fighters"].append(row)
    return out


def _supported(client, name):
    return callable(getattr(client, name, None))


def _stats_ok(client):
    if not _supported(client, "stats"):
        return False
    check = getattr(client, "has_stats", False)
    try:
        return bool(check() if callable(check) else check)
    except Exception:  # noqa: BLE001 -- unsupported installed clients keep the page hidden
        return False


def state(owner):
    init(owner)
    client = owner._online_client
    return dict(capabilities=dict(profiles=_supported(client, "profile"), leaderboard=_supported(client, "leaderboard"),
                                  community_stats=_stats_ok(client)),
                profile=copy.deepcopy(owner._t5_profile), leaderboard=copy.deepcopy(owner._t5_board),
                community_stats=copy.deepcopy(owner._t5_stats), profile_history_offset=owner._t5_profile_offset)


def _submit(owner, client, verb, work):
    generation = owner._online_generation

    def guarded():
        owner._online_check_request(generation, client)
        return work()
    owner._online_submit(PREFIX + verb, guarded)


def action(owner, request, client):
    init(owner)
    recognized = request.startswith(("profile_", "profile_player:", "profile_board:", "leaderboard_", "stats_"))
    if not recognized:
        return False
    if owner._online_busy or owner._online_phase != "logged_in" or client is None:
        return True
    if request in ("profile_self", "profile_load") or request.startswith(("profile_player:", "profile_board:")):
        if not _supported(client, "profile"):
            return True
        name = None
        if request == "profile_load":
            name = owner._online_fields["online_profile_name"].strip()[:64] or None
        elif request.startswith("profile_player:"):
            player = next((row for row in owner._online_players if str(row.get("id")) == request.partition(":")[2]), None)
            if player is None:
                return True
            name = player.get("name")
        elif request.startswith("profile_board:"):
            name = request.partition(":")[2]
            if not any(row.get("name") == name for row in owner._t5_board["rows"]):
                return True
        _submit(owner, client, "load", lambda: (name, client.profile(name, history=PAGE)))
    elif request in ("profile_history_next", "profile_history_previous"):
        if not owner._t5_profile or not _supported(client, "history"):
            return True
        if request.endswith("next") and len(owner._t5_profile.get("history", [])) < PAGE:
            return True
        offset = max(0, owner._t5_profile_offset + (PAGE if request.endswith("next") else -PAGE))
        target = owner._t5_profile_target
        _submit(owner, client, "history", lambda: (offset, client.history(target, limit=PAGE, offset=offset)))
    elif request.startswith("leaderboard_sort:"):
        field = request.partition(":")[2]
        if field in BOARD_SORTS:
            board = owner._t5_board
            board["descending"] = not board["descending"] if board["sort"] == field else field not in ("name", "place", "main")
            board["sort"] = field
    elif request in ("leaderboard_refresh", "leaderboard_next", "leaderboard_previous"):
        if not _supported(client, "leaderboard"):
            return True
        board = owner._t5_board
        if request.endswith("next") and not board["has_next"]:
            return True
        offset = max(0, board["offset"] + (PAGE if request.endswith("next") else -PAGE if request.endswith("previous") else 0))
        _submit(owner, client, "board", lambda: (offset, client.leaderboard(limit=PAGE, offset=offset)))
    elif request == "stats_refresh":
        if _stats_ok(client):
            _submit(owner, client, "stats", client.stats)
    elif request.startswith("stats_mode:"):
        mode = request.partition(":")[2]
        if mode in MODES:
            owner._t5_stats["mode"] = mode
    elif request.startswith("stats_sort:"):
        sort = request.partition(":")[2]
        if sort in SORTS:
            owner._t5_stats["sort"] = sort
    return True


def completion(owner, operation, value, error):
    if not operation.startswith(PREFIX):
        return False
    init(owner)
    if error:
        owner._online_message = owner._online_error(error)
        return True
    verb = operation[len(PREFIX):]
    if verb == "load":
        target, source = value
        owner._t5_profile = _profile(source)
        if owner._t5_profile.get("self") is True and not owner._t5_profile.get("main"):
            owner._t5_profile["main"] = local_main(owner)
        owner._t5_profile_target = target
        owner._t5_profile_offset = 0
        _link_replays(owner)
    elif verb == "history":
        offset, source = value
        owner._t5_profile["history"] = _history(source)
        owner._t5_profile_offset = offset
        _link_replays(owner)
    elif verb == "board":
        offset, source = value
        owner._t5_board.update(rows=_board(source), offset=offset,
                               has_next=isinstance(source, list) and len(source) >= PAGE, updated=time.time())
    elif verb == "stats":
        owner._t5_stats.update(_stats(value))
    owner._online_message = "@online.profile_updated"
    return True


def event(owner, incoming):
    return False


def close(owner):
    reset(owner)



