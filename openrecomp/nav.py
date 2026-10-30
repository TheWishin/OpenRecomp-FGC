"""The launcher's state machine: semantic actions in, one plain dict for the screens out. No Qt in here.

Actions: up down left right confirm back x social prev next play switchGame. The screens never decide anything; every
press goes through act(), so the whole launcher can be driven and checked without a window.
Section and overlay mixins keep their input and view code together; Nav owns the shared state and dispatch.
"""
from . import i18n
from .nav_common import (
    DEVICE_LABEL, FRIENDLY_RESULT, GAP, GLYPHS, GRID_COLS, HOLD_SECONDS, OSK,
    OSK_ACTIONS, PICKER_VISIBLE, ROWS_VISIBLE, SCREEN_W, SECTION_TITLES,
    SPINE_GAME, SPINE_SLOT, TRAIL, WIDE, badge, uri, window,
)
from .nav_dialog import Dialog
from .nav_drawer import Drawer
from .nav_grid import Grid
from .nav_hub import Hub
from .nav_keyboard import Keyboard
from .nav_online import Online
from .nav_picker import Picker
from .nav_sections import Sections
from .nav_shelf import Shelf
from .nav_tools import Tools


class Game:
    def __init__(self, manifest, adapter):
        self.m = manifest
        self.a = adapter
        self.id = manifest["id"]
        self.short = manifest["short"]
        self.accent = manifest["accent"]


class Nav(Shelf, Hub, Sections, Dialog, Drawer, Grid, Keyboard, Picker, Tools, Online):
    def __init__(self, games, on_quit=None, install=None, launch_env=None, language=None, on_language=None,
                 last_game=None, on_game=None, fullscreen=True, reduced_motion=False, on_preferences=None,
                 on_update_check=None, on_update_install=None):
        self.games = games
        self.on_quit = on_quit or (lambda: None)
        self.install = install              # path -> message; a player's manifest (the free slots)
        self.launch_env = launch_env or {}  # test runs: mute, background
        self.language = i18n.normalize(language)
        self.on_language = on_language or (lambda _language: None)
        self.on_game = on_game or (lambda _game: None)
        self.fullscreen = bool(fullscreen)
        self.reduced_motion = bool(reduced_motion)
        self.on_preferences = on_preferences or (lambda _fullscreen, _reduced_motion: None)
        self.dry = False                    # test runs: nothing starts, nothing is written, only a message
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
        self.osk = None
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

    def act(self, action, device=None):
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
                self._finish_hold(item)
        return changed

    def say(self, message, seconds=4.5):
        self.toast = message
        self.toast_left = seconds

    def _handle(self, a):
        if self.overlay == "binding":
            return self._binding(a)
        if self.overlay == "dialog":
            return self._dialog(a)
        if self.overlay == "osk":
            return self._osk(a)
        if self.overlay == "picker":
            return self._picker(a)
        if self.overlay == "fighters":
            return self._fighters(a)
        if self.overlay == "drawer":
            return self._drawer(a)
        if a == "social":
            self.overlay = "drawer"
            self.drawer_focus = min(self.drawer_focus, len(self._drawer_items()) - 1)
            return None
        if self.screen == "start":
            return self._start(a)
        return self._hub(a)

    def _dry(self, what):
        """True in a dry run: says what would have happened instead of doing it."""
        if self.dry:
            self.say(i18n.message("dry_run", what=what))
        return self.dry

    def start_game(self, g):
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
        v = dict(screen=self.screen, overlay=self.overlay or "", toast=self.toast, fullscreen=self.fullscreen, reducedMotion=self.reduced_motion,
                 device="@" + DEVICE_LABEL["kb" if self.device == "kb" else self.pad_kind],
                 trail=self._trail(), social=self.glyph("social"), prevG=self.glyph("prev"), nextG=self.glyph("next"), confirmInk=self.glyph("confirm", True),
                 shelf=dict(tiles=[], x=0, w=SCREEN_W), tabs=[], rows=[], detail=dict(rows=[], results=[], images=[]), hint="", prompts=[], accent="#ECE9E1", badge="", gameShort="", numeral="",
                 topline="", hold=0, more=dict(up=False, down=False), grid=dict(cells=[], main=""), osk=dict(rows=[], text="", title=""), dialog=dict(title="", text="", options=[]),
                 picker=dict(rows=[], title="", path="", up=False, down=False), drawer=dict(rows=[]), quickAccess="@quick_access", recentSets="@recent_sets", folder="@folder", file="@file", pick="@picker.pick", mainLabel="@main", fighterTitle="@fighter.choose", fighterMain="@fighter.main")
        if self.screen == "start":
            self._view_start(v)
        else:
            self._view_hub(v)
        over = getattr(self, "_view_" + self.overlay, None) if self.overlay else None
        if over:
            over(v)
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
