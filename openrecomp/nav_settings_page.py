"""The Settings section as grouped cards: Display & graphics, Controls, Online, Audio, Offline & training, Replays,
Updates, Advanced. No Qt. The rows stay the adapter's own settings (same ids, same setters); this module only sorts
them into groups, adds the group headings and the launcher's update rows, and builds the page's view."""
from . import i18n, ui_sound

GROUPS = ("display", "controls", "online", "audio", "offline", "replays", "updates", "advanced")
GROUP_LABELS = {"display": "@settings_ui.group.display", "controls": "@settings_ui.group.controls",
                "online": "@settings_ui.group.online", "audio": "@settings_ui.group.audio",
                "offline": "@settings_ui.group.offline", "replays": "@settings_ui.group.replays",
                "updates": "@settings_ui.group.updates", "advanced": "@settings_ui.group.advanced"}
GROUP_NOTES = {"display": "@settings_ui.note.display", "controls": "@settings_ui.note.controls",
               "online": "@settings_ui.note.online", "audio": "@settings_ui.note.audio",
               "offline": "@settings_ui.note.offline", "replays": "@settings_ui.note.replays",
               "updates": "@settings_ui.note.updates", "advanced": "@settings_ui.note.advanced"}
# setting id -> group (adapters may also say "group" themselves); anything else is Advanced
GROUP_OF = {
    "display": "display", "internal_res": "display", "vsync": "display", "shadows": "display", "effects": "display",
    "stage_blur": "display", "resolution": "display", "fullscreen": "display", "fullscreen_exclusive": "display",
    "aa": "display", "hud": "display", "anisotropic": "display", "progressive": "display",
    "pad_bindings": "controls", "screen_side": "controls", "always_left": "controls",
    "input_delay": "online", "spectators": "online", "spectators_ranked": "online", "auto_spectate": "online",
    "mute": "audio", "sound": "audio", "ui_sounds": "audio", "ui_sound_volume": "audio",
    "training": "offline", "practice": "offline", "unlock_stages": "offline", "unlock_items": "offline",
    "unlock_all": "offline",
    "replays": "replays", "replay_names": "replays", "replay_dir": "replays", "reset:replay_dir": "replays",
    "launcher_update": "updates", "game_updates": "updates", "test_versions": "updates",
}
SETTINGS_LINES = 12


class SettingsPage:
    def _settings_groups(self, g, out):
        """Settings rows -> group headings + rows in group order, plus Controls and Updates rows of the launcher."""
        extra = []
        if "controls" in self.sections(g):
            extra.append(dict(kind="action", id="pad_bindings", label="@settings_ui.pad_bindings", verb="@open",
                              hint="@settings_ui.pad_bindings_hint",
                              detail=dict(kicker="@section.settings", title="@settings_ui.pad_bindings",
                                          lead="@settings_ui.pad_bindings_hint", rows=[]),
                              run=lambda: self._go(g, "controls")))
        if getattr(self, "on_update_check", None) is not None:
            version = (getattr(self, "update_state", None) or {}).get("version", "")
            extra.append(dict(kind="action", id="launcher_update", label="@updates.check", verb="@confirm",
                              value=i18n.literal(version) if version else "", hint="@updates.hint",
                              detail=dict(kicker="@section.settings", title="@updates.check", lead="@updates.hint",
                                          rows=[]),
                              run=self._check_update))
        if getattr(self, "on_setup", None) is not None:
            extra.append(dict(kind="action", id="game_updates", label="@setup.check", verb="@confirm",
                              hint="@setup.check_hint",
                              detail=dict(kicker="@section.settings", title="@setup.check", lead="@setup.check_hint",
                                          rows=[]),
                              run=self._settings_game_check))
            extra.append(dict(kind="cycler", id="test_versions", label="@setup.test_versions",
                              value="@on" if self.game_prereleases else "@off", options=[(False, "@off"), (True, "@on")],
                              current=bool(self.game_prereleases), set=self._settings_prereleases,
                              hint="@setup.test_versions_hint",
                              detail=dict(kicker="@section.settings", title="@setup.test_versions",
                                          lead="@setup.test_versions_hint", rows=[])))
        if getattr(self, "on_ui_sound", None) is not None:
            extra += self._ui_sound_rows()
        by_group = {group: [] for group in GROUPS}
        for item in out + extra:
            if item.get("kind") == "heading":
                continue
            iid = item.get("id") or ""
            group = item.get("group") or GROUP_OF.get(iid) or "advanced"
            item["settingsGroup"] = group
            by_group[group].append(item)
        page = []
        for group in GROUPS:
            if by_group[group]:
                page.append(dict(kind="heading", label=GROUP_LABELS[group], note=GROUP_NOTES[group],
                                 settingsGroup=group))
                page += by_group[group]
        return page

    def _ui_sound_rows(self):
        """The launcher's own menu sounds (ui_sound.py): the same two rows in every game's Settings > Audio."""
        percent = {v: i18n.message("ui_sound.percent", value=v) for v in ui_sound.VOLUMES}
        on = bool(self.ui_sounds)
        return [dict(kind="cycler", id="ui_sounds", label="@ui_sound.label", value="@on" if on else "@off",
                     options=[(False, "@off"), (True, "@on")], current=on, set=self._set_ui_sounds,
                     hint="@ui_sound.hint",
                     detail=dict(kicker="@section.settings", title="@ui_sound.label", lead="@ui_sound.hint", rows=[])),
                dict(kind="cycler", id="ui_sound_volume", label="@ui_sound.volume",
                     value=percent[self.ui_sound_volume], options=[(v, percent[v]) for v in ui_sound.VOLUMES],
                     current=self.ui_sound_volume, set=self._set_ui_sound_volume, hint="@ui_sound.volume_hint",
                     detail=dict(kicker="@section.settings", title="@ui_sound.volume", lead="@ui_sound.volume_hint",
                                 rows=[]))]

    def _set_ui_sounds(self, value):
        self.ui_sounds = bool(value)
        self.on_ui_sound(self.ui_sounds, self.ui_sound_volume)

    def _set_ui_sound_volume(self, value):
        self.ui_sound_volume = ui_sound.clean_volume(value)
        self.on_ui_sound(self.ui_sounds, self.ui_sound_volume)

    def _settings_game_check(self):
        if not self._dry("@setup.check"):
            self.on_setup("check_all", "", True)
            self.say("@setup.checking")

    def _settings_prereleases(self, value):
        self.game_prereleases = bool(value)
        self.on_prereleases(self.game_prereleases)

    def _view_settings_page(self, v, items, fi):
        lines = []
        focus_line = 0
        for n, it in enumerate(items):
            if it.get("kind") == "heading":
                lines.append(dict(kind="group", label=it.get("label", ""), note=it.get("note", ""),
                                  group=it.get("settingsGroup", "")))
                continue
            if n == fi:
                focus_line = len(lines)
            cycler = it.get("kind") == "cycler"
            lines.append(dict(kind="setting", index=n, label=it.get("label", ""), value=it.get("value") or "",
                              hint=it.get("hint", ""), focused=n == fi, cycler=cycler,
                              disabled=bool(it.get("disabled")), verb=it.get("verb", "") if n == fi and not cycler else "",
                              group=it.get("settingsGroup", "")))
        start = 0
        if len(lines) > SETTINGS_LINES:
            start = max(0, min(len(lines) - SETTINGS_LINES, focus_line - SETTINGS_LINES // 2))
        shown = lines[start:start + SETTINGS_LINES]
        if start > 0 and shown and shown[0]["kind"] == "setting":
            # the group of the first row shown stays named at the top
            head = next((line for line in reversed(lines[:start]) if line["kind"] == "group"), None)
            if head:
                shown = [head] + shown[:-1]
        it = items[fi] if items else {}
        d = it.get("detail") or {}
        options = []
        if it.get("kind") == "cycler":
            for value, label in it.get("options") or []:
                options.append(dict(label=label, current=type(value) is type(it.get("current")) and value == it.get("current")))
        present = [g for g in GROUPS if any(line.get("group") == g for line in lines if line["kind"] == "group")]
        groups = [dict(id=g, label=GROUP_LABELS[g], active=g == it.get("settingsGroup")) for g in present]
        v["settingsPage"] = dict(layout="groups", lines=shown, up=start > 0, down=start + SETTINGS_LINES < len(lines),
                                 groups=groups,
                                 detail=dict(kicker=GROUP_LABELS.get(it.get("settingsGroup"), ""), title=d.get("title") or it.get("label", ""),
                                             lead=d.get("lead") or it.get("hint", ""), value=it.get("value") or "",
                                             options=options[:12], rows=[dict(k=r["k"], v=r["v"]) for r in d.get("rows") or []
                                                                     if r.get("k") != "@current"][:6]))
