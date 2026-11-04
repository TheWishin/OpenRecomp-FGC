"""The game sections and their adapter actions."""
import os

from . import i18n


class Sections:
    # ---- play
    def _items_play(self, g):
        st = g.a.status()
        ready = g.a.ready()
        running = g.a.running()
        detail = dict(kicker=st["status"], title=i18n.literal(g.short), lead=st["detail"],
                      rows=[dict(k="@version", v=st["version"]), dict(k="@last_played", v=st["last"])],
                      results=g.a.recent_results(), image="")
        by_id = {s["id"]: s for s in g.a.settings()}
        for sid in g.a.quick_settings():
            s = by_id.get(sid)
            if s:
                detail["rows"].append(dict(k=s["label"], v=self._option_label(s)))
        if running:
            detail["primary"] = "@stop"
            start = dict(kind="action", id="start", label="@game_running", verb="@stop", run=lambda: self._ask("stop_game"),
                         hint=i18n.message("game_is_running", name=i18n.literal(g.short)), detail=detail)
        elif ready:
            if g.m.get("adapter") == "t4":
                detail["lead"] = "@t4.play_hint"
            detail["primary"] = "@play"
            start = dict(kind="action", id="start", label="@start_game", verb="@start", run=lambda: self.start_game(g),
                         hint="@t4.play_hint" if g.m.get("adapter") == "t4" else "@start_hint", detail=detail)
        else:
            can_build = "build" in self.sections(g)
            detail["primary"] = "@go_build" if can_build else ""
            start = dict(kind="action", id="start", label="@build_first" if can_build else "@not_found", verb="@go_build" if can_build else "",
                         run=(lambda: self._go(g, "build")) if can_build else None,
                         hint=st["detail"], detail=detail)
        out = self._setup_items(g, "play") + [start]
        for sid in g.a.quick_settings():
            if sid in by_id:
                out.append(self._cycler_item(g, by_id[sid]))
        if getattr(g.a, "coexistence_state", lambda: dict(active=False))()["active"]:
            out.extend(self._coexistence_items(g))
        if g.a.native_label:
            out.append(self._native_item(g))
        return out

    def _go(self, g, section):
        self.sec[g.id] = section

    def _native_item(self, g):
        def run():
            if self._dry(i18n.message("dry_open", name=g.a.native_label)):
                return
            if self._offline_action(g.a.open_native):
                self.say(i18n.message("opening", name=g.a.native_label))
        return dict(kind="action", id="native", label="@native_launcher", verb="@open", run=run,
                    hint=i18n.message("native_hint", name=g.a.native_label),
                    detail=dict(kicker="@also", title=g.a.native_label, lead="@native_lead", rows=[]))

    @staticmethod
    def _option_label(s):
        return next((label for value, label in s["options"]
                     if type(value) is type(s["value"]) and value == s["value"]), str(s["value"]))

    def _cycler_item(self, g, s):
        def setter(value):
            g.a.set_setting(s["id"], value)
        label = self._option_label(s)
        return dict(kind="cycler", id=s["id"], label=s["label"], value=label, options=s["options"], current=s["value"], set=setter,
                    hint=s.get("hint", ""), detail=dict(kicker="@setting", title=s["label"], lead=s.get("lead", ""), rows=[dict(k="@current", v=label)]))

    # ---- online
    def _items_online(self, g):
        return self._setup_items(g, "online") + self._items_online_rows(g)

    def _items_online_rows(self, g):
        if g.m.get("adapter") == "t4" and not g.a.found():
            return [dict(kind="action", id="folder", label="@onboarding.choose_folder", verb="@go_build",
                         run=lambda: self._go(g, "build"), hint="@t4.onboarding_hint",
                         detail=dict(kicker="@section.online", title="@onboarding.choose_folder", lead="@t4.onboarding_hint", rows=[]))]
        if g.m.get("adapter") == "t5dr" and not g.a.found():
            return [dict(kind="action", id="folder", label="@onboarding.choose_folder", verb="@go_build",
                         run=lambda: self._go(g, "build"), hint="@onboarding.hint",
                         detail=dict(kicker="@section.online", title="@onboarding.choose_folder", lead="@onboarding.hint", rows=[]))]
        if self._direct_online(g):
            return self._direct_online_items(g)
        if getattr(g.a, "online_supported", lambda: False)():
            if not self.dry:
                # Shown: the remembered login logs in by itself once (adapters decide; never a password).
                getattr(g.a, "online_shown", lambda: None)()
            return self._online_items(g)
        out = []
        for it in g.a.online_items():
            it = dict(it)
            opens = it.get("opens")
            if opens == "fighters":
                it["run"] = self._open_fighters
            elif opens and opens.startswith("text:"):
                it["run"] = lambda tid=opens[5:]: self._open_osk(tid)
            elif it.get("kind") == "action":
                it["run"] = lambda iid=it["id"], label=it["label"]: self._dry(i18n.message("dry_start", name=label)) or self.say(g.a.run_online(iid))
            out.append(it)
        return out

    # ---- replays
    def _items_replays(self, g):
        replays = g.a.replays()
        if not replays:
            return [dict(kind="action", id="none", label="@no_replays", verb="", hint="@replays_hint",
                         detail=dict(kicker="@section.replays", title="@no_replays", lead="@replays_lead", rows=[]))]
        out, last = [], None
        for r in replays:
            if r["group"] != last:
                out.append(dict(kind="heading", label=r["group"]))
                last = r["group"]
            result = r["result"] if self.show_results else "@hidden"
            out.append(dict(kind="action", id=r["id"], replay=r["id"], label=r["label"], value=r["when"], verb="@watch",
                            run=lambda rid=r["id"]: self._play_replay(g, rid),
                            hint="@replay_hint",
                            detail=dict(kicker=r["group"], title=r["label"], lead="@saved_locally", images=r.get("images", []),
                                        rows=[dict(k="@date", v=r["date"]), dict(k="@opponent", v=r["opponent"]), dict(k="@netcode", v=r["netcode"]), dict(k="@result", v=result)],
                                        primary="@watch")))
        return out

    def _play_replay(self, g, rid):
        if self._dry("@dry_replay"):
            return
        if self._offline_action(g.a.play_replay, rid, extra_env=self.launch_env or None):
            self.say("@replay_starting")

    # ---- build
    def _items_build(self, g):
        return self._setup_items(g, "build") + self._items_build_rows(g)

    def _open_source_picker(self, src, title=None):
        """A Build source row (or the shelf's first step): its own dialog title and file type when it names them."""
        title = title or src.get("title") or i18n.message("choose_named", name=src["label"])
        self._open_picker("source:" + src["id"], title, src["exts"], src["dirs"], src.get("kind", "file"), src.get("filter", ""))

    def _items_build_rows(self, g):
        if getattr(g.a, "coexistence_state", lambda: dict(active=False))()["active"]:
            return self._coexistence_items(g, choose=True) + [dict(
                kind="action", id="build", label="@build_game", disabled=True,
                hint="@t5.coexist.build_blocked",
                detail=dict(kicker="@section.build", title="@build_game",
                            lead="@t5.coexist.build_blocked", rows=[]))]
        state = g.a.build_state()
        source_state = g.a.source_state()
        out = []
        for s in g.a.sources():
            src = dict(s)
            detail = dict(kicker="@your_files", title=s["label"], lead=s.get("note") or s["hint"],
                          rows=[dict(k="@current", v=s["value"], accent=not s["ok"]), dict(k="@source", v=g.m.get("source", "@own_file"))])
            checking = source_state.get("running") and source_state.get("id") == s["id"]
            installing = checking and s["id"] == "folder"
            if checking:
                detail["lead"] = "@t4.installing" if installing else "@iso.checking"
            blocked = state["running"] or checking
            out.append(dict(kind="action", id=s["id"], label=s["label"], value=("@t4.installing" if installing else "@iso.checking") if checking else s["value"], missing=not s["ok"], disabled=blocked, verb="" if blocked else ("@choose" if not s["ok"] else "@change"),
                            hint=detail["lead"] if checking else s["hint"], detail=detail,
                            run=None if blocked else lambda src=src: self._open_source_picker(src)))
            if s.get("kind") == "file_or_folder" and s.get("exts"):
                # The folder is the usual answer (Explorer opens its folder dialog); a downloaded release zip is this row.
                zip_detail = dict(kicker="@your_files", title="@picker.have_zip", lead="@picker.have_zip_hint", rows=[])
                out.append(dict(kind="action", id=s["id"] + ":zip", label="@picker.have_zip", value="", disabled=blocked,
                                verb="" if blocked else "@choose", hint="@picker.have_zip_hint", detail=zip_detail,
                                run=None if blocked else lambda src=src: self._open_picker(
                                    "source:" + src["id"], "@picker.choose_zip", src["exts"], src["dirs"], "file",
                                    "@picker.zip_filter")))
        for o in g.a.build_options():
            out.append(self._cycler_item(g, o))
        # Build tools: one row at most. Missing ones come before Build (they block it); "ready" goes after it.
        tools = self._prerequisite_items(g, state["running"] or source_state.get("running", False))
        tools_first = any(t["id"] in ("tools:install", "tools:installing") for t in tools)
        if tools_first:
            out.extend(tools)
        problem = g.a.build_ready()
        if not g.a.found():
            return out or [dict(kind="action", id="none", label="@not_found", hint="@build_unavailable_hint",
                                detail=dict(kicker="@section.build", title="@not_found", lead="@build_unavailable_hint", rows=[]))]
        st = g.a.status()
        if state["running"]:
            def cancel():
                self._ask("cancel_build")
            t4 = g.m.get("adapter") == "t4"
            rows = list(state["steps"])
            if t4 and state["line"]:
                rows.append(dict(k="@t4.build_output", v=i18n.literal(state["line"][-160:])))
            out.append(dict(kind="action", id="build", label="@build_running", verb="@cancel", run=cancel, hint="@t4.build_wait" if t4 else (state["line"][:90] or "@build_running_hint"),
                            detail=dict(kicker=i18n.message("step", name=state["title"]), title="@build_running", lead="@t4.build_wait" if t4 else (state["line"][:160] or "@build_running_hint"), rows=rows, progress=state["fraction"])))
            return out

        def build():
            if problem:
                self.say(problem)
            elif not self._dry("@dry_build"):
                if self._offline_action(g.a.build_start):
                    self.say("@build_starting")
        lead = state["result"] or problem or ("@built_hint" if g.a.ready() else "@build_hint")
        first_play = (g.m.get("adapter") == "t4" and g.a.ready()
                      and (not state["result"] or state["result"] in ("@build_finished", "@t4.build_finished")))
        if first_play:
            lead = "@t4.build_next"
        out.append(dict(kind="action", id="build", label="@start_game" if first_play else "@build_game", verb="@play" if first_play else ("@files_missing" if problem else "@build"), run=(lambda: self.start_game(g)) if first_play else build,
                        hint=lead, detail=dict(kicker=st["status"], title="@start_game" if first_play else "@build_game", lead=lead, rows=state["steps"], primary="@play" if first_play else ("" if problem else "@build"))))
        if not tools_first:
            out.extend(tools)
        if g.m.get("adapter") == "t4" and g.a.ready():
            out.append(dict(kind="action", id="online_setup", label="@t4.direct_title", verb="@confirm",
                            hint="@t4.network.check", run=lambda: self._go(g, "online"),
                            detail=dict(kicker="@section.online", title="@t4.direct_title",
                                        lead="@t4.network.check", leadLines=6, rows=[])))
        if not problem:
            def rebuild():
                self._ask("rebuild")
            out.append(dict(kind="heading", label="@from_scratch", mt=16))
            out.append(dict(kind="hold", id="rebuild", label="@rebuild_all", verb="@hold", run=rebuild, hint="@rebuild_hint",
                            detail=dict(kicker="@takes_longer", title="@rebuild_all", lead="@rebuild_lead", rows=[])))
        return out

    def _prerequisite_items(self, g, blocked=False):
        """The PC's build tools as ONE row: checked by themselves in the background, versions only in its details.

        Checking -> "Build tools: Checking...", all there -> "Build tools ready" (confirm checks again), some missing
        -> "Install missing tools" (a dialog lists them; winget installs them), installing -> its progress."""
        checks = g.a.prerequisites()
        if not checks:
            return []
        install = g.a.prerequisite_install_state()
        checking = any(check.get("busy") for check in checks)
        missing = [check for check in checks if check.get("ok") is False and not check.get("busy")]
        details = dict(kicker="@section.build", title="@t4.tools.title", lead="@t4.tools.details_hint", leadLines=6,
                       rows=[dict(k=check["label"], v=check["value"], accent=check.get("ok") is False) for check in checks])
        if install.get("running"):
            progress = i18n.message("t4.tools.install_progress", done=install.get("done", 0) + 1,
                                    total=install.get("total", 0), name=install.get("current", ""))
            return [dict(kind="action", id="tools:installing", label="@t4.tools.installing", value=progress, disabled=True,
                         verb="", hint="@t4.tools.installing_hint", run=None,
                         detail=dict(details, lead="@t4.tools.installing_hint"))]
        if checking:
            return [dict(kind="action", id="tools:checking", label="@t4.tools.title", value="@t4.tools.checking",
                         disabled=True, verb="", hint="@t4.tools.details_hint", run=None, detail=details)]
        if missing:
            def ask():
                self.tools_game = g
                self._ask("tools_install")
            return [dict(kind="action", id="tools:install", label="@t4.tools.install_missing",
                         value=i18n.message("t4.tools.missing_count", count=len(missing)), missing=True,
                         disabled=blocked, verb="" if blocked else "@t4.tools.install", hint="@t4.tools.install_hint",
                         run=None if blocked else ask, detail=dict(details, lead="@t4.tools.install_hint"))]

        def refresh():
            if not self._dry("@t4.tools.recheck"):
                self._offline_action(g.a.refresh_prerequisites)
        return [dict(kind="action", id="tools:ready", label="@t4.tools.ready", value="", disabled=blocked,
                     verb="" if blocked else "@t4.tools.recheck_short", hint="@t4.tools.details_hint",
                     run=None if blocked else refresh, detail=details)]

    def _tools_plan(self, g):
        """[(label, command)] of the missing tools, one per installer (as the adapter will run them)."""
        plan, seen = [], set()
        for check in g.a.prerequisites():
            command = check.get("command") or ""
            if check.get("ok") is False and not check.get("busy") and command and command not in seen:
                seen.add(command)
                plan.append((check["label"], command))
        return plan

    def _tools_dialog(self, a):
        """Install missing build tools: Cancel / Copy commands / Install (3 options)."""
        g = getattr(self, "tools_game", None) or self.game
        if a in ("left", "up"):
            self.exit_focus = (self.exit_focus - 1) % 3
        elif a in ("right", "down"):
            self.exit_focus = (self.exit_focus + 1) % 3
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            self.overlay = None
            plan = self._tools_plan(g)
            if self.exit_focus == 1 and plan:
                self.copy_text(os.linesep.join(command for _label, command in plan))
                if not self.dry:
                    self.say("@t4.tools.copied_all", 8)
            elif self.exit_focus == 2 and plan and not self._dry("@t4.tools.install"):
                if g.a.install_prerequisites():
                    self.tools_installing = g
                    self.say("@t4.tools.installing_hint", 10)
                else:
                    self.say("@t4.tools.work_busy", 8)

    def _view_tools_dialog(self, v):
        g = getattr(self, "tools_game", None) or self.game
        names = ", ".join(i18n.localize(label, self.language) for label, _command in self._tools_plan(g))
        v["dialog"] = dict(title="@t4.tools.install_title",
                           text=i18n.message("t4.tools.install_text", names=i18n.literal(names)),
                           options=[dict(label=label, index=i, focused=self.exit_focus == i) for i, label in
                                    enumerate(("@cancel", "@t4.tools.copy_commands", "@t4.tools.install"))])
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]

    def poll_tools_install(self):
        """The installs ended: say how, once. -> True when the screen must be redrawn."""
        g = getattr(self, "tools_installing", None)
        if g is None:
            return False
        state = g.a.prerequisite_install_state()
        if state.get("running"):
            return False
        self.tools_installing = None
        if state.get("result"):
            self.say(state["result"], 12)
        return True

    # ---- settings
    def _items_settings(self, g):
        out = self._coexistence_items(g, choose=True) if getattr(g.a, "coexistence_state", lambda: dict(active=False))()["active"] else []
        for s in g.a.settings():
            if s.get("kind") == "folder":
                value = i18n.literal(s["value"]) if s.get("value") else s.get("display", "")
                out.append(dict(kind="action", id=s["id"], label=s["label"], value=value,
                                verb="@change", hint=s.get("hint", ""),
                                detail=dict(kicker="@setting", title=s["label"], lead=s.get("hint", ""),
                                            rows=[dict(k="@current", v=value)]),
                                run=lambda s=s: self._open_picker("setting:" + s["id"], s["label"], [],
                                                               [s.get("value", "")], "folder")))
                if s.get("value"):
                    out.append(dict(kind="action", id="reset:" + s["id"], label="@t5.replay_folder_reset",
                                    verb="@confirm", hint=s.get("hint", ""),
                                    run=lambda sid=s["id"]: self._dry("@dry_text") or g.a.set_setting(sid, "")))
            else:
                out.append(self._cycler_item(g, s))
        if g.a.native_label:
            out.append(dict(kind="heading", label="@also", mt=12))
            out.append(self._native_item(g))
        if not out:
            out.append(dict(kind="action", id="none", label="@no_settings", verb="", hint="@no_settings_hint",
                            detail=dict(kicker="@section.settings", title="@no_settings", lead="@no_settings_hint", rows=[])))
        return out

    def _coexistence_items(self, g, choose=False):
        state = g.a.coexistence_state()
        compatibility = {"same": "@t5.coexist.build_match", "different": "@t5.coexist.build_differs"}
        build = compatibility.get(state["build"], "@t5.coexist.build_unknown")
        source = i18n.literal(state["source"])
        out = [dict(kind="action", id="coexistence", label="@t5.coexist.title", hint="@t5.coexist.hint",
                    detail=dict(kicker="@t5.coexist.title", title="@t5.coexist.title",
                                lead="@t5.coexist.hint", rows=[
                                    dict(k="@t5.coexist.source", v=source),
                                    dict(k="@version", v=build),
                                    dict(k="@section.settings", v="@t5.coexist.settings"),
                                    dict(k="@section.online", v="@t5.coexist.login")]))]
        if choose:
            out.append(dict(kind="action", id="coexistence_folder", label="@t5.coexist.choose_install",
                            verb="@choose", hint="@t5.coexist.choose_hint",
                            detail=dict(kicker="@t5.coexist.title", title="@t5.coexist.choose_install",
                                        lead="@t5.coexist.choose_hint", rows=[]),
                            run=lambda: self._open_picker("source:folder", "@t5.coexist.choose_install",
                                                          [], [state["source"]], "folder")))
        return out
