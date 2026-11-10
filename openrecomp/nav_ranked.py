"""Ranked standing and ranking presentation, using only the adapter's public snapshot."""
from . import i18n
from .nav_common import placing, uri
from .nav_profiles import _stamp


LABELS = {
    "ranked": "@official_ui.ranked", "standing": "@official_ui.standing", "rating": "@official_ui.rating",
    "progress": "@official_ui.progress", "recent": "@official_ui.recent", "no_recent": "@official_ui.no_recent",
    "ranking": "@official_ui.ranking", "podium": "@official_ui.podium", "your_position": "@official_ui.your_position",
    "updated_unknown": "@official_ui.updated_unknown", "page_filter": "@official_ui.page_filter",
    "filters": "@official_ui.filters", "sort": "@official_ui.sort", "rank": "@official_ui.rank",
    "player": "@official_ui.player", "record": "@official_ui.record", "main": "@official_ui.main",
    "placement": "@official_ui.placement", "season": "@official_ui.season", "unavailable": "@official_ui.unavailable",
    "empty": "@official_ui.empty",
}


def _number(value):
    return str(value) if value is not None else "—"


def ranked(nav, g, state, items, fi, profile, find):
    source = state.get("profile") or {}
    mine = str(source.get("name") or "").casefold() == str(state.get("name") or "").casefold()
    recent = []
    if mine:
        for row in source.get("history") or []:
            if row.get("ranked") is not True:
                continue
            result = {"win": "@online.result_win", "won": "@online.result_win",
                      "loss": "@online.result_loss", "lost": "@online.result_loss",
                      "draw": "@online.draws"}.get(row.get("result"), "@online.result_none")
            recent.append(dict(opponent=i18n.literal(row.get("opponent") or ""), result=result,
                               score=" : ".join(str(n) for n in row.get("score") or [])))
    return dict(labels=LABELS, profile=profile, find=find, recent=recent[:6],
                available=bool((state.get("capabilities") or {}).get("ranked")),
                season=i18n.literal(state["season"]) if state.get("season") else "@official_ui.season",
                placement=bool(placing(state.get("me") or {})),
                rating=_number((state.get("me") or {}).get("rating")))


def leaderboard(nav, g, state, items, fi):
    board = state.get("leaderboard") or {}
    prefs = nav.__dict__.setdefault("board_filters", {}).get(g.id, {})
    mode = prefs.get("mode", "ranked")
    fighter = prefs.get("fighter", "")
    by_id = {it.get("id"): n for n, it in enumerate(items)}

    def entry(source):
        name = str(source.get("name") or "")
        index = by_id.get("profile_board:" + name, -1)
        wins, losses = source.get(mode + "_wins"), source.get(mode + "_losses")
        if wins is None and mode == "ranked":
            wins, losses = source.get("wins"), source.get("losses")
        record = nav._record([wins, losses]) if wins is not None and losses is not None else "—"
        main = source.get("main") or ""
        return dict(index=index, name=i18n.literal(name), place=_number(source.get("place")),
                    rank=nav._rank_label(source), rating=_number(source.get("rating")), record=record,
                    main=i18n.literal(g.a.fighter_label(main)) if main else "—",
                    face=uri(g.a.fighter_image(main)) if main else "",
                    plate=uri(g.a.rank_plate(source.get("tier"))), focused=index == fi and index >= 0,
                    own=name.casefold() == str(state.get("name") or "").casefold())

    sources = board.get("rows") or []
    shown = [row for row in sources if not fighter or row.get("main") == fighter]
    order = {it.get("id"): n for n, it in enumerate(items)}
    shown.sort(key=lambda row: order.get("profile_board:" + str(row.get("name") or ""), len(items)))
    podium = sorted((row for row in sources if row.get("place") in (1, 2, 3)), key=lambda row: row["place"])
    own = next((row for row in sources if str(row.get("name") or "").casefold() == str(state.get("name") or "").casefold()), None)
    if own is None and state.get("account") and state.get("me"):
        own = dict(state["me"], name=state.get("name") or "")
    controls = [nav._btn(items, n, fi) for n, it in enumerate(items) if it.get("id") in
                ("leaderboard_mode", "leaderboard_fighter")]
    sorts = [nav._btn(items, n, fi) for n, it in enumerate(items) if str(it.get("id") or "").startswith("leaderboard_sort:")]
    buttons = [nav._btn(items, n, fi) for n, it in enumerate(items) if it.get("id") in
               ("leaderboard_refresh", "leaderboard_previous", "leaderboard_next", "leaderboard_podium", "stats_refresh")]
    return dict(labels=LABELS, podium=[entry(row) for row in podium], rows=[entry(row) for row in shown],
                own=entry(own) if own else None, controls=controls, sorts=sorts, buttons=buttons,
                podiumOpen=nav.__dict__.get("board_podium", {}).get(g.id, False),
                updated=i18n.message("official_ui.updated", time=_stamp(board["updated"])) if board.get("updated") else "@official_ui.updated_unknown")
