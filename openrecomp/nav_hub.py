"""Hub navigation, focused rows, and the hub view."""
from . import i18n, ui_sound
from .nav_common import ROWS_VISIBLE, SECTION_TITLES, badge, uri, window


class Hub:
    def sections(self, g=None):
        g = g or self.game
        sections = [s for s in g.m["sections"] if s not in ("controls", "support")]
        if getattr(g.a, "controls_supported", lambda: False)():
            sections.append("controls")
        if getattr(g.a, "support_available", lambda: False)():
            sections.append("support")
        return sections

    def section(self):
        g = self.game
        secs = self.sections(g)
        if g.id not in self.sec:
            self.sec[g.id] = "play" if g.a.ready() or "build" not in secs else "build"
        if self.sec[g.id] not in secs:
            self.sec[g.id] = secs[0]
        return self.sec[g.id]

    def key(self):
        return f"{self.game.id}:{self.section()}"

    def items(self):
        return getattr(self, "_items_" + self.section())(self.game)

    def focus_index(self, items):
        i = max(0, min(len(items) - 1, self.focus.get(self.key(), 0)))
        while i < len(items) - 1 and items[i].get("kind") == "heading":
            i += 1
        return i

    def _hub(self, a):
        if getattr(self, "main_menu_game", "") == self.game.id:
            return self._main_menu(a)
        if a == "home" and self.has_main_menu():
            return self.open_main_menu()
        from . import nav_arcade
        if nav_arcade.action(self, a):
            return
        items = self.items()
        i = self.focus_index(items)
        it = items[i] if items else {}
        secs = self.sections()
        page = it.get("region") is not None and self.section() == "online"
        if page and a in ("up", "down"):
            self.focus[self.key()] = self._online_move(items, i, -1 if a == "up" else 1)
        elif page and a in ("prev", "next") and self.game.id in getattr(self, "main_menu_visited", set()):
            self._online_chapter(items, i, -1 if a == "prev" else 1)
        elif page and a in ("left", "right") and it.get("region") == "login":
            j = self._login_side(items, i, -1 if a == "left" else 1)
            if j is not None:
                self.focus[self.key()] = j
        elif page and a in ("left", "right") and self._online_side(items, i, -1 if a == "left" else 1) is not None:
            self.focus[self.key()] = self._online_side(items, i, -1 if a == "left" else 1)
        elif page and a in ("chapterPrev", "chapterNext"):
            self._online_chapter(items, i, -1 if a == "chapterPrev" else 1)
        elif page and a == "x" and it.get("replay") is None and it.get("region") != "login":
            self._chat_jump(items, i)
        elif a in ("up", "down"):
            step = -1 if a == "up" else 1
            j = i + step
            while 0 <= j < len(items) and items[j].get("kind") == "heading":
                j += step
            if 0 <= j < len(items):
                self.focus[self.key()] = j
        elif a in ("prev", "next"):
            pos = secs.index(self.section())
            self.sec[self.game.id] = secs[(pos + (-1 if a == "prev" else 1)) % len(secs)]
        elif a == "back":
            if self.game.id in getattr(self, "main_menu_visited", set()):
                self.open_main_menu()
            elif self.section() == "online" and self._direct_online(self.game):
                self._direct_online_back(self.game)
            else:
                self.screen = "start"
                self.start_focus = self.games.index(self.game)
        elif a == "switchGame":
            pos = (self.games.index(self.game) + 1) % len(self.games)
            self._select_game(self.games[pos])
        elif a == "play":
            if self.section() == "online" and (self.game.m.get("adapter") in ("t4", "t5dr")
                    or getattr(self.game.a, "online_supported", lambda: False)()):
                self.say(self.game.a.online_state().get("message") or "@online.search_hint")
            else:
                self.start_game(self.game)
        elif a == "x":
            if it.get("replay") is not None:
                self.show_results = not self.show_results
            elif self.section() == "build":
                self.toggle_build_log()
        elif a in ("left", "right") and it.get("kind") == "cycler":
            self._cycle(it, 1 if a == "right" else -1)
        elif a == "confirm":
            self._activate(it)

    def _cycle(self, it, step):
        if self._dry(i18n.message("dry_change", name=it["label"])):
            return
        options = it["options"]
        values = [o[0] for o in options]
        pos = next((i for i, value in enumerate(values)
                    if type(value) is type(it["current"]) and value == it["current"]), 0)
        it["set"](values[(pos + step) % len(values)])
        self.hint_toggle(values[(pos + step) % len(values)], step)

    def _activate(self, it):
        if it.get("disabled"):
            self.hint_sound(ui_sound.ERROR)
            return
        kind = it.get("kind")
        if kind == "cycler":
            self._cycle(it, 1)
        elif kind == "hold":
            self.holding = it
            self.hold = 0.0
        elif kind == "action" and it.get("run"):
            it["run"]()

    def _finish_hold(self, it):
        if it.get("run"):
            try:
                it["run"]()
            except Exception as e:  # noqa: BLE001 -- as in act()
                self.hint_sound(ui_sound.ERROR)
                self.say(i18n.error_message(e))

    def _view_hub(self, v):
        g = self.game
        v["accent"], v["gameShort"], v["numeral"] = g.accent, i18n.literal(g.short), i18n.literal(g.m["numeral"])
        v["badge"] = badge(g)
        v["topline"] = g.a.status()["status"]
        v["hero"] = uri(g.a.hero())
        v["mainMenu"]["available"] = self.has_main_menu(g)
        v["mainMenu"]["homeLabel"] = "@main_menu.title"
        if getattr(self, "main_menu_game", "") == g.id:
            self._view_main_menu(v, g)
            return
        sec = self.section()
        v["tabs"] = [dict(id=s, label="@" + SECTION_TITLES[s], active=s == sec) for s in self.sections(g)]
        items = self.items()
        fi = self.focus_index(items)
        start = window(len(items), fi, ROWS_VISIBLE)
        rows = []
        for i in range(start, min(len(items), start + ROWS_VISIBLE)):
            it = items[i]
            foc = i == fi
            kind = it.get("kind", "action")
            cyc = kind == "cycler"
            value = it.get("value") or ""
            rows.append(dict(index=i, heading=kind == "heading", focused=foc, label=it.get("label", ""), mt=it.get("mt", 0), hold=kind == "hold", disabled=bool(it.get("disabled")),
                             missing=bool(it.get("missing")), value=(i18n.message("selected_option", name=value) if cyc and foc else value) if (cyc or not foc) else "", verb=(it.get("verb", "") if foc and not cyc else ""),
                             holdPct=self.hold if foc and kind == "hold" else 0))
        while rows and rows[-1]["heading"]:      # a group's title never stands alone at the bottom
            rows.pop()
        v["rows"] = rows
        v["more"] = dict(up=start > 0, down=start + ROWS_VISIBLE < len(items))
        it = items[fi] if items else {}
        d = it.get("detail") or dict(kicker="", title=it.get("label", ""), lead="", rows=[])
        v["detail"] = dict(kicker=d.get("kicker", ""), title=d.get("title", ""), lead=d.get("lead", ""), leadLines=d.get("leadLines", 3),
                           rows=[dict(k=r["k"], v=r["v"], accent=bool(r.get("accent"))) for r in d.get("rows", [])],
                           results=self._cells(d.get("results", []) or []), primary=d.get("primary", ""), primaryG=self.glyph("confirm", True),
                           images=[uri(p) for p in d.get("images", []) if p], image=uri(d.get("image", "")), progress=d.get("progress", -1))
        v["hint"] = it.get("hint", "")
        prompts = []
        page = sec == "online" and it.get("region") is not None
        if sec == "settings" and items:
            self._view_settings_page(v, items, fi)
        if sec in ("play", "replays", "controls", "support"):
            self._view_session_page(v, g, sec, items, fi)
        if sec == "online" and not page and any(item.get("id") == "online_status" for item in items):
            self._view_online_card(v, g, items, fi)
        login = page and it.get("region") == "login"
        if login:
            self._view_online_login(v, g, g.a.online_state(), items, fi)
            page = False
        if page:
            state = g.a.online_state()
            self._view_online_page(v, g, state, items, fi)
            if v["hint"] in ("", "@online.challenge_hint", "@online.chat_hint") and state.get("message"):
                v["hint"] = state["message"]
        arcade = v["online"].get("arcade", {}) if page and v["online"].get("chapter") == "lobby" else {}
        arcade_card = next((card for card in arcade.get("players", []) if card.get("focused")), {})
        arcade_profile = any(button.get("id", "").startswith("profile_") for button in arcade_card.get("buttons", []))
        arcade_watch = any(button.get("id", "").startswith("arcade_watch:") for button in arcade_card.get("buttons", []))
        if it.get("kind") == "cycler":
            prompts += [self.prompt("confirm", "@change"), self.prompt("right", "@change")]
        elif it.get("verb"):
            prompts.append(self.prompt("confirm", it["verb"]))
        elif arcade_card.get("own") and arcade_card.get("index") == fi and arcade_profile:
            prompts.append(self.prompt("confirm", "@arcade.profile"))
        if page:
            prompts.append(dict(action="chapterNext", label="@online_ui.chapters", g=self.glyph("chapters")))
            prompts.append(self.prompt("x", "@arcade.watch" if arcade_watch else "@online_ui.chat_back" if it.get("region") == "chat" else "@online.chat"))
        if it.get("replay") is not None:
            prompts.append(self.prompt("x", "@hide_result" if self.show_results else "@show_result"))
        arcade_drawer = any(arcade.get(name) for name in ("optionsOpen", "moreOpen", "helpOpen"))
        prompts.append(self.prompt("back", "@arcade.close" if arcade_drawer else "@main_menu.title" if g.id in getattr(self, "main_menu_visited", set()) else "@games"))
        if g.a.ready() and not (sec == "online" and (g.m.get("adapter") in ("t4", "t5dr")
                or getattr(g.a, "online_supported", lambda: False)())):
            prompts.append(self.prompt("play", "@play"))
        profile_shortcut = page and it.get("region") == "lobby" and it.get("group") and any(
            row.get("group") == it["group"] and (row.get("id") or "").startswith("profile_player:") for row in items)
        if arcade_card:
            prompts.append(self.prompt("play", "@arcade.more"))
        prompts += [self.prompt("social", "@arcade.profile" if arcade_profile else "@online_ui.chapter.profile" if profile_shortcut else "@quick_access"), self.prompt("switchGame", "@switch_game")]
        v["prompts"] = prompts
        if sec == "build":
            self._view_build_page(v, g, items, fi)

    def _view_session_page(self, v, g, section, items, focus):
        """Compact page snapshots reuse the same action indices and focused details."""
        indexed = [(i, it) for i, it in enumerate(items)
                   if section != "replays" or it.get("kind") != "heading"]
        selected = next((j for j, (i, _) in enumerate(indexed) if i == focus), 0)
        start = window(len(indexed), selected, 10)
        primary = "start" if section == "play" else (
            "send" if any(it.get("id") == "send" for it in items) else "report") if section == "support" else ""
        rows = [dict(index=i, id=it.get("id", ""), heading=it.get("kind") == "heading",
                     label=it.get("label") or ("@support.not_checked" if section == "support" else ""), value=it.get("value") or "", verb=it.get("verb", ""),
                     focused=i == focus, disabled=bool(it.get("disabled")), primary=it.get("id") == primary,
                     hint=it.get("hint", ""), cells=it.get("cells", []))
                for i, it in indexed[start:start + 10]]
        state = g.a.support_state() if section == "support" else {}
        leads = dict(play="@ui.play.lead", replays="@ui.replays.lead", controls="@ui.controls.lead", support="@ui.support.lead")
        v["sessionPage"] = dict(show=True, section=section, title="@" + SECTION_TITLES[section],
                                lead=leads[section], rows=rows,
                                replayColumns=["@date", "@opponent", "@ui.replays.fighters", "@result", "@ui.replays.length"],
                                up=start > 0, down=start + 10 < len(indexed),
                                empty=len(items) == 1 and items[0].get("id") == "none",
                                notice=state.get("send_notice", "@support.send.notice") if primary == "send" else "@support.local_only",
                                busy=bool(state.get("running")), error=state.get("error", ""))

    def click_row(self, index):
        if self.overlay:
            return
        self._cancel_hold()
        previous = self.online_rows.get(self.game.id) if self.section() == "online" else None
        items = self.items()
        current = self.online_rows.get(self.game.id)
        if previous is not None and current is not None and (
                index >= len(previous) or index >= len(current) or previous[index] != current[index]):
            return
        if 0 <= index < len(items) and items[index].get("kind") != "heading":
            already = self.focus_index(items) == index
            self.focus[self.key()] = index
            if already or items[index].get("kind") != "hold":
                if items[index].get("kind") == "hold":
                    self.say("@hold_hint")
                else:
                    self._guard(self._activate, items[index])

    def click_tab(self, section):
        if self.overlay:
            return
        self._cancel_hold()
        if section in self.sections():
            self.sec[self.game.id] = section

    def click_primary(self):
        if self.overlay:
            return
        items = self.items()
        if items:
            self._guard(self._activate, items[self.focus_index(items)])
