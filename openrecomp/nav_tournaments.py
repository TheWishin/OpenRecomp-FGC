"""Pad-selectable tournament lists, bracket sets and organizer controls."""
import time

from . import i18n


STATES = {"signup": "@online.tour_signup", "checkin": "@online.tour_state_checkin",
          "running": "@online.tour_running", "finished": "@online.tour_finished",
          "cancelled": "@online.tour_cancelled"}
OPTION_LABELS = dict(format="@online.tour_format", set_wins="@online.tour_set_wins",
                     start_minutes="@online.tour_start_minutes", max_players="@online.tour_max_players",
                     checkin_minutes="@online.tour_checkin_minutes", seeding="@online.tour_seeding")
VALUES = dict(single="@online.tour_single", double="@online.tour_double",
              random="@online.tour_random", rating="@online.tour_rating")
CHANGE_LABELS = dict(tour_start="@online.tour_start", tour_cancel="@online.tour_cancel",
                     tour_leave="@online.tour_leave", tour_win0="@online.tour_win0",
                     tour_win1="@online.tour_win1", tour_reset="@online.tour_reset",
                     tour_dq="@online.tour_submit_dq")


def _info(detail):
    result = [dict(k="@online.tour_state", v=STATES.get(detail.get("state"), i18n.literal(detail.get("state") or "")))]
    for key, label in (("organizer", "@online.tour_organizer"), ("set_wins", "@online.tour_set_wins"),
                       ("players", "@online.players"), ("max_players", "@online.tour_max_players"),
                       ("checkin_minutes", "@online.tour_checkin_minutes")):
        if detail.get(key) is not None:
            result.append(dict(k=label, v=i18n.literal(detail[key])))
    if detail.get("seeding"):
        seed = detail["seeding"]
        result.append(dict(k="@online.tour_seeding", v=VALUES.get(seed, i18n.literal(seed))))
    if isinstance(detail.get("start"), (int, float)):
        try:
            start = time.strftime("%Y-%m-%d %H:%M", time.localtime(detail["start"]))
        except (ValueError, OSError, OverflowError):
            start = ""
        result.append(dict(k="@online.tour_clock", v=i18n.literal(start)))
    return result


def rows(nav, game, state, action):
    if not (state.get("capabilities") or {}).get("tournaments"):
        return []
    data = state.get("tournaments") or {}
    out = [dict(kind="heading", label="@online.tournaments"), action("tour_refresh", "@online.tour_refresh")]
    call = data.get("call") or {}
    if call:
        tid = str((call.get("tournament") or {}).get("id") or "")
        sid = str((call.get("set") or {}).get("id") or "")
        item = action("tour_accept:" + tid + ":" + sid, "@online.tour_accept")
        item["detail"]["rows"] = [dict(k="@online.tournaments", v=i18n.literal((call.get("tournament") or {}).get("name") or "")),
                                      dict(k="@online.opponent", v=i18n.literal((call.get("opponent") or {}).get("name") or "")),
                                      dict(k="@online.tour_set_wins", v=i18n.literal(call.get("best_of", 3)))]
        item["value"] = i18n.literal(call.get("seconds", 0))
        if call.get("accepted") or not call.get("seconds"):
            item.update(run=None, disabled=True)
        out.append(item)
    for tournament in data.get("rows") or []:
        tid = str(tournament.get("id") or "")
        item = action("tour_select:" + tid, i18n.literal(tournament.get("name") or tid))
        item["value"] = STATES.get(tournament.get("state"), i18n.literal(tournament.get("state") or ""))
        item["detail"]["rows"] = _info(tournament)
        out.append(item)
    if data.get("can_create") and state.get("account"):
        out.append(nav._online_text_item(game, "online_tour_name", "@online.tour_name", "@online.tournaments"))
        for field, label in OPTION_LABELS.items():
            item = action("tour_option:" + field, label)
            value = (data.get("options") or {}).get(field, "")
            item["value"] = VALUES.get(value, i18n.literal(value))
            out.append(item)
        out.append(nav._online_text_item(game, "online_tour_clock", "@online.tour_clock", "@online.tour_clock"))
        out.append(action("tour_create", "@online.tour_create"))
    elif data.get("create_hint"):
        hint = i18n.literal(data["create_hint"])
        out.append(dict(kind="action", id="tour_create_hint", label=hint, detail=dict(kicker="@online.tournaments", title=hint, rows=[])))
    detail = data.get("detail") or {}
    tid = str(detail.get("id") or "")
    if not tid:
        return out
    out.append(dict(kind="heading", label=i18n.literal(detail.get("name") or tid)))
    item = action("tour_refresh_detail:" + tid, "@online.tour_refresh")
    item["detail"]["rows"] = _info(detail)
    if data.get("stale"):
        item["hint"] = item["detail"]["lead"] = "@online.tour_waiting"
    out.append(item)
    you = detail.get("you") or {}
    current = detail.get("state")
    if state.get("account"):
        if current in ("signup", "checkin"):
            verb = "leave" if you.get("entrant") else "join"
            if verb == "leave" or you.get("build_ok", True):
                label = "@online.tour_leave" if verb == "leave" else "@online.tour_join"
                out.append(action("tour_" + verb + ":" + tid, label))
            if current == "checkin" and you.get("entrant") and not you.get("checked_in"):
                out.append(action("tour_checkin:" + tid, "@online.tour_checkin"))
        elif current == "running" and you.get("entrant") and not you.get("dq") and not you.get("place"):
            out.append(action("tour_leave:" + tid, "@online.tour_leave"))
    if detail.get("can_manage"):
        if current in ("signup", "checkin"):
            out.append(action("tour_start:" + tid, "@online.tour_start"))
        if current in ("signup", "checkin", "running"):
            out.append(action("tour_cancel:" + tid, "@online.tour_cancel"))
    if detail.get("entrants"):
        out.append(dict(kind="heading", label="@online.tour_entrants"))
    for index, entrant in enumerate(detail.get("entrants") or []):
        name = i18n.literal(entrant.get("name") or "")
        info = [dict(k="@online.tour_seeding", v=i18n.literal(entrant.get("seed") or ""))]
        if "checked_in" in entrant:
            info.append(dict(k="@online.tour_checkin", v="@on" if entrant["checked_in"] else "@off"))
        if entrant.get("dq"):
            info.append(dict(k="@online.tour_dq", v=i18n.literal(entrant["dq"])))
        out.append(dict(kind="action", id="tour_entrant:" + tid + ":" + str(index), label=name,
                        detail=dict(kicker="@online.tour_entrants", title=name, rows=info)))
    sets = (detail.get("bracket") or {}).get("sets") or []
    if sets:
        out.append(dict(kind="heading", label="@online.tour_bracket"))
    for bracket_set in sets:
        sid = str(bracket_set.get("id") or "")
        names = bracket_set.get("p") or [None, None]
        label = i18n.literal(sid + "  " + " / ".join(str(name or "?") for name in names))
        item = action("tour_select_set:" + sid, label)
        scores = bracket_set.get("wins") if bracket_set.get("live") == "playing" else bracket_set.get("score")
        info = [dict(k="@online.players", v=i18n.literal(" / ".join(str(name or "?") for name in names)))]
        if scores:
            info.append(dict(k="@online.result", v=i18n.literal(" - ".join(str(score) for score in scores))))
        elif bracket_set.get("winner") in (0, 1) and len(names) == 2:
            info.append(dict(k="@online.result", v=i18n.literal(names[bracket_set["winner"]] or "?")))
        live = bracket_set.get("live")
        if live:
            info.append(dict(k="@online.tour_state", v={"called": "@online.tour_called", "playing": "@online.tour_live",
                                                             "attention": "@online.tour_attention"}.get(live, i18n.literal(live))))
        item["detail"]["rows"] = info
        out.append(item)
    selected = next((row for row in sets if str(row.get("id")) == data.get("selected_set")), None)
    if selected:
        sid = str(selected["id"])
        if detail.get("can_manage") and current == "running":
            for verb in ("win0", "win1", "reset"):
                item = action("tour_" + verb + ":" + tid + ":" + sid, CHANGE_LABELS["tour_" + verb])
                item["value"] = i18n.literal(sid)
                out.append(item)
            out.append(nav._online_text_item(game, "online_tour_dq", "@online.tour_dq", "@online.tour_dq"))
            out.append(action("tour_dq:" + tid + ":" + game.a.text_value("online_tour_dq").strip(), "@online.tour_submit_dq"))
        if (state.get("capabilities") or {}).get("spectating") and selected.get("watch") and selected.get("live") == "playing" and state.get("name") not in (selected.get("p") or []):
            out.append(action("spec_watch_tour:" + tid + ":" + sid, "@online.tour_watch"))
    if detail.get("standings"):
        out.append(dict(kind="heading", label="@online.tour_standings"))
    for index, standing in enumerate(detail.get("standings") or []):
        name = i18n.literal(standing.get("name") or "")
        out.append(dict(kind="action", id="tour_standing:" + tid + ":" + str(index), label=name,
                        value=i18n.literal(standing.get("place") or ""),
                        detail=dict(kicker="@online.tour_standings", title=name,
                                    rows=[dict(k="@online.rank", v=i18n.literal(standing.get("place") or ""))])))
    pending = data.get("pending")
    if pending:
        item = action("tour_confirm:" + pending, "@online.tour_confirm", "@online.tour_pending")
        verb = pending.partition(":")[0]
        item["detail"]["rows"] = [dict(k="@online.tournaments", v=i18n.literal(detail.get("name") or tid)),
                                      dict(k="@online.tour_confirm", v=CHANGE_LABELS.get(verb, "@online.tour_confirm"))]
        extra = pending.partition(":")[2].partition(":")[2]
        if verb == "tour_dq":
            item["detail"]["rows"].append(dict(k="@online.name", v=i18n.literal(extra)))
        elif extra:
            item["detail"]["rows"].append(dict(k="@online.tour_bracket", v=i18n.literal(extra)))
            selected = next((row for row in sets if str(row.get("id")) == extra), None)
            if selected:
                names = " / ".join(str(name or "?") for name in selected.get("p") or [])
                item["detail"]["rows"].append(dict(k="@online.players", v=i18n.literal(names)))
        out.extend([item, action("tour_abandon_change", "@cancel")])
    return out
