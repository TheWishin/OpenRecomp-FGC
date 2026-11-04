"""Controller rows for server-negotiated casual match choices."""
from . import i18n


def _cycler(nav, g, field, label, choices, current, hint):
    value = next((text for key, text in choices if key == current), "@auto")
    return dict(kind="cycler", id="challenge_" + field, label=label, value=value,
                options=choices, current=current,
                set=lambda choice: nav._online_action(g, "challenge_option:" + field + ":" + str(choice)),
                hint=hint, detail=dict(kicker="@online.challenge_preferences", title=label, lead=hint,
                                       rows=[dict(k="@current", v=value)]))


def rows(nav, g, state, action):
    from .nav_online_layout import connection

    if not (state.get("capabilities") or {}).get("challenge_preferences"):
        return []
    prefs = state.get("challenge_preferences") or {}
    out = [dict(kind="heading", label="@online.challenge_preferences")]
    hint = "@online.challenge_preferences_hint"
    if prefs.get("delay_supported"):
        maximum = 8 if prefs.get("delay_max") == 8 else 2
        choices = [("auto", "@auto")] + [(str(n), str(n)) for n in range(maximum + 1)]
        current = prefs.get("delay") if prefs.get("delay") in [key for key, _ in choices] else "auto"
        out.append(_cycler(nav, g, "delay", "@online.challenge_delay", choices, current, "@online.challenge_delay_hint"))
    if prefs.get("sets_supported"):
        choices = [(str(n), i18n.message("online.challenge_ft", wins=n)) for n in (1, 2, 3, 5, 10)]
        out.append(_cycler(nav, g, "first_to", "@online.challenge_first_to", choices, str(prefs.get("first_to", 1)), hint))
    if prefs.get("casual_supported"):
        choices = [("any", "@online.challenge_any_side"), ("0", "@online.challenge_p1"), ("1", "@online.challenge_p2")]
        side = prefs.get("side")
        out.append(_cycler(nav, g, "side", "@online.challenge_side", choices, "any" if side is None else str(side), hint))
        choices = [("random", "@online.challenge_random_stage")]
        choices += [(stage, i18n.literal(stage)) for stage in prefs.get("stages") or []]
        current = prefs.get("stage") if prefs.get("stage") in [key for key, _ in choices] else "random"
        out.append(_cycler(nav, g, "stage", "@online.challenge_stage", choices, current, hint))
    if prefs.get("auto_skip_supported"):
        out.append(_cycler(nav, g, "auto_skip", "@online.challenge_auto_skip", [("off", "@off"), ("on", "@on")],
                           "on" if prefs.get("auto_skip") else "off", hint))
    if state.get("open_challenges"):
        out.append(dict(kind="heading", label="@online.open_challenges"))
        for challenge in state["open_challenges"]:
            item = action("cancel_challenge:" + challenge["id"], i18n.literal(challenge.get("name") or ""))
            item["verb"] = "@online.cancel_challenge"
            item["value"] = connection(challenge)["text"]
            item["detail"]["rows"] = [dict(k="@online.ping", v=item["value"])] + _details(challenge)
            out.append(item)
    return out


def _details(info):
    details = []
    delay = info.get("delay")
    if type(delay) is int:
        delay = dict(frames=delay)
    elif not isinstance(delay, dict):
        delay = {}
    if "frames" in delay:
        details.append(dict(k="@online.challenge_delay", v=str(delay["frames"])))
    elif delay.get("auto"):
        details.append(dict(k="@online.challenge_delay", v="@auto"))
    if info.get("first_to"):
        details.append(dict(k="@online.challenge_first_to", v=i18n.message("online.challenge_ft", wins=info["first_to"])))
    wish = info.get("wish") or {}
    if wish.get("side") in (0, 1):
        details.append(dict(k="@online.challenge_side", v="@online.challenge_p1" if wish["side"] == 0 else "@online.challenge_p2"))
    if wish.get("stage"):
        details.append(dict(k="@online.challenge_stage", v="@online.challenge_random_stage" if wish["stage"] == "random"
                            else i18n.literal(wish["stage"])))
    return details


def enhance_rows(out, state):
    prefs = state.get("challenge_preferences") or {}
    incoming = prefs.get("incoming") or {}
    incoming_matches = incoming.get("id") == (state.get("challenge") or {}).get("id")
    for item in out:
        iid = item.get("id") or ""
        details = []
        if incoming_matches and iid in ("accept_challenge", "decline_challenge"):
            details = _details(incoming)
        elif iid.startswith("challenge:") and prefs:
            peer = iid.partition(":")[2]
            delay = prefs.get("delay", "auto")
            maximum = (prefs.get("peer_delay_max") or {}).get(peer, 2)
            effective = (delay if prefs.get("delay_supported") and delay in [str(n) for n in range(maximum + 1)]
                         else "@auto")
            details = [dict(k="@online.challenge_delay", v=effective),
                       dict(k="@online.challenge_first_to", v=i18n.message("online.challenge_ft",
                            wins=prefs.get("first_to", 1) if prefs.get("sets_supported") else 1))]
        if details:
            detail = item.setdefault("detail", {})
            detail["rows"] = list(detail.get("rows") or []) + details
