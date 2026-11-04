"""Quick access drawer actions and view."""
from . import i18n, ui_sound


class Drawer:
    def _drawer_items(self):
        out = [dict(id="language", label="@language", value="@language." + self.language, language=True, hint="@language_hint"),
               dict(id="display", label="@display_mode", value="@fullscreen" if self.fullscreen else "@windowed", fullscreen=True, hint="@display_mode_hint"),
               dict(id="motion", label="@motion", value="@motion_reduced" if self.reduced_motion else "@motion_full", motion=True, hint="@motion_hint")]
        phase = self.update_state.get("phase", "idle")
        update_hint = {"checking": "@updates.checking", "installing": "@updates.installing", "current": "@updates.current",
                       "waiting": "@updates.waiting", "unconfigured": "@updates.unconfigured", "error": "@updates.failed"}.get(phase, "@updates.hint")
        out.append(dict(id="updates", label="@updates.check", value=self.update_state.get("version", ""), update=True, hint=update_hint))
        if getattr(self, "on_setup", None) is not None:
            out.append(dict(id="game_updates", label="@setup.check", value="", game_check=True, hint="@setup.check_hint"))
            out.append(dict(id="prereleases", label="@setup.test_versions", value="@on" if self.game_prereleases else "@off",
                            prereleases=True, hint="@setup.test_versions_hint"))
        for g in self.games:
            if g.a.found() and g.a.native_label:
                out.append(dict(id="native:" + g.id, label=g.a.native_label, value=g.short, game=g, hint=i18n.message("native_hint", name=g.a.native_label)))
        out.append(dict(id="discord", label="@community.discord", value="", discord=True, hint="@community.hint"))
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
            if items[self.drawer_focus].get("update"):
                return self._check_update()
            if items[self.drawer_focus].get("discord"):
                return self.open_discord()
            if items[self.drawer_focus].get("activity"):
                from . import nav_feedback
                return nav_feedback.return_activity(self)
            if items[self.drawer_focus].get("game_check"):
                if not self._dry("@setup.check"):
                    self.on_setup("check_all", "", True)
                    self.say("@setup.checking")
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

    def _update_busy(self):
        if getattr(self, "library_busy", False):
            return True
        for g in self.games:
            if (g.a.running() or g.a.build_state().get("running") or g.a.source_state().get("running")
                    or g.a.support_state().get("running")):
                return True
            online = g.a.online_state()
            if online.get("busy") or online.get("phase", "offline") not in ("", "offline", "error", "kicked"):
                return True
        return False

    def _check_update(self):
        if self.update_state.get("phase") in ("checking", "installing", "waiting"):
            self.say({"checking": "@updates.checking", "installing": "@updates.installing",
                      "waiting": "@updates.waiting"}[self.update_state["phase"]])
            return
        if self._update_busy():
            self.say("@updates.busy")
            return
        if self.update_state.get("phase") == "available":
            self.overlay = None
            self.offer_update(force=True)
        elif self.on_update_check and not self._dry("@updates.check"):
            self.on_update_check()
        elif not self.on_update_check:
            self.say("@updates.unconfigured")

    def offer_update(self, force=False):
        """Offer once per session when the launcher is free; confirmation remains a separate action."""
        version = self.update_state.get("version", "")
        if (self.update_state.get("phase") != "available" or not version or self.overlay or self._update_busy()
                or (not force and self.update_offered == version)):
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
