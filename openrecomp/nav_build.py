"""The Build page as cards: the game, your files, the build tools, and the big Build card on the right.

The rows of _items_build stay the focus order (up/down, confirm, mouse); each row names its card ("game", "files",
"tools", "main", "more"). This module only arranges them and adds what a player wants to see while waiting: the
step's name, how long it has taken, about how long it will still take, and a log that opens with X.
No Qt in here.
"""
import math
import time

from . import i18n

QUIET_SECONDS = 120           # no new build output for this long: say the step is still working (T5DR issue #27)
CLOCK_SECONDS = 0.5
FINISHED = ("@build_finished", "@t4.build_finished")
CARD_ORDER = ("game", "files", "tools")
CHIP = dict(done="@build.status.done", todo="@build.status.todo", work="@build.status.work",
            error="@build.status.error", wait="@build.status.wait")
FILES_TEXT = dict(t4="@build.files_t4", t5dr="@build.files_t5dr")
TYPICAL_MINUTES = dict(t4=(10, 30), t5dr=(3, 15))


def clock_text(seconds):
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = str(rest // 60), str(rest % 60).zfill(2)
    return ":".join((str(hours), minutes.zfill(2), secs)) if hours else ":".join((minutes, secs))


class BuildPage:
    # ------------------------------------------------------------------------------------------ time
    def _now(self):
        return getattr(self, "clock", time.monotonic)()

    def _build_clock(self, g, state, now):
        """Follow one game's build: when it started, its current step (and since when), its last output line.
        A finished build's step times are kept (build_history -> the launcher's config) for the next estimate."""
        clocks = self.__dict__.setdefault("build_clocks", {})
        c = clocks.get(g.id)
        if state.get("running"):
            if c is None or not c["running"]:
                c = clocks[g.id] = dict(running=True, start=now, step=None, step_at=now, line=None, line_at=now,
                                        steps=[], build_at=None)
            phase = state.get("phase") or "build"
            key = phase + ":" + str(state.get("title") or "")
            if phase == "build" and c["build_at"] is None:
                c["build_at"] = now
            if key != c["step"]:
                if c["step"] is not None:
                    c["steps"].append((c["step"], now - c["step_at"]))
                c["step"], c["step_at"] = key, now
            if state.get("line") != c["line"]:
                c["line"], c["line_at"] = state.get("line"), now
        elif c is not None and c["running"]:
            c["running"] = False
            if c["step"] is not None:
                c["steps"].append((c["step"], now - c["step_at"]))
            if state.get("result") in FINISHED:
                steps = [[key, round(seconds, 1)] for key, seconds in c["steps"] if key.startswith("build:")]
                if steps:
                    history = dict(steps=steps, total=round(sum(s for _k, s in steps), 1))
                    self.__dict__.setdefault("build_history", {})[g.id] = history
                    if not self.dry and callable(getattr(self, "on_build_history", None)):
                        self.on_build_history(g.id, history)
        return c

    def _build_remaining(self, g, state, c, now):
        """Seconds still to go, or None: from the last finished build's step times, else from the progress."""
        if state.get("phase") == "tools" or c is None:
            return None
        history = (getattr(self, "build_history", None) or {}).get(g.id) or {}
        steps = [s for s in history.get("steps") or [] if isinstance(s, list) and len(s) == 2]
        keys = [k for k, _s in steps]
        if c["step"] in keys:
            i = keys.index(c["step"])
            return max(0.0, steps[i][1] - (now - c["step_at"])) + sum(s for _k, s in steps[i + 1:])
        fraction = float(state.get("fraction") or 0.0)
        built = now - (c["build_at"] if c["build_at"] is not None else c["start"])
        if fraction >= 0.1 and built >= 30:
            return built * (1.0 - fraction) / fraction
        return None

    def poll_build(self, dt):
        """The app's timer: follow running builds, and once per start continue a build a restart interrupted.
        -> True when the screen must be redrawn."""
        self._build_poll = getattr(self, "_build_poll", 0.0) + dt
        if self._build_poll < CLOCK_SECONDS:
            return False
        self._build_poll = 0.0
        changed = False
        now = self._now()
        resumed = self.__dict__.setdefault("_resume_checked", set())
        for g in self.games:
            if not g.a.found():
                continue
            state = g.a.build_state()
            clock = (getattr(self, "build_clocks", None) or {}).get(g.id)
            if state.get("running") or clock is not None and clock["running"]:
                self._build_clock(g, state, now)
                changed = True
            if g.id in resumed or self.dry or any(row.get("busy") for row in g.a.prerequisites()):
                continue
            resumed.add(g.id)
            if g.a.build_resume_pending():
                try:
                    g.a.build_resume()
                    self.say("@build.resumed", 10)
                except Exception as error:  # noqa: BLE001 -- the Build page shows what is missing instead
                    self.say(i18n.error_message(error) or error.__class__.__name__, 10)
                changed = True
        return changed

    def focus_next_build_step(self, g):
        """After a file was chosen: on to the next file still missing, else to the big Build button (first-run walk:
        package -> licence -> Build without hunting for the next row)."""
        if self.game is not g or self.screen != "hub" or self.section() != "build":
            return
        items = self._items_build(g)
        nxt = next((i for i, it in enumerate(items) if it.get("card") == "files" and it.get("missing")
                    and not it.get("secondary") and not it.get("disabled")), None)
        if nxt is None:
            nxt = next((i for i, it in enumerate(items) if it.get("primary")), None)
        if nxt is not None:
            self.focus[g.id + ":build"] = nxt

    # ------------------------------------------------------------------------------------------ log
    def toggle_build_log(self):
        opened = self.__dict__.setdefault("build_log_open", {})
        opened[self.game.id] = not opened.get(self.game.id, False)

    # ------------------------------------------------------------------------------------------ view
    def _build_action(self, i, it, focused):
        kind = it.get("kind", "action")
        value = it.get("value") or ""
        if kind == "cycler":
            value = i18n.message("selected_option", name=value) if focused else value
        return dict(index=i, label=it.get("label", ""), value=value, verb=it.get("verb", "") if focused and kind != "cycler" else "",
                    focused=focused, disabled=bool(it.get("disabled")), missing=bool(it.get("missing")),
                    ok=bool(it.get("ok")), busy=bool(it.get("busy")), secondary=bool(it.get("secondary")),
                    hold=kind == "hold", holdPct=self.hold if focused and kind == "hold" else 0, cycler=kind == "cycler")

    def _view_build_page(self, v, g, items, fi):
        now = self._now()
        state = g.a.build_state()
        clock = self._build_clock(g, state, now)
        adapter = g.m.get("adapter", "")
        found = g.a.found()
        setup = self._setup(g.id) if self._setup_supported(g) else {}
        by_card = {}
        for i, it in enumerate(items):
            if it.get("kind") != "heading":
                by_card.setdefault(it.get("card") or "more", []).append((i, it))
        primary = next(((i, it) for i, it in enumerate(items) if it.get("primary")), None)
        if primary is None:
            primary = (by_card.get("game") or by_card.get("files") or [None])[0]
        cards = []

        def card(cid, title, text, status, actions=(), note=""):
            acts = [self._build_action(i, it, i == fi) for i, it in actions if primary is None or i != primary[0]]
            cards.append(dict(id=cid, num=len(cards) + 1, title=title, text=text, status=status, chip=CHIP[status],
                              note=note, focused=any(a["focused"] for a in acts), actions=acts))

        # 1 -- the game itself: install / choose its folder, an update, or the install borrowed from T5DR's launcher
        game_items = by_card.get("game", [])
        if game_items or not found:
            install_problem = next((it["install_problem"] for _i, it in game_items if it.get("install_problem")), "")
            if install_problem:
                card("game", "@build.card.game", install_problem, "error", game_items)
            elif not found:
                installing = setup.get("phase") in ("installing", "updating")
                text = ("@t5.folder_old" if g.a.setup_root() else
                        ("@build.game_text" if self._setup_supported(g) else "@build.game_folder_text"))
                card("game", "@build.card.game", text, "work" if installing else "todo", game_items,
                     note=self._setup_progress_text(setup) if installing else "")
            elif any(it.get("id") == "coexistence" for _i, it in game_items):
                card("game", "@t5.coexist.title", "@t5.coexist.hint", "done",
                     [(i, it) for i, it in game_items if it.get("id") != "coexistence"])
            elif any(it.get("id") == "game_update" for _i, it in game_items):
                needed = setup.get("required")
                card("game", "@build.card.update", "@setup.update_needed_hint" if needed else "@setup.update_hint",
                     "todo", game_items)
            else:
                card("game", "@build.card.game", "@t4.portable_required", "todo", game_items)
        # 2 -- the player's own files
        file_items = by_card.get("files", [])
        if file_items:
            sources = [it for _i, it in file_items if not it.get("secondary")]
            if any(it.get("busy") for it in sources):
                status = "work"
            elif all(it.get("ok") for it in sources):
                status = "done"
            else:
                status = "todo"
            note = next((it["note"] for it in sources if it.get("note") and not it.get("busy")), "")
            card("files", "@build.card.files", FILES_TEXT.get(adapter, "@build.files_text"), status, file_items, note=note)
        # 3 -- build tools: one line, never the list
        checks = g.a.prerequisites() if found else []
        if checks:
            tools = state.get("tools") or {}
            if state.get("running") and state.get("phase") == "tools":
                text = i18n.message("build.tools_installing", done=min(tools.get("done", 0) + 1, max(1, tools.get("total", 0))),
                                    total=max(1, tools.get("total", 0)), name=tools.get("current") or "@build.card.tools"
                                    ) if tools.get("total") else "@build.tools_checking"
                card("tools", "@build.card.tools", text, "work", by_card.get("tools", []),
                     note="@build.tools_installing_text" if tools.get("total") else "")
            elif state.get("failed") == "tools":
                card("tools", "@build.card.tools", state.get("result") or "@build.tools_failed_hint", "error",
                     by_card.get("tools", []))
            elif any(row.get("busy") for row in checks):
                card("tools", "@build.card.tools", "@build.tools_checking", "work")
            elif all(row.get("ok") is True for row in checks):
                card("tools", "@build.card.tools", "@build.tools_ready", "done")
            else:
                card("tools", "@build.card.tools", "@build.tools_auto", "wait")
        # the big card on the right
        main = self._build_main(g, state, clock, now, primary, fi, setup)
        more = [self._build_action(i, it, i == fi) for i, it in by_card.get("more", [])]
        v["build"] = dict(show=True, cards=cards, main=main, more=more, moreTitle="@build.card.more",
                          logTitle="@build.log_title", xG=self.glyph("x"))
        if main["canLog"]:
            back = next((n for n, p in enumerate(v["prompts"]) if p.get("action") == "back"), len(v["prompts"]))
            v["prompts"].insert(back, self.prompt("x", "@build.log_hide" if main["logOpen"] else "@build.log_show"))

    def _build_main(self, g, state, clock, now, primary, fi, setup):
        it = primary[1] if primary else {}
        index = primary[0] if primary else -1
        running = bool(state.get("running"))
        failed = state.get("failed") if not running else ""
        lines = [str(line) for line in state.get("lines") or [] if str(line).strip()]
        log_open = bool((getattr(self, "build_log_open", None) or {}).get(g.id))
        title = (it.get("detail") or {}).get("title") or it.get("label", "")
        main = dict(kicker="", title=title, lead=it.get("hint", ""), tone="todo", progress=-1.0,
                    stepLine="", eta="", elapsed="", quiet="", error="", note="",
                    button=dict(index=index, label=it.get("verb") or it.get("label", ""), focused=index == fi and index >= 0,
                                disabled=bool(it.get("disabled")) or index < 0, blocked=bool(it.get("blocked")),
                                g=self.glyph("confirm", index == fi)),
                    canLog=bool(lines), logOpen=log_open and bool(lines), logLines=lines[-8:] if log_open else [])
        if it.get("install_problem"):
            main.update(kicker="@build.kicker.error", tone="error", lead=it["install_problem"])
            return main
        if not g.a.found():
            installing = setup.get("phase") == "installing"
            main.update(kicker="@setup.kicker", lead="@setup.install_lead" if it.get("id") == "game_setup" else it.get("hint", ""),
                        tone="work" if installing else "todo")
            if installing:
                total = setup.get("total") or 0
                main.update(progress=min(1.0, setup.get("done", 0) / total) if total else 0.0,
                            stepLine=self._setup_progress_text(setup))
            return main
        if running:
            tools_phase = state.get("phase") == "tools"
            tools = state.get("tools") or {}
            main.update(kicker="@build.kicker.running", title="@build_running", tone="work",
                        lead="@build.tools_installing_text" if tools_phase else "@build.running_lead",
                        progress=-1.0 if tools_phase else float(state.get("fraction") or 0.0))
            if tools_phase:
                main["stepLine"] = i18n.message("build.tools_installing", done=min(tools.get("done", 0) + 1, max(1, tools.get("total", 0))),
                                                total=max(1, tools.get("total", 0)), name=tools.get("current") or "@build.card.tools"
                                                ) if tools.get("total") else "@build.tools_checking"
                if tools.get("total"):
                    main["progress"] = max(0.0, min(1.0, tools.get("done", 0) / tools["total"]))
            elif state.get("step_no"):
                n, total = state["step_no"]
                listed = state.get("steps") or []
                name = listed[n - 1]["k"] if 0 < n <= len(listed) and listed[n - 1].get("k") else state.get("title") or ""
                main["stepLine"] = i18n.message("build.step_line", n=n, total=total, name=name)
            elif state.get("title"):
                main["stepLine"] = i18n.message("step", name=state["title"])
            if clock is not None:
                main["elapsed"] = i18n.message("build.elapsed", time=i18n.literal(clock_text(now - clock["start"])))
                remaining = self._build_remaining(g, state, clock, now)
                if remaining is not None:
                    main["eta"] = "@build.eta_soon" if remaining < 60 else i18n.message("build.eta", minutes=math.ceil(remaining / 60))
                elif not tools_phase and g.m.get("adapter") in TYPICAL_MINUTES:
                    low, high = TYPICAL_MINUTES[g.m["adapter"]]
                    main["eta"] = i18n.message("build.eta_typical", low=low, high=high)
                quiet = now - clock["line_at"]
                if not tools_phase and quiet >= QUIET_SECONDS:
                    main["quiet"] = i18n.message("build.quiet", name=state.get("title") or "?", minutes=int(quiet // 60))
            return main
        if it.get("first_play"):
            main.update(kicker="@build.kicker.done", tone="done", progress=1.0)
        elif failed == "tools":           # the tools card says what failed and has Help; this is the Try again
            main.update(kicker="@build.kicker.error", tone="error", lead="@build.tools_failed_hint")
        elif failed:
            main.update(kicker="@build.kicker.error", tone="error", error=state.get("result") or "",
                        lead="@build.failed_lead")
        elif it.get("blocked") or it.get("disabled"):
            main.update(kicker="@build.kicker.blocked", tone="todo")
        else:
            main.update(kicker="@build.kicker.ready", tone="todo")
            tools_missing = any(row.get("ok") is not True for row in g.a.prerequisites())
            low_high = TYPICAL_MINUTES.get(g.m.get("adapter", ""))
            if tools_missing:
                main["lead"] = "@build.lead_tools"
            elif state.get("result") and state["result"] not in FINISHED:
                main["lead"] = state["result"]
            elif low_high and not g.a.ready():
                main["lead"] = i18n.message("build.lead_ready", low=low_high[0], high=low_high[1])
        return main
