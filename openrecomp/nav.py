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
from .nav_picker import Picker
from .nav_sections import Sections
from .nav_shelf import Shelf


class Game:
    def __init__(self, manifest, adapter):
        self.m = manifest
        self.a = adapter
        self.id = manifest["id"]
        self.short = manifest["short"]
        self.accent = manifest["accent"]


class Nav(Shelf, Hub, Sections, Dialog, Drawer, Grid, Keyboard, Picker):
    def __init__(self, games, on_quit=None, install=None, launch_env=None, language=None, on_language=None):
        self.games = games
        self.on_quit = on_quit or (lambda: None)
        self.install = install              # path -> message; a player's manifest (the free slots)
        self.launch_env = launch_env or {}  # test runs: mute, background
        self.language = i18n.normalize(language)
        self.on_language = on_language or (lambda _language: None)
        self.dry = False                    # test runs: nothing starts, nothing is written, only a message
        self.screen = "start"
        self.game = games[0] if games else None
        self.start_focus = 0
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

    def act(self, action, device=None):
        if device:
            self.device = device
        self.trail = (self.trail + [TRAIL.get(action, "?")])[-16:]
        try:
            self._handle(action)
        except Exception as e:  # noqa: BLE001 -- a game's core saying no is a message, never a dead launcher
            self.say(i18n.error_message(e) or e.__class__.__name__)

    def release(self, action):
        if action == "confirm" and self.holding:
            self.holding = None
            self.hold = 0.0

    def tick(self, dt):
        """Time passes (the app's timer). -> True when the screen must be redrawn."""
        changed = False
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
            self.drawer_focus = 0
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
        if self._dry(i18n.message("dry_start", name=g.short)):
            return
        if g.a.running():
            self.say(i18n.message("game_already_running", name=g.short))
            return
        g.a.start(extra_env=self.launch_env or None)
        self.say(i18n.message("game_starting", name=g.short))

    def glyph(self, action, ink=False):
        table = GLYPHS["kb"] if self.device == "kb" else GLYPHS[self.pad_kind]
        text = table[action]
        symbol = text in ("✕", "○", "□", "△")
        return dict(text=text, round=len(text) == 1 and self.device != "kb", ink=ink, key=self.device == "kb", symbol=symbol)

    def prompt(self, action, label):
        return dict(action=action, label=label, g=self.glyph(action))

    def view(self):
        v = dict(screen=self.screen, overlay=self.overlay or "", toast=self.toast, device="@" + DEVICE_LABEL["kb" if self.device == "kb" else self.pad_kind],
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
        if self.overlay == "picker":
            self.picker["focus"] = index
            self.act("confirm")
        elif self.overlay == "drawer":
            self.drawer_focus = index
            self.act("confirm")
        elif self.overlay == "dialog":
            self.exit_focus = index
            self.act("confirm")
