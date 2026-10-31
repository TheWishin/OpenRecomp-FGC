"""The game sections and their adapter actions."""
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
        out = [start]
        for sid in g.a.quick_settings():
            if sid in by_id:
                out.append(self._cycler_item(g, by_id[sid]))
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
        return next((label for value, label in s["options"] if value == s["value"]), str(s["value"]))

    def _cycler_item(self, g, s):
        def setter(value):
            g.a.set_setting(s["id"], value)
        label = self._option_label(s)
        return dict(kind="cycler", id=s["id"], label=s["label"], value=label, options=s["options"], current=s["value"], set=setter,
                    hint=s.get("hint", ""), detail=dict(kicker="@setting", title=s["label"], lead=s.get("lead", ""), rows=[dict(k="@current", v=label)]))

    # ---- online
    def _items_online(self, g):
        if g.m.get("adapter") == "t4" and not g.a.found():
            return [dict(kind="action", id="folder", label="@onboarding.choose_folder", verb="@go_build",
                         run=lambda: self._go(g, "build"), hint="@t4.onboarding_hint",
                         detail=dict(kicker="@section.online", title="@onboarding.choose_folder", lead="@t4.onboarding_hint", rows=[]))]
        if g.m.get("adapter") == "t5dr" and not g.a.found():
            return [dict(kind="action", id="folder", label="@onboarding.choose_folder", verb="@go_build",
                         run=lambda: self._go(g, "build"), hint="@onboarding.hint",
                         detail=dict(kicker="@section.online", title="@onboarding.choose_folder", lead="@onboarding.hint", rows=[]))]
        if g.m.get("adapter") == "t4" or (g.a.online_state().get("capabilities") or {}).get("direct_ip"):
            return self._direct_online_items(g)
        if getattr(g.a, "online_supported", lambda: False)():
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
                            run=None if blocked else lambda src=src: self._open_picker("source:" + src["id"], i18n.message("choose_named", name=src["label"]), src["exts"], src["dirs"], src.get("kind", "file"))))
        for o in g.a.build_options():
            out.append(self._cycler_item(g, o))
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
        if not problem:
            def rebuild():
                self._ask("rebuild")
            out.append(dict(kind="heading", label="@from_scratch", mt=16))
            out.append(dict(kind="hold", id="rebuild", label="@rebuild_all", verb="@hold", run=rebuild, hint="@rebuild_hint",
                            detail=dict(kicker="@takes_longer", title="@rebuild_all", lead="@rebuild_lead", rows=[])))
        return out

    # ---- settings
    def _items_settings(self, g):
        out = []
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
