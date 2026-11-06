"""The launcher's own Settings page (0.1.5): separate from every game's Settings. Reached from the game shelf (RB / E, or
the top bar's Launcher settings) and from Quick access. Language, window, start with Windows, button prompts, menu
sounds, update channel and "check now", the data folder, uninstall and About. No Qt.

It is a screen of its own ("launcher"): the same grouped page the game Settings use (settingsPage), but the rows belong
to the launcher. The app wires `on_launcher(action, value)`; without it the rows that need the app are left out."""
from . import __version__, i18n, ui_sound
from .launcher_prefs import PROMPT_STYLES

RELEASES_URL = "https://github.com/TheWishin/OpenRecomp-FGC/releases"
TABS = ("general", "audio", "updates", "data", "about")
TAB_LABELS = {"general": "@launcher_settings.tab.general", "audio": "@launcher_settings.tab.audio",
              "updates": "@launcher_settings.tab.updates", "data": "@launcher_settings.tab.data",
              "about": "@launcher_settings.tab.about"}
STYLE_LABELS = {"auto": "@auto", "xbox": "@launcher_settings.prompts.xbox",
                "ps": "@launcher_settings.prompts.ps", "kb": "@launcher_settings.prompts.kb"}


class LauncherSettings:
    # ---- entry and exit
    def open_launcher_settings(self):
        """From the shelf or Quick access. The page remembers where to go back to."""
        self.overlay = None
        if self.screen == "launcher":
            return
        self._cancel_hold()
        self.launcher_back = self.screen
        self.screen = "launcher"
        self.launcher_focus = getattr(self, "launcher_focus", 0)
        self.launcher_refresh()

    def close_launcher_settings(self):
        back = getattr(self, "launcher_back", "start")
        self.screen = back if back in ("start", "hub") else "start"
        if self.screen == "hub" and self.game is None:
            self.screen = "start"

    def launcher_refresh(self):
        """Ask the app what it knows now (start with Windows, the data folder)."""
        on_launcher = getattr(self, "on_launcher", None)
        self.launcher_info = dict(on_launcher("get", None) or {}) if on_launcher else {}

    def _launcher_call(self, action, value=None):
        on_launcher = getattr(self, "on_launcher", None)
        return on_launcher(action, value) if on_launcher else None

    # ---- rows
    def _launcher_items(self):
        info = getattr(self, "launcher_info", None) or {}
        rows = []

        def cycler(rid, tab, label, hint, options, current, setter):
            value = next((caption for option, caption in options if type(option) is type(current) and option == current), "")
            rows.append(dict(kind="cycler", id=rid, tab=tab, label=label, value=value, options=options, current=current,
                             set=setter, hint=hint, detail=dict(kicker=TAB_LABELS[tab], title=label, lead=hint, rows=[])))

        def action(rid, tab, label, hint, run, verb="@open", value="", detail_rows=()):
            rows.append(dict(kind="action", id=rid, tab=tab, label=label, value=value, verb=verb, hint=hint, run=run,
                             detail=dict(kicker=TAB_LABELS[tab], title=label, lead=hint, rows=list(detail_rows))))

        languages = [(code, "@language." + code) for code in i18n.LANGUAGES]
        cycler("language", "general", "@language", "@language_hint", languages, self.language, self._launcher_language)
        cycler("display", "general", "@launcher_settings.display", "@launcher_settings.display_hint",
               [(True, "@fullscreen"), (False, "@windowed")], bool(self.fullscreen), self._launcher_display)
        if info.get("startup") is not None:
            cycler("startup", "general", "@launcher_settings.startup", "@launcher_settings.startup_hint",
                   [(False, "@off"), (True, "@on")], bool(info["startup"]), self._launcher_startup)
        style = getattr(self, "prompt_style", "auto")
        style = style if style in PROMPT_STYLES else "auto"
        cycler("prompts", "general", "@launcher_settings.prompts", "@launcher_settings.prompts_hint",
               [(s, STYLE_LABELS[s]) for s in PROMPT_STYLES], style, self._launcher_prompts)
        if getattr(self, "on_ui_sound", None) is not None:
            percent = {v: i18n.message("ui_sound.percent", value=v) for v in ui_sound.VOLUMES}
            cycler("ui_sounds", "audio", "@ui_sound.label", "@ui_sound.hint", [(False, "@off"), (True, "@on")],
                   bool(self.ui_sounds), self._set_ui_sounds)
            cycler("ui_sound_volume", "audio", "@ui_sound.volume", "@ui_sound.volume_hint",
                   [(v, percent[v]) for v in ui_sound.VOLUMES], self.ui_sound_volume, self._set_ui_sound_volume)
        if getattr(self, "on_setup", None) is not None:
            cycler("channel", "updates", "@launcher_settings.channel", "@launcher_settings.channel_hint",
                   [(False, "@launcher_settings.channel.stable"), (True, "@launcher_settings.channel.test")],
                   bool(self.game_prereleases), self._settings_prereleases)
        if getattr(self, "on_update_check", None) is not None:
            version = (getattr(self, "update_state", None) or {}).get("version", "")
            action("check_now", "updates", "@updates.check", "@updates.hint", self._check_update, verb="@confirm",
                   value=i18n.literal(version) if version else "")
        if getattr(self, "on_setup", None) is not None:
            action("check_games", "updates", "@setup.check", "@setup.check_hint", self.setup_check_manual, verb="@confirm")
        folder = info.get("data_dir", "")
        if getattr(self, "on_launcher", None) is not None and folder:
            action("data_dir", "data", "@launcher_settings.data", "@launcher_settings.data_hint", self._launcher_open_data,
                   verb="@launcher_settings.open_folder",
                   detail_rows=[dict(k="@folder", v=i18n.literal(folder))])      # a long path reads better in the panel
        if getattr(self, "on_uninstall", None) is not None:
            action("uninstall_all", "data", "@uninstall.title", "@uninstall.hint", self.uninstall_ask)
        action("version", "about", "@version", "@launcher_settings.version_hint", self._launcher_copy_version,
               verb="@launcher_settings.copy", value=i18n.literal(__version__))
        action("releases", "about", "@launcher_settings.releases", "@launcher_settings.releases_hint",
               lambda: self._launcher_url(RELEASES_URL))
        action("discord", "about", "@community.discord", "@community.hint", self.open_discord)
        return rows

    def _launcher_language(self, code):
        self._settings_language(code)

    def _launcher_display(self, full):
        self.fullscreen = bool(full)
        self.on_preferences(self.fullscreen, self.reduced_motion)

    def _launcher_startup(self, on):
        if self._dry("@launcher_settings.startup"):
            return
        if self._launcher_call("startup", bool(on)):
            self.launcher_refresh()
        else:
            self.hint_sound(ui_sound.ERROR)
            self.say("@launcher_settings.startup_failed", 8)

    def _launcher_prompts(self, style):
        self.prompt_style = style if style in PROMPT_STYLES else "auto"
        self._launcher_call("prompt_style", self.prompt_style)

    def _launcher_open_data(self):
        if self._dry("@launcher_settings.data"):
            return
        if not self._launcher_call("open_data", None):
            self.say("@launcher_settings.open_failed", 8)

    def _launcher_copy_version(self):
        self.copy_text(__version__)
        if not self.dry:
            self.say("@launcher_settings.copied")

    def _launcher_url(self, url):
        if self._dry("@launcher_settings.releases"):
            return
        self.pending_url = url
        self.say("@community.opening")

    # ---- input
    def _launcher_index(self, items):
        self.launcher_focus = max(0, min(len(items) - 1, getattr(self, "launcher_focus", 0)))
        return self.launcher_focus

    def _launcher_tab_jump(self, items, step):
        tabs = [t for t in TABS if any(it["tab"] == t for it in items)]
        pos = tabs.index(items[self._launcher_index(items)]["tab"])
        self.launcher_focus = next(n for n, it in enumerate(items) if it["tab"] == tabs[(pos + step) % len(tabs)])

    def _launcher(self, a):
        items = self._launcher_items()
        i = self._launcher_index(items)
        it = items[i]
        if a == "up":
            self.launcher_focus = max(0, i - 1)
        elif a == "down":
            self.launcher_focus = min(len(items) - 1, i + 1)
        elif a == "prev":
            self._launcher_tab_jump(items, -1)
        elif a == "next":
            self._launcher_tab_jump(items, 1)
        elif a in ("back", "home", "launcherSettings"):
            self.close_launcher_settings()
        elif a in ("left", "right") and it["kind"] == "cycler":
            self._cycle(it, 1 if a == "right" else -1)
        elif a == "confirm":
            self._activate(it)
        elif a == "social":
            self.overlay = "drawer"
            self.drawer_focus = min(self.drawer_focus, len(self._drawer_items()) - 1)
        # "play", "x" and "switchGame" mean nothing on this page

    def select_launcher_tab(self, tab):
        items = self._launcher_items()
        target = next((n for n, it in enumerate(items) if it["tab"] == tab), None)
        if target is not None:
            self.launcher_focus = target

    def click_launcher_row(self, index):
        items = self._launcher_items()
        if self.overlay or not 0 <= index < len(items):
            return
        self._cancel_hold()
        self.launcher_focus = index
        self._guard(self._activate, items[index])

    # ---- view
    def _view_launcher(self, v):
        items = self._launcher_items()
        fi = self._launcher_index(items)
        it = items[fi]
        lines = []
        for n, row in enumerate(items):
            cycler = row["kind"] == "cycler"
            lines.append(dict(kind="setting", index=n, label=row["label"], value=row.get("value") or "",
                              hint=row.get("hint", "") if n == fi else "", focused=n == fi, cycler=cycler,
                              disabled=False, group=row["tab"], verb=row.get("verb", "") if n == fi and not cycler else ""))
        options = [dict(label=label, current=type(value) is type(it.get("current")) and value == it.get("current"))
                   for value, label in it.get("options") or []] if it["kind"] == "cycler" else []
        d = it["detail"]
        tabs = [t for t in TABS if any(row["tab"] == t for row in items)]
        v["screen"] = "hub"
        v["gameShort"] = "@launcher_settings.crumb"
        v["numeral"], v["badge"], v["topline"], v["hero"] = "", "", "", ""
        v["mainMenu"] = dict(show=False, available=True, homeLabel="@back")
        v["tabs"] = [dict(id="launcher", label="@launcher_settings.title", active=True)]
        v["settingsPage"] = dict(
            layout="groups", adapterEmptyHint="", lines=lines, up=False, down=False, groups=[],
            activeTab=it["tab"], optionLabel="@settings_ui.available_options",
            tabs=[dict(id=t, label=TAB_LABELS[t], active=t == it["tab"]) for t in tabs],
            tabLines=[line for line in lines if line["group"] == it["tab"]],
            detail=dict(kicker=d["kicker"], title=d["title"], lead=d["lead"], value=it.get("value") or "",
                        options=options[:12], rows=[dict(k=r["k"], v=r["v"]) for r in d.get("rows", [])][:6]))
        v["hint"] = it.get("hint", "")
        prompts = []
        if it["kind"] == "cycler":
            prompts += [self.prompt("confirm", "@change"), self.prompt("right", "@change")]
        elif it.get("verb"):
            prompts.append(self.prompt("confirm", it["verb"]))
        prompts += [self.prompt("next", "@launcher_settings.page"), self.prompt("social", "@quick_access"),
                    self.prompt("back", "@back")]
        v["prompts"] = prompts
        v["accent"] = "#ECE9E1"
