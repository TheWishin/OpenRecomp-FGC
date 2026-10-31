"""Controller rows for the installed client's public records and statistics."""
from datetime import datetime

from . import i18n


_COUNT_LABELS = (("games", "@online.games"), ("wins", "@online.wins"), ("losses", "@online.losses"),
                 ("draws", "@online.draws"), ("win_rate", "@online.win_rate"))
_BOARD_LABELS = (("place", "@online.place"), ("rating", "@rating"), ("rank", "@online.rank"),
                 ("wins", "@online.wins"), ("losses", "@online.losses"),
                 ("ranked_wins", "@online.ranked_wins"), ("ranked_losses", "@online.ranked_losses"),
                 ("casual_wins", "@online.casual_wins"), ("casual_losses", "@online.casual_losses"))


def _detail(iid, title, kicker, details, hint="@online.profile_hint", value=""):
    return dict(kind="action", id=iid, label=title, value=value, hint=hint,
                detail=dict(kicker=kicker, title=title, lead=hint, rows=details))


def _stamp(value):
    try:
        return datetime.fromtimestamp(float(value)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""

def _counts(data):
    out = [dict(k=label, v=str(data[key]) + (" %" if key == "win_rate" else ""))
           for key, label in _COUNT_LABELS if key in data]
    if "win_rate" not in data and data.get("games", 0) > 0 and "wins" in data:
        out.append(dict(k="@online.win_rate", v=f"{100 * data['wins'] / data['games']:.2f} %"))
    return out


def _fighter(g, key):
    return next((fighter.get("name") or key for fighter in g.a.fighters() if fighter.get("key") == key), key)


def _profile_rows(nav, g, state, action):
    profile = state.get("profile") or {}
    title = i18n.literal(profile.get("name") or state.get("name") or "")
    details = [dict(k=label, v=i18n.literal(profile[key])) for key, label in
               (("rank", "@online.rank"), ("rating", "@rating"), ("rd", "@online.rating_uncertainty"),
                ("place", "@online.place"), ("peak_rank", "@online.peak_rank"),
                ("ranked_games", "@online.ranked_matches"), ("voids_24h", "@online.voids_24h"),
                ("recovery_codes_left", "@online.recovery_left")) if key in profile]
    if profile.get("main"):
        details.append(dict(k="@fighter.main", v=i18n.literal(_fighter(g, profile["main"]))))
    if profile.get("provisional"):
        details.append(dict(k="@online.rank", v="@online.provisional"))
    if profile.get("badge") == "dev":
        details.append(dict(k="@online.name", v="@online.dev_badge"))
    record = profile.get("record") or []
    details += [dict(k=label, v=str(value)) for value, label in zip(record, ("@online.wins", "@online.losses", "@online.draws"))]
    out = [_detail("profile_summary", title, "@online.profile", details)]
    stats = profile.get("stats") or {}
    if stats:
        total = {key: sum(mode.get(key, 0) for mode in stats.values()) for key in ("games", "wins", "losses", "draws")}
        out.append(_detail("profile_stats:all", "@online.all", "@online.profile", _counts(total)))
    for mode, label in (("ranked", "@online.ranked_mode"), ("casual", "@online.casual_mode")):
        if mode in stats:
            out.append(_detail("profile_stats:" + mode, label, "@online.profile", _counts(stats[mode])))
    for row in profile.get("chars") or []:
        out.append(_detail("profile_char:" + row["char"], i18n.literal(_fighter(g, row["char"])), "@online.profile", _counts(row)))
    if "ranked_chars" in profile:
        out.append(dict(kind="heading", label="@online.ranked_chars"))
        for row in profile["ranked_chars"]:
            out.append(_detail("profile_ranked_char:" + row["char"], i18n.literal(_fighter(g, row["char"])),
                               "@online.ranked_chars", _counts(row)))
        if not profile["ranked_chars"]:
            out.append(_detail("no_ranked_chars", "@online.no_ranked_chars", "@online.ranked_chars", []))
    out.append(dict(kind="heading", label="@online.history"))
    for index, row in enumerate(profile.get("history") or []):
        result = {"win": "@online.result_win", "won": "@online.result_win", "loss": "@online.result_loss",
                  "lost": "@online.result_loss", "draw": "@online.draws"}.get(row.get("result"), "@online.result_none")
        details = [dict(k="@date", v=_stamp(row.get("time"))), dict(k="@result", v=result)]
        if row.get("status"):
            details.append(dict(k="@online.history_status", v="@online.history_" + row["status"]))
        if row.get("reason"):
            details.append(dict(k="@online.history_reason", v="@online.history_" + row["reason"]))
        for key in ("you_char", "opp_char"):
            if row.get(key):
                details.append(dict(k="@fighter" if key == "you_char" else "@online.opponent",
                                    v=i18n.literal(_fighter(g, row[key]))))
        score = row.get("score")
        if score:
            details.append(dict(k="@online.score", v=" : ".join(str(n) for n in score)))
        if "delta" in row:
            details.append(dict(k="@rating", v=f"{row['delta']:+g}"))
        if row.get("set"):
            info = row["set"]
            for key, label in (("game", "@online.set_game_label"), ("first_to", "@online.first_to_label")):
                if key in info:
                    details.append(dict(k=label, v=str(info[key])))
            if info.get("wins"):
                details.append(dict(k="@online.score", v=" : ".join(str(n) for n in info["wins"])))
        out.append(_detail("profile_history:" + str(index), i18n.literal(row.get("opponent") or ""),
                           "@online.history", details, value=result))
        if row.get("replay_id") is not None:
            replay_id = row["replay_id"]
            replay = _detail("profile_history_replay:" + str(index), "@watch", "@online.history", details)
            replay["verb"] = "@watch"
            replay["run"] = lambda replay_id=replay_id: nav._play_replay(g, replay_id)
            out.append(replay)
    if state.get("profile_history_offset", 0):
        out.append(action("profile_history_previous", "@online.previous_page"))
    if len(profile.get("history") or []) >= 20:
        out.append(action("profile_history_next", "@online.next_page"))
    return out


def _board_rows(nav, g, state, action):
    board = state.get("leaderboard") or {}
    out = [dict(kind="heading", label="@online.leaderboard")]
    for key, label in (("place", "@online.place"), ("name", "@online.name"), ("rating", "@rating"),
                       ("rank", "@online.rank"), ("main", "@fighter"),
                       ("ranked_wins", "@online.ranked_wins"), ("ranked_losses", "@online.ranked_losses"),
                       ("casual_wins", "@online.casual_wins"), ("casual_losses", "@online.casual_losses")):
        item = action("leaderboard_sort:" + key, label)
        item["verb"] = "@online.sort"
        if board.get("sort") == key:
            item["value"] = "@online.descending" if board.get("descending") else "@online.ascending"
        out.append(item)
    key = board.get("sort", "place")

    def sort_key(row):
        value = row.get("rating" if key == "rank" else key)
        if key == "main":
            value = _fighter(g, value or "")
        return (0, value) if isinstance(value, (int, float)) else (1, str(value or "").casefold())
    for row in sorted(board.get("rows") or [], key=sort_key, reverse=bool(board.get("descending"))):
        item = action("profile_board:" + row["name"], i18n.literal(row["name"]))
        item["value"] = str(row.get("place", ""))
        item["detail"]["rows"] = [dict(k=label, v=i18n.literal(row[field])) for field, label in _BOARD_LABELS if field in row]
        if row.get("main"):
            item["detail"]["rows"].append(dict(k="@fighter", v=i18n.literal(_fighter(g, row["main"]))))
        if row.get("badge") == "dev":
            item["detail"]["rows"].append(dict(k="@online.name", v="@online.dev_badge"))
        out.append(item)
    if board.get("offset"):
        out.append(action("leaderboard_previous", "@online.previous_page"))
    if board.get("has_next"):
        out.append(action("leaderboard_next", "@online.next_page"))
    return out


def _stats_rows(nav, g, state, action):
    stats = state.get("community_stats") or {}
    labels = (("accounts", "@online.accounts"), ("players", "@online.players"), ("matches", "@online.matches"),
              ("ranked", "@online.ranked_matches"), ("matches_24h", "@online.matches_24h"), ("players_24h", "@online.players_24h"))
    out = [_detail("community_totals", "@online.community_stats", "@online.community_stats",
                   [dict(k=label, v=str(stats[key])) for key, label in labels if key in stats], hint="@online.stats_hint")]
    if stats.get("made"):
        out[0]["detail"]["rows"].append(dict(k="@date", v=_stamp(stats["made"])))
    for mode, label in (("all", "@online.all"), ("ranked", "@online.ranked_mode"), ("casual", "@online.casual_mode")):
        out.append(action("stats_mode:" + mode, label))
    for sort, label in (("matches", "@online.sort_matches"), ("winrate", "@online.sort_winrate"), ("fighter", "@online.sort_fighter")):
        out.append(action("stats_sort:" + sort, label))
    rows = []
    for source in stats.get("fighters") or []:
        parts = [source.get(mode) or [0, 0, 0] for mode in (("ranked", "casual") if stats.get("mode", "all") == "all" else (stats["mode"],))]
        games, wins, draws = (sum(part[i] for part in parts) for i in range(3))
        if games:
            rows.append(dict(char=source["char"], games=games, wins=wins, draws=draws))
    sort = stats.get("sort", "matches")
    if sort == "fighter":
        rows.sort(key=lambda row: _fighter(g, row["char"]).casefold())
    elif sort == "winrate":
        rows.sort(key=lambda row: (row["games"] < 30, -row["wins"] / row["games"], -row["games"], row["char"]))
    else:
        rows.sort(key=lambda row: (-row["games"], -row["wins"], row["char"]))
    total = sum(row["games"] for row in rows) or 1
    for row in rows:
        details = _counts(row) + [dict(k="@online.picked", v=f"{100 * row['games'] / total:.1f} %")]
        out.append(_detail("community_fighter:" + row["char"], i18n.literal(_fighter(g, row["char"])),
                           "@online.community_stats", details, hint="@online.stats_hint"))
    if not rows:
        out.append(_detail("no_statistics", "@online.no_statistics", "@online.community_stats", [], hint="@online.stats_hint"))
    return out


def rows(nav, g, state, action):
    capabilities = state.get("capabilities") or {}
    if not any(capabilities.get(key) for key in ("profiles", "leaderboard", "community_stats")):
        return []
    pages = getattr(nav, "_t5_profile_pages", None)
    if pages is None:
        pages = nav._t5_profile_pages = {}
    current = pages.get(g.id, "")

    def page_action(iid, label, target):
        item = action(iid, label)
        run = item["run"]

        def open_page():
            pages[g.id] = target
            run()
        item["run"] = open_page
        return item

    out = [dict(kind="heading", label="@online.profile")]
    if capabilities.get("profiles"):
        out.append(page_action("profile_self", "@online.profile_self", "profile"))
        out.append(nav._online_text_item(g, "online_profile_name", "@online.profile_lookup", "@online.profile_hint"))
        out.append(page_action("profile_load", "@online.profile_load", "profile"))
        for player in state.get("players") or []:
            item = page_action("profile_player:" + str(player["id"]), "@online.profile", "profile")
            item["value"] = i18n.literal(player.get("name") or "")
            out.append(item)
    if capabilities.get("leaderboard"):
        out.append(page_action("leaderboard_refresh", "@online.leaderboard_refresh", "leaderboard"))
    if capabilities.get("community_stats"):
        out.append(page_action("stats_refresh", "@online.stats_refresh", "stats"))
    if current == "profile" and capabilities.get("profiles"):
        out += _profile_rows(nav, g, state, action)
    elif current == "leaderboard" and capabilities.get("leaderboard"):
        board_rows = _board_rows(nav, g, state, action)
        for item in board_rows:
            if str(item.get("id", "")).startswith("profile_board:"):
                item["run"] = page_action(item["id"], item["label"], "profile")["run"]
        out += board_rows
    elif current == "stats" and capabilities.get("community_stats"):
        out += _stats_rows(nav, g, state, action)
    if current:
        item = _detail("close_profile", "@online.close_profile", "@online.profile", [])
        item["verb"] = "@back"

        def close():
            pages[g.id] = ""
            nav.focus[g.id + ":online"] = 0
        item["run"] = close
        out.append(item)
    return out





