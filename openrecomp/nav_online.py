"""Login and search screens through the optional common adapter interface."""
from . import i18n


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
        capabilities = state.get("capabilities") or {}
        match_flow = capabilities.get("match_flow", False)
        rows = []
        if state.get("name"):
            rows.append(dict(k="@online.name", v=i18n.literal(state["name"])))
        if phase in ("logged_in", "searching", "cancelling", "starting", "playing", "result", "result_sent"):
            rows.append(dict(k="@online.session", v="@online.account_kind" if state.get("account") else "@online.guest_kind"))
        if state.get("rank"):
            rows.append(dict(k="@online.rank", v=i18n.literal(state["rank"])))
        if phase in ("matched", "starting", "playing", "result", "result_sent"):
            if match.get("opponent"):
                rows.append(dict(k="@online.opponent", v=i18n.literal(match["opponent"])))
            if match.get("ping") is not None:
                rows.append(dict(k="@online.ping", v=str(match["ping"])))
        title = "@online.match_found" if phase == "matched" else "@online.status"
        if phase in ("result", "result_sent"):
            title = "@online.result"
        elif phase == "playing":
            title = "@online.match_active"
        detail = dict(kicker="@section.online", title=title,
                      lead="@online.match_stop" if phase == "matched" and not match_flow else message, rows=rows)
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
                out.append(dict(kind="action", id=tid, label=label, value=i18n.literal(value), verb="@change", hint=message,
                                detail=dict(kicker="@section.online", title=label, lead=message, rows=[]),
                                run=lambda tid=tid: self._open_osk(tid)))
            if state.get("saved_available"):
                out.append(action("login_saved", "@online.saved"))
            out += [action("login_guest", "@online.guest"), action("login_account", "@online.account")]
        elif phase == "logged_in":
            out.append(action("search_casual", "@online.casual", "@online.search_hint"))
            if capabilities.get("ranked", True):
                out.append(action("search_ranked", "@online.ranked", "@online.search_hint"))
            if capabilities.get("lobby", False):
                self._online_lobby_items(g, state, out, action)
            out.append(action("logout", "@online.logout"))
        elif phase in ("connecting", "searching", "cancelling"):
            out.append(action("cancel", "@cancel" if phase == "connecting" else "@online.cancel"))
        elif phase == "matched":
            if match_flow:
                out += [action("start_match", "@online.start_match", "@online.start_hint"),
                        action("cancel_match", "@online.cancel_match")]
            else:
                out.append(action("logout", "@online.logout", "@online.match_stop"))
        elif phase == "starting" and match_flow:
            out.append(action("cancel_match", "@online.cancel_match"))
        elif phase == "playing" and match_flow:
            out.append(action("stop_match", "@online.stop_match"))
        elif phase == "result" and match_flow:
            out += [action("result_win", "@online.result_win", "@online.result_hint"),
                    action("result_loss", "@online.result_loss", "@online.result_hint"),
                    action("result_none", "@online.result_none", "@online.result_hint")]
        elif phase == "result_sent" and match_flow:
            out.append(action("return_lobby", "@online.return_lobby"))
        if g.a.native_label:
            out.append(self._native_item(g))
        # A reply can replace Cancel with Search, or reorder lobby targets between
        # input events. Never let the old row index authorize the replacement.
        challenge_id = (state.get("challenge") or {}).get("id")
        rows = [(item.get("id"), challenge_id if item.get("id") in ("accept_challenge", "decline_challenge") else None)
                for item in out]
        previous = self.online_rows.get(g.id)
        index = self.focus.get(g.id + ":online", 0)
        if previous is not None and (index >= len(previous) or index >= len(rows) or previous[index] != rows[index]):
            self.focus[g.id + ":online"] = 0
        self.online_rows[g.id] = rows
        return out

    def _online_lobby_items(self, g, state, out, action):
        challenge = state.get("challenge") or {}
        if challenge:
            details = [dict(k="@online.name", v=i18n.literal(challenge.get("name") or ""))]
            for iid, label in (("accept_challenge", "@online.accept_challenge"),
                               ("decline_challenge", "@online.decline_challenge")):
                item = action(iid, label)
                item["detail"]["rows"] = details
                out.append(item)
        out.append(dict(kind="heading", label="@online.players"))
        out.append(action("refresh_players", "@online.refresh_players"))
        for player in state.get("players") or []:
            item = action("challenge:" + str(player["id"]), i18n.literal(player["name"]), "@online.challenge_hint")
            item["verb"] = "@online.challenge"
            item["value"] = i18n.literal(player.get("rank") or "")
            item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(player["name"]))]
            if player.get("rank"):
                item["detail"]["rows"].append(dict(k="@online.rank", v=i18n.literal(player["rank"])))
            out.append(item)
        if not state.get("players"):
            out.append(dict(kind="action", id="no_players", label="@online.no_players", hint="@online.challenge_hint"))
        out.append(dict(kind="heading", label="@online.rooms"))
        out += [action("refresh_rooms", "@online.refresh_rooms"), action("create_room", "@online.create_room")]
        if state.get("room"):
            out.append(action("leave_room", "@online.leave_room"))
        for room in state.get("rooms") or []:
            name = room.get("name") or room.get("host")
            item = action("join_room:" + str(room["id"]), i18n.literal(name) if name else "@online.join_room", "@online.room_hint")
            item["verb"] = "@online.join_room"
            out.append(item)
        if not state.get("rooms"):
            out.append(dict(kind="action", id="no_rooms", label="@online.no_rooms", hint="@online.room_hint"))
        out.append(dict(kind="heading", label="@online.chat"))
        for index, message in enumerate(state.get("chat") or []):
            name = i18n.literal(message["name"]) if message.get("name") else "@online.chat"
            text = i18n.literal(message.get("text") or "")
            out.append(dict(kind="action", id="chat:" + str(index), label=name,
                            value=text, hint="@online.chat_hint",
                            detail=dict(kicker="@online.chat", title=name, lead=text, leadLines=10, rows=[])))
        if not state.get("chat"):
            out.append(dict(kind="action", id="no_chat", label="@online.no_chat", hint="@online.chat_hint"))
        out.append(dict(kind="action", id="online_chat", label="@online.chat", value=i18n.literal(g.a.text_value("online_chat")),
                        verb="@change", hint="@online.chat_hint",
                        detail=dict(kicker="@online.chat", title="@online.chat", lead="@online.chat_hint", rows=[]),
                        run=lambda: self._open_osk("online_chat")))
        out.append(action("send_chat", "@online.send_chat", "@online.chat_hint"))

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
                    if state.get("phase") in ("matched", "result", "result_sent", "kicked", "error"):
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
