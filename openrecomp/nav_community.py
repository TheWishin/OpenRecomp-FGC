"""Controller rows for room drafts, host controls and authenticated chat decorations."""
from . import i18n


def _cycler(nav, g, key, label, choices, current, prefix="community_option"):
    shown = next((text for value, text in choices if value == current), "")
    return dict(kind="cycler", id=prefix + ":" + key, label=label, value=shown,
                options=choices, current=current,
                set=lambda value: nav._online_action(g, prefix + ":" + key + ":" + str(value)),
                hint="@online.community_hint", detail=dict(kicker="@online.community", title=label,
                    lead="@online.community_hint", rows=[dict(k="@current", v=shown)]))


def rows(nav, g, state, action):
    caps = state.get("capabilities") or {}
    data = state.get("community") or {}
    out = []
    if caps.get("mentions"):
        for player in state.get("players") or []:
            item = action("mention:" + str(player["id"]), "@online.mention_player")
            item["value"] = i18n.literal(player.get("name") or "")
            out.append(item)
    if not caps.get("community"):
        return out
    prefs = data.get("preferences") or {}
    out.append(dict(kind="heading", label="@online.community"))
    choices = [
        ("size", "@online.community_size", [(n, str(n)) for n in range(2, min(8, data.get("maximum", 8)) + 1)]),
        ("rotation", "@online.community_rotation", [("winner", "@online.rotation_winner"), ("queue", "@online.rotation_queue")]),
        ("access", "@online.community_access", [("none", "@online.room_open"), ("password", "@online.create_password_room"),
                                                ("code", "@online.create_code_room")]),
        ("hidden", "@online.community_hidden", [(False, "@off"), (True, "@on")]),
    ]
    if caps.get("room_tables"):
        choices.append(("mode", "@online.community_mode", [("line", "@online.room_line_mode"), ("tables", "@online.room_tables_mode")]))
    if data.get("first_to"):
        choices.append(("first_to", "@online.community_first_to", [(n, i18n.message("online.challenge_ft", wins=n))
                                                                for n in range(1, 11)]))
    if data.get("training"):
        choices.append(("training", "@online.community_training", [(False, "@off"), (True, "@on")]))
    if data.get("rematch_rules") and prefs.get("size") == 2 and prefs.get("mode") != "tables" and not prefs.get("training"):
        choices.append(("rematch_policy", "@online.community_policy", [("both_confirm", "@online.rematch_both"),
                                                                      ("auto_unless_declined", "@online.rematch_auto")]))
        if data.get("auto_skip"):
            choices.append(("auto_skip_after_round", "@online.community_auto_skip", [(False, "@off"), (True, "@on")]))
    for key, label, options in choices:
        out.append(_cycler(nav, g, key, label, options, prefs.get(key)))
    out.append(action("community_create", "@online.community_create"))
    room = data.get("room") or {}
    if not room:
        return out
    members = {p["id"]: p for p in room.get("members") or []}
    out.append(dict(kind="heading", label="@online.community_members"))
    for member in members.values():
        item = dict(kind="action", id="community_member:" + str(member["id"]),
                    label=i18n.literal(member.get("name") or ""), hint="@online.community_hint",
                    detail=dict(kicker="@online.community_members", title=i18n.literal(member.get("name") or ""),
                        rows=[dict(k="@online.community_rotation", v="@online.community_back_in_line"
                                   if member["id"] in room.get("line", []) else "@online.community_sit_out")]))
        out.append(item)
    if room.get("size", 2) > 2 or room.get("mode") == "tables":
        out.append(action("community_sit_out" if room.get("in_line") else "community_back_in_line",
                          "@online.community_sit_out" if room.get("in_line") else "@online.community_back_in_line"))
    out.append(action("community_copy_code", "@online.community_copy_code"))
    for table in room.get("tables") or []:
        names = [members.get(pid, {}).get("name") or "?" for pid in table.get("players") or []]
        item = dict(kind="action", id="community_table:" + str(table["id"]), label="@online.community_table",
                    value=i18n.literal(str(table["id"])), hint="@online.community_hint",
                    detail=dict(kicker="@online.community", title="@online.community_table", lead=i18n.literal(" / ".join(names)),
                                rows=[dict(k="@online.community_first_to", v=i18n.literal(" / ".join(str(n) for n in table.get("wins") or [])))]))
        out.append(item)
    if room.get("host"):
        out += [action("community_apply", "@online.community_apply"), action("community_new_code", "@online.community_new_code")]
        if room.get("lock") == "password":
            item = action("community_bar", "@online.community_bar")
            item["value"] = str(room.get("wrong_passwords", 0))
            out.append(item)
        for member in members.values():
            if member.get("name") != state.get("name"):
                item = action("community_kick:" + str(member["id"]), "@online.community_kick")
                item["value"] = i18n.literal(member.get("name") or "")
                out.append(item)
        if room.get("mode") == "tables":
            pair = data.get("pair") or {}
            options = [(p["id"], i18n.literal(p.get("name") or "")) for p in room.get("available") or []]
            table_options = [(t["id"], i18n.literal(str(t["id"]))) for t in room.get("tables") or [] if not t.get("playing")]
            for key, label, values in (("table", "@online.community_table", table_options),
                                       ("p1", "@online.community_player1", options), ("p2", "@online.community_player2", options)):
                if values:
                    out.append(_cycler(nav, g, key, label, values, pair.get(key), "community_pair_option"))
            out.append(action("community_pair", "@online.community_pair"))
    return out


def enhance_rows(out, state):
    players = {"challenge:" + str(p["id"]): p for p in state.get("players") or []}
    chat = state.get("chat") or []
    for item in out:
        player = players.get(item.get("id"))
        line = None
        if item.get("id", "").startswith("chat:"):
            try:
                line = chat[int(item["id"].partition(":")[2])]
            except (ValueError, IndexError):
                pass
        if (player or line or {}).get("badge") == "dev":
            item.setdefault("detail", {}).setdefault("rows", []).append(dict(k="@online.dev_badge", v="@yes"))
            item["value"] = "@online.dev_badge" if player else item.get("value", "")
        if line and line.get("mentioned"):
            item["hint"] = "@online.mention_notice"
            item.setdefault("detail", {}).setdefault("rows", []).append(dict(k="@online.mention_notice", v="@yes"))
    return out
