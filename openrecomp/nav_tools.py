"""Optional controls and local problem reports, through the common game interface."""
from . import i18n, ui_sound
from .community import DISCORD_URL

CAPTURE_SECONDS = 5


class Tools:
    def _begin_binding(self, g, pad, slot):
        if self._dry("@controls.bind"):
            return
        g.a.begin_binding(pad, slot)
        item = next((it for it in self.items() if it.get("slot") == slot), {})
        self.binding_info = dict(label=item.get("label", slot), notation=slot, glyphs=item.get("glyphs") or [])
        self.binding_game = g
        self.binding_result = dict(state="waiting", left=CAPTURE_SECONDS)
        self.overlay = "binding"

    def _begin_input_test(self, g, pad):
        g.a.begin_input_test(pad)
        self.binding_info = dict(label="@controls.test", notation="", glyphs=[])
        self.binding_game = g
        self.binding_result = dict(state="test")
        self.overlay = "binding"

    def binding_active(self):
        """A capture or the input test: every pad button belongs to the controller being set up, not the launcher."""
        return self.overlay == "binding" and self.binding_result.get("state") in ("waiting", "test")

    def _binding(self, action):
        if self.binding_active():
            # Every pad button is a binding candidate, including the usual Back button (held: cancel).
            if action == "back" and self.device == "kb":
                self._cancel_binding()
            return
        if action in ("left", "right", "up", "down"):
            self.exit_focus = 1 - self.exit_focus
        elif action == "back":
            self._cancel_binding()
        elif action == "confirm":
            if self.exit_focus == 1:
                if self._offline_action(self.binding_game.a.accept_binding):
                    self.say("@controls.saved")
                self._cancel_binding()
            else:
                self._cancel_binding()

    def _cancel_binding(self):
        if self.binding_game:
            self.binding_game.a.cancel_binding()
        self.overlay = None
        self.binding_game = None

    def _view_binding(self, v):
        result = self.binding_result
        info = getattr(self, "binding_info", None) or {}
        if result.get("state") == "test":
            v["overlay"] = ""           # the page itself shows the test: lit actions and the notation strip
            return
        waiting = self.binding_active()
        swap = result.get("swap") or {}
        if waiting:
            text = "@controls.waiting.text"
        elif swap:
            text = i18n.message("controls.conflict.swap", source=result.get("source", ""),
                                slots=", ".join(i18n.localize(s, self.language) for s in result.get("conflicts", [])),
                                slot=swap.get("slot", ""), given=" / ".join(swap.get("sources") or []))
        else:
            text = i18n.message("controls.conflict.text", source=result.get("source", ""),
                                slots=", ".join(i18n.localize(s, self.language) for s in result.get("conflicts", [])))
        left = max(0, min(CAPTURE_SECONDS, int(result.get("left", 0) + 0.999)))
        v["overlay"] = "bindcapture"
        v["bindCapture"] = dict(
            title="@controls.waiting.title" if waiting else "@controls.conflict.title", text=text,
            action=info.get("label", ""), notation=info.get("notation", ""), glyphs=info.get("glyphs") or [],
            waiting=waiting, left=left, progress=max(0.0, min(1.0, float(result.get("left", 0)) / CAPTURE_SECONDS)),
            holding=bool(result.get("holding")), cancel="@controls.waiting.cancel",
            options=[] if waiting else [dict(label="@no", index=0, focused=self.exit_focus == 0),
                                        dict(label="@controls.swap" if swap else "@yes", index=1,
                                             focused=self.exit_focus == 1)])
        # the old dialog fields stay filled for screens that only know the dialog
        v["dialog"] = dict(title=v["bindCapture"]["title"], text=text, options=v["bindCapture"]["options"])
        v["hint"] = "@controls.waiting.hint" if waiting else "@dialog_hint"
        v["prompts"] = [] if waiting else [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]

    def poll_tools(self, active=True):
        """The app polls installed readers and workers; all state stays in this plain model."""
        changed = False
        if self.controls_game and not self.binding_active() and active:
            try:
                result = self.controls_game.a.poll_binding(active=True)
                if self.binding_game and result.get("state") == "disconnected":
                    self._cancel_binding()
                    self.say("@controls.disconnected")
            except Exception as e:  # noqa: BLE001 -- a reader failure should not stop the app timer
                self.say(i18n.error_message(e) or "@controls.failed")
                self.controls_game.a.controls_close()
                self.controls_game = None
            changed = True
        if self.binding_active():
            try:
                testing = self.binding_result.get("state") == "test"
                result = self.binding_game.a.poll_binding(active=active)
                state = result.get("state", "waiting")
                if result != self.binding_result:
                    changed = True
                if testing and state == "test":
                    self.binding_result = result
                    changed = True                  # the live input strip follows every poll
                elif testing:
                    self._cancel_binding()
                    self.binding_result = {}
                    if state == "disconnected":
                        self.say("@controls.disconnected")
                    changed = True
                elif state == "waiting":
                    self.binding_result = result
                elif state == "multi":
                    self.binding_result = dict(state="waiting", left=self.binding_result.get("left", CAPTURE_SECONDS))
                    self.say("@controls.multi")
                else:
                    changed = True
                    self.binding_result = result
                    if state == "ready":
                        self.binding_game.a.accept_binding()
                        self.say("@controls.saved")
                        self.overlay = None
                        self.binding_game = None
                    elif state == "conflict":
                        self.exit_focus = 0
                    else:
                        self._cancel_binding()
                        messages = dict(timeout="@controls.timeout",
                                        disconnected="@controls.disconnected", cancelled="@controls.cancelled",
                                        game_key="@controls.game_key")
                        if state == "cancelled":
                            self.note_sound(ui_sound.BACK)
                        self.say(result.get("error") or messages.get(state, "@controls.failed"))
            except Exception as e:  # noqa: BLE001 -- unplugging a pad must leave navigation usable
                self._cancel_binding()
                self.say(i18n.error_message(e) or "@controls.failed")
                changed = True
        if self.controls_game and (self.screen != "hub" or self.game is not self.controls_game or self.section() != "controls" or not active):
            self.controls_game.a.controls_close()
            if self.binding_game:
                self._cancel_binding()
            self.controls_game = None
            changed = True
        if self.support_game:
            state = self.support_game.a.support_state()
            if state != self.support_snapshot:
                self.support_snapshot = state
                changed = True
            if not state["running"]:
                self.support_game = None
        return changed

    def _items_support(self, g):
        state = g.a.support_state()
        busy = state["running"]
        out = []
        if hasattr(g.a, "support_probe"):
            g.a.support_probe()                 # (once: does the server take reports? an older one hides Send)
        if state.get("send_available") is not False and getattr(g.a, "support_send_info", lambda: None)():
            # One click: Send is the page's first row (focused); the note and the contact are optional.
            sending = busy and state.get("operation") == "send"
            note, contact = state.get("note", ""), state.get("contact", "")
            rows = [dict(k="@support.send.note", v=note or "-"), dict(k="@support.send.contact", v=contact or "-")]
            out.append(dict(kind="action", id="send", label="@support.send", verb="" if busy else "@support.send.verb",
                            disabled=busy, run=None if busy else (lambda: self._start_support(g, "send")),
                            hint="@support.send.sending" if sending else "@support.send.hint",
                            detail=dict(kicker="@section.support", title="@support.send",
                                        lead="@support.send.sending" if sending else "@support.send.notice", rows=rows,
                                        primary="" if busy else "@support.send.verb")))
            for tid, label, value in (("support_note", "@support.send.note", note),
                                      ("support_contact", "@support.send.contact", contact)):
                out.append(dict(kind="action", id=tid, label=label, value=value, verb="" if busy else "@support.send.edit",
                                disabled=busy, run=None if busy else (lambda tid=tid: self._open_osk(tid)),
                                hint="@support.send.field_hint",
                                detail=dict(kicker="@section.support", title=label, lead="@support.send.field_hint",
                                            rows=[dict(k=label, v=value or "-")])))
        for kind, label, hint in (("check", "@support.check", "@support.check.hint"), ("report", "@support.report", "@support.report.hint")):
            run = (lambda: self._ask("support_report")) if kind == "report" else (lambda: self._start_support(g, "check"))
            out.append(dict(kind="action", id=kind, label=label, verb="" if busy else "@start", disabled=busy,
                            run=None if busy else run, hint="@support.running" if busy else hint,
                            detail=dict(kicker="@section.support", title=label, lead="@support.running" if busy else hint,
                                        rows=[dict(k="@support.local_only", v="@support.local_only")], primary="" if busy else "@start")))
        if state.get("error"):
            out.append(self._support_finding("error", "@support.error", state["error"], "@support.check.hint"))
        for finding in state["findings"]:
            out.append(self._support_finding(finding["id"], finding["label"], finding.get("seen", ""), finding["fix"]))
        if state.get("sent"):
            out.append(self._support_finding("sent", i18n.message("support.send.done", id=i18n.literal(state["sent"])),
                                             "", "@support.send.done_hint"))
        if state["report"]:
            out.append(self._support_finding("saved", "@support.report_ready", state["report"], "@support.local_only"))
        elif not state["findings"] and not busy and not state.get("sent"):
            label = "@support.no_findings" if state["checked"] else "@support.not_checked"
            out.append(self._support_finding("none", label, "", "@support.check.hint"))
        out.append(dict(kind="action", id="discord", label="@community.discord", verb="@open", run=self.open_discord,
                        hint="@community.hint",
                        detail=dict(kicker="@section.support", title="@community.discord", lead="@community.hint",
                                    rows=[dict(k="@community.link", v=i18n.literal(DISCORD_URL))], primary="@open")))
        return out

    @staticmethod
    def _support_finding(sid, label, seen, fix):
        return dict(kind="action", id=sid, label=label, hint=fix,
                    detail=dict(kicker="@support.next_step", title=label, lead=fix,
                                rows=[dict(k="@support.report_path" if sid == "saved" else "@support.observation", v=seen)] if seen else []))

    def _start_support(self, g, kind):
        if self._dry({"report": "@support.report", "send": "@support.send"}.get(kind, "@support.check")):
            return
        if g.a.support_start(kind):
            self.support_game = g
            self.support_snapshot = g.a.support_state()
