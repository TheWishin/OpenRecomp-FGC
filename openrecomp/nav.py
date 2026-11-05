"""The launcher's state machine: semantic actions in, one plain dict for the screens out. No Qt in here.

Actions: up down left right confirm back x social prev next play switchGame. The screens never decide anything; every
press goes through act(), so the whole launcher can be driven and checked without a window.
Section and overlay mixins keep their input and view code together; Nav owns the shared state and dispatch.
"""
from . import i18n, ui_sound
from .community import DISCORD_URL
from .nav_common import (
    DEVICE_LABEL, FRIENDLY_RESULT, GAP, GLYPHS, GRID_COLS, HOLD_SECONDS, OSK,
    OSK_ACTIONS, PICKER_VISIBLE, ROWS_VISIBLE, SCREEN_W, SECTION_TITLES,
    SPINE_GAME, SPINE_SLOT, TRAIL, WIDE, badge, uri, window,
)
from .nav_build import BuildPage
from .nav_controls_page import ControlsPage
from .nav_dialog import Dialog
from .nav_drawer import Drawer
from .nav_game_setup import GameSetupNav
from .nav_grid import Grid
from .nav_hub import Hub
from .nav_main_menu import MainMenu
from .nav_keyboard import Keyboard
from .nav_library import Library
from .nav_online import Online
from .nav_online_layout import OnlineLayout
from .nav_online_login import OnlineLogin
from .nav_settings_page import SettingsPage
from .nav_picker import Picker
from .nav_sections import Sections
from .nav_shelf import Shelf
from .nav_sound import Sound
from .nav_tools import Tools


class Game:
    def __init__(self, manifest, adapter):
        self.m = manifest
        self.a = adapter
        self.id = manifest["id"]
        self.short = manifest["short"]
        self.accent = manifest["accent"]


class Nav(GameSetupNav, Shelf, Hub, MainMenu, Sections, BuildPage, Dialog, Drawer, Grid, Keyboard, Picker, Tools, ControlsPage, Online, OnlineLayout, OnlineLogin, SettingsPage, Library, Sound):
    def __init__(self, games, on_quit=None, install=None, launch_env=None, language=None, on_language=None,
                 last_game=None, on_game=None, fullscreen=True, reduced_motion=False, on_preferences=None,
                 on_update_check=None, on_update_install=None, on_game_preview=None, on_game_accept=None,
                 on_game_remove=None, on_game_update_check=None, on_game_update_install=None, on_setup=None,
                 game_prereleases=False, on_prereleases=None, native_picker=False, picker_dirs=None, on_picker_dir=None,
                 online_prefs=None, on_online_prefs=None, ui_sounds=True, ui_sound_volume=None, on_ui_sound=None,
                 text_size=100, high_contrast=False, on_accessibility=None):
        self.games = games
        self.ui_sounds = bool(ui_sounds)                  # the launcher's menu sounds (Settings > Audio)
        self.ui_sound_volume = ui_sound.clean_volume(ui_sound_volume)
        self.on_ui_sound = on_ui_sound                    # (on, volume) -> None; None = the rows are not offered
        self.online_prefs = dict(online_prefs or {})   # per game: {auto_login} (Remember me on the login card)
        self.on_online_prefs = on_online_prefs
        self.on_quit = on_quit or (lambda: None)
        self.install = install              # path -> message; a player's manifest (the free slots)
        self.launch_env = launch_env or {}  # test runs: mute, background
        self.language = i18n.normalize(language)
        self.on_language = on_language or (lambda _language: None)
        self.on_game = on_game or (lambda _game: None)
        self.fullscreen = bool(fullscreen)
        self.reduced_motion = bool(reduced_motion)
        self.text_size = text_size if type(text_size) is int and text_size in (100, 115, 130) else 100
        self.high_contrast = bool(high_contrast)
        self.on_accessibility = on_accessibility or (lambda _size, _contrast: None)
        self.on_preferences = on_preferences or (lambda _fullscreen, _reduced_motion: None)
        self.dry = False                    # test runs: nothing starts, nothing is written, only a message
        self.pending_clipboard = None
        self.screen = "start"
        self.game = next((g for g in games if g.id == last_game), games[0] if games else None)
        self.start_focus = games.index(self.game) if self.game else 0
        self.sec = {}
        self.focus = {}
        self.overlay = None
        self.device = "xbox"
        self.trail = []
        self.toast = ""
        self.toast_left = 0.0
        self.hold = 0.0
        self.holding = None
        self.exit_focus = 0
        self.confirm_kind = "exit"
        self.drawer_focus = 0
        self.grid_focus = 0
        self.show_results = False
        self.picker = None
        self.native_picker = bool(native_picker)    # the app can open the Windows Explorer dialog
        self.pending_native = None                  # a dialog the app opens after this action
        self.picker_dirs = dict(picker_dirs or {})  # {".iso": folder, "folder": folder}: where the player last chose one
        self.on_picker_dir = on_picker_dir or (lambda _key, _folder: None)
        self.osk = None
        self.tools_game = None                      # the game whose missing build tools the dialog lists
        self.tools_installing = None                # the game whose tools are being installed (result toast once)
        self.pad_kind = "xbox"
        self.was_running = {}
        self.controls_game = None
        self.binding_game = None
        self.binding_result = {}
        self.support_game = None
        self.support_snapshot = None
        self.on_update_check = on_update_check
        self.on_update_install = on_update_install
        self.update_state = dict(phase="idle", version="", notes="", size=0)
        self.update_offered = ""
        self.update_version = ""
        self.online_rows = {}
        self.source_checks = {}
        self.on_game_preview = on_game_preview
        self.on_game_accept = on_game_accept
        self.on_game_remove = on_game_remove
        self.on_game_update_check = on_game_update_check
        self.on_game_update_install = on_game_update_install
        self.library_request = 0
        self.library_pending = ""
        self.library_busy = False
        self.library_preview = None
        self.library_page = 0
        self.library_game = ""
        self.library_offer = None
        self.on_setup = on_setup              # game install/update work (app.GameSetup); None = not offered
        self.on_prereleases = on_prereleases or (lambda _on: None)
        self.game_prereleases = bool(game_prereleases)
        self.setup_state = {}
        self.setup_game = ""
        self.setup_parent = ""
        self.setup_space = {}
        self.setup_waiting = False

    def act(self, action, device=None):
        self.sounded(action, self._act, action, device)

    def _act(self, action, device):
        if device:
            self.device = device
            if device in ("xbox", "ps"):
                self.pad_kind = device
        if action != "confirm":
            self._cancel_hold()
        self.trail = (self.trail + [TRAIL.get(action, "?")])[-16:]
        try:
            self._handle(action)
        except Exception as e:  # noqa: BLE001 -- a game's core saying no is a message, never a dead launcher
            self.hint_sound(ui_sound.ERROR)
            self.say(i18n.error_message(e) or e.__class__.__name__)

    def release(self, action):
        if action == "confirm":
            self._cancel_hold()

    def _cancel_hold(self):
        self.holding = None
        self.hold = 0.0

    def _select_game(self, game):
        if self.controls_game and self.controls_game is not game:
            self.controls_game.a.controls_close()
            self.controls_game = None
        self.game = game
        self.start_focus = self.games.index(game)
        if not self.dry:
            self.on_game(game.id)

    def tick(self, dt):
        """Time passes (the app's timer). -> True when the screen must be redrawn."""
        changed = self.poll_online()
        changed = self.tick_online_feedback(dt) or changed
        changed = self.poll_sources() or changed
        changed = self.poll_tools_install() or changed
        changed = self.poll_build(dt) or changed
        if self.toast:
            self.toast_left -= dt
            if self.toast_left <= 0:
                self.toast = ""
                changed = True
        if self.holding:
            self.hold = min(1.0, self.hold + dt / HOLD_SECONDS)
            changed = True
            if self.hold >= 1.0:
                item, self.holding, self.hold = self.holding, None, 0.0
                self.sounded("confirm", self._finish_hold, item)
        return changed

    def say(self, message, seconds=3):
        self.toast = message
        self.toast_left = seconds

    def copy_text(self, text):
        if self._dry("@t4.tools.copy"):
            return
        self.pending_clipboard = str(text)

    def open_discord(self):
        """The players' Discord (community.DISCORD_URL) in the browser: the app opens nav.pending_url."""
        if self._dry("@community.discord"):
            return
        self.pending_url = DISCORD_URL
        self.say("@community.opening")

    def _handle(self, a):
        if getattr(self, "native_edit", ""):
            return self._native_action(a)
        if self.library_busy:
            if (self.overlay == "dialog" and self.confirm_kind.startswith("library_")
                    and (a == "back" or a == "confirm" and self.confirm_kind == "library_loading")):
                self._cancel_library()
            else:
                self.say("@library.busy")
            return
        if a == "quit":
            return self.request_quit()
        if a == "returnGame":
            return self._return_game()
        if a == "discord":                  # the top bar's OpenRecomp-FGC Discord (mouse); pads: Quick access
            return self.open_discord()
        if self.overlay == "binding":
            return self._binding(a)
        from . import nav_feedback
        if not self.overlay or self.overlay not in ("osk", "native"):
            if nav_feedback.global_action(self, "offers" if a == "social" and nav_feedback.global_view(self) else a):
                return None
            if a == "returnActivity":
                return nav_feedback.return_activity(self)
        if self.overlay == "dialog":
            return self._dialog(a)
        if self.overlay == "ctlpreset":
            return self._ctlpreset(a)
        if self.overlay == "osk":
            return self._osk(a)
        if self.overlay == "picker":
            return self._picker(a)
        if self.overlay == "fighters":
            return self._fighters(a)
        if self.overlay == "drawer":
            return self._drawer(a)
        if a == "social":
            from . import nav_arcade
            if nav_arcade.action(self, a):
                return None
            if self.online_profile_shortcut():
                return None
            self.overlay = "drawer"
            self.drawer_focus = min(self.drawer_focus, len(self._drawer_items()) - 1)
            return None
        if self.screen == "start":
            return self._start(a)
        return self._hub(a)

    def _return_game(self):
        game = next((g for g in self.games if g.m.get("adapter") == "t4" and g.a.running()), None)
        if game is None or self._dry("@dry_stop"):
            return
        online = game.a.online_state().get("phase") == "playing"
        if online:
            try:
                game.a.online_action("stop_match")
            except Exception:  # noqa: BLE001 -- online failures must not expose session details
                self.say("@online.failure", 12)
                return
        elif not self._offline_action(game.a.stop):
            return
        self._cancel_hold()
        self.overlay = None
        self._select_game(game)
        self.main_menu_game = ""
        self.screen = "hub"
        self.sec[game.id] = "online" if online else "play"
        self.focus[game.id + ":" + self.sec[game.id]] = 0
        self.say("@t4.returning", 8)

    def request_quit(self):
        if self.library_busy:
            self.say("@library.busy", 12)
            return False
        setup = next((gid for gid, st in (getattr(self, "setup_state", None) or {}).items()
                      if (st or {}).get("phase") in ("installing", "updating")), None)
        if setup:                     # files of a game are being exchanged: never quit in the middle of it
            self.setup_game = setup
            if not (self.overlay == "dialog" and self.confirm_kind == "setup_progress"):
                self._ask("setup_progress")
            self.say("@setup.quit_busy", 12)
            return False
        busy = next((g for g in self.games if g.a.source_state().get("running") or g.a.build_state().get("running")), None)
        if busy:
            self._cancel_hold()
            self.overlay = None
            self._select_game(busy)
            self.screen = "hub" if busy.a.found() else "start"
            if self.screen == "hub" and "build" in self.sections(busy):
                self.sec[busy.id] = "build"
                items = self._items_build(busy)
                self.focus[busy.id + ":build"] = next((i for i, item in enumerate(items) if item.get("id") == "build"), 0)
            self.say("@t4.quit_busy", 12)
            return False
        self._ask("exit")
        return True

    def _dry(self, what):
        """True in a dry run: says what would have happened instead of doing it."""
        if self.dry:
            self.say(i18n.message("dry_run", what=what))
        return self.dry

    def start_game(self, g):
        if self.library_busy:
            self.say("@library.busy")
            return
        if self._dry(i18n.message("dry_start", name=i18n.literal(g.short))):
            return
        if g.a.running():
            self.say(i18n.message("game_already_running", name=i18n.literal(g.short)))
            return
        if not g.a.ready():
            self._select_game(g)
            self.screen = "hub"
            if "build" in self.sections(g):
                self.sec[g.id] = "build"
            self.say(g.a.status()["detail"])
            return
        if self._offline_action(g.a.start, extra_env=self.launch_env or None):
            self.say(i18n.message("game_starting", name=i18n.literal(g.short)))

    def _offline_action(self, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
            return True
        except Exception as e:  # noqa: BLE001 -- preserve the cause and give a way to recover
            self.say(i18n.message("action_failed", error=i18n.error_message(e) or e.__class__.__name__), 12)
            return False

    def glyph(self, action, ink=False):
        table = GLYPHS["kb"] if self.device == "kb" else GLYPHS[self.pad_kind]
        text = table[action]
        symbol = text in ("✕", "○", "□", "△")
        return dict(text=text, round=len(text) == 1 and self.device != "kb", ink=ink, key=self.device == "kb", symbol=symbol)

    def prompt(self, action, label):
        return dict(action=action, label=label, g=self.glyph(action))

    def view(self):
        v = dict(screen=self.screen, overlay=self.overlay or "", toast=self.toast, fullscreen=self.fullscreen, reducedMotion=self.reduced_motion or getattr(self, "system_reduced_motion", False),
                 textScale=self.text_size / 100, highContrast=self.high_contrast,
                 inputMode=self.device, nativeEdit=getattr(self, "native_edit", ""), nativeField={},
                 device="@" + DEVICE_LABEL["kb" if self.device == "kb" else self.pad_kind],
                 trail=self._trail(), social=self.glyph("social"), prevG=self.glyph("prev"), nextG=self.glyph("next"), confirmInk=self.glyph("confirm", True), backG=self.glyph("back"),
                 shelf=dict(tiles=[], x=0, w=SCREEN_W), tabs=[], rows=[], detail=dict(rows=[], results=[], images=[]), hint="", prompts=[], accent="#ECE9E1", badge="", gameShort="", numeral="",
                 topline="", hold=0, mainMenu=dict(show=False), sessionPage=dict(show=False), loading="@ui.loading", loadError="@ui.load_error", more=dict(up=False, down=False), grid=dict(cells=[], main=""), osk=dict(rows=[], text="", title="", selected=False, paste="", copy="", canCopy=False), dialog=dict(title="", text="", options=[]),
                 picker=dict(rows=[], title="", path="", up=False, down=False), drawer=dict(rows=[]), build=dict(show=False, cards=[], main=dict(button={}, logLines=[]), more=[]), online=dict(layout=""), settingsPage=dict(layout=""), bindingsPage=dict(layout="", tabs=[], lines=[]), bindCapture=dict(options=[], glyphs=[]), ctlPreset=dict(rows=[]), quickAccess="@quick_access", discord="@community.discord", recentSets="@recent_sets", folder="@folder", file="@file", pick="@picker.pick", mainLabel="@main", fighterTitle="@fighter.choose", fighterMain="@fighter.main")
        if self.screen == "start":
            self._view_start(v)
        else:
            self._view_hub(v)
        over = getattr(self, "_view_" + self.overlay, None) if self.overlay else None
        if over:
            over(v)
        from . import nav_feedback
        v["globalOffers"] = nav_feedback.global_view(self)
        v["activity"] = nav_feedback.activity_view(self)
        v["matchVersus"] = nav_feedback.match_view(self, self.game) if self.game else {}
        from . import nav_rank_cue
        v["promotion"] = nav_rank_cue.view(self)
        if v["globalOffers"]:
            for prompt in v["prompts"]:
                if prompt.get("action") == "social":
                    prompt["label"] = "@feedback.offers"
        v["gameTheme"] = self.game.m.get("adapter", "") if self.game and self.screen == "hub" else ""
        from .living_background import background_view
        background_game = self.game
        if self.screen == "start":
            ids = self.tile_ids()
            background_game = self.game_by_id(ids[min(self.start_focus, len(ids) - 1)])
        v["livingBackground"] = background_view(background_game.a, background_game.m.get("adapter", ""),
                                                reduced_motion=v["reducedMotion"]) if background_game else {}
        if v["gameTheme"] in ("t4", "t5dr"):
            v["accent"] = "#71CBE5" if v["gameTheme"] == "t4" else "#D11F3F"
        v["nativeEdit"] = getattr(self, "native_edit", "")
        return i18n.localize(v, self.language)

    def _trail(self):
        cells = []
        n = len(self.trail)
        for i in range(16):
            idx = i - (16 - n)
            cells.append(dict(text=self.trail[idx] if 0 <= idx < n else "", newest=i == 15 and n > 0))
        return cells

    def _cells(self, results):
        labels = {"W": "@result.win_short", "L": "@result.loss_short"}
        return [dict(text=labels.get(r, r), win=FRIENDLY_RESULT.get(r, False)) for r in results]

    def _guard(self, fn, *args):
        try:
            fn(*args)
        except Exception as e:  # noqa: BLE001 -- as in act()
            self.say(i18n.error_message(e) or e.__class__.__name__)

    def click_entry(self, index):
        if self.overlay == "binding" and not self.binding_active():
            self.exit_focus = index
            self.act("confirm")
        elif self.overlay == "picker":
            self.picker["focus"] = index
            self.act("confirm")
        elif self.overlay == "drawer":
            self.drawer_focus = index
            self.act("confirm")
        elif self.overlay == "dialog":
            self.exit_focus = index
            self.act("confirm")
        elif self.overlay == "ctlpreset":
            self.click_preset(index)
