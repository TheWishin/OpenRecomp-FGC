"""Install a game from the launcher (T5DR Online, T4) and update it: rows, dialogs and the tile's badge.

`setup_state` comes from the backend's GameSetup every tick ({gid: view}); `on_setup(action, gid, arg)` asks it
to work: "check", "install" (arg = parent folder), "update", "cancel", "restart", "space" (arg = parent folder;
returns the space dict at once).
"""
import os

from . import i18n

SETUP_GAMES = ("t5dr", "t4")
STEP_TEXT = {"download": "@setup.step_download", "check": "@setup.step_check", "unpack": "@setup.step_unpack",
             "swap": "@setup.step_swap"}


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
        if not g.a.found() and g.a.setup_root() and st.get("phase") != "updated":
            label = "@t5.update_here"
            return [dict(kind="action", id="game_update", label=label, verb="@setup.update",
                         value=self._setup_progress_text(st) if st.get("phase") == "updating" else "",
                         run=lambda: self.setup_offer_update(g), hint="@t5.folder_old",
                         detail=dict(kicker="@setup.kicker", title=label, lead="@t5.folder_old",
                                     rows=[dict(k="@game_folder", v=i18n.literal(g.a.setup_root()))], primary=label))]
        if not g.a.found() and not g.a.setup_root():
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
        # A folder without a version marker (own copy, old bundle): "own version", never "?" (0.1.4)
        installed = st.get("installed") or i18n.message("setup.own_version")
        version = i18n.message("setup.version_arrow", old=installed, new=i18n.literal(st.get("latest") or ""))
        if st.get("needs_launcher"):
            # 0.1.4: this release needs a newer launcher -- say so (never a "damaged zip" later) and offer Update all
            text = i18n.message("setup.needs_launcher_row", launcher=i18n.literal(st["needs_launcher"]))
            return [dict(kind="action", id="game_update", label="@setup.update_available", verb="@setup.update_all",
                         value=version, run=lambda: self._ask_needs_launcher(g.id), hint=text,
                         detail=dict(kicker="@setup.kicker", title="@setup.update_available", lead=text,
                                     rows=[dict(k="@version", v=version)], primary="@setup.update_all"))]
        label = "@setup.update_needed" if st.get("required") else "@setup.update_available"
        hint = "@setup.update_needed_hint" if st.get("required") else "@setup.update_hint"
        folder = getattr(g.a, "root", None) or ""
        return [dict(kind="action", id="game_update", label=label, verb="@setup.update", value=version,
                     run=lambda: self.setup_offer_update(g),
                     hint=i18n.message("setup.update_in_folder", text=hint, folder=i18n.literal(folder)) if folder else hint,
                     detail=dict(kicker="@setup.kicker", title=label, lead="@setup.update_lead",
                                 rows=[dict(k="@version", v=version)] + ([dict(k="@game_folder", v=i18n.literal(folder))] if folder else []) + [
                                       dict(k="@setup.download", v=i18n.message("setup.megabytes", mb=self._mb(st.get("size"))))],
                                 primary="@setup.update"))]

    def _setup_progress_text(self, st):
        """"Download 45 % · 120 of 274 MB · 8.3 MB/s · 19 s left" (0.1.4); steps without a size: their name."""
        step = STEP_TEXT.get(st.get("step"), STEP_TEXT["download"])
        if st.get("total"):
            pct = min(100, int(st.get("done", 0) * 100 / max(1, st["total"])))
            text = i18n.message("setup.progress_mb", step=step, percent=pct, done=self._mb(st.get("done")),
                                total=self._mb(st.get("total")))
            if st.get("speed"):
                text = i18n.message("setup.progress_speed", text=text,
                                    speed=i18n.literal(f"{st['speed'] / 1_000_000:.1f}"))
            if st.get("left"):
                left = int(st["left"])
                left_text = (i18n.message("setup.time_min_s", min=left // 60, sec=left % 60) if left >= 60
                             else i18n.message("setup.time_s", sec=left))
                text = i18n.message("setup.progress_left", text=text, left=left_text)
            return text
        return step

    def _ask_needs_launcher(self, gid):
        self.setup_game = gid
        self._ask("setup_needs_launcher")

    def _prereleases(self):
        return bool(getattr(self, "game_prereleases", False))

    # ------------------------------------------------------------------------------------------ flow
    def setup_begin(self, g):
        """Install: look up the newest release, then ask where."""
        if self._dry("@setup.install"):
            return
        if self._update_busy(allow_lobby=True) or self._setup(g.id).get("phase") in ("installing", "updating"):
            self.say("@setup.busy")
            return
        self.setup_game = g.id
        self.setup_parent = getattr(self, "setup_parent", "") or ""
        self.setup_new_roots = set()
        if self._setup_existing(g.id):
            return
        self._setup_begin_release(g.id)

    def _setup_existing(self, gid):
        g = self.game_by_id(gid)
        declined = getattr(self, "setup_new_roots", set())
        roots = g.a.existing_installs(getattr(self, "setup_parent", "")) if g is not None else []
        roots = [root for root in roots if root not in declined]
        if not roots:
            return False
        self.setup_existing_root = roots[0]
        self._ask("setup_existing")
        return True

    def _setup_begin_release(self, gid):
        st = self._setup(gid)
        if st.get("phase") == "ready" and st.get("latest"):
            self._setup_where(gid)
        else:
            self.setup_waiting = True
            self.on_setup("check", gid, True)
            self._ask("setup_loading")

    def _setup_where(self, gid):
        st = self._setup(gid)
        if not st.get("latest"):
            self._ask("setup_none")
            return
        if not self.setup_parent:
            self.setup_parent = self.on_setup("default_parent", gid, None) or ""
        if self._setup_existing(gid):
            return
        if st.get("needs_launcher"):
            self._ask_needs_launcher(gid)
            return
        self.setup_space = self.on_setup("space", gid, self.setup_parent) or {}
        self._ask("setup_install")

    def setup_offer_update(self, g):
        if self._dry("@setup.update"):
            return
        if self._update_busy(allow_lobby=True) or self._setup(g.id).get("phase") in ("installing", "updating"):
            self.say("@setup.busy")
            return
        self.setup_game = g.id
        st = self._setup(g.id)
        if st.get("phase") != "ready" or not st.get("latest"):
            self.setup_waiting = self.setup_update_waiting = True
            if st.get("phase") != "checking" and not self.on_setup("check", g.id, True):
                self.setup_waiting = self.setup_update_waiting = False
                self.say("@setup.busy")
                return
            self._ask("setup_loading")
            return
        self._ask("setup_needs_launcher" if st.get("needs_launcher") else "setup_update")

    def setup_reinstall(self, g):
        """Repair this install in place, using the same protected-file exchange as an update."""
        if self._dry("@t5.reinstall"):
            return
        st = self._setup(g.id)
        if self._update_busy(allow_lobby=True) or st.get("phase") in ("installing", "updating"):
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
        elif self._update_busy(allow_lobby=True) or not self.on_setup("reinstall", gid, None):
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
                update = getattr(self, "setup_update_waiting", False)
                self.setup_update_waiting = False
                if self.overlay == "dialog" and self.confirm_kind == "setup_loading":
                    if error:
                        self.overlay = None
                        self.say(error[0], 10)
                    elif reinstall:
                        self._setup_reinstall_start(gid)
                    elif update:
                        st = self._setup(gid)
                        self._ask(("setup_needs_launcher" if st.get("needs_launcher") else "setup_update")
                                  if st.get("latest") else "setup_none")
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
        if g is None or not (g.a.found() or g.a.setup_root()):
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
                self.setup_waiting = self.setup_reinstall_waiting = self.setup_update_waiting = False
            self.overlay = None
            return
        if a != "confirm":
            return
        yes = self.exit_focus == 1
        if kind == "setup_existing":
            if not yes:
                self.overlay = None
                if self.on_setup("use_existing", gid, self.setup_existing_root):
                    self.say(i18n.message("t5.folder_taken", folder=i18n.literal(self.setup_existing_root)), 15)
            else:
                self.setup_new_roots.add(self.setup_existing_root)
                if not self._setup_existing(gid):
                    self._setup_begin_release(gid)
        elif kind in ("setup_loading", "setup_none"):
            self.setup_waiting = False
            self.setup_reinstall_waiting = False
            self.setup_update_waiting = False
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
            elif self._setup_existing(gid):
                return
            elif not self.on_setup("allow_new", gid, sorted(getattr(self, "setup_new_roots", set()))):
                self.say("@setup.busy")
            elif self.on_setup("install", gid, self.setup_parent):
                self.setup_cancelling = False
                self._ask("setup_progress")
            else:
                self.overlay = None
                self.say("@setup.busy")
        elif kind == "setup_update":
            self.overlay = None
            if yes:
                if self._update_busy(allow_lobby=True):
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
        elif kind == "setup_needs_launcher":
            self.overlay = None
            if yes:
                need = self._setup(gid).get("needs_launcher", "")
                if self._update_busy():                 # the launcher restarts: not while in a lobby
                    self.say("@setup.busy")
                elif self.on_setup("update_all", gid, need):
                    self.say("@setup.updating_launcher", 15)
                else:
                    self.say("@updates.busy")

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
        if kind == "setup_existing":
            title = "@setup.install_t5dr"
            text = i18n.message("t5.existing_prompt", folder=i18n.literal(self.setup_existing_root))
            labels = ["@t5.existing_use", "@t5.existing_new"]
        elif kind == "setup_loading":
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
            if space.get("long") and not space.get("problem"):
                text = i18n.message("setup.long_path", text=text)
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
            text = i18n.message("setup.update_text", name=name,
                                old=i18n.literal(st["installed"]) if st.get("installed") else i18n.message("setup.own_version"),
                                new=i18n.literal(st.get("latest", "")), mb=self._mb(st.get("size")),
                                notes=i18n.literal(str(offer.get("notes", ""))[:300]))
            labels = ["@no", "@setup.update"]
            game = self.game_by_id(gid)
            if game is not None and not game.a.found() and game.a.setup_root():
                title = "@t5.update_here"
                text = i18n.message("t5.folder_update", text=text, folder=i18n.literal(game.a.setup_root()))
                labels = ["@cancel", "@t5.update_here"]
            elif game is not None and getattr(game.a, "root", None):
                # 0.1.3: which install is updated (a player can have several)
                text = i18n.message("setup.update_in_folder", text=text, folder=i18n.literal(game.a.root))
        elif kind == "setup_needs_launcher":
            title = "@setup.needs_launcher_title"
            text = i18n.message("setup.needs_launcher_text", name=name, version=i18n.literal(st.get("latest", "")),
                                launcher=i18n.literal(st.get("needs_launcher", "")),
                                current=i18n.literal(st.get("launcher")) if st.get("launcher") else i18n.message("setup.own_version"))
            labels = ["@cancel", "@setup.update_all"]
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
