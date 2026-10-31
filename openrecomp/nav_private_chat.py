"""Controller rows for private conversations and explicitly selected report evidence."""
from . import i18n


def rows(nav, g, state, action):
    caps = state.get("capabilities") or {}
    if not caps.get("private_chat"):
        return []
    data = state.get("private_chat") or {}
    threads = data.get("threads") or []
    selected = data.get("selected") or ""
    current = next((thread for thread in threads if thread.get("id") == selected), None)
    out = [dict(kind="heading", label="@online_chat.private_title")]
    listed_ids, listed_names = set(), set()
    by_id = {str(thread["id"]): thread for thread in threads}
    for player in list(threads) + list(state.get("players") or []):
        target = str(player["id"])
        name = player.get("name") or target
        normalized = name.lower()
        if target in listed_ids or normalized in listed_names:
            continue
        listed_ids.add(target)
        listed_names.add(normalized)
        thread = by_id.get(target) or {}
        item = action("private_open:" + target, "@online_chat.private_open", "@online_chat.private_hint")
        item["label"] = i18n.literal(name)
        item["target"] = (target, name)
        item["verb"] = "@online_chat.private_open"
        item["detail"] = dict(kicker="@online_chat.private_title", title=item["label"],
                              lead="@online_chat.private_hint", rows=[])
        if thread.get("unread"):
            item["value"] = i18n.message("online_chat.private_unread", count=thread["unread"])
        out.append(item)
    if current is None:
        return out

    def targeted(iid, label, hint="@online_chat.private_hint"):
        item = action(iid, label, hint)
        item["target"] = selected
        return item

    out.append(dict(kind="heading", label="@online_chat.private_history"))
    messages = current.get("messages") or []
    for index, message in enumerate(messages):
        reporting = bool(caps.get("private_reports") and message.get("id"))
        name = i18n.literal(message.get("name") or "")
        text = i18n.literal(message.get("text") or "")
        if reporting:
            item = targeted("private_select:" + str(message["id"]), name)
            item["verb"] = "@online_chat.private_selected" if message.get("selected") else "@online_chat.private_select"
        else:
            item = dict(kind="action", id="private_message:" + str(index), label=name, target=selected)
        item.update(value=text, hint="@online_chat.private_hint",
                    detail=dict(kicker="@online_chat.private_history", title=name, lead=text, leadLines=10, rows=[]))
        if reporting:
            item["detail"]["rows"] = [dict(k="@online_chat.private_selected", v="@on" if message.get("selected") else "@off")]
        out.append(item)
    if not messages:
        out.append(dict(kind="action", id="private_empty", label="@online_chat.private_empty",
                        hint="@online_chat.private_hint", target=selected))
    compose = nav._online_text_item(g, "online_private_chat", "@online_chat.private_compose", "@online_chat.private_hint")
    compose["target"] = selected
    out += [compose, targeted("private_send", "@online_chat.private_send")]
    if caps.get("private_reports") and messages:
        hint = i18n.message("online_chat.private_report_hint", count=data.get("report_limit", 5))
        reason = nav._online_text_item(g, "online_private_report_reason", "@online_chat.report_reason", hint)
        reason["target"] = selected
        out += [reason, targeted("private_report", "@online_chat.private_report", hint)]
    out.append(targeted("private_close", "@online_chat.private_close"))
    return out
