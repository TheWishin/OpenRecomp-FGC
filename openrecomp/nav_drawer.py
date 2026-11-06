"""Quick access drawer actions and view."""
from . import i18n, ui_sound
from .nav_game_setup import UPDATE_STEP_TEXT

UPDATE_BUSY = ("checking", "installing", "waiting")


class Drawer:
    def _drawer_items(self):
        out = [dict(id="language", label="@language", value="@language." + self.language, language=True, hint="@language_hint"),
               dict(id="display", label="@display_mode", value="@fullscreen" if self.fullscreen else "@windowed", fullscreen=True, hint="@display_mode_hint"),
               dict(id="motion", label="@motion", value="@motion_reduced" if self.reduced_motion else "@motion_full", motion=True, hint="@motion_hint")]
        phase = self.update_state.get("phase", "idle")
        update_hint = {"checking": "@updates.checking", "installing": "@updates.installing", "current": "@updates.current",
                       "waiting": "@updates.waiting", "unconfigured": "@updates.unconfigured", "error": self.update_failure_key(),
                       "cancelled": "@updates.cancelled", "ready": "@updates.ready"}.get(phase, "@updates.hint")
        if phase in UPDATE_BUSY:
            # While it runs the row shows where it is (the same line as the progress window)
            update_hint = self._update_progress_line()
            if phase != "waiting" and self.update_state.get("can_cancel", True) and not self.update_state.get("cancelling"):
                update_hint = i18n.message("updates.running_hint", progress=update_hint, cancel="@updates.cancel_hint")
        value = self.update_state.get("version", "")
        if phase == "current" and self.update_state.get("test_version"):
            # 0.1.4: stable is current, a newer test version (pre-release) is out: name it, Confirm installs it
            value = self.update_state["test_version"]
            update_hint = i18n.message("updates.current_test", version=i18n.literal(value))
        out.append(dict(id="updates", label="@updates.check", value=value, update=True, hint=update_hint))
        if getattr(self, "on_setup", None) is not None:
            out.append(dict(id="game_updates", label="@setup.check", value="", game_check=True, hint="@setup.check_hint"))
            out.append(dict(id="prereleases", label="@setup.test_versions", value="@on" if self.game_prereleases else "@off",
                            prereleases=True, hint="@setup.test_versions_hint"))
        for g in self.games:
            if g.a.found() and g.a.native_label:
                out.append(dict(id="native:" + g.id, label=g.a.native_label, value=g.short, game=g, hint=i18n.message("native_hint", name=g.a.native_label)))
        out.append(dict(id="launcher", label="@launcher_settings.title", value="", launcher=True, hint="@launcher_settings.hint"))
        out.append(dict(id="discord", label="@community.discord", value="", discord=True, hint="@community.hint"))
        if self.progress_jobs() or self.progress_ends:
            out.append(dict(id="progress", label="@progress.show", value="", progress=True, hint="@progress.drawer_hint"))
        from . import nav_feedback
        activity = nav_feedback.activity_view(self)
        if activity:
            out.append(dict(id="returnActivity", label=activity["label"], value=activity["name"],
                            activity=True, hint=activity["status"]))
        rows = [item["id"] for item in out]
        previous = getattr(self, "drawer_rows", None)
        index = self.drawer_focus
        if (not 0 <= index < len(rows) or previous is not None
                and (index >= len(previous) or previous[index] != rows[index])):
            self.drawer_focus = 0
        self.drawer_rows = rows
        return out

    def _drawer(self, a):
        previous = getattr(self, "drawer_rows", None)
        index = self.drawer_focus
        items = self._drawer_items()
        if a in ("confirm", "left", "right") and previous is not None and (
                not 0 <= index < len(previous) or index >= len(items)
                or previous[index] != self.drawer_rows[index]):
            return
        if a == "up":
            self.drawer_focus = max(0, self.drawer_focus - 1)
        elif a == "down":
            self.drawer_focus = min(len(items) - 1, self.drawer_focus + 1)
        elif a in ("left", "right"):
            self._drawer_cycle(items[self.drawer_focus], 1 if a == "right" else -1)
        elif a in ("back", "social"):
            self.overlay = None
        elif a == "confirm":
            if self._drawer_cycle(items[self.drawer_focus], 1):
                return
            if items[self.drawer_focus].get("launcher"):
                self.overlay = None
                return self.open_launcher_settings()
            if items[self.drawer_focus].get("update"):
                return self._check_update()
            if items[self.drawer_focus].get("discord"):
                return self.open_discord()
            if items[self.drawer_focus].get("progress"):
                self.overlay = None
                return self.progress_open()
            if items[self.drawer_focus].get("activity"):
                from . import nav_feedback
                return nav_feedback.return_activity(self)
            if items[self.drawer_focus].get("game_check"):
                self.setup_check_manual()
                return
            g = items[self.drawer_focus].get("game")
            if g and not self._dry(i18n.message("dry_open", name=g.a.native_label)):
                g.a.open_native()
                self.overlay = None
                self.say(i18n.message("opening", name=g.a.native_label))

    def _drawer_cycle(self, item, step):
        if item.get("language"):
            self._cycle_language(step)
        elif item.get("prereleases"):
            if self._dry(i18n.message("dry_change", name=item["label"])):
                return True
            self.game_prereleases = not self.game_prereleases
            self.on_prereleases(self.game_prereleases)
            self.hint_toggle(self.game_prereleases)
        elif item.get("fullscreen") or item.get("motion"):
            if self._dry(i18n.message("dry_change", name=item["label"])):
                return True
            if item.get("fullscreen"):
                self.fullscreen = not self.fullscreen
            else:
                self.reduced_motion = not self.reduced_motion
            self.on_preferences(self.fullscreen, self.reduced_motion)
            self.hint_toggle(self.fullscreen if item.get("fullscreen") else not self.reduced_motion)
        else:
            return False
        return True

    def _cycle_language(self, step):
        if self._dry(i18n.message("dry_change", name="@language")):
            return
        codes = i18n.LANGUAGES
        self.language = codes[(codes.index(self.language) + step) % len(codes)]
        self.on_language(self.language)
        self.hint_toggle(self.language, step)

    def _update_busy(self, allow_lobby=False):
        """allow_lobby: a game install/update may run while logged in to a lobby (0.1.4); the launcher's own update
        (it restarts the launcher) still waits."""
        if getattr(self, "library_busy", False):
            return True
        for g in self.games:
            if (g.a.running() or g.a.build_state().get("running") or g.a.source_state().get("running")
                    or g.a.support_state().get("running")):
                return True
            online = g.a.online_state()
            idle = ("", "offline", "error", "kicked") + (("logged_in",) if allow_lobby else ())
            if online.get("busy") or online.get("phase", "offline") not in idle:
                return True
        return False

    def update_failure_key(self):
        """The plain sentence for a failed launcher update: its reason in words (network, security check, free
        space), else the general one. Every one of them says that nothing was changed."""
        reason = self.update_state.get("reason", "")
        return {"network": "@updates.err_network", "verify": "@updates.err_verify",
                "space": "@updates.err_space"}.get(reason, "@updates.failed")

    def _update_progress_line(self):
        st = self.update_state
        if st.get("cancelling"):
            return "@setup.cancelling"
        if st.get("phase") == "waiting":
            return "@updates.waiting"
        return self._setup_progress_text(st, UPDATE_STEP_TEXT)

    def poll_update(self):
        """Called with every new launcher-update state: the progress window closes when the run is over (the
        outcome is said as a message by the backend)."""
        changed = False
        self.note_launcher_update()
        if (self.overlay == "dialog" and self.confirm_kind == "update_progress"
                and self.update_state.get("phase") not in UPDATE_BUSY):
            self.overlay = None
            changed = True
        version = str(self.update_state.get("version", ""))
        if (self.update_state.get("phase") == "ready" and self.update_restart_asked != version and self.overlay is None
                and not self._update_busy()):
            # Downloaded and checked while nothing else runs: one prompt, never over another dialog or a running game
            self.update_restart_asked = version
            self._ask("update_restart")
            changed = True
        return changed

    def launcher_update_line(self):
        """The line on the home screen about the launcher's own update ("" when there is nothing to say)."""
        st = self.update_state
        phase = st.get("phase")
        if phase == "available":
            return i18n.message("updates.home_available", version=i18n.literal(str(st.get("version", ""))))
        if phase == "ready":
            return "@updates.home_ready"
        if phase == "installing":
            return i18n.message("updates.home_installing", progress=self._update_progress_line())
        if phase == "waiting":
            return "@updates.waiting"
        return ""

    def launcher_update_action(self):
        """The home screen's Update: one action for whatever the launcher itself needs (its own entry in Quick
        access does the same thing)."""
        self._check_update()

    def setup_check_manual(self):
        """Check for game updates because the player asked: the result is said when the checks are done."""
        if self._dry("@setup.check"):
            return
        self.setup_check_pending = True
        self.on_setup("check_all", "", True)
        self.say("@setup.checking")

    def _check_update(self):
        phase = self.update_state.get("phase")
        if phase in UPDATE_BUSY:
            # Pressing the entry again shows the running update's progress (and its Cancel); it never starts another
            self._ask("update_progress")
            return
        if phase == "ready":
            self.update_restart_asked = ""
            self._ask("update_restart")
            return
        if phase == "available":
            self.overlay = None
            self.offer_update(force=True)     # also while a game runs: it downloads now, installs when closed
        elif self._update_busy():
            self.say("@updates.busy")
            return
        elif (self.update_state.get("phase") == "current" and self.update_state.get("test_version")
              and getattr(self, "on_update_test", None) and not self._dry("@updates.install")):
            if self.on_update_test():
                self.overlay = None
                self.offer_update(force=True)
        elif self.on_update_check and not self._dry("@updates.check"):
            self.on_update_check()
        elif not self.on_update_check:
            self.say("@updates.unconfigured")

    def offer_update(self, force=False):
        """Offer once per session when the launcher is free; confirmation remains a separate action."""
        version = self.update_state.get("version", "")
        if (self.update_state.get("phase") != "available" or not version or self.overlay
                or (self._update_busy() and not force) or (not force and self.update_offered == version)):
            return False
        self.update_offered = self.update_version = version
        self._ask("update")
        self.note_sound(ui_sound.NOTIFY)
        return True

    def _view_drawer(self, v):
        items = self._drawer_items()
        v["drawer"] = dict(rows=[dict(index=i, label=it["label"], value=it["value"], focused=i == self.drawer_focus) for i, it in enumerate(items)])
        item = items[self.drawer_focus]
        cycler = item.get("language") or item.get("fullscreen") or item.get("motion") or item.get("prereleases")
        v["hint"] = item["hint"]
        v["prompts"] = [self.prompt("confirm", "@change" if cycler else "@open")]
        if cycler:
            v["prompts"].append(self.prompt("right", "@change"))
        v["prompts"].append(self.prompt("back", "@close"))
