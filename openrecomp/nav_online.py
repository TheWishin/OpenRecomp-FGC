"""Login and search screens through the optional common adapter interface."""


class Online:
    def _online_action(self, g, action):
        if self._dry("@online.status"):
            return
        try:
            g.a.online_action(action)
        except Exception:  # noqa: BLE001 -- no raw server details or credentials in an error toast
            self.say("@online.failure", 12)
        self.focus[g.id + ":online"] = 0

    def _online_items(self, g):
        state = g.a.online_state()
        phase = state.get("phase", "offline")
        message = state.get("message") or "@online.login_hint"
        match = state.get("match") or {}
        rows = []
        if state.get("name"):
            rows.append(dict(k="@online.name", v=state["name"]))
        if phase in ("logged_in", "searching", "cancelling"):
            rows.append(dict(k="@online.session", v="@online.account_kind" if state.get("account") else "@online.guest_kind"))
        if phase == "matched":
            if match.get("opponent"):
                rows.append(dict(k="@online.opponent", v=match["opponent"]))
            if match.get("ping") is not None:
                rows.append(dict(k="@online.ping", v=str(match["ping"])))
        detail = dict(kicker="@section.online", title="@online.match_found" if phase == "matched" else "@online.status",
                      lead="@online.match_stop" if phase == "matched" else message, rows=rows)
        out = [dict(kind="action", id="online_status", label=detail["title"], hint=message, detail=detail)]

        def action(iid, label, hint=message):
            return dict(kind="action", id=iid, label=label, verb="@confirm", hint=hint,
                        detail=dict(kicker="@section.online", title=label, lead=hint, rows=rows),
                        run=lambda: self._online_action(g, iid))

        if phase in ("offline", "error", "kicked"):
            for tid, label in (("online_name", "@online.name"), ("online_password", "@online.password"), ("online_server", "@online.server")):
                value = g.a.text_value(tid)
                if tid == "online_password":
                    value = "•" * len(value)
                out.append(dict(kind="action", id=tid, label=label, value=value, verb="@change", hint=message,
                                detail=dict(kicker="@section.online", title=label, lead=message, rows=[]),
                                run=lambda tid=tid: self._open_osk(tid)))
            if state.get("saved_available"):
                out.append(action("login_saved", "@online.saved"))
            out += [action("login_guest", "@online.guest"), action("login_account", "@online.account")]
        elif phase == "logged_in":
            out += [action("search_casual", "@online.casual", "@online.search_hint"),
                    action("search_ranked", "@online.ranked", "@online.search_hint"),
                    action("logout", "@online.logout")]
        elif phase in ("connecting", "searching", "cancelling"):
            out.append(action("cancel", "@cancel" if phase == "connecting" else "@online.cancel"))
        elif phase == "matched":
            out.append(action("logout", "@online.logout", "@online.match_stop"))
        if g.a.native_label:
            out.append(self._native_item(g))
        return out

    def poll_online(self):
        if self.dry:
            return False
        changed = False
        for g in self.games:
            if not getattr(g.a, "online_supported", lambda: False)():
                continue
            try:
                if g.a.online_poll():
                    changed = True
                    state = g.a.online_state()
                    if state.get("phase") in ("matched", "kicked", "error"):
                        self.focus[g.id + ":online"] = 0
                        self.say(state.get("message") or "@online.status", 12)
            except Exception:  # noqa: BLE001 -- keep the timer alive without exposing login details
                self.say("@online.failure", 12)
                changed = True
        return changed

    def close_online(self):
        if not self.dry:
            for g in self.games:
                if getattr(g.a, "online_supported", lambda: False)():
                    try:
                        g.a.online_close()
                    except Exception:  # noqa: BLE001 -- a failed disconnect must not prevent closing the app
                        pass
