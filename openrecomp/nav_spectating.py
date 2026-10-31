"""Controller rows for installed-client live watching."""
from . import i18n


def rows(nav, g, state, action):
    view = state.get("spectating") or {}
    if not (state.get("capabilities") or {}).get("spectating") and not view.get("active"):
        return []
    out = [dict(kind="heading", label="@online.spectating")]
    if view.get("active") or view.get("pending"):
        item = action("spec_stop", "@online.stop_watching")
        item["disabled"] = False
        item["run"] = lambda: nav._online_action(g, "spec_stop")
        item["detail"]["lead"] = {"waiting": "@online.watch_waiting", "starting": "@online.watch_starting",
                                   "playing": "@online.watch_playing", "over": "@online.watch_over"}.get(
                                       view.get("state"), "@online.watch_waiting")
        item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(p.get("name") or ""))
                                    for p in view.get("players") or []]
        if view.get("delay") is not None:
            item["detail"]["rows"].append(dict(k="@online.watch_delay", v=str(view["delay"])))
        out.append(item)
    else:
        for target in view.get("targets") or []:
            label = {"friend": "@online.watch_friend", "room": "@online.watch_room",
                     "table": "@online.watch_table"}[target["kind"]]
            item = action(target["id"], label)
            item["value"] = i18n.literal(target["name"])
            item["detail"]["lead"] = "@online.watch_hint"
            out.append(item)
    if view.get("count"):
        out.append(dict(kind="action", id="spec_count", label="@online.spectators", value=str(view["count"]),
                        detail=dict(kicker="@online.spectating", title="@online.spectators", lead="", rows=[])))
    return out
