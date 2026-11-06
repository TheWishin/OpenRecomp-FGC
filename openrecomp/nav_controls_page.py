"""The Pad bindings page (the "controls" section): one tab per controller, the game's actions in Tekken notation with
the controller's own button glyphs, presets, reset, and a live input test. No Qt.

Rows stay the hub's usual items (up/down, confirm, click), so the page works by pad, keyboard and mouse alike:
LT/RT (PgUp/PgDn) or the Controller row switch controllers, Confirm binds the focused action, X clears it. The
capture itself, the conflict question and the input test live in nav_tools.Tools."""
from . import i18n, pad_glyphs, pad_presets, ui_sound

GROUPS = (("attack", "@controls.group.attack"), ("macro", "@controls.group.macro"),
          ("menu", "@controls.group.menu"), ("dir", "@controls.group.dir"))
LINES = 12
TYPE_LABEL = {"xbox": "@controls.type.xbox", "ps": "@controls.type.ps", "generic": "@controls.type.generic",
              "keyboard": "@controls.type.keyboard"}
SOCD_LABEL = {"neutral": "@controls.socd.neutral", "up": "@controls.socd.up", "last": "@controls.socd.last",
              "off": "@controls.socd.off"}
STICK_LABEL = {"analog": "@controls.stick.analog", "dpad": "@controls.stick.dpad"}
PLAYERS = 2


class ControlsPage:
    # ---------------------------------------------------------------- which controller
    def _ctl_pads(self, g):
        return list(g.a.controls())

    def _ctl_pad(self, g, pads=None):
        pads = self._ctl_pads(g) if pads is None else pads
        if not pads:
            return None
        chosen = self.__dict__.setdefault("ctl_pad", {}).get(g.id)
        pad = next((p for p in pads if p["id"] == chosen), None)
        if pad is None:
            pad = next((p for p in pads if not p.get("disabled")), pads[0])
            self.ctl_pad[g.id] = pad["id"]
        return pad

    def _ctl_select(self, g, pad_id):
        """Another controller; the focus stays on the same action (or setting) where the new one has it."""
        key = g.id + ":controls"
        items = self._items_controls(g) if self.screen == "hub" and self.game is g else []
        pos = self.focus.get(key, 0)
        mark = items[pos].get("slot") or items[pos].get("id") if 0 <= pos < len(items) else None
        self.__dict__.setdefault("ctl_pad", {})[g.id] = pad_id
        if mark:
            items = self._items_controls(g)
            self.focus[key] = next((i for i, it in enumerate(items) if (it.get("slot") or it.get("id")) == mark), pos)

    def _ctl_step(self, g, step):
        pads = self._ctl_pads(g)
        pad = self._ctl_pad(g, pads)
        if pad is None or len(pads) < 2:
            self.hint_sound(ui_sound.ERROR)
            return
        pos = [p["id"] for p in pads].index(pad["id"])
        self._ctl_select(g, pads[(pos + step) % len(pads)]["id"])

    @staticmethod
    def _ctl_tab_label(pad):
        port = pad.get("port", -1)
        player = i18n.message("controls.player_short", n=port + 1) if port >= 0 else "@controls.no_player"
        return i18n.message("controls.tab", player=player, name=ControlsPage._ctl_name(pad))

    @staticmethod
    def _ctl_name(pad):
        """A device's name as the reader gives it (literal), or a catalog key for a game's own fixed layout."""
        name = pad.get("name") or ""
        return name if isinstance(name, str) and name.startswith("@") else i18n.literal(name)

    # ---------------------------------------------------------------- the rows
    def _items_controls(self, g):
        if self.controls_game and self.controls_game is not g:
            self.controls_game.a.controls_close()
        self.controls_game = g
        pads = self._ctl_pads(g)
        pad = self._ctl_pad(g, pads)
        if pad is None:
            hint = i18n.message("controls.hint", clear=self.glyph("x")["text"])
            return [dict(kind="action", id="none", label="@controls.empty", hint=hint,
                         detail=dict(kicker="@section.controls", title="@controls.empty", lead=hint, rows=[]))]
        features = pad.get("features") or {}
        disabled = bool(pad.get("disabled"))
        kicker = self._ctl_name(pad)
        fixed = bool(pad.get("fixed"))     # the game's buttons cannot be changed (Tekken 4): shown, never bound
        out = []
        if len(pads) > 1:
            out.append(dict(kind="cycler", id="ctl:device", local=True, label="@controls.device", ctl="setting",
                            value=self._ctl_tab_label(pad), options=[(p["id"], self._ctl_tab_label(p)) for p in pads],
                            current=pad["id"], set=lambda pid: self._ctl_select(g, pid), hint="@controls.device_hint",
                            detail=dict(kicker=kicker, title="@controls.device", lead="@controls.device_hint", rows=[])))
        if features.get("player"):
            options = [(None, "@controls.player.auto")] + [(p, i18n.message("controls.player_short", n=p + 1))
                                                         for p in range(PLAYERS)]
            current = pad.get("player")
            value = dict(options).get(current, "@controls.player.auto")
            out.append(dict(kind="cycler", id="ctl:player", label="@controls.player", ctl="setting", value=value,
                            options=options, current=current, set=lambda p: self._ctl_write(g, "set_control_player", pad["id"], p),
                            hint="@controls.player_hint",
                            detail=dict(kicker=kicker, title="@controls.player", lead="@controls.player_hint", rows=[])))
        presets = pad.get("presets") or []
        if presets:
            current = dict(presets).get(pad.get("preset"), "@controls.preset.custom")
            out.append(dict(kind="action", id="ctl:preset", label="@controls.preset", ctl="setting", value=current,
                            verb="@controls.choose", disabled=disabled, hint="@controls.preset_hint",
                            run=lambda: self._ctl_open_presets(g, pad),
                            detail=dict(kicker=kicker, title="@controls.preset", lead="@controls.preset_hint", rows=[])))
        if features.get("reset"):
            out.append(dict(kind="action", id="ctl:reset", label="@controls.reset", ctl="setting", verb="@confirm",
                            disabled=disabled, hint="@controls.reset_hint", run=lambda: self._ask("controls_reset"),
                            detail=dict(kicker=kicker, title="@controls.reset", lead="@controls.reset_hint", rows=[])))
        options = pad.get("options")
        if options and not disabled:
            socd = [(v, SOCD_LABEL[v]) for v in pad_presets.SOCD]
            out.append(dict(kind="cycler", id="ctl:socd", label="@controls.socd", ctl="setting",
                            value=SOCD_LABEL.get(options.get("socd"), options.get("socd") or ""), options=socd,
                            current=options.get("socd"), hint="@controls.socd_hint",
                            set=lambda v: self._ctl_write(g, "set_control_option", pad["id"], "socd", v),
                            detail=dict(kicker=kicker, title="@controls.socd", lead="@controls.socd_hint", rows=[])))
            stick = [(v, STICK_LABEL[v]) for v in pad_presets.STICK]
            out.append(dict(kind="cycler", id="ctl:stick", label="@controls.stick", ctl="setting",
                            value=STICK_LABEL.get(options.get("stick"), options.get("stick") or ""), options=stick,
                            current=options.get("stick"), hint="@controls.stick_hint",
                            set=lambda v: self._ctl_write(g, "set_control_option", pad["id"], "stick", v),
                            detail=dict(kicker=kicker, title="@controls.stick", lead="@controls.stick_hint", rows=[])))
        if fixed:
            out.append(dict(kind="action", id="ctl:fixed", label="@controls.fixed", ctl="setting", verb="",
                            hint="@controls.fixed_hint",
                            detail=dict(kicker=kicker, title="@controls.fixed", lead="@controls.fixed_hint", rows=[])))
        if features.get("test"):
            out.append(dict(kind="action", id="ctl:test", label="@controls.test", ctl="setting", verb="@controls.start_test",
                            hint="@controls.test_hint", run=lambda: self._begin_input_test(g, pad["id"]),
                            detail=dict(kicker=kicker, title="@controls.test", lead="@controls.test_hint", rows=[])))
        slots = pad.get("slots") or []
        for group, label in GROUPS:
            mine = [s for s in slots if (s.get("group") or "menu") == group]
            if not mine:
                continue
            out.append(dict(kind="heading", label=label, ctlGroup=group))
            for slot in mine:
                out.append(self._ctl_slot_item(g, pad, slot, kicker, disabled or fixed, features, fixed))
        return out

    def _ctl_slot_item(self, g, pad, slot, kicker, disabled, features, fixed=False):
        unbound = not slot.get("sources") and slot.get("value") in ("", "@controls.unbound")
        value = slot.get("text") or slot.get("value") or ""
        rows = [dict(k="@controls.current", v=value or "@controls.unbound")]
        hint = i18n.message("controls.hint", clear=self.glyph("x")["text"])      # X, or the square in PlayStation prompts
        glyphs = list(slot.get("glyphs") or [])
        style, dtype = getattr(self, "prompt_style", "auto"), pad.get("type")
        if style in ("xbox", "ps") and style != dtype and dtype in ("xbox", "ps") and slot.get("sources"):
            glyphs = [pad_glyphs.restyle(dtype, s, style) for s in slot["sources"]]      # Settings > Button prompts
        return dict(kind="action", id=str(pad["id"]) + ":" + slot["id"], slot=slot["id"], ctl="slot",
                    label=slot["label"], notation=slot["id"], value=value, glyphs=glyphs,
                    unbound=unbound, verb="" if disabled else "@controls.bind",
                    hint="@controls.fixed_hint" if fixed else hint, disabled=disabled and not fixed,
                    clear=bool(features.get("clear")) and not disabled and not unbound,
                    run=None if disabled else lambda pid=pad["id"], sid=slot["id"]: self._begin_binding(g, pid, sid),
                    detail=dict(kicker=kicker, title=slot["label"], lead="@controls.fixed_hint" if fixed else hint, rows=rows,
                                primary="" if disabled else "@controls.bind"))

    # ---------------------------------------------------------------- edits
    def _ctl_write(self, g, method, *args):
        if self._dry(i18n.message("dry_change", name="@section.controls")):
            return
        if self._offline_action(getattr(g.a, method), *args):
            self.say("@controls.saved")

    def _controls_key(self, a, items, i):
        """Keys the controls page answers itself; True when handled."""
        g = self.game
        it = items[i] if items else {}
        if a in ("chapterPrev", "chapterNext"):
            self._ctl_step(g, -1 if a == "chapterPrev" else 1)
            return True
        if a == "x" and it.get("ctl") == "slot":
            if not it.get("clear"):
                self.hint_sound(ui_sound.ERROR)
                return True
            pad = self._ctl_pad(g)
            self._ctl_write(g, "clear_binding", pad["id"], it["slot"])
            return True
        return False

    def _ctl_open_presets(self, g, pad):
        presets = pad.get("presets") or []
        if not presets:
            return
        ids = [pid for pid, _label in presets]
        self.ctl_presets = dict(pad=pad["id"], ids=ids, labels=dict(presets),
                                focus=ids.index(pad["preset"]) if pad.get("preset") in ids else 0)
        self._cancel_hold()
        self.overlay = "ctlpreset"

    def _ctlpreset(self, a):
        p = self.ctl_presets
        if a in ("up", "down"):
            p["focus"] = (p["focus"] + (-1 if a == "up" else 1)) % len(p["ids"])
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            self.overlay = None
            self._ctl_write(self.game, "apply_preset", p["pad"], p["ids"][p["focus"]])

    def _view_ctlpreset(self, v):
        p = self.ctl_presets
        v["ctlPreset"] = dict(title="@controls.preset", rows=[
            dict(index=n, label=p["labels"][pid], hint=pad_presets.PRESET_HINTS.get(pid, ""), focused=n == p["focus"])
            for n, pid in enumerate(p["ids"])])
        v["hint"] = "@controls.preset_hint"
        v["prompts"] = [self.prompt("confirm", "@controls.apply"), self.prompt("back", "@cancel")]

    def click_preset(self, index):
        if self.overlay == "ctlpreset" and 0 <= index < len(self.ctl_presets["ids"]):
            self.ctl_presets["focus"] = index
            self.act("confirm")

    def click_chapter(self, chapter):
        """A mouse click on a controller tab; anything else is the online page's chapter tabs."""
        if not self.overlay and self.screen == "hub" and self.section() == "controls":
            if any(p["id"] == chapter for p in self._ctl_pads(self.game)):
                self._ctl_select(self.game, chapter)
            return
        super().click_chapter(chapter)

    def _reset_controls(self):
        pad = self._ctl_pad(self.game)
        if pad is not None:
            self._ctl_write(self.game, "reset_controls", pad["id"])

    # ---------------------------------------------------------------- the view
    def _view_controls_page(self, v, items, fi):
        g = self.game
        pads = self._ctl_pads(g)
        pad = self._ctl_pad(g, pads)
        if pad is None:
            return
        test = self.overlay == "binding" and (self.binding_result or {}).get("state") == "test"
        try:
            live = g.a.controls_input(pad["id"]) if hasattr(g.a, "controls_input") else {}
        except Exception:  # noqa: BLE001 -- a reader hiccup only darkens the strip
            live = {}
        lit = set(live.get("lit") or ())
        lines, focus_line = [], 0
        for n, it in enumerate(items):
            if it.get("kind") == "heading":
                lines.append(dict(kind="group", label=it.get("label", "")))
                continue
            if n == fi:
                focus_line = len(lines)
            cycler = it.get("kind") == "cycler"
            line = dict(kind=it.get("ctl", "setting"), index=n, label=it.get("label", ""), value=it.get("value") or "",
                        focused=n == fi and not test, cycler=cycler, disabled=bool(it.get("disabled")),
                        verb=it.get("verb", "") if n == fi and not cycler else "")
            if it.get("ctl") == "slot":
                line.update(notation=it.get("notation", ""), glyphs=it.get("glyphs") or [],
                            unbound=bool(it.get("unbound")), lit=it.get("slot") in lit)
            lines.append(line)
        start = 0
        if len(lines) > LINES:
            start = max(0, min(len(lines) - LINES, focus_line - LINES // 2))
        shown = lines[start:start + LINES]
        it = items[fi] if items else {}
        d = it.get("detail") or {}
        options = []
        if it.get("kind") == "cycler":
            for value, label in it.get("options") or []:
                options.append(dict(label=label, current=type(value) is type(it.get("current")) and value == it.get("current")))
        tabs = [dict(id=p["id"], label=self._ctl_tab_label(p), type=p.get("type") or "generic",
                     typeLabel=TYPE_LABEL.get(p.get("type") or "generic", ""), active=p["id"] == pad["id"],
                     disabled=bool(p.get("disabled"))) for p in pads]
        v["bindingsPage"] = dict(
            layout="bindings", tabs=tabs, unbound="@controls.unbound", lines=shown, up=start > 0, down=start + LINES < len(lines),
            type=pad.get("type") or "generic", typeLabel=TYPE_LABEL.get(pad.get("type") or "generic", ""),
            preset=dict(pad.get("presets") or []).get(pad.get("preset"), "@controls.preset.custom"),
            detail=dict(kicker=d.get("kicker", ""), title=d.get("title") or it.get("label", ""),
                        lead=d.get("lead") or it.get("hint", ""), notation=it.get("notation", ""),
                        glyphs=it.get("glyphs") or [], unbound=bool(it.get("unbound")),
                        slot=it.get("ctl") == "slot", options=options[:8]),
            test=dict(active=test, notation=live.get("notation") or "", label="@controls.test_strip",
                      idle="@controls.test_idle", hint="@controls.test_end" if test else "@controls.test_live"))
        if test:
            v["hint"] = "@controls.test_end"
            v["prompts"] = [dict(action="back", label="@controls.finish_test", g=self.glyph("back"))]
            return
        prompts = []
        if it.get("kind") == "cycler":
            prompts.append(self.prompt("right", "@change"))
        elif it.get("verb") and not it.get("disabled"):
            prompts.append(self.prompt("confirm", it["verb"]))
        if it.get("ctl") == "slot" and it.get("clear"):
            prompts.append(self.prompt("x", "@controls.clear"))
        if len(pads) > 1:
            prompts.append(dict(action="chapterNext", label="@controls.next_pad", g=self.glyph("chapters")))
        prompts += [self.prompt("back", "@games"), self.prompt("social", "@quick_access")]
        v["prompts"] = prompts
