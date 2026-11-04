"""Install a game from the launcher (T5DR Online, T4) and update it: rows, dialogs and the tile's badge.

`setup_state` comes from the backend's GameSetup every tick ({gid: view}); `on_setup(action, gid, arg)` asks it
to work: "check", "install" (arg = parent folder), "update", "cancel", "restart", "space" (arg = parent folder;
returns the space dict at once).
"""
import os

from . import i18n

SETUP_GAMES = ("t5dr", "t4")
STEP_TEXT = {"download": "@setup.step_download", "unpack": "@setup.step_unpack", "swap": "@setup.step_swap"}


class GameSetupNav:
    def _setup(self, gid):
        return (getattr(self, "setup_state", None) or {}).get(gid) or {}

    def _setup_supported(self, g):
        return g is not None and g.m.get("adapter") in SETUP_GAMES and getattr(self, "on_setup", None) is not None

    def setup_update_needed(self, g):
        st = self._setup(g.id) if self._setup_supported(g) else {}
        return bool(g.a.found() and (st.get("required") or st.get("available")))

    def _mb(self, n):
        return max(1, int(n or 0) // 1_000_000)

    def _gb(self, n):
        """Free space and the build's need read in GB ("1673464 MB" was hard to read): one decimal."""
        return i18n.literal(str(round(max(0, int(n or 0)) / 1_000_000_000, 1)))

    # ------------------------------------------------------------------------------------------ rows
    def _setup_items(self, g, section):
        """Rows at the top of a game's Play / Online / Build section."""
        if not self._setup_supported(g):
            return []
        st = self._setup(g.id)
        if not g.a.found():
            from .game_releases import SOURCES
            if section == "online":
                return []
            busy = st.get("phase") == "installing"
            label = "@setup.install_t5dr" if g.id == "t5dr" else "@setup.install_t4"
            return [dict(kind="action", id="game_setup", label=label, verb="@setup.install",
                         value=self._setup_progress_text(st) if busy else "",
                         run=lambda: self.setup_begin(g), hint="@setup.install_hint",
                         detail=dict(kicker="@setup.kicker", title=label, lead="@setup.install_lead", rows=[
                             dict(k="@setup.source", v=i18n.literal(SOURCES[g.id].repository)),
                             dict(k="@setup.channel", v="@setup.channel_test" if self._prereleases() else "@setup.channel_stable")],
                             primary="@setup.install"))]
        if not (st.get("required") or st.get("available")) and st.get("phase") not in ("updating", "updated"):
            return []
        if st.get("phase") == "updated":
            return [dict(kind="action", id="game_update", label="@setup.updated_restart" if st.get("restart") else "@setup.updated",
                         verb="@setup.restart" if st.get("restart") else "", value=i18n.literal(st.get("installed", "")),
                         run=(lambda: self._ask("setup_restart")) if st.get("restart") else None,
                         hint="@setup.restart_hint" if st.get("restart") else ("@setup.rebuild_hint" if st.get("rebuild") else "@setup.updated_hint"),
                         detail=dict(kicker="@setup.kicker", title="@setup.updated", lead="@setup.restart_hint", rows=[]))]
        label = "@setup.update_needed" if st.get("required") else "@setup.update_available"
        version = i18n.literal(f"{st.get('installed') or '?'} → {st.get('latest') or '?'}")
        return [dict(kind="action", id="game_update", label=label, verb="@setup.update", value=version,
                     run=lambda: self.setup_offer_update(g),
                     hint="@setup.update_needed_hint" if st.get("required") else "@setup.update_hint",
                     detail=dict(kicker="@setup.kicker", title=label, lead="@setup.update_lead",
                                 rows=[dict(k="@version", v=version),
                                       dict(k="@setup.download", v=i18n.message("setup.megabytes", mb=self._mb(st.get("size"))))],
                                 primary="@setup.update"))]

    def _setup_progress_text(self, st):
        step = STEP_TEXT.get(st.get("step"), STEP_TEXT["download"])
        if st.get("total"):
            pct = min(100, int(st.get("done", 0) * 100 / max(1, st["total"])))
            return i18n.message("setup.progress", step=step, percent=pct)
        return step

    def _prereleases(self):
        return bool(getattr(self, "game_prereleases", False))

    # ------------------------------------------------------------------------------------------ flow
    def setup_begin(self, g):
        """Install: look up the newest release, then ask where."""
        if self._dry("@setup.install"):
            return
        if self._update_busy() or self._setup(g.id).get("phase") in ("installing", "updating"):
            self.say("@setup.busy")
            return
        self.setup_game = g.id
        self.setup_parent = getattr(self, "setup_parent", "") or ""
        st = self._setup(g.id)
        if st.get("phase") == "ready" and st.get("latest"):
            self._setup_where(g.id)
        else:
            self.setup_waiting = True
            self.on_setup("check", g.id, True)
            self._ask("setup_loading")

    def _setup_where(self, gid):
        st = self._setup(gid)
        if not st.get("latest"):
            self._ask("setup_none")
            return
        if not self.setup_parent:
            self.setup_parent = self.on_setup("default_parent", gid, None) or ""
        self.setup_space = self.on_setup("space", gid, self.setup_parent) or {}
        self._ask("setup_install")

    def setup_offer_update(self, g):
        if self._dry("@setup.update"):
            return
        if self._update_busy() or self._setup(g.id).get("phase") in ("installing", "updating", "checking"):
            self.say("@setup.busy")
            return
        self.setup_game = g.id
        self._ask("setup_update")

    def setup_reinstall(self, g):
        """Repair this install in place, using the same protected-file exchange as an update."""
        if self._dry("@t5.reinstall"):
            return
        st = self._setup(g.id)
        if self._update_busy() or st.get("phase") in ("installing", "updating"):
            self.say("@setup.busy")
            return
        self.setup_game = g.id
        if st.get("latest") and st.get("phase") == "ready":
            self._setup_reinstall_start(g.id)
            return
        self.setup_waiting = True
        self.setup_reinstall_waiting = True
        if st.get("phase") != "checking" and not self.on_setup("check", g.id, True):
            self.setup_waiting = self.setup_reinstall_waiting = False
            self.say("@setup.busy")
            return
        self._ask("setup_loading")

    def _setup_reinstall_start(self, gid):
        if not self._setup(gid).get("latest"):
            self._ask("setup_none")
        elif self._update_busy() or not self.on_setup("reinstall", gid, None):
            self.overlay = None
            self.say("@setup.busy")
        else:
            self.setup_cancelling = False
            self._ask("setup_progress")

    def poll_setup(self, finished):
        """Called by the backend with GameSetup.poll()'s events. -> True when the screen changed."""
        changed = False
        for gid, kind, result, error in finished:
            changed = True
            if kind == "check" and getattr(self, "setup_waiting", False) and getattr(self, "setup_game", "") == gid:
                self.setup_waiting = False
                reinstall = getattr(self, "setup_reinstall_waiting", False)
                self.setup_reinstall_waiting = False
                if self.overlay == "dialog" and self.confirm_kind == "setup_loading":
                    if error:
                        self.overlay = None
                        self.say(error[0], 10)
                    elif reinstall:
                        self._setup_reinstall_start(gid)
                    else:
                        self._setup_where(gid)
            elif kind == "install":
                self.setup_cancelling = False
                if self.overlay == "dialog" and self.confirm_kind == "setup_progress":
                    self.overlay = None
                if error:
                    self.say(error[0], 12)
                else:
                    self.on_setup("attach", gid, result)
            elif kind == "update":
                self.setup_cancelling = False
                if self.overlay == "dialog" and self.confirm_kind == "setup_progress":
                    self.overlay = None
                if error:
                    self.say(error[0], 12)
                elif result.get("restart"):
                    self._ask("setup_restart")
                else:
                    self.on_setup("reload", gid, result)
                    self.say("@setup.rebuild_hint" if result.get("rebuild") else "@setup.updated_hint", 12)
        if self.overlay == "dialog" and self.confirm_kind == "setup_progress":
            changed = True
        return changed

    def setup_installed(self, gid):
        """After the launcher attached the new install: straight to the game's Build section."""
        g = self.game_by_id(gid)
        if g is None or not g.a.found():
            return
        self._select_game(g)
        self.screen = "hub"
        if "build" in self.sections(g):
            self.sec[g.id] = "build"
            self.focus[g.id + ":build"] = 0
        self.say("@setup.next_t5dr" if gid == "t5dr" else "@setup.next_t4", 15)

    # ------------------------------------------------------------------------------------------ dialogs
    def _setup_dialog(self, a):
        kind = self.confirm_kind
        count = 1 if kind in ("setup_loading", "setup_progress") or kind == "setup_none" and not self._setup_none_folder() else 2
        if a in ("left", "right", "up", "down"):
            self.exit_focus = (self.exit_focus + 1) % count
            return
        gid = getattr(self, "setup_game", "")
        if kind == "setup_progress":
            if a in ("back", "confirm"):
                # The dialog stays until the worker has stopped: no build, Play or quit against files being
                # replaced (poll_setup closes it with the worker's result).
                if self._setup(gid).get("phase") not in ("installing", "updating"):
                    self.overlay = None
                elif not getattr(self, "setup_cancelling", False):
                    self.setup_cancelling = True
                    self.on_setup("cancel", gid, None)
                    self.say("@setup.cancelling")
            return
        if a == "back":
            if kind == "setup_loading":
                self.setup_waiting = self.setup_reinstall_waiting = False
            self.overlay = None
            return
        if a != "confirm":
            return
        yes = self.exit_focus == 1
        if kind in ("setup_loading", "setup_none"):
            self.setup_waiting = False
            self.setup_reinstall_waiting = False
            self.overlay = None
            source = self._setup_none_folder() if kind == "setup_none" and yes else None
            if source:              # nothing published yet: the folder the player already has
                self._open_source_picker(source, source.get("title") or "@onboarding.choose_folder")
        elif kind == "setup_install":
            if not yes:
                self.overlay = None
                self._open_picker("setup_folder", "@setup.choose_folder", [], [self.setup_parent, os.path.expanduser("~")], "folder")
            elif (self.setup_space or {}).get("problem"):
                self.say(self.setup_space["problem"], 10)
            elif self.on_setup("install", gid, self.setup_parent):
                self.setup_cancelling = False
                self._ask("setup_progress")
            else:
                self.overlay = None
                self.say("@setup.busy")
        elif kind == "setup_update":
            self.overlay = None
            if yes:
                if self._update_busy():
                    self.say("@setup.busy")
                elif self.on_setup("update", gid, None):
                    self.setup_cancelling = False
                    self._ask("setup_progress")
                else:
                    self.say("@setup.busy")
        elif kind == "setup_restart":
            self.overlay = None
            if yes:
                self.on_setup("restart", gid, None)

    def _setup_none_folder(self):
        """No release to install: the game's own "choose your game folder" row, when it has one."""
        g = self.game_by_id(getattr(self, "setup_game", ""))
        return self._folder_source(g) if g is not None else None

    def setup_folder_picked(self, path):
        self.setup_parent = path
        self._setup_where(self.setup_game)

    def _view_setup_dialog(self, v):
        from .game_releases import SOURCES
        kind = self.confirm_kind
        gid = getattr(self, "setup_game", "")
        st = self._setup(gid)
        name = i18n.literal(SOURCES[gid].title if gid in SOURCES else gid)
        title, text, labels = "@setup.kicker", "", ["@cancel"]
        offer = st.get("offer") or {}
        if kind == "setup_loading":
            text = "@setup.looking"
        elif kind == "setup_none":
            source = self._setup_none_folder()
            if source:
                text = i18n.message("setup.not_published", name=name)
                labels = ["@close", source.get("title") or "@onboarding.choose_folder"]
            else:
                text = "@setup.none_stable" if not self._prereleases() else "@setup.none_any"
                labels = ["@close"]
        elif kind == "setup_install":
            space = self.setup_space or {}
            title = "@setup.install_t5dr" if gid == "t5dr" else "@setup.install_t4"
            text = i18n.message("setup.install_text", name=name, version=i18n.literal(offer.get("version", "")),
                                mb=self._mb(offer.get("size")), folder=i18n.literal(space.get("target", "")),
                                need=self._gb(space.get("need")), free=self._gb(space.get("free")))
            if offer.get("prerelease"):
                text = i18n.message("setup.test_version", text=text)
            if space.get("problem"):
                text = i18n.message("setup.problem", text=text, problem=space["problem"])
            labels = ["@setup.other_folder", "@setup.install_here"]
        elif kind == "setup_progress":
            title = "@setup.working"
            progress = "@setup.cancelling" if getattr(self, "setup_cancelling", False) else self._setup_progress_text(st)
            text = i18n.message("setup.progress_text", name=name, progress=progress)
            labels = ["@cancel"]
        elif kind == "setup_update":
            title = "@setup.update"
            text = i18n.message("setup.update_text", name=name, old=i18n.literal(st.get("installed") or "?"),
                                new=i18n.literal(st.get("latest", "")), mb=self._mb(st.get("size")),
                                notes=i18n.literal(str(offer.get("notes", ""))[:300]))
            labels = ["@no", "@setup.update"]
        elif kind == "setup_restart":
            title = "@setup.updated"
            text = i18n.message("setup.restart_text", name=name, version=i18n.literal(st.get("installed", "")))
            labels = ["@setup.later", "@setup.restart"]
        self.exit_focus = min(self.exit_focus, len(labels) - 1)
        v["dialog"] = dict(title=title, text=text, options=[dict(label=label, index=index, focused=self.exit_focus == index)
                                                          for index, label in enumerate(labels)])
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("back", "@cancel")]
        if len(labels) > 1:
            v["prompts"].insert(1, self.prompt("right", "@switch"))
