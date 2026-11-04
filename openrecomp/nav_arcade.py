"""Arcade-floor presentation and controller routes; adapter actions remain unchanged."""
from . import i18n, ui_sound
from .nav_common import uri


LABELS = {key: "@arcade." + key for key in (
    "title", "players", "cabinets", "rooms", "quick", "quick_note", "ranked", "ranked_note",
    "options", "more", "help", "you", "idle", "searching", "in_room", "challenge", "watch",
    "profile", "join", "empty", "empty_note", "close", "score", "actions", "options_note",
    "no_matches", "no_rooms")}
LABELS.update(lobbyTitle="@online_ui.chapter.lobby", subtitle="@community_ui.lobby_subtitle",
              needsAccount="@online_density.needs_account")
TOGGLES = {"arcade_options", "arcade_more", "arcade_help"}
SORTS = (("recommended", "@community_ui.recommended"), ("name", "@community_ui.name"),
         ("rank", "@online.rank"), ("rating", "@rating"), ("ping", "@community_ui.ping"),
         ("status", "@community_ui.status"), ("main", "@online_ui.col.main"))


def player_order(nav, g, state, players):
    mode = memory(nav, "sort").get(g.id, "recommended")
    friends = {str(p.get("id") or p.get("name") or "").casefold() for p in state.get("friends") or []}
    def key(pair):
        p, own = pair
        name = str(p.get("name") or "").casefold()
        ping = p.get("ping") if isinstance(p.get("ping"), (int, float)) else float("inf")
        if mode == "name": value = (name,)
        elif mode == "rank": value = (-(p.get("tier") if isinstance(p.get("tier"), (int, float)) else -1), name)
        elif mode == "rating": value = (-(p.get("rating") if isinstance(p.get("rating"), (int, float)) else -1), name)
        elif mode == "ping": value = (ping, name)
        elif mode == "status": value = (str(p.get("status") or ""), ping, name)
        elif mode == "main": value = (str(p.get("main") or ""), name)
        else:
            friend = p.get("friend") or str(p.get("id") or "").casefold() in friends or name in friends
            available = p.get("status") in (None, "idle", "online", "available")
            value = (not friend, not available, ping, name)
        return (not own,) + value
    ordered = sorted(players, key=key)
    if memory(nav, "sort_reverse").get(g.id, False):
        ordered = [pair for pair in ordered if pair[1]] + list(reversed([pair for pair in ordered if not pair[1]]))
    return ordered


def memory(nav, name):
    return nav.__dict__.setdefault("arcade_" + name, {})


def sort_by(nav, g, mode, toggle=False):
    if mode not in dict(SORTS):
        return
    reverse = toggle and memory(nav, "sort").get(g.id, "recommended") == mode and not memory(nav, "sort_reverse").get(g.id, False)
    memory(nav, "sort")[g.id] = mode
    memory(nav, "sort_reverse")[g.id] = reverse


def toggle(nav, name):
    gid = nav.game.id
    opening = not memory(nav, name).get(gid, False)
    if opening:
        items = nav.items()
        memory(nav, "opener").setdefault(gid, {})[name] = items[nav.focus_index(items)].get("id")
    memory(nav, name)[gid] = opening
    if name in ("options", "more") and memory(nav, name)[gid]:
        memory(nav, "more" if name == "options" else "options")[gid] = False
    nav.hint_sound(ui_sound.OPEN if memory(nav, name)[gid] else ui_sound.CLOSE)


def option(item):
    return item.get("region") == "find" and (item.get("kind") == "cycler" or item.get("id") in (
        "online_fighter", "ranked_strict", "netext_options", "native", "leave_set", "game_setup", "game_update"))


def add_rows(nav, g, page):
    from .nav_online_layout import CHAPTERS, CHAPTER_LABELS

    page.append(dict(kind="action", id="chat_latest", region="chat", label="@community_ui.latest", hint="",
                     run=lambda: memory(nav, "latest").__setitem__(g.id, memory(nav, "latest").get(g.id, 0) + 1)))
    current = memory(nav, "sort").get(g.id, "recommended")
    page.append(dict(kind="cycler", id="arcade_sort", region="lobby", label="@community_ui.sort",
                     value=dict(SORTS)[current], options=list(SORTS), current=current, hint="",
                     set=lambda value: sort_by(nav, g, value)))
    for mode, label in SORTS[1:]:
        page.append(dict(kind="action", id="arcade_sort:" + mode, region="lobby", label=label, hint="",
                         run=lambda mode=mode: sort_by(nav, g, mode, toggle=True)))
    data = g.a.online_state().get("private_chat") or {}
    for thread in data.get("threads") or []:
        tid = str(thread["id"])
        page.append(dict(kind="action", id="chat_close:" + tid, region="chat", label="@online_chat.private_close",
                         run=lambda tid=tid: nav.close_chat_tab(tid)))
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
    main = player.get("main") or ""
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
    me["main"] = me.get("main") or ""
    if me["main"] == "random":
        me["main"] = ""
    own_id = str(me.get("id") or "self")
    raw_players = [(me, True)] + [(p, False) for p in state.get("players") or []
                                if str(p.get("id")) != own_id]
    for p, own in player_order(nav, g, state, raw_players):
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
        for button in primary:
            if button.get("feedback", {}).get("kind") in ("pending", "waiting") and button["id"].startswith("challenge:"):
                button["disabled"] = True
        for b in primary:
            b["semantic"] = "challenge" if b["id"].startswith("challenge:") else "watch" if b["id"].startswith("arcade_watch:") else "profile"
        index = by_id.get("online_status", 0) if own else by_id.get("challenge:" + pid, -1)
        extra = [_btn(nav, items, by_id, prefix + pid, fi) for prefix in (
            "private_open:", "mention:", "moderation_mute:", "moderation_block:")]
        message = next((b for b in extra if b.get("id", "").startswith("private_open:")), None)
        if message:
            message["label"] = "@online_density.message"
            message["semantic"] = "message"
            primary.append(message)
        if own:
            extra.append(_btn(nav, items, by_id, "logout", fi))
        extra = [b for b in extra if b]
        focused = fi == index or any(b["focused"] for b in primary + extra)
        if focused:
            selected = pid
            memory(nav, "selected")[g.id] = pid
        status = {"idle": "@arcade.idle", "online": "@arcade.idle", "available": "@arcade.idle",
                  "queue": "@arcade.searching", "searching": "@arcade.searching",
                  "room": "@arcade.in_room", "in_room": "@arcade.in_room"}.get(p.get("status"), "@unknown")
        if p.get("status") in ("match", "playing", "in_match"):
            status = "@online_ui.status.playing"
        players.append(dict(id=pid, index=index, name=i18n.literal(p.get("name") or ""),
                            face=_face(g, p)["face"], plate=uri(g.a.rank_plate(p.get("tier"))) if "tier" in p else "",
                            rank=nav._rank_label(p) or "\u2014", rating=str(p["rating"]) if p.get("rating") is not None else "\u2014",
                            main=i18n.literal(g.a.fighter_label(p.get("main"))) if p.get("main") else "\u2014",
                            status=status, connection=connection(p), areaLanguage=where(p), own=own, focused=focused,
                            buttons=primary[:4], more=extra, moreOpen=more_open and selected == pid))
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
    if not any(p["id"] == selected for p in players):
        selected = next((p["id"] for p in players if not p["own"]), own_id)
        memory(nav, "selected")[g.id] = selected
    selected_card = next((p for p in players if p["id"] == selected), {})
    cancel = _btn(nav, items, by_id, "cancel", fi)
    phase = state.get("phase")
    search = None
    if phase in ("searching", "cancelling"):
        from . import nav_feedback
        receipt = next((r for action, r in nav_feedback.records(nav, g.id).items()
                        if action.startswith("search_") and r.get("kind") in ("pending", "waiting")), {})
        ranked = receipt.get("action") == "search_ranked" or state.get("message") == "@online.searching_ranked"
        seconds = int(max(0, receipt.get("age", 0)))
        cancel = dict(cancel, label="@cancel") if cancel else dict(id="cancel", index=-1, label="@cancel", disabled=True)
        if phase == "cancelling":
            cancel = dict(cancel, disabled=True, disabledReason="@online.cancelling")
        search = dict(text="@online.cancelling" if phase == "cancelling" else
                           "@online_density.search_ranked" if ranked else "@online_density.search_casual",
                      phase=phase, ranked=ranked, elapsed=f"{seconds // 60}:{seconds % 60:02}", buttons=[cancel])
    result = nav.__dict__.get("last_action_result", {}).get(g.id)
    return dict(players=players, cabinets=cabinets, rooms=rooms, selected=selected,
                createRoom=_btn(nav, items, by_id, "arcade_create_room", fi),
                joinCode=_btn(nav, items, by_id, "arcade_join_code", fi),
                sort=nav._btn(items, by_id["arcade_sort"], fi),
                headers=[dict(_btn(nav, items, by_id, "arcade_sort:" + mode, fi), key=mode,
                              descending=(mode in ("rank", "rating")) != bool(memory(nav, "sort_reverse").get(g.id, False)),
                              active=memory(nav, "sort").get(g.id, "recommended") == mode)
                         for mode in ("name", "rank", "rating", "main", "status", "ping")],
                search=search, result=result,
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
                columns=1,
                labels=dict(LABELS))


def active(nav, items, i):
    if getattr(nav, "main_menu_game", "") == nav.game.id:
        return False
    if nav.section() != "online" or not items or getattr(nav, "ranked_page", "") == nav.game.id:
        return False
    if not any(it.get("id") == "arcade_options" for it in items):
        return False
    return nav._chapter_of_focus(items, i) == "lobby"


def routes(nav, items, i):
    state = nav.game.a.online_state()
    floor = view(nav, nav.game, state, items, i)
    by_id = {it.get("id"): n for n, it in enumerate(items)}
    controls = floor["controls"]
    if floor["helpOpen"]:
        return [[controls["help"]["index"]]], floor
    if floor["optionsOpen"] or floor["moreOpen"]:
        fields = floor["options"] if floor["optionsOpen"] else floor["more"] + floor["secondary"] + floor["destinations"]
        rows = [[controls["options" if floor["optionsOpen"] else "more"]["index"]]]
        rows += [[b["index"]] for b in fields]
        rows += [[controls["help"]["index"]]]
    else:
        rows = [[by_id[iid] for iid in ("profile_self", "logout", "search_ranked", "search_casual", "arcade_options", "arcade_more") if iid in by_id]]
        for prefixes in (("accept_challenge", "decline_challenge"), ("cancel_challenge:",), ("other_here", "other_keep"), ("cancel",)):
            row = [n for n, it in enumerate(items) if ((it.get("id") or "").startswith("cancel_challenge:") if prefixes == ("cancel_challenge:",) else it.get("id") in prefixes)]
            if row: rows.append(row)
        top_options = [b for b in floor["options"] if b["id"] in ("online_input_delay", "netext_online_feel")]
        rows += [[b["index"]] for b in (top_options or floor["options"][:2])]
        rows.append([floor["sort"]["index"]])
        rows.append([b["index"] for b in floor["headers"]])
        rows += [[p["index"]] for p in floor["players"] if p["index"] >= 0]
        selected = next((p for p in floor["players"] if p["id"] == floor["selected"]), None)
        if selected: rows.append([b["index"] for b in selected["buttons"]])
        for ids in (("arcade_create_room", "arcade_join_code"),):
            row = [by_id[iid] for iid in ids if iid in by_id]
            if row: rows.append(row)
        rows += [[c["watch"]["index"]] for c in floor["cabinets"] if c.get("watch")]
        rows += [[b["index"] for b in (r.get("join"), r.get("watch")) if b] for r in floor["rooms"]]
        chat = nav._view_chat(nav.game, state, items, i)
        rows += [[b["index"] for b in chat["tabs"]] + [b["closeIndex"] for b in chat["tabs"] if b.get("closeIndex") is not None]]
        rows += [[line["index"]] for line in chat["lines"]]
        rows += [[b["index"]] for b in chat["other"]]
        rows += [[b["index"] for b in (chat.get("latest"), chat.get("compose"), chat.get("send")) if b]]
    seen, unique = set(), []
    for row in rows:
        distinct = [index for index in row if index >= 0 and index not in seen]
        seen.update(distinct)
        if distinct: unique.append(distinct)
    return unique, floor


def move(nav, items, i, step, horizontal=False):
    rows, floor = routes(nav, items, i)
    selected = next((p for p in floor["players"] if p["id"] == floor["selected"]), None)
    if selected and not horizontal and step < 0 and i != selected["index"] and any(b["index"] == i for b in selected["buttons"]):
        return selected["index"]
    if horizontal and not (floor["optionsOpen"] or floor["moreOpen"] or floor["helpOpen"]):
        region = items[i].get("region")
        if region == "chat" and step < 0:
            target = memory(nav, "pane_back").get(nav.game.id)
            return next((n for n, it in enumerate(items) if it.get("id") == target), floor["players"][0]["index"])
        if step < 0 and any(p["index"] == i for p in floor["players"]):
            return next((b["index"] for b in selected["buttons"] if b["index"] != i), i) if selected else i
        if any(p["index"] == i for p in floor["players"]) and step > 0:
            memory(nav, "pane_back")[nav.game.id] = items[i]["id"]
            return next((n for n, it in enumerate(items) if it.get("id") in ("online_private_chat", "online_chat")), i)
    location = next(((r, row.index(i)) for r, row in enumerate(rows) if i in row), None)
    if location is None: return rows[0][0]
    row, column = location
    if horizontal: return rows[row][max(0, min(len(rows[row]) - 1, column + step))]
    # Players and chat are independent vertical panes.
    region = items[i].get("region")
    candidates = [r for r, indexes in enumerate(rows) if region != "chat" or any(items[n].get("region") == "chat" for n in indexes)]
    if region != "chat": candidates = [r for r in candidates if not all(items[n].get("region") == "chat" for n in rows[r])]
    position = candidates.index(row) if row in candidates else 0
    target = candidates[max(0, min(len(candidates) - 1, position + step))]
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
                opener = memory(nav, "opener").get(nav.game.id, {}).get(name, "arcade_" + name)
                nav.focus[nav.key()] = next((n for n, it in enumerate(items) if it.get("id") == opener),
                                          next(n for n, it in enumerate(items) if it.get("id") == "arcade_" + name))
                return True
    floor = view(nav, nav.game, nav.game.a.online_state(), items, i)
    card = next((p for p in floor["players"] if p["focused"]), None)
    if (floor["helpOpen"] or floor["moreOpen"] or floor["optionsOpen"]) and action in ("x", "social", "play"):
        return True
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
            if action == "confirm" and not card["own"]:
                nav.challenge_player(card["id"])
            else:
                nav._activate(items[button["index"]])
            return True
    return False
