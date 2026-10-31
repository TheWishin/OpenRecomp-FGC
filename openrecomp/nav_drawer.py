"""Quick access drawer actions and view."""
from . import i18n


class Drawer:
    def _drawer_items(self):
        out = [dict(label="@language", value="@language." + self.language, language=True, hint="@language_hint"),
               dict(label="@display_mode", value="@fullscreen" if self.fullscreen else "@windowed", fullscreen=True, hint="@display_mode_hint"),
               dict(label="@motion", value="@motion_reduced" if self.reduced_motion else "@motion_full", motion=True, hint="@motion_hint")]
        phase = self.update_state.get("phase", "idle")
        update_hint = {"checking": "@updates.checking", "installing": "@updates.installing", "current": "@updates.current",
                       "waiting": "@updates.waiting", "unconfigured": "@updates.unconfigured", "error": "@updates.failed"}.get(phase, "@updates.hint")
        out.append(dict(label="@updates.check", value=self.update_state.get("version", ""), update=True, hint=update_hint))
        for g in self.games:
            if g.a.found() and g.a.native_label:
                out.append(dict(label=g.a.native_label, value=g.short, game=g, hint=i18n.message("native_hint", name=g.a.native_label)))
        return out

    def _drawer(self, a):
        items = self._drawer_items()
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
            g = items[self.drawer_focus].get("game")
            if g and not self._dry(i18n.message("dry_open", name=g.a.native_label)):
                g.a.open_native()
                self.overlay = None
                self.say(i18n.message("opening", name=g.a.native_label))

    def _drawer_cycle(self, item, step):
        if item.get("language"):
            self._cycle_language(step)
        elif item.get("fullscreen") or item.get("motion"):
            if self._dry(i18n.message("dry_change", name=item["label"])):
                return True
            if item.get("fullscreen"):
                self.fullscreen = not self.fullscreen
            else:
                self.reduced_motion = not self.reduced_motion
            self.on_preferences(self.fullscreen, self.reduced_motion)
        else:
            return False
        return True

    def _cycle_language(self, step):
        if self._dry(i18n.message("dry_change", name="@language")):
            return
        codes = i18n.LANGUAGES
        self.language = codes[(codes.index(self.language) + step) % len(codes)]
        self.on_language(self.language)

    def _update_busy(self):
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
        return True

    def _view_drawer(self, v):
        items = self._drawer_items()
        v["drawer"] = dict(rows=[dict(index=i, label=it["label"], value=it["value"], focused=i == self.drawer_focus) for i, it in enumerate(items)])
        item = items[self.drawer_focus]
        cycler = item.get("language") or item.get("fullscreen") or item.get("motion")
        v["hint"] = item["hint"]
        v["prompts"] = [self.prompt("confirm", "@change" if cycler else "@open")]
        if cycler:
            v["prompts"].append(self.prompt("right", "@change"))
        v["prompts"].append(self.prompt("back", "@close"))
