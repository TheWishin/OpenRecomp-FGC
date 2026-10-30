"""Hub navigation, focused rows, and the hub view."""
from . import i18n
from .nav_common import ROWS_VISIBLE, SECTION_TITLES, badge, uri, window


class Hub:
    def sections(self, g=None):
        return (g or self.game).m["sections"]

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
        items = self.items()
        i = self.focus_index(items)
        it = items[i] if items else {}
        secs = self.sections()
        if a in ("up", "down"):
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
            self.screen = "start"
            self.start_focus = self.games.index(self.game)
        elif a == "switchGame":
            pos = (self.games.index(self.game) + 1) % len(self.games)
            self._select_game(self.games[pos])
        elif a == "play":
            self.start_game(self.game)
        elif a == "x":
            if it.get("replay") is not None:
                self.show_results = not self.show_results
        elif a in ("left", "right") and it.get("kind") == "cycler":
            self._cycle(it, 1 if a == "right" else -1)
        elif a == "confirm":
            self._activate(it)

    def _cycle(self, it, step):
        if self._dry(i18n.message("dry_change", name=it["label"])):
            return
        options = it["options"]
        values = [o[0] for o in options]
        pos = values.index(it["current"]) if it["current"] in values else 0
        it["set"](values[(pos + step) % len(values)])

    def _activate(self, it):
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
                self.say(i18n.error_message(e))

    def _view_hub(self, v):
        g = self.game
        v["accent"], v["gameShort"], v["numeral"] = g.accent, g.short, g.m["numeral"]
        v["badge"] = badge(g)
        v["topline"] = g.a.status()["status"]
        v["hero"] = uri(g.a.hero())
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
        v["detail"] = dict(kicker=d.get("kicker", ""), title=d.get("title", ""), lead=d.get("lead", ""),
                           rows=[dict(k=r["k"], v=r["v"], accent=bool(r.get("accent"))) for r in d.get("rows", [])],
                           results=self._cells(d.get("results", []) or []), primary=d.get("primary", ""), primaryG=self.glyph("confirm", True),
                           images=[uri(p) for p in d.get("images", []) if p], image=uri(d.get("image", "")), progress=d.get("progress", -1))
        v["hint"] = it.get("hint", "")
        prompts = []
        if it.get("kind") == "cycler":
            prompts += [self.prompt("confirm", "@change"), self.prompt("right", "@change")]
        elif it.get("verb"):
            prompts.append(self.prompt("confirm", it["verb"]))
        if it.get("replay") is not None:
            prompts.append(self.prompt("x", "@hide_result" if self.show_results else "@show_result"))
        prompts.append(self.prompt("back", "@games"))
        if g.a.ready():
            prompts.append(self.prompt("play", "@play"))
        prompts += [self.prompt("social", "@quick_access"), self.prompt("switchGame", "@switch_game")]
        v["prompts"] = prompts

    def click_row(self, index):
        self._cancel_hold()
        items = self.items()
        if 0 <= index < len(items) and items[index].get("kind") != "heading":
            already = self.focus_index(items) == index
            self.focus[self.key()] = index
            if already or items[index].get("kind") != "hold":
                if items[index].get("kind") == "hold":
                    self.say("@hold_hint")
                else:
                    self._guard(self._activate, items[index])

    def click_tab(self, section):
        self._cancel_hold()
        if section in self.sections():
            self.sec[self.game.id] = section

    def click_primary(self):
        items = self.items()
        if items:
            self._guard(self._activate, items[self.focus_index(items)])
