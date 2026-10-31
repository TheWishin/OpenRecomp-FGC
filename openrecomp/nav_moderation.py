"""Controller rows for personal mutes, player blocks and server chat notices."""
from . import i18n


def _player_action(action, requested, label, hint, name, target):
    item = action(requested, label, hint)
    item["value"] = i18n.literal(name)
    item["target"] = target
    item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(name))]
    return item


def rows(nav, g, state, action):
    if state.get("phase") != "logged_in":
        return []
    caps = state.get("capabilities") or {}
    data = state.get("moderation") or {}
    out = []
    notice = data.get("notice")
    if notice:
        out.append(dict(kind="action", id="moderation_notice", label="@online_chat.filter_notice",
                        hint=notice, detail=dict(kicker="@online.chat", title="@online_chat.filter_notice",
                                                 lead=notice, leadLines=6, rows=[])))
    muted = {row["name"].casefold(): row["name"] for row in data.get("mutes") or []
             if isinstance(row, dict) and isinstance(row.get("name"), str)}
    for player in state.get("players") or []:
        name, pid = player.get("name") or "", str(player.get("id") or "")
        if not name or not pid:
            continue
        target = (pid, name)
        if caps.get("mutes"):
            existing = muted.get(name.casefold())
            requested = "moderation_unmute:" + existing if existing else "moderation_mute:" + pid
            item = _player_action(action, requested, "@online_chat.unmute" if existing else "@online_chat.mute",
                                  "@online_chat.mute_hint", name, target)
            out.append(item)
        if caps.get("blocks"):
            out.append(_player_action(action, "moderation_block:" + pid, "@online_chat.block",
                                      "@online_chat.block_hint", name, target))
    if caps.get("mutes"):
        out += [dict(kind="heading", label="@online_chat.muted_players"),
                action("moderation_refresh_mutes", "@online_chat.refresh_mutes", "@online_chat.mute_hint")]
        for name in muted.values():
            item = _player_action(action, "moderation_unmute:" + name, "@online_chat.unmute",
                                  "@online_chat.mute_hint", name, name)
            item["id"] = "moderation_muted:" + name
            out.append(item)
    return out
