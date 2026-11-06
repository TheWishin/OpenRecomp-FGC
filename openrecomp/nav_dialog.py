"""Confirmation dialog actions and view."""
from . import i18n


class Dialog:
    def _ask(self, kind):
        self._cancel_hold()
        self.overlay = "dialog"
        self.confirm_kind = kind
        self.exit_focus = 0

    def _dialog(self, a):
        if self.confirm_kind == "online_challenge":
            return self._online_challenge_dialog(a)
        if self.confirm_kind == "netext_forget":
            from . import nav_netext
            return nav_netext.dialog(self, a)
        if self.confirm_kind.startswith("library_"):
            return self._library_dialog(a)
        if self.confirm_kind.startswith("setup_"):
            return self._setup_dialog(a)
        if self.confirm_kind == "update_progress":
            return self._update_progress_dialog(a)
        if self.confirm_kind == "tools_help":
            return self._tools_dialog(a)
        if self.confirm_kind == "uninstall_all":
            return self._uninstall_dialog(a)
        if a in ("left", "right", "up", "down"):
            self.exit_focus = 1 - self.exit_focus
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            yes = self.exit_focus == 1
            self.overlay = None
            if yes and self.confirm_kind == "exit":
                if not self._dry("@dry_quit"):
                    if self.request_quit():
                        self.overlay = None
                        self.on_quit()
            elif yes and self.confirm_kind == "cancel_build" and not self._dry("@dry_cancel_build"):
                if self._offline_action(self.game.a.build_cancel):
                    self.say("@cancelling_build")
            elif yes and self.confirm_kind == "stop_game" and not self._dry("@dry_stop"):
                self._offline_action(self.game.a.stop)
            elif yes and self.confirm_kind == "rebuild":
                self._start_build(self.game, force=True)
            elif yes and self.confirm_kind == "t5_folder":
                # The one-time notice is told: remember it (the launcher's own config, nothing in the folder), then build.
                self.game.a.foreign_notice_done()
                if self.on_adapter_config:
                    self.on_adapter_config()
                self._start_build(self.game, force=bool(getattr(self, "build_force", False)))
            elif yes and self.confirm_kind == "controls_reset":
                self._reset_controls()
            elif yes and self.confirm_kind == "support_report":
                self._start_support(self.game, "report")
            elif yes and self.confirm_kind == "update":
                if self._update_busy():
                    self.say("@updates.busy")
                elif self.update_state.get("phase") == "available" and self.update_state.get("version") == self.update_version:
                    if self.on_update_install and not self._dry("@updates.install"):
                        if self.on_update_install() is not False:
                            self._ask("update_progress")     # step, MB, speed, time left -- and Cancel

    # ---- the launcher's own update: progress and cancel
    def _update_progress_dialog(self, a):
        if a not in ("back", "confirm"):
            return
        st = self.update_state
        if st.get("phase") not in ("checking", "installing", "waiting"):
            self.overlay = None
        elif st.get("step") == "restart" or st.get("can_cancel") is False:
            # Files are being replaced: nothing to cancel any more. The window says why and stays.
            self.say("@updates.step_restart")
        elif not st.get("cancelling"):
            if self.on_update_cancel is not None:
                self.on_update_cancel()
            self.say("@setup.cancelling")

    def _view_update_progress(self, v):
        st = self.update_state
        restart = st.get("step") == "restart" or st.get("can_cancel") is False
        text = i18n.message("updates.progress_text", version=i18n.literal(str(st.get("version", ""))),
                            progress=self._update_progress_line())
        v["dialog"] = dict(title="@updates.progress_title", text=text,
                           options=[dict(label="@setup.ok_wait" if restart else "@cancel", index=0, focused=True)])
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@setup.ok_wait" if restart else "@cancel"), self.prompt("back", "@setup.ok_wait" if restart else "@cancel")]

    # ---- complete uninstall (0.1.3): the list first, then Cancel / keep saves / remove everything
    def uninstall_ask(self):
        on_uninstall = getattr(self, "on_uninstall", None)
        if on_uninstall is None or self._dry("@uninstall.title"):
            return
        self.uninstall_plan = on_uninstall("plan", None) or {}
        self._ask("uninstall_all")

    def _uninstall_dialog(self, a):
        if a in ("left", "right", "up", "down"):
            self.exit_focus = (self.exit_focus + (1 if a in ("right", "down") else 2)) % 3
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            choice = self.exit_focus
            self.overlay = None
            if choice in (1, 2):
                self.on_uninstall("run", choice == 1)        # keep saves and replays = option 1

    def _view_uninstall_dialog(self, v):
        plan = getattr(self, "uninstall_plan", None) or {}
        lines = [i18n.message("uninstall.line_game", folder=i18n.literal(g["root"])) for g in plan.get("games", [])]
        lines += [i18n.message("uninstall.line_skipped", folder=i18n.literal(s["root"])) for s in plan.get("skipped", [])]
        if plan.get("data"):
            lines.append(i18n.message("uninstall.line_data", folder=i18n.literal(plan["data"])))
        if plan.get("program"):
            lines.append(i18n.message("uninstall.line_program", folder=i18n.literal(plan["program"])))
        text = i18n.message("uninstall.text_list", count=len(lines))
        for line in lines:
            text = i18n.message("uninstall.join", text=text, line=line)
        v["dialog"] = dict(title="@uninstall.title", text=text,
                           options=[dict(label=label, index=index, focused=self.exit_focus == index)
                                    for index, label in enumerate(("@cancel", "@uninstall.keep_saves", "@uninstall.everything"))])
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]

    def _view_dialog(self, v):
        if self.confirm_kind == "online_challenge":
            return self._view_online_challenge(v)
        if self.confirm_kind == "netext_forget":
            from . import nav_netext
            return nav_netext.view_dialog(self, v)
        if self.confirm_kind.startswith("library_"):
            return self._view_library_dialog(v)
        if self.confirm_kind.startswith("setup_"):
            return self._view_setup_dialog(v)
        if self.confirm_kind == "update_progress":
            return self._view_update_progress(v)
        if self.confirm_kind == "tools_help":
            return self._view_tools_dialog(v)
        if self.confirm_kind == "uninstall_all":
            return self._view_uninstall_dialog(v)
        if self.confirm_kind == "exit":
            title, text = "@dialog.quit.title", "@dialog.quit.text"
        elif self.confirm_kind == "stop_game":
            title, text = "@dialog.stop.title", "@dialog.stop.text"
        elif self.confirm_kind == "rebuild":
            title, text = "@dialog.rebuild.title", "@dialog.rebuild.text"
        elif self.confirm_kind == "t5_folder":
            title, text = "@dialog.t5_folder.title", "@dialog.t5_folder.text"
        elif self.confirm_kind == "controls_reset":
            title, text = "@controls.reset", "@controls.reset_confirm"
        elif self.confirm_kind == "support_report":
            title, text = "@support.report.confirm.title", "@support.report.confirm.text"
            text = self.game.a.support_state().get("confirm_text", text)
        elif self.confirm_kind == "update":
            title = "@updates.confirm.title"
            text = i18n.message("updates.confirm.text", version=self.update_version,
                                size=max(1, round(int(self.update_state.get("size") or 0) / 1_000_000)),
                                notes=i18n.literal(" ".join(str(self.update_state.get("notes", "")).split())[:300]))
        else:
            title, text = "@dialog.cancel.title", "@dialog.cancel.text"
        v["dialog"] = dict(title=title, text=text, options=[dict(label="@no", index=0, focused=self.exit_focus == 0), dict(label="@yes", index=1, focused=self.exit_focus == 1)])
        if self.confirm_kind == "update":
            v["dialog"]["options"][1]["label"] = "@updates.install"
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]
