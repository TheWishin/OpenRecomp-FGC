"""Arcade-floor presentation and controller routes; adapter actions remain unchanged."""
from . import i18n, ui_sound
from .nav_common import uri


LABELS = {key: "@arcade." + key for key in (
    "title", "players", "cabinets", "rooms", "quick", "quick_note", "ranked", "ranked_note",
    "options", "more", "help", "you", "idle", "searching", "in_room", "challenge", "watch",
    "profile", "join", "empty", "empty_note", "close", "score", "actions", "options_note",
    "no_matches", "no_rooms")}
TOGGLES = {"arcade_options", "arcade_more", "arcade_help"}


def memory(nav, name):
    return nav.__dict__.setdefault("arcade_" + name, {})


def toggle(nav, name):
    gid = nav.game.id
    memory(nav, name)[gid] = not memory(nav, name).get(gid, False)
    if name in ("options", "more") and memory(nav, name)[gid]:
        memory(nav, "more" if name == "options" else "options")[gid] = False
    nav.hint_sound(ui_sound.OPEN if memory(nav, name)[gid] else ui_sound.CLOSE)


def option(item):
    return item.get("region") == "find" and (item.get("kind") == "cycler" or item.get("id") in (
        "online_fighter", "ranked_strict", "netext_options", "native", "leave_set", "game_setup", "game_update"))


def add_rows(nav, g, page):
    from .nav_online_layout import CHAPTERS, CHAPTER_LABELS

    for name in ("options", "more", "help"):
        page.append(dict(kind="action", id="arcade_" + name, region="find" if name == "options" else "lobby",
                         label="@arcade." + name, verb="@open", hint="",
                         run=lambda name=name: toggle(nav, name)))
    for item in list(page):
        if (item.get("id") or "").startswith("spec_watch_"):
            page.append(dict(item, id="arcade_watch:" + item["id"], region="lobby"))
        elif item.get("id") == "refresh_rooms" or (item.get("id") or "").startswith(("join_room:", "room_watch:")):
            page.append(dict(item, id="arcade_room:" + item["id"], region="lobby"))
    for chapter in CHAPTERS:
        if chapter != "lobby" and any(it.get("region") == chapter for it in page):
            page.append(dict(kind="action", id="arcade_chapter:" + chapter, region="lobby", label=CHAPTER_LABELS[chapter],
                             verb="@open", hint="", run=lambda chapter=chapter: nav.click_chapter(chapter)))


def _btn(nav, items, by_id, iid, fi, label=""):
    if iid not in by_id:
        return {}
    button = nav._btn(items, by_id[iid], fi)
    if label:
        button["label"] = label
    button["value"] = ""
    return button


def _face(g, player):
    main = player.get("main") or player.get("char") or ""
    return dict(name=i18n.literal(player.get("name") or ""), face=uri(g.a.fighter_image(main)) if main else "")


def view(nav, g, state, items, fi):
    from .nav_online_layout import connection
    from .nav_netext import where

    by_id = {it.get("id"): n for n, it in enumerate(items)}
    focused_item = items[fi] if items else {}
    detail = focused_item.get("detail") or {}
    help_text = detail.get("lead") or focused_item.get("hint")
    if focused_item.get("id") not in TOGGLES and help_text:
        memory(nav, "help_context")[g.id] = dict(title=detail.get("title") or focused_item.get("label") or "@arcade.help", text=help_text)
    options_open = bool(memory(nav, "options").get(g.id, False))
    more_open = bool(memory(nav, "more").get(g.id, False))
    selected = memory(nav, "selected").get(g.id, "")
    targets = (state.get("spectating") or {}).get("targets") or []
    players = []
    me = dict(state.get("me") or {})
    me.update(name=state.get("name") or me.get("name") or "", status=me.get("status") or "idle")
    me["main"] = me.get("main") or g.a.main_fighter() or g.a.chosen_fighter()
    if me["main"] == "random":
        me["main"] = ""
    own_id = str(me.get("id") or "self")
    raw_players = [(me, True)] + [(p, False) for p in state.get("players") or []
                                if str(p.get("id")) != own_id]
    for p, own in raw_players:
        pid = own_id if own else str(p.get("id") or "")
        ids = (["profile_self"] if own else ["challenge:" + pid, "profile_player:" + pid])
        watch = next(("arcade_watch:" + t["id"] for t in targets
                      if str(t.get("player") or "") == pid
                      or t.get("id") in ("spec_watch_friend:" + pid, "spec_watch_friend:" + str(p.get("name") or ""))), "")
        if watch:
            ids.insert(1, watch)
        primary = [_btn(nav, items, by_id, iid, fi,
                       "@arcade.profile" if iid.startswith("profile_") else "@arcade.watch" if iid.startswith("arcade_watch:")
                       else "@arcade.challenge" if iid.startswith("challenge:") else "") for iid in ids]
        primary = [b for b in primary if b]
        index = by_id.get("online_status", 0) if own else by_id.get("challenge:" + pid, -1)
        extra = [_btn(nav, items, by_id, prefix + pid, fi) for prefix in (
            "private_open:", "mention:", "moderation_mute:", "moderation_block:")]
        if own:
            extra.append(_btn(nav, items, by_id, "logout", fi))
        extra = [b for b in extra if b]
        focused = fi == index or any(b["focused"] for b in primary + extra)
        if focused:
            selected = pid
            memory(nav, "selected")[g.id] = pid
        status = {"idle": "@arcade.idle", "queue": "@arcade.searching", "searching": "@arcade.searching",
                  "room": "@arcade.in_room", "in_room": "@arcade.in_room"}.get(p.get("status"), "@arcade.idle")
        if p.get("status") in ("match", "playing", "in_match"):
            opponent = p.get("opponent") or p.get("opponent_name")
            status = i18n.message("arcade.playing", name=i18n.literal(opponent)) if opponent else "@online_ui.status.playing"
        players.append(dict(id=pid, index=index, name=i18n.literal(p.get("name") or ""),
                            face=_face(g, p)["face"], plate=uri(g.a.rank_plate(p.get("tier"))) if "tier" in p else "",
                            rank=nav._rank_label(p), main=i18n.literal(g.a.fighter_label(p.get("main"))) if p.get("main") else "",
                            status=status, connection=connection(p), areaLanguage=where(p), own=own, focused=focused,
                            buttons=primary[:3], more=extra, moreOpen=more_open and selected == pid))
    cabinets = []
    room_data = {str(r.get("id")): r for r in state.get("rooms") or []}
    current_room = (state.get("community") or {}).get("room") or {}
    if current_room.get("id"):
        rid = str(current_room["id"])
        room_data[rid] = dict(room_data.get(rid, {}), **current_room)
    known_players = {str(p.get("id")): p for p in (current_room.get("members") or []) + [me]
                     + (state.get("players") or [])}
    for target in targets:
        iid = "arcade_watch:" + str(target.get("id") or "")
        if iid not in by_id:
            continue
        target_parts = str(target.get("id") or "").split(":")
        rid = target.get("room") or (target_parts[1] if len(target_parts) > 1 else "")
        room = room_data.get(str(rid), {})
        table = next((t for t in room.get("tables") or [] if target.get("kind") == "table"
                      and len(target_parts) > 2 and str(t.get("id")) == target_parts[2]), {})
        if not table and target.get("kind") == "room":
            table = next((t for t in room.get("tables") or [] if t.get("playing") and len(t.get("players") or []) == 2), {})
        people = target.get("players") or table.get("players") or room.get("match_players") or []
        if not people and room.get("status") in ("playing", "match"):
            people = room.get("members") or []
        people = [dict(known_players.get(str(p.get("id")), {}), **p) if isinstance(p, dict)
                  else known_players.get(str(p), {}) for p in people][:2]
        if len(people) != 2:
            continue
        score = target.get("score") or table.get("wins") or room.get("score") or []
        cabinets.append(dict(id=target["id"], index=by_id[iid], name=i18n.literal(target.get("name") or ""),
                             players=[_face(g, p) for p in people], score=" : ".join(str(n) for n in score[:2]),
                             watch=_btn(nav, items, by_id, iid, fi, "@arcade.watch"), focused=fi == by_id[iid]))
    rooms = []
    for rid, r in room_data.items():
        iid = "arcade_room:join_room:" + rid
        if iid not in by_id:
            continue
        count = r.get("players")
        count = len(count) if isinstance(count, (list, tuple)) else count
        if count is None:
            count = len(r.get("members") or [])
        capacity = r.get("size") or r.get("maximum")
        rooms.append(dict(id=rid, index=by_id[iid], name=i18n.literal(r.get("name") or ""),
                          count=str(count) + (" / " + str(capacity) if capacity else ""), areaLanguage=where(r),
                          mode={"line": "@online.room_line_mode", "tables": "@online.room_tables_mode"}.get(r.get("mode"), ""),
                          join=_btn(nav, items, by_id, iid, fi, "@arcade.join"),
                          watch=_btn(nav, items, by_id, "arcade_room:room_watch:" + rid, fi, "@arcade.watch"), focused=fi == by_id[iid]))
    selected_card = next((p for p in players if p["id"] == selected), {})
    return dict(players=players, cabinets=cabinets, rooms=rooms, selected=selected,
                optionsOpen=options_open, moreOpen=more_open,
                helpOpen=bool(memory(nav, "help").get(g.id, False)),
                help=memory(nav, "help_context").get(g.id, dict(title="@arcade.help", text="@arcade.options_note")),
                options=[nav._btn(items, n, fi) for n, it in enumerate(items) if option(it)],
                more=selected_card.get("more", []) + [nav._btn(items, n, fi) for n, it in enumerate(items)
                    if it.get("id") in ("refresh_players", "arcade_room:refresh_rooms")],
                secondary=[nav._btn(items, n, fi) for n, it in enumerate(items)
                           if it.get("region") in ("find", "lobby") and it.get("kind") != "heading"
                           and it.get("id") not in TOGGLES | {"online_status", "search_casual", "search_ranked"}
                           and not option(it) and not (it.get("id") or "").startswith(("challenge:", "profile_player:",
                               "private_open:", "mention:", "arcade_chapter:"))],
                destinations=[nav._btn(items, n, fi) for n, it in enumerate(items)
                              if (it.get("id") or "").startswith("arcade_chapter:")],
                controls={name: _btn(nav, items, by_id, "arcade_" + name, fi) for name in ("options", "more", "help")},
                glyphs={key: nav.glyph(action) for key, action in (("a", "confirm"), ("b", "back"), ("x", "x"), ("y", "social"), ("more", "play"))},
                columns=2 if options_open or more_open or items[fi].get("region") == "chat" else 3,
                labels=dict(LABELS))


def active(nav, items, i):
    if getattr(nav, "main_menu_game", "") == nav.game.id:
        return False
    if nav.section() != "online" or not items or getattr(nav, "ranked_page", "") == nav.game.id:
        return False
    if not any(it.get("id") == "arcade_options" for it in items):
        return False
    return nav._chapter_of_focus(items, i) == "lobby" and items[i].get("region") != "chat"


def routes(nav, items, i):
    state = nav.game.a.online_state()
    floor = view(nav, nav.game, state, items, i)
    by_id = {it.get("id"): n for n, it in enumerate(items)}
    if floor["helpOpen"]:
        return [[floor["controls"]["help"]["index"]]], floor
    routes = [[by_id[iid] for iid in ("search_casual", "search_ranked", "arcade_options") if iid in by_id]]
    if floor["optionsOpen"]:
        routes += [[b["index"]] for b in floor["options"]]
    for kind in ("incoming", "outgoing", "notice"):
        # Pending requests stay reachable even while the options drawer is closed.
        prefixes = {"incoming": ("accept_challenge", "decline_challenge"), "outgoing": ("cancel_challenge:",),
                    "notice": ("other_here", "other_keep")}[kind]
        row = [n for n, it in enumerate(items) if (it.get("id") or "").startswith(prefixes)]
        if row:
            routes.append(row)
    for cards in (floor["players"],):
        indexes = [c["index"] for c in cards if c["index"] >= 0]
        routes += [indexes[n:n + floor["columns"]] for n in range(0, len(indexes), floor["columns"])]
    if not floor["optionsOpen"] and not floor["moreOpen"]:
        routes += [[c["index"]] for c in floor["cabinets"] + floor["rooms"] if c["index"] >= 0]
    selected = memory(nav, "selected").get(nav.game.id)
    card = next((p for p in floor["players"] if p["id"] == selected), None)
    if card:
        actions = [b["index"] for b in card["buttons"] if b["index"] != card["index"]]
        if actions:
            routes.append(actions)
    routes.append([floor["controls"]["more"]["index"]])
    if floor["moreOpen"]:
        indexes = [b["index"] for b in floor["more"] + floor["secondary"] + floor["destinations"]]
        routes += [[index] for index in dict.fromkeys(indexes)]
    if floor["optionsOpen"] or floor["moreOpen"]:
        routes.append([floor["controls"]["help"]["index"]])
    seen, unique = set(), []
    for row in routes:
        distinct = [index for index in row if index not in seen]
        seen.update(distinct)
        if distinct:
            unique.append(distinct)
    return unique, floor


def move(nav, items, i, step, horizontal=False):
    rows, floor = routes(nav, items, i)
    location = next(((r, row.index(i)) for r, row in enumerate(rows) if i in row), None)
    if location is None:
        card = next((c for c in floor["players"] if c["focused"]), None)
        if card:
            return move(nav, items, card["index"], step, horizontal)
        return rows[0][0]
    row, column = location
    if horizontal:
        return rows[row][max(0, min(len(rows[row]) - 1, column + step))]
    target = max(0, min(len(rows) - 1, row + step))
    return rows[target][min(column, len(rows[target]) - 1)]


def action(nav, action):
    if action not in ("back", "confirm", "x", "social", "play"):
        return False
    if nav.screen != "hub" or nav.overlay or nav.section() != "online":
        return False
    items = nav.items()
    i = nav.focus_index(items)
    if not active(nav, items, i):
        return False
    if action == "back":
        for name in ("help", "more", "options"):
            if memory(nav, name).get(nav.game.id):
                memory(nav, name)[nav.game.id] = False
                nav.hint_sound(ui_sound.BACK)
                nav.focus[nav.key()] = next(n for n, it in enumerate(items) if it.get("id") == "arcade_" + name)
                return True
    floor = view(nav, nav.game, nav.game.a.online_state(), items, i)
    card = next((p for p in floor["players"] if p["focused"]), None)
    if card and action == "play":
        toggle(nav, "more")
        nav.focus[nav.key()] = floor["controls"]["more"]["index"]
        return True
    if card and action in ("x", "social", "confirm"):
        if action == "confirm" and i != card["index"]:
            return False
        prefix = {"x": "arcade_watch:", "social": "profile_", "confirm": "profile_" if card["own"] else "challenge:"}[action]
        button = next((b for b in card["buttons"] if b["id"].startswith(prefix)), None)
        if button:
            nav.focus[nav.key()] = button["index"]
            nav._activate(items[button["index"]])
            return True
    return False
