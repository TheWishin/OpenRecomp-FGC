"""Login and search screens through the optional common adapter interface."""
from . import i18n, nav_feedback, ui_sound
from .nav_keyboard import ONLINE_PASSWORDS


class Online:
    def challenge_player(self, player_id):
        """Double-click and pad confirmation share one guarded semantic challenge."""
        if self.screen != "hub" or self.overlay or self.section() != "online":
            return
        state = self.game.a.online_state()
        if state.get("phase") != "logged_in" or state.get("busy"):
            return
        player = next((p for p in state.get("players") or [] if str(p.get("id")) == str(player_id)), None)
        own = str((state.get("me") or {}).get("id") or "self")
        if not player or str(player_id) == own or player.get("status") not in (None, "idle", "online", "available"):
            return
        if (state.get("capabilities") or {}).get("challenges") is False or player.get("challenge") is False:
            return
        iid = "challenge:" + str(player_id)
        if nav_feedback.records(self, self.game.id).get(iid, {}).get("kind") in ("pending", "waiting"):
            return
        items = self.items()
        item = next((it for it in items if it.get("id") == iid), None)
        if item and not item.get("disabled"):
            self.focus[self.key()] = items.index(item)
            self.sounded("confirm", self._activate, item)

    @staticmethod
    def _direct_online(g):
        """Direct connection is an explicit adapter mode opened from Advanced settings."""
        capabilities = g.a.online_state().get("capabilities") or {}
        return bool(capabilities.get("direct_ip"))

    def _open_direct_online(self, g):
        if self._online_action(g, "mode_direct") and self._direct_online(g):
            self.__dict__.setdefault("direct_from_settings", set()).add(g.id)
            self._go(g, "online")

    def _direct_online_back(self, g):
        if not self._online_action(g, "disconnect"):
            return
        if g.id in self.__dict__.get("direct_from_settings", set()):
            if self._online_action(g, "mode_lobby") and not self._direct_online(g):
                self.direct_from_settings.discard(g.id)
                self._go(g, "settings")
            return
        self.screen = "start"
        self.start_focus = self.games.index(g)

    def _direct_online_items(self, g):
        state = g.a.online_state()
        phase = state.get("phase", "offline")
        busy = bool(state.get("busy")) or phase in ("checking", "starting", "playing")
        message = state.get("message") or "@t4.direct_hint"
        checks = state.get("checks") or []
        role = state.get("role", "host")
        rows = [dict(k="@t4.direct_role", v="@t4.direct_role_host" if role == "host" else "@t4.direct_role_join")]
        identity = [("build_id", "@t4.direct_build_id"), ("compiler", "@t4.direct_compiler")]
        rows += [dict(k=label, v=i18n.literal(state[key])) for key, label in identity if state.get(key)]
        rows += [dict(k=check["label"], v=check["value"], accent=check.get("ok") is False) for check in checks]
        out = [dict(kind="action", id="online_status", label="@t4.direct_title", hint=message,
                    detail=dict(kicker="@section.online", title="@t4.direct_title", lead=message,
                                leadLines=6, rows=rows))]
        out += self._other_launcher_items(g, state)

        def action(iid, label, hint=message, disabled=False):
            return dict(kind="action", id=iid, label=label, disabled=disabled,
                        verb="" if disabled else "@confirm", hint=hint,
                        detail=dict(kicker="@t4.direct_title", title=label, lead=hint, leadLines=6, rows=[]),
                        run=None if disabled else lambda: self._online_action(g, iid))

        out += [action("host", "@t4.direct_host", "@t4.direct_hint", busy),
                action("join", "@t4.direct_join", "@t4.direct_hint", busy)]
        address = self._online_text_item(g, "online_address", "@t4.direct_address", "@t4.direct_address_hint")
        address["detail"]["rows"] = [dict(k="@current", v=i18n.literal(g.a.text_value("online_address")))]
        if busy:
            address.update(disabled=True, run=None, verb="")
        out.append(address)
        out.append(action("check", "@t4.direct_check", "@t4.direct_hint", busy))
        for check in checks:
            out.append(dict(kind="action", id="check:" + check["id"], label=check["label"],
                            value=check["value"], hint=check["value"],
                            detail=dict(kicker="@t4.direct_checks", title=check["label"], lead=check["value"],
                                        leadLines=6, rows=[])))
        if phase == "checked" and checks and all(check.get("ok") is True for check in checks):
            out.append(action("start_match", "@t4.direct_start"))
        elif phase in ("checking", "starting"):
            out.append(action("cancel_match", "@cancel"))
        elif phase == "playing":
            out.append(action("stop_match", "@online.stop_match"))
        out.append(action("collect_logs", "@t4.direct_logs", disabled=busy))
        for key, label in identity + [("log_path", "@t4.direct_log_path")]:
            if state.get(key):
                value = i18n.literal(state[key])
                out.append(dict(kind="action", id="direct:" + key, label=label, value=value, hint=value,
                                detail=dict(kicker="@t4.direct_title", title=label, lead=value,
                                            leadLines=10, rows=[])))
        if (state.get("capabilities") or {}).get("lobby_available"):
            out.append(action("mode_lobby", "@t4.lobby_mode", "@t4.lobby_mode_hint", busy))
        for step in ("firewall", "forward", "tailscale", "check"):
            label = "@t4.network." + step + "_title"
            hint = "@t4.network." + step
            out.append(dict(kind="action", id="network:" + step, label=label, hint=hint,
                            detail=dict(kicker="@t4.network.title", title=label, lead=hint,
                                        leadLines=10, rows=[])))
        back = action("direct_back", "@t4.direct_back", "@t4.direct_hint")
        back["run"] = lambda: self._direct_online_back(g)
        out.append(back)
        return self._remember_online_rows(g, out)

    def _online_action(self, g, action):
        if self._dry("@online.status"):
            return True
        try:
            state = g.a.online_state()
        except Exception:  # noqa: BLE001 -- snapshot failures use the same safe receipt as action failures
            self.say("@online.failure", 3)
            return False
        switching_chat = action == "private_close" or action.startswith("private_open:")
        if switching_chat:
            editing = getattr(self, "native_edit", "")
            if editing in ("online_chat", "online_private_chat", "online_private_report_reason"):
                self.finish_edit(editing, False)
            selected = str((state.get("private_chat") or {}).get("selected") or "")
            self.__dict__.setdefault("private_drafts", {}).setdefault(g.id, {})[selected] = g.a.text_value("online_private_chat")
            if action.startswith("private_open:"):
                self.__dict__.setdefault("closed_chat_tabs", {}).setdefault(g.id, {}).pop(action.partition(":")[2], None)
        receipt = nav_feedback.records(self, g.id).get(action, {})
        if action.startswith("challenge:") and receipt.get("kind") == "waiting" and any(offer.get("id") == receipt.get("challenge")
                                                     for offer in state.get("open_challenges") or []):
            action = "cancel_challenge:" + receipt["challenge"]
        tracked = nav_feedback.begin(self, g, action, state)
        if tracked is None:
            return True
        success = True
        try:
            g.a.online_action(action)
            if switching_chat:
                selected = str((g.a.online_state().get("private_chat") or {}).get("selected") or "")
                if action.startswith("private_open:"):
                    self.__dict__.setdefault("closed_chat_tabs", {}).setdefault(g.id, {}).pop(selected, None)
                g.a.set_text_value("online_private_chat", self.__dict__.get("private_drafts", {}).get(g.id, {}).get(selected, ""))
            nav_feedback.observe(self, g, g.a.online_state())
            self.observe_online_sound(g, g.a.online_state())
            if action in ("result_win", "result_loss") and state.get("phase") == "result":
                self.hint_sound(ui_sound.WIN if action == "result_win" else ui_sound.LOSS)
        except Exception:  # noqa: BLE001 -- no raw server details or credentials in an error toast
            self.say("@online.failure", 12)
            nav_feedback.fail(self, g, action)
            success = False
        if not tracked:
            self.focus[g.id + ":online"] = 0
        return success

    def tick_online_feedback(self, dt):
        changed = nav_feedback.tick(self, dt)
        self.tick_offer_sounds()
        return changed

    def online_profile_shortcut(self):
        if self.screen != "hub" or self.section() != "online" or self.overlay:
            return False
        if getattr(self, "main_menu_game", "") == self.game.id:
            return False
        items = self.items()
        item = items[self.focus_index(items)] if items else {}
        group = item.get("group")
        if not group or item.get("region") != "lobby":
            return False
        profile = next((it for it in items if it.get("group") == group
                        and (it.get("id") or "").startswith("profile_player:")), None)
        if profile and profile.get("run"):
            self._guard(self._activate, profile)
            return True
        return False

    OTHER_TEXTS = {("native", "t5dr"): "@other_launcher.native_t5dr", ("native", "t4"): "@other_launcher.native_t4",
                   "online": "@other_launcher.online", "window": "@other_launcher.window"}
    OTHER_PHASES = ("offline", "error", "kicked", "connecting", "logged_in", "searching", "cancelling", "checked")

    def _other_launcher_text(self, state):
        """The note's sentence when another launcher of this game is open and the player has not chosen yet."""
        other = state.get("other_launcher") or {}
        if not other.get("kind") or other.get("choice") == "here" or state.get("phase", "offline") not in self.OTHER_PHASES:
            return ""
        if other.get("choice") == "other":
            return "@other_launcher.kept_note"
        return (self.OTHER_TEXTS.get((other["kind"], other.get("game"))) or self.OTHER_TEXTS.get(other["kind"])
                or "@other_launcher.window")

    def _other_launcher_items(self, g, state):
        """Use OpenRecomp here / Keep the other one: the note's two buttons (owner: "it should say: hey, you are logged
        in, but you can really only play in one launcher")."""
        text = self._other_launcher_text(state)
        if not text:
            return []

        buttons = (("other_here", "@other_launcher.use_here"), ("other_keep", "@other_launcher.keep_other"))
        if (state.get("other_launcher") or {}).get("choice") == "other":
            buttons = buttons[:1]                 # kept the other one: only the way back
        return [dict(kind="action", id=iid, label=label, verb="@confirm", hint=text,
                     detail=dict(kicker="@other_launcher.title", title=label, lead=text, leadLines=6, rows=[]),
                     run=lambda iid=iid: self._online_action(g, iid)) for iid, label in buttons]

    def _online_items(self, g):
        from . import nav_rules

        state = g.a.online_state()
        phase = state.get("phase", "offline")
        message = state.get("message") or "@online.login_hint"
        match = state.get("match") or {}
        capabilities = state.get("capabilities") or {}
        match_flow = capabilities.get("match_flow", False)
        rows = []
        rows.extend(nav_rules.detail_rows(state))
        if state.get("name"):
            rows.append(dict(k="@online.name", v=i18n.literal(state["name"])))
        if phase in ("logged_in", "searching", "cancelling", "matched", "starting", "playing", "result", "result_sent"):
            rows.append(dict(k="@online.session", v="@online.account_kind" if state.get("account") else "@online.guest_kind"))
        if state.get("rank"):
            rows.append(dict(k="@online.rank", v=i18n.literal(state["rank"])))
        if phase in ("matched", "starting", "playing", "result", "result_sent"):
            if match.get("opponent"):
                rows.append(dict(k="@online.opponent", v=i18n.literal(match["opponent"])))
            from .nav_online_layout import connection

            conn = connection(match)
            rows.append(dict(k="@online.ping", v=conn["text"]))
            if conn["path"]:
                rows.append(dict(k="@online_ui.path", v=conn["path"]))
            # Who plays which side (T4: P1 = the host), with name, rank and rank badge.
            from .nav_common import uri
            for index, side in enumerate((match.get("sides") or [])[:2]):
                if not isinstance(side, dict) or not side.get("name"):
                    continue
                name, rank = i18n.literal(side["name"]), i18n.literal(side.get("rank") or "")
                if side.get("you"):
                    value = (i18n.message("t4.side_you_rank", name=name, rank=rank) if side.get("rank")
                             else i18n.message("t4.side_you", name=name))
                else:
                    value = i18n.message("t4.side_rank", name=name, rank=rank) if side.get("rank") else name
                tier = side.get("tier")
                rows.append(dict(k="@online.challenge_p1" if index == 0 else "@online.challenge_p2", v=value,
                                 accent=bool(side.get("you")),
                                 plate=uri(g.a.rank_plate(tier)) if isinstance(tier, int) else ""))
        result = state.get("result") or {}
        if phase in ("result", "result_sent") and "winner" in result:
            winner, slot = result.get("winner"), result.get("slot")
            if winner is None:
                rows.append(dict(k="@online.result", v="@online.result_draw"))
            elif type(winner) is int and winner in (0, 1) and type(slot) is int and slot in (0, 1):
                rows.append(dict(k="@online.result", v="@online.result_won" if winner == slot else "@online.result_lost"))
            score = result.get("score")
            if isinstance(score, (list, tuple)) and len(score) == 2:
                rows.append(dict(k="@online.score", v=str(score[0]) + "–" + str(score[1])))
        set_state = state.get("set") or {}
        if set_state:
            wins = set_state.get("wins") or []
            if len(wins) == 2:
                rows.append(dict(k="@online.set", v=i18n.message("online.set_score", mine=wins[0], theirs=wins[1])))
            if set_state.get("first_to"):
                rows.append(dict(k="@online.set", v=i18n.message("online.first_to", wins=set_state["first_to"])))
            if set_state.get("number") and set_state.get("best_of"):
                rows.append(dict(k="@online.set", v=i18n.message("online.set_game", number=set_state["number"], best=set_state["best_of"])))
            if state.get("character_locked"):
                rows.append(dict(k="@your_fighter", v="@online.character_locked"))
            if isinstance(set_state.get("next"), dict) and set_state["next"].get("in") is not None:
                rows.append(dict(k="@online.set", v=i18n.message("online.set_next", seconds=set_state["next"]["in"])))
        title = "@online.match_found" if phase == "matched" else "@online.status"
        if phase in ("result", "result_sent"):
            title = "@online.result"
        elif phase == "playing":
            title = "@online.match_active"
        detail = dict(kicker="@section.online", title=title,
                      lead="@online.match_stop" if phase == "matched" and not match_flow else message,
                      leadLines=6 if phase in ("offline", "error", "kicked") else 3, rows=rows)
        out = [dict(kind="action", id="online_status", label=detail["title"], hint=message, detail=detail)]
        out += self._other_launcher_items(g, state)

        def action(iid, label, hint=message):
            return dict(kind="action", id=iid, label=label, verb="@confirm", hint=hint,
                        detail=dict(kicker="@section.online", title=label, lead=hint,
                                    leadLines=6 if phase in ("offline", "error", "kicked") else 3, rows=rows),
                        run=lambda: self._online_action(g, iid))

        if phase == "logged_in" and state.get("recovery_codes"):
            out[0].update(label="@online.recovery_codes", hint="@online.recovery_hint",
                          detail=dict(kicker="@section.online", title="@online.recovery_codes",
                                      lead="@online.recovery_hint", rows=[]))
            for index, code in enumerate(state["recovery_codes"]):
                out.append(dict(kind="action", id="recovery_code:" + str(index), label=i18n.literal(code),
                                hint="@online.recovery_hint",
                                detail=dict(kicker="@online.recovery_codes", title=i18n.literal(code),
                                            lead="@online.recovery_hint", rows=[])))
            out.append(action("acknowledge_recovery", "@online.recovery_done", "@online.recovery_hint"))
        elif phase in ("offline", "error", "kicked"):
            for tid, label in (("online_name", "@online.name"), ("online_password", "@online.password"), ("online_server", "@online.server")):
                value = g.a.text_value(tid)
                if tid == "online_password":
                    value = "•" * len(value)
                out.append(dict(kind="action", id=tid, label=label, value=i18n.literal(value), verb="@change", hint=message,
                                detail=dict(kicker="@section.online", title=label, lead=message, leadLines=6, rows=[]),
                                run=lambda tid=tid: self._edit_field(tid)))
            if state.get("saved_available") and state.get("saved_shared"):
                out.append(action("login_saved", "@t4.saved_shared", "@t4.saved_shared_hint"))
            elif state.get("saved_available"):
                out.append(action("login_saved", "@online.saved"))
            out += [action("login_guest", "@online.guest"), action("login_account", "@online.account")]
            if capabilities.get("registration", False):
                out.append(action("login_register", "@online.register"))
            from . import nav_accounts
            out.extend(nav_accounts.rows(self, g, state, action))
        elif phase in ("logged_in", "searching", "cancelling"):
            fighters = g.a.fighters()
            if fighters:
                locked = bool(state.get("character_locked"))
                chosen = g.a.chosen_fighter()
                name = next((i18n.literal(f["name"]) for f in fighters if f["key"] == chosen), "@random" if chosen == "random" else i18n.literal(chosen))
                fighter = dict(kind="action", id="online_fighter", label="@your_fighter",
                               value=name, disabled=locked,
                               verb="" if locked else "@change", hint="@online.character_locked" if locked else "@fighter.lead",
                               detail=dict(kicker="@section.online", title="@your_fighter",
                                           lead="@online.character_locked" if locked else "@fighter.lead", rows=[]),
                               run=None if locked else self._open_fighters)
                out.append(fighter)
            out.append(action("search_casual", "@online.casual", "@online.search_hint"))
            if capabilities.get("ranked", True):
                out.append(action("search_ranked", "@online.ranked", "@online.search_hint"))
            if phase in ("searching", "cancelling"):
                out.append(action("cancel", "@online.cancel"))
            if capabilities.get("lobby", False):
                self._online_lobby_items(g, state, out, action)
                self._online_feature_items(g, state, out, action)
            out.append(action("logout", "@online.logout"))
            if phase in ("searching", "cancelling"):
                for item in out:
                    if item.get("run") and item.get("id") != "cancel":
                        item.update(disabled=True, run=None, verb="")
                if phase == "cancelling":
                    next(item for item in out if item.get("id") == "cancel").update(
                        disabled=True, run=None, verb="", label="@online.cancelling")
        elif phase in ("connecting", "searching", "cancelling"):
            out.append(action("cancel", "@cancel" if phase == "connecting" else "@online.cancel"))
        elif phase == "matched":
            if match_flow:
                from . import nav_community

                out += nav_community.match_rows(state, action)
                out.append(action("cancel_match", "@online.cancel_match"))
            else:
                out.append(action("logout", "@online.logout", "@online.match_stop"))
        elif phase == "starting" and match_flow:
            from . import nav_community

            out += nav_community.match_rows(state, action)
            out.append(action("cancel_match", "@online.cancel_match"))
        elif phase == "playing" and match_flow:
            out.append(action("stop_match", "@online.stop_match"))
        elif phase == "result" and match_flow:
            out += [action("result_win", "@online.result_win", "@online.result_hint"),
                    action("result_loss", "@online.result_loss", "@online.result_hint"),
                    action("result_none", "@online.result_none", "@online.result_hint")]
        elif phase == "result_sent" and match_flow:
            if capabilities.get("rematch", False):
                rematch = action("rematch", "@online.rematch", "@online.rematch_hint")
                if state.get("busy") or capabilities.get("rematch_ready") is False:
                    # Not ready yet (a request of this launcher still runs, the match driver is not there): a press
                    # would be dropped, so the row says so instead of looking pressable.
                    rematch.update(disabled=True, run=None, verb="")
                out.append(rematch)
            out.append(action("return_lobby", "@online.return_lobby"))
        if capabilities.get("leave_set", False):
            out.append(action("leave_set", "@online.leave_set", "@online.leave_ranked_set" if set_state.get("rated") else "@online.leave_set"))
        if g.a.native_label:
            out.append(self._native_item(g))
        if phase == "logged_in":
            delay = next((setting for setting in g.a.settings() if setting.get("id") == "input_delay"), None)
            if delay and delay.get("options"):
                control = self._cycler_item(g, delay)
                control["id"] = "online_input_delay"
                out.append(control)
            elif capabilities.get("lobby"):
                out.append(dict(kind="action", id="online_input_delay", label="@input_delay", value="@official_ui.unavailable",
                    disabled=True, hint="@official_ui.unavailable", detail=dict(title="@input_delay", lead="@official_ui.unavailable", rows=[])))
        out = self._online_layout_items(g, state, out)
        out = self._login_items(g, state, out)
        from .nav_lobby_chat import ensure_rows
        out = ensure_rows(self, g, state, out)
        out = self._remember_online_rows(g, out, state)
        self._land_on_result(g, state, out)
        if out and out[0].get("region") == "login":
            self._login_start_focus(g, out)
        else:
            self.__dict__.setdefault("login_focused", set()).discard(g.id)
        return out

    def _land_on_result(self, g, state, out):
        """The result page's focus starts on its first action (Rematch, else Back to lobby), never on the status
        row: that row is the card's title, nothing shows it focused and a press on it does nothing. A Rematch row
        that appears a moment later takes the focus too -- while nobody has touched the pad or the mouse."""
        memory = self.__dict__.setdefault("result_landing", {})
        phase = state.get("phase")
        if phase not in ("result", "result_sent") or not (state.get("capabilities") or {}).get("match_flow"):
            memory.pop(g.id, None)
            return
        order = ("rematch", "return_lobby") if phase == "result_sent" else ("result_win",)
        ids = [it.get("id") for it in out]
        target = next((iid for iid in order if iid in ids), None)
        if target is None:
            return
        keys = {g.id + ":online"} | ({self.key()} if g is self.game else set())
        landing = memory.get(g.id)
        if landing and landing["phase"] == phase:
            untouched = self.trail is landing["trail"] and all(
                ids[min(self.focus.get(key, 0), len(ids) - 1)] == landing["id"] for key in keys)
            if not (untouched and target != landing["id"]):
                return
        index = ids.index(target)
        for key in keys:
            self.focus[key] = index
        memory[g.id] = dict(phase=phase, id=target, trail=self.trail)

    def _online_feature_items(self, g, state, out, action):
        from . import (nav_accounts, nav_challenges, nav_community, nav_moderation, nav_private_chat,
                       nav_profiles, nav_rules, nav_spectating, nav_tournaments, nav_netext)

        for module in (nav_profiles, nav_tournaments, nav_spectating, nav_community, nav_accounts, nav_rules,
                       nav_challenges, nav_moderation, nav_private_chat, nav_netext):
            out.extend(module.rows(self, g, state, action))
        nav_community.enhance_rows(out, state)
        nav_challenges.enhance_rows(out, state)

    def _remember_online_rows(self, g, out, state=None):
        state = state or {}
        editing = getattr(self, "native_edit", "")
        if editing.startswith("online_") and not any(item.get("id") == editing or item.get("opens") == "text:" + editing
                                                     for item in out):
            self.finish_edit(editing, False)
        # A reply can replace Cancel with Search, or reorder lobby targets between
        # input events. Never let the old row index authorize the replacement.
        challenge_id = (state.get("challenge") or {}).get("id")
        invite_id = (state.get("outgoing_invite") or {}).get("id")
        rows = [(item.get("id"), challenge_id if item.get("id") in ("accept_challenge", "decline_challenge")
                 else invite_id if item.get("id") == "cancel_invite" else None, item.get("target"))
                for item in out]
        previous = self.online_rows.get(g.id)
        index = self.focus.get(g.id + ":online", 0)
        if previous is not None and (index >= len(previous) or index >= len(rows) or previous[index] != rows[index]):
            # The same row moved (a chat line or a player arrived above it): the focus goes with it -- it is the same
            # action. A row that is gone or changed its target: the top (the status row, which does nothing).
            moved = rows.index(previous[index]) if index < len(previous) and previous[index] in rows else 0
            self.focus[g.id + ":online"] = moved
        self.online_rows[g.id] = rows
        return out

    def _online_lobby_items(self, g, state, out, action):
        capabilities = state.get("capabilities") or {}
        challenge = state.get("challenge") or {}
        if challenge:
            from .nav_online_layout import connection

            details = [dict(k="@online.name", v=i18n.literal(challenge.get("name") or ""))]
            details.append(dict(k="@online.ping", v=connection(challenge)["text"]))
            for iid, label in (("accept_challenge", "@online.accept_challenge"),
                               ("decline_challenge", "@online.decline_challenge")):
                item = action(iid, label)
                item["detail"]["rows"] = details
                pending = any(row.get("incoming") == str(challenge.get("id") or "")
                              and row.get("kind") in ("pending", "waiting")
                              for row in nav_feedback.records(self, g.id).values())
                if pending or state.get("busy") or not challenge.get("id"):
                    item.update(disabled=True, run=None, verb="")
                out.append(item)
        out.append(dict(kind="heading", label="@online.players"))
        out.append(action("refresh_players", "@online.refresh_players"))
        for player in state.get("players") or []:
            item = action("challenge:" + str(player["id"]), i18n.literal(player["name"]), "@online.challenge_hint")
            item["verb"] = "@online.challenge"
            own = str((state.get("me") or {}).get("id") or "self")
            if (str(player.get("id")) == own or player.get("status") not in (None, "idle", "online", "available")
                    or capabilities.get("challenges") is False or player.get("challenge") is False
                    or state.get("phase") != "logged_in" or state.get("busy")):
                item.update(disabled=True, run=None, verb="", hint="@online_ui.status.playing")
            receipt = nav_feedback.records(self, g.id).get(item["id"], {})
            if receipt.get("kind") in ("pending", "waiting"):
                can_cancel = receipt.get("kind") == "waiting" and any(
                    offer.get("id") == receipt.get("challenge") for offer in state.get("open_challenges") or [])
                item.update(verb="@cancel" if can_cancel else "", disabled=not can_cancel,
                            hint=nav_feedback.view(self, g.id, item["id"])["text"])
            item["value"] = i18n.literal(player.get("rank") or "")
            item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(player["name"]))]
            if player.get("rank"):
                item["detail"]["rows"].append(dict(k="@online.rank", v=i18n.literal(player["rank"])))
            if player.get("build_note"):
                # Another build cannot be paired: say why (other version / other game files or compiler).
                item["detail"]["rows"].append(dict(k="@t4.build_differs", v=player["build_note"]))
                if not item.get("disabled"):
                    item["hint"] = player["build_note"]
            out.append(item)
        if not state.get("players"):
            out.append(dict(kind="action", id="no_players", label="@online.no_players", hint="@online.challenge_hint"))
        if capabilities.get("rooms", True):
            self._online_room_items(g, state, out, action)
        self._online_chat_items(g, state, out, action)
        if capabilities.get("friends", False):
            self._online_friend_items(g, state, out, action)

    def _online_room_items(self, g, state, out, action):
        capabilities = state.get("capabilities") or {}
        out.append(dict(kind="heading", label="@online.rooms"))
        out += [action("refresh_rooms", "@online.refresh_rooms"), action("create_room", "@online.create_room")]
        if capabilities.get("private_rooms", False):
            for tid, label in (("online_room_name", "@online.room_name"),
                               ("online_room_password", "@online.room_password"),
                               ("online_room_code", "@online.room_code")):
                out.append(self._online_text_item(g, tid, label, "@online.private_room_hint"))
            out += [action("create_password_room", "@online.create_password_room", "@online.private_room_hint"),
                    action("create_code_room", "@online.create_code_room", "@online.private_room_hint"),
                    action("join_room_code", "@online.join_room_code", "@online.private_room_hint")]
        if state.get("room"):
            code = state["room"].get("code")
            if code and capabilities.get("private_rooms", False):
                out.append(dict(kind="action", id="room_invite_code", label="@online.room_invite_code",
                                value=i18n.literal(code), hint="@online.private_room_hint",
                                detail=dict(kicker="@online.rooms", title="@online.room_invite_code",
                                            lead=i18n.literal(code), rows=[])))
            out.append(action("leave_room", "@online.leave_room"))
        rooms = [room for room in state.get("rooms") or [] if capabilities.get("private_rooms", False)
                 or not (room.get("private") or room.get("lock") not in (None, "", False, "none"))]
        for room in rooms:
            name = room.get("name") or room.get("host")
            item = action("join_room:" + str(room["id"]), i18n.literal(name) if name else "@online.join_room", "@online.room_hint")
            item["verb"] = "@online.join_room"
            if room.get("lock") == "password":
                item["hint"] = "@online.private_room_hint"
                item["detail"]["lead"] = "@online.private_room_hint"
            out.append(item)
        if not rooms:
            out.append(dict(kind="action", id="no_rooms", label="@online.no_rooms", hint="@online.room_hint"))

    def _online_chat_items(self, g, state, out, action):
        out.append(dict(kind="heading", label="@online.chat"))
        from .nav_lobby_chat import identities
        messages = state.get("chat") or []
        for index, message in zip(identities(self, g, messages), messages):
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
                        run=lambda: self._edit_field("online_chat")))
        out.append(action("send_chat", "@online.send_chat", "@online.chat_hint"))

    def _online_text_item(self, g, tid, label, hint):
        value = g.a.text_value(tid)
        if tid in ONLINE_PASSWORDS:
            value = "\u2022" * len(value)
        return dict(kind="action", id=tid, label=label, value=i18n.literal(value),
                    verb="@change", hint=hint,
                    detail=dict(kicker="@section.online", title=label, lead=hint, rows=[]),
                    run=lambda: self._edit_field(tid))

    def _online_friend_items(self, g, state, out, action):
        from .nav_profiles import player_art

        out.append(dict(kind="heading", label="@online.friends"))
        out.append(action("refresh_friends", "@online.refresh_friends", "@online.friends_hint"))
        out.append(self._online_text_item(g, "online_friend_name", "@online.friend_name", "@online.friends_hint"))
        out.append(action("add_friend", "@online.add_friend", "@online.friends_hint"))

        def friend_action(prefix, label, person):
            name = str(person.get("name") or "")
            item = action(prefix + ":" + name, label, "@online.friends_hint")
            item.update(player_art(g, person))
            item["value"] = i18n.literal(name)
            item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(name))]
            if person.get("status"):
                status = {"online": "@online.friend_online", "in_match": "@online.friend_in_match",
                          "offline": "@online.friend_offline"}.get(person["status"], i18n.literal(person["status"]))
                item["detail"]["rows"].append(dict(k="@online.friend_status", v=status))
            return item

        friends = state.get("friends") or []
        if not friends:
            out.append(dict(kind="action", id="no_friends", label="@online.no_friends", hint="@online.friends_hint"))
        for friend in friends:
            if friend.get("invite"):
                out.append(friend_action("invite_friend", "@online.invite_friend", friend))
                if state.get("room"):
                    out.append(friend_action("invite_room", "@online.invite_room", friend))
            out.append(friend_action("remove_friend", "@online.remove_friend", friend))
        for friend in state.get("friend_incoming") or []:
            out.append(friend_action("accept_friend", "@online.accept_friend", friend))
            out.append(friend_action("decline_friend", "@online.decline_friend", friend))
        for friend in state.get("friend_outgoing") or []:
            out.append(friend_action("cancel_friend", "@online.cancel_friend", friend))
        for invite in state.get("invites") or []:
            for prefix, label in (("accept_invite", "@online.accept_invite"),
                                  ("decline_invite", "@online.decline_invite")):
                item = action(prefix + ":" + str(invite["id"]), label, "@online.friends_hint")
                item["value"] = i18n.literal(invite.get("name") or "")
                item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(invite.get("name") or ""))]
                out.append(item)
        if state.get("outgoing_invite"):
            item = action("cancel_invite", "@online.cancel_invite", "@online.friends_hint")
            item["detail"]["rows"] = [dict(k="@online.name", v=i18n.literal(state["outgoing_invite"].get("name") or ""))]
            out.append(item)

    def poll_online(self):
        if self.dry:
            return False
        changed = False
        for g in self.games:
            if not getattr(g.a, "online_supported", lambda: False)():
                continue
            try:
                from . import nav_rank_cue
                before_rank = nav_rank_cue.baseline(g.a.online_state())
                if g.a.online_poll():
                    changed = True
                    state = g.a.online_state()
                    nav_rank_cue.observe(self, g, before_rank, state)
                    nav_feedback.observe(self, g, state)
                    self.observe_online_sound(g, state)
                    phase = state.get("phase")
                    seen = self.__dict__.setdefault("_online_seen_phase", {})
                    if phase in ("matched", "result", "result_sent", "kicked", "error"):
                        # Notifications do not disturb a page's semantic focus. The offer layer owns
                        # its sound/attention; rebuilding online rows repairs removed destinations.
                        if seen.get(g.id) != phase:
                            if (phase == "matched" and not (state.get("capabilities") or {}).get("match_flow")
                                    and not any(game.a.running() for game in self.games)):
                                self.note_sound(ui_sound.NOTIFY)
                            self.say(state.get("message") or "@online.status", 12)
                    seen[g.id] = phase
            except Exception:  # noqa: BLE001 -- keep the timer alive without exposing login details
                self.say("@online.failure", 12)
                changed = True
        try:
            return self._poll_online_challenge() or changed
        except Exception:  # noqa: BLE001 -- invitation state must not stop the timer or reveal server details
            self.say("@online.failure", 12)
            return True

    def _poll_online_challenge(self):
        """One shared, controller-operated invitation dialog for both games."""
        pending = getattr(self, "online_challenge", None)
        if pending and self.overlay == "dialog" and self.confirm_kind == "online_challenge":
            g, challenge_id = pending
            state = g.a.online_state()
            if (g is not self.game or self.screen != "hub" or self.section() != "online"
                    or state.get("phase") != "logged_in"
                    or (state.get("challenge") or {}).get("id") != challenge_id):
                self.overlay = None
                self.online_challenge = None
                return True
            return False
        if self.overlay or self.screen != "hub" or self.section() != "online":
            return False
        g = self.game
        state = g.a.online_state()
        challenge_id = (state.get("challenge") or {}).get("id")
        seen = self.__dict__.setdefault("online_challenge_seen", {})
        if state.get("phase") in ("offline", "connecting", "kicked", "error"):
            seen.pop(g.id, None)
        if state.get("phase") != "logged_in" or not challenge_id or seen.get(g.id) == challenge_id:
            return False
        seen[g.id] = challenge_id
        self.online_challenge = (g, challenge_id)
        self._ask("online_challenge")
        self.note_sound(ui_sound.NOTIFY)
        return True

    def _online_challenge_dialog(self, action):
        if action in ("left", "right", "up", "down"):
            self.exit_focus = 1 - self.exit_focus
        elif action in ("back", "confirm"):
            g, challenge_id = self.online_challenge
            state = g.a.online_state()
            if state.get("phase") == "logged_in" and (state.get("challenge") or {}).get("id") == challenge_id:
                if state.get("busy"):
                    self.say("@online.busy")
                    return
                if not self._online_action(g, "accept_challenge" if action == "confirm" and self.exit_focus == 1
                                           else "decline_challenge"):
                    return
            self.overlay = None
            self.online_challenge = None

    def _view_online_challenge(self, v):
        from .nav_online_layout import connection
        from .nav_challenges import _details

        g, challenge_id = self.online_challenge
        state = g.a.online_state()
        challenge = state.get("challenge") or {}
        conn = connection(challenge)
        terms = (state.get("challenge_preferences") or {}).get("incoming") or {}
        lines = [i18n.localize(conn["text"], self.language)]
        if conn["path"]:
            lines.append(i18n.localize(conn["path"], self.language))
        if terms.get("id") == challenge_id:
            lines += [str(i18n.localize(row["k"], self.language)) + ": " + str(i18n.localize(row["v"], self.language))
                      for row in _details(terms)]
        text = "\n".join(str(line) for line in lines)
        v["dialog"] = dict(title=i18n.message("online_ui.incoming", name=i18n.literal(challenge.get("name") or "")),
                           text=i18n.literal(text), options=[
                               dict(label="@online.decline_challenge", index=0, focused=self.exit_focus == 0),
                               dict(label="@online.accept_challenge", index=1, focused=self.exit_focus == 1)])
        v["hint"] = "@online.challenge_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"),
                        self.prompt("back", "@online.decline_challenge")]

    def close_online(self, only=None):
        """Log out of the lobbies (the window closes), or only one game's (only=its id: its install is replaced)."""
        if not self.dry:
            for g in self.games:
                if only is not None and g.id != only:
                    continue
                if getattr(g.a, "online_supported", lambda: False)():
                    try:
                        g.a.online_close()
                    except Exception:  # noqa: BLE001 -- a failed disconnect must not prevent closing the app
                        pass
