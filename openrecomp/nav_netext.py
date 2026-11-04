"""Controller rows and the two confirmations for T5DR's new online options. No Qt."""
from . import i18n


def choice(nav, g, key, label, hint, options, current):
    value = next((label for value, label in options if type(value) is type(current) and value == current), options[0][1])

    def select(value):
        nav._online_action(g, "netext_set:" + key + ":" + ("any" if value is None else str(value).lower()))
        target = next((n for n, row in enumerate(nav.items()) if row.get("id") == "netext_" + key), None)
        if target is not None:
            nav.focus[nav.key()] = target

    return dict(kind="cycler", id="netext_" + key, label=label, hint=hint, value=value,
        options=options, current=current, set=select,
        detail=dict(kicker="@section.online", title=label, lead=hint, rows=[dict(k="@current", v=value)]))


def rows(nav, g, state, action):
    caps = state.get("capabilities") or {}
    if state.get("phase") != "logged_in" or not caps.get("online_feel"):
        return []
    prefs = state.get("netext") or {}
    out = []
    if caps.get("search_options"):
        out.append(dict(kind="heading", label="@netext.search_options"))
        for key, options in (("max_ping", [(None, "@netext.any")] + [(n, i18n.message("online_ui.ping_ms", ping=n)) for n in (60, 100, 150)]),
                              ("no_wifi", [(False, "@off"), (True, "@on")]),
                              ("steady", [(False, "@off"), (True, "@on")])):
            out.append(choice(nav, g, key, "@netext." + key, "@netext.search_hint", options, prefs.get(key)))
        shortcut = action("netext_options", "@netext.search_options", "@netext.search_hint")
        shortcut["run"] = lambda: show_options(nav)
        out.append(shortcut)
    out.append(dict(kind="heading", label="@netext.online_feel"))
    out.append(choice(nav, g, "online_feel", "@netext.online_feel", "@netext.feel_hint",
                      [(feel, "@netext." + feel) for feel in ("responsive", "balanced", "smooth")],
                      prefs.get("online_feel", "balanced")))
    out.append(choice(nav, g, "net_line", "@netext.net_line", "@netext.line_hint",
                      [(False, "@off"), (True, "@on")], bool(prefs.get("net_line"))))
    if caps.get("forget_me"):
        out.append(dict(kind="heading", label="@netext.forget"))
        if not caps.get("account_tools"):
            item = nav._online_text_item(g, "online_current_password", "@online120.current_password", "@netext.forget_hint")
            item["value"] = i18n.literal("\u2022" * len(g.a.text_value("online_current_password")))
            out.append(item)
        operation = "netext_forget_confirm" if state.get("forget_counts") is not None else "netext_forget_preview"
        item = action(operation, "@netext.forget", "@netext.forget_review" if state.get("forget_counts") is not None else "@netext.forget_hint")
        item["run"] = lambda: ask(nav, g, operation)
        out.append(item)
        if state.get("forget_counts") is not None:
            out.append(action("netext_forget_cancel", "@cancel", "@netext.forget_hint"))
    return out


def show_options(nav):
    items = nav.items()
    nav._show_chapter(items, "account")
    target = next((n for n, row in enumerate(items) if row.get("id") == "netext_max_ping"), None)
    if target is not None:
        nav.focus[nav.key()] = target


def ask(nav, g, operation):
    state = g.a.online_state()
    nav._netext_target = (g, state.get("netext_session"), state.get("name"), operation, state.get("forget_counts"))
    nav._ask("netext_forget")


def dialog(nav, action):
    if action in ("left", "right", "up", "down"):
        nav.exit_focus = 1 - nav.exit_focus
        return
    if action not in ("confirm", "back"):
        return
    g, session, name, operation, counts = nav._netext_target
    state = g.a.online_state()
    nav.overlay = None
    valid = (nav.game is g and state.get("netext_session") == session and state.get("name") == name
             and state.get("phase") == "logged_in" and (state.get("capabilities") or {}).get("forget_me")
             and state.get("forget_counts") == counts)
    if valid and action == "confirm" and nav.exit_focus == 1:
        nav._online_action(g, operation)
    else:
        nav._online_action(g, "netext_forget_cancel")
    nav._netext_target = None


def view_dialog(nav, v):
    _g, _session, name, operation, counts = nav._netext_target
    text = "@netext.forget_first"
    if operation == "netext_forget_confirm":
        text = i18n.message("netext.forget_final", name=i18n.literal(name or ""), **(counts or {}))
    v["dialog"] = dict(title="@netext.forget", text=text,
        options=[dict(label="@no", index=0, focused=nav.exit_focus == 0),
                 dict(label="@yes", index=1, focused=nav.exit_focus == 1)])
    v["hint"] = "@dialog_hint"
    v["prompts"] = [nav.prompt("confirm", "@confirm"), nav.prompt("right", "@switch"), nav.prompt("back", "@cancel")]


def where(row):
    return " ".join(value for value in (str(row.get("area") or "").upper(), row.get("lang") or "") if value)
