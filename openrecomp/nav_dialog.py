"""Confirmation dialog actions and view."""
from . import i18n


class Dialog:
    def _ask(self, kind):
        self._cancel_hold()
        self.overlay = "dialog"
        self.confirm_kind = kind
        self.exit_focus = 0

    def _dialog(self, a):
        if self.confirm_kind.startswith("library_"):
            return self._library_dialog(a)
        if self.confirm_kind.startswith("setup_"):
            return self._setup_dialog(a)
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
            elif yes and self.confirm_kind == "rebuild" and not self._dry("@dry_rebuild"):
                if self._offline_action(self.game.a.build_start, force=True):
                    self.say("@rebuild_starting")
            elif yes and self.confirm_kind == "support_report":
                self._start_support(self.game, "report")
            elif yes and self.confirm_kind == "update":
                if self._update_busy():
                    self.say("@updates.busy")
                elif self.update_state.get("phase") == "available" and self.update_state.get("version") == self.update_version:
                    if self.on_update_install and not self._dry("@updates.install"):
                        self.on_update_install()

    def _view_dialog(self, v):
        if self.confirm_kind.startswith("library_"):
            return self._view_library_dialog(v)
        if self.confirm_kind.startswith("setup_"):
            return self._view_setup_dialog(v)
        if self.confirm_kind == "exit":
            title, text = "@dialog.quit.title", "@dialog.quit.text"
        elif self.confirm_kind == "stop_game":
            title, text = "@dialog.stop.title", "@dialog.stop.text"
        elif self.confirm_kind == "rebuild":
            title, text = "@dialog.rebuild.title", "@dialog.rebuild.text"
        elif self.confirm_kind == "support_report":
            title, text = "@support.report.confirm.title", "@support.report.confirm.text"
        elif self.confirm_kind == "update":
            title = "@updates.confirm.title"
            text = i18n.message("updates.confirm.text", version=self.update_version,
                                size=self.update_state.get("size", 0),
                                notes=i18n.literal(" ".join(str(self.update_state.get("notes", "")).split())[:300]))
        else:
            title, text = "@dialog.cancel.title", "@dialog.cancel.text"
        v["dialog"] = dict(title=title, text=text, options=[dict(label="@no", index=0, focused=self.exit_focus == 0), dict(label="@yes", index=1, focused=self.exit_focus == 1)])
        if self.confirm_kind == "update":
            v["dialog"]["options"][1]["label"] = "@updates.install"
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]
