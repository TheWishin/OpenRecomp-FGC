"""The launcher's state machine: semantic actions in, one plain dict for the screens out. No Qt in here.

Actions: up down left right confirm back x social prev next play switchGame. The screens never decide anything; every
press goes through act(), so the whole launcher can be driven and checked without a window.
"""
import os
import pathlib
import string

from . import manifest as mf
from . import i18n

SECTION_TITLES = {"play": "section.play", "online": "section.online", "build": "section.build", "replays": "section.replays", "settings": "section.settings"}
GLYPHS = {
    "xbox": dict(confirm="A", back="B", x="X", social="Y", prev="LB", next="RB", play="Start", switchGame="View", right="‹ ›"),
    "ps": dict(confirm="✕", back="○", x="□", social="△", prev="L1", next="R1", play="Options", switchGame="Share", right="‹ ›"),
    "kb": dict(confirm="Enter", back="Esc", x="X", social="F", prev="Q", next="E", play="Space", switchGame="G", right="← →"),
}
TRAIL = dict(up="↑", down="↓", left="←", right="→", confirm="A", back="B", x="X", social="Y", prev="LB", next="RB", play="St", switchGame="Vw")
DEVICE_LABEL = dict(xbox="device.xbox", ps="device.ps", kb="device.kb")
OSK = ("1234567890", "QWERTYUIOP", "ASDFGHJKL-", "ZXCVBNM_.,")
OSK_ACTIONS = (("space", "osk.space"), ("del", "osk.delete"), ("done", "osk.done"))
ROWS_VISIBLE = 9
PICKER_VISIBLE = 11
SCREEN_W = 1920
WIDE, SPINE_GAME, SPINE_SLOT, GAP = 1040, 260, 140, 2
GRID_COLS = 9
HOLD_SECONDS = 1.5
FRIENDLY_RESULT = {"W": True, "L": False}


def uri(path):
    return pathlib.Path(path).as_uri() if path else ""


def window(count, focus, size):
    """First visible index so that `focus` stays in a list of `size` rows."""
    if count <= size:
        return 0
    return max(0, min(count - size, focus - size // 2))


def badge(g):
    """What kind of recomp a game is, from its manifest: PS3 RECOMP."""
    platform = g.m.get("platform", "")
    return f"{platform} RECOMP".upper() if platform else ""


class Game:
    def __init__(self, manifest, adapter):
        self.m = manifest
        self.a = adapter
        self.id = manifest["id"]
        self.short = manifest["short"]
        self.accent = manifest["accent"]


class Nav:
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

    # ------------------------------------------------------------------------------------ the shelf
    def tile_ids(self):
        ids = [g.id for g in self.games]
        free = max(1, mf.TOTAL_SLOTS - len(ids))
        return ids + [f"slot{i}" for i in range(free)]

    def game_by_id(self, gid):
        return next((g for g in self.games if g.id == gid), None)

    def set_games(self, games):
        keep = self.game.id if self.game else None
        self.games = games
        self.game = self.game_by_id(keep) or (games[0] if games else None)
        self.start_focus = min(self.start_focus, len(self.tile_ids()) - 1)

    # ------------------------------------------------------------------------------------ input
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

    # ------------------------------------------------------------------------------------ start screen
    def _start(self, a):
        ids = self.tile_ids()
        if a == "left":
            self.start_focus = max(0, self.start_focus - 1)
        elif a == "right":
            self.start_focus = min(len(ids) - 1, self.start_focus + 1)
        elif a == "switchGame":
            self.start_focus = (self.start_focus + 1) % len(ids)
        elif a == "back":
            self._ask("exit")
        else:
            g = self.game_by_id(ids[self.start_focus])
            if g is None:
                if a == "confirm":
                    self._open_picker("manifest", "@choose_manifest", [".json"], [mf.BUILTIN_DIR, os.path.expanduser("~\\Downloads")], "file")
            elif a == "confirm":
                self.game = g
                self.screen = "hub"
            elif a == "play":
                self.game = g
                self.start_game(g)

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

    # ------------------------------------------------------------------------------------ the game's sections
    def sections(self, g=None):
        return (g or self.game).m["sections"]

    def section(self):
        g = self.game
        secs = self.sections(g)
        if g.id not in self.sec:
            self.sec[g.id] = "play" if g.a.ready() or "build" not in secs else "build"
        if self.sec[g.id] not in secs:
            self.sec[g.id] = secs[0]
        return self.sec[g.id]

    def key(self):
        return f"{self.game.id}:{self.section()}"

    def items(self):
        return getattr(self, "_items_" + self.section())(self.game)

    def focus_index(self, items):
        i = max(0, min(len(items) - 1, self.focus.get(self.key(), 0)))
        while i < len(items) - 1 and items[i].get("kind") == "heading":
            i += 1
        return i

    def _hub(self, a):
        items = self.items()
        i = self.focus_index(items)
        it = items[i] if items else {}
        secs = self.sections()
        if a in ("up", "down"):
            step = -1 if a == "up" else 1
            j = i + step
            while 0 <= j < len(items) and items[j].get("kind") == "heading":
                j += step
            if 0 <= j < len(items):
                self.focus[self.key()] = j
        elif a in ("prev", "next"):
            pos = secs.index(self.section())
            self.sec[self.game.id] = secs[(pos + (-1 if a == "prev" else 1)) % len(secs)]
        elif a == "back":
            self.screen = "start"
            self.start_focus = self.games.index(self.game)
        elif a == "switchGame":
            pos = (self.games.index(self.game) + 1) % len(self.games)
            self.game = self.games[pos]
            self.start_focus = pos
        elif a == "play":
            self.start_game(self.game)
        elif a == "x":
            if it.get("replay") is not None:
                self.show_results = not self.show_results
        elif a in ("left", "right") and it.get("kind") == "cycler":
            self._cycle(it, 1 if a == "right" else -1)
        elif a == "confirm":
            self._activate(it)

    def _cycle(self, it, step):
        if self._dry(i18n.message("dry_change", name=it["label"])):
            return
        options = it["options"]
        values = [o[0] for o in options]
        pos = values.index(it["current"]) if it["current"] in values else 0
        it["set"](values[(pos + step) % len(values)])

    def _activate(self, it):
        kind = it.get("kind")
        if kind == "cycler":
            self._cycle(it, 1)
        elif kind == "hold":
            self.holding = it
            self.hold = 0.0
        elif kind == "action" and it.get("run"):
            it["run"]()

    def _finish_hold(self, it):
        if it.get("run"):
            try:
                it["run"]()
            except Exception as e:  # noqa: BLE001 -- as in act()
                self.say(i18n.error_message(e))

    # ---- play
    def _items_play(self, g):
        st = g.a.status()
        ready = g.a.ready()
        running = g.a.running()
        detail = dict(kicker=st["status"], title=g.short, lead=st["detail"],
                      rows=[dict(k="@version", v=st["version"]), dict(k="@last_played", v=st["last"])],
                      results=g.a.recent_results(), image="")
        by_id = {s["id"]: s for s in g.a.settings()}
        for sid in g.a.quick_settings():
            s = by_id.get(sid)
            if s:
                detail["rows"].append(dict(k=s["label"], v=self._option_label(s)))
        if running:
            detail["primary"] = "@stop"
            start = dict(kind="action", id="start", label="@game_running", verb="@stop", run=g.a.stop,
                         hint=i18n.message("game_is_running", name=g.short), detail=detail)
        elif ready:
            detail["primary"] = "@play"
            start = dict(kind="action", id="start", label="@start_game", verb="@start", run=lambda: self.start_game(g),
                         hint="@start_hint", detail=detail)
        else:
            detail["primary"] = "@go_build" if "build" in self.sections(g) else ""
            start = dict(kind="action", id="start", label="@build_first", verb="@go_build", run=lambda: self._go(g, "build"),
                         hint=st["detail"], detail=detail)
        out = [start]
        for sid in g.a.quick_settings():
            if sid in by_id:
                out.append(self._cycler_item(g, by_id[sid]))
        if g.a.native_label:
            out.append(self._native_item(g))
        return out

    def _go(self, g, section):
        self.sec[g.id] = section

    def _native_item(self, g):
        def run():
            if self._dry(i18n.message("dry_open", name=g.a.native_label)):
                return
            g.a.open_native()
            self.say(i18n.message("opening", name=g.a.native_label))
        return dict(kind="action", id="native", label="@native_launcher", verb="@open", run=run,
                    hint=i18n.message("native_hint", name=g.a.native_label),
                    detail=dict(kicker="@also", title=g.a.native_label, lead="@native_lead", rows=[]))

    @staticmethod
    def _option_label(s):
        return next((label for value, label in s["options"] if value == s["value"]), str(s["value"]))

    def _cycler_item(self, g, s):
        def setter(value):
            g.a.set_setting(s["id"], value)
        label = self._option_label(s)
        return dict(kind="cycler", id=s["id"], label=s["label"], value=label, options=s["options"], current=s["value"], set=setter,
                    hint=s.get("hint", ""), detail=dict(kicker="@setting", title=s["label"], lead=s.get("lead", ""), rows=[dict(k="@current", v=label)]))

    # ---- online
    def _items_online(self, g):
        out = []
        for it in g.a.online_items():
            it = dict(it)
            opens = it.get("opens")
            if opens == "fighters":
                it["run"] = self._open_fighters
            elif opens and opens.startswith("text:"):
                it["run"] = lambda tid=opens[5:]: self._open_osk(tid)
            elif it.get("kind") == "action":
                it["run"] = lambda iid=it["id"], label=it["label"]: self._dry(i18n.message("dry_start", name=label)) or self.say(g.a.run_online(iid))
            out.append(it)
        return out

    # ---- replays
    def _items_replays(self, g):
        replays = g.a.replays()
        if not replays:
            return [dict(kind="action", id="none", label="@no_replays", verb="", hint="@replays_hint",
                         detail=dict(kicker="@section.replays", title="@no_replays", lead="@replays_lead", rows=[]))]
        out, last = [], None
        for r in replays:
            if r["group"] != last:
                out.append(dict(kind="heading", label=r["group"]))
                last = r["group"]
            result = r["result"] if self.show_results else "@hidden"
            out.append(dict(kind="action", id=r["id"], replay=r["id"], label=r["label"], value=r["when"], verb="@watch",
                            run=lambda rid=r["id"]: self._play_replay(g, rid),
                            hint="@replay_hint",
                            detail=dict(kicker=r["group"], title=r["label"], lead="@saved_locally", images=r.get("images", []),
                                        rows=[dict(k="@date", v=r["date"]), dict(k="@opponent", v=r["opponent"]), dict(k="@netcode", v=r["netcode"]), dict(k="@result", v=result)],
                                        primary="@watch")))
        return out

    def _play_replay(self, g, rid):
        if self._dry("@dry_replay"):
            return
        g.a.play_replay(rid, extra_env=self.launch_env or None)
        self.say("@replay_starting")

    # ---- build
    def _items_build(self, g):
        state = g.a.build_state()
        out = []
        for s in g.a.sources():
            src = dict(s)
            detail = dict(kicker="@your_files", title=s["label"], lead=s.get("note") or s["hint"],
                          rows=[dict(k="@current", v=s["value"], accent=not s["ok"]), dict(k="@source", v=g.m.get("source", "@own_file"))])
            out.append(dict(kind="action", id=s["id"], label=s["label"], value=s["value"], missing=not s["ok"], verb="@choose" if not s["ok"] else "@change",
                            hint=s["hint"], detail=detail,
                            run=lambda src=src: self._open_picker("source:" + src["id"], i18n.message("choose_named", name=src["label"]), src["exts"], src["dirs"], src.get("kind", "file"))))
        for o in g.a.build_options():
            out.append(self._cycler_item(g, o))
        problem = g.a.build_ready()
        if not g.a.found():
            return out
        st = g.a.status()
        if state["running"]:
            def cancel():
                self._ask("cancel_build")
            out.append(dict(kind="action", id="build", label="@build_running", verb="@cancel", run=cancel, hint=state["line"][:90] or "@build_running_hint",
                            detail=dict(kicker=i18n.message("step", name=state["title"]), title="@build_running", lead=state["line"][:160], rows=state["steps"], progress=state["fraction"])))
            return out

        def build():
            if problem:
                self.say(problem)
            elif not self._dry("@dry_build"):
                g.a.build_start()
                self.say("@build_starting")
        lead = state["result"] or problem or ("@built_hint" if g.a.ready() else "@build_hint")
        out.append(dict(kind="action", id="build", label="@build_game", disabled=bool(problem), verb="@files_missing" if problem else "@build", run=build,
                        hint=lead, detail=dict(kicker=st["status"], title="@build_game", lead=lead, rows=state["steps"], primary="" if problem else "@build")))
        if not problem:
            def rebuild():
                if self._dry("@dry_rebuild"):
                    return
                g.a.build_start(force=True)
                self.say("@rebuild_starting")
            out.append(dict(kind="heading", label="@from_scratch", mt=16))
            out.append(dict(kind="hold", id="rebuild", label="@rebuild_all", verb="@hold", run=rebuild, hint="@rebuild_hint",
                            detail=dict(kicker="@takes_longer", title="@rebuild_all", lead="@rebuild_lead", rows=[])))
        return out

    # ---- settings
    def _items_settings(self, g):
        out = [self._cycler_item(g, s) for s in g.a.settings()]
        if g.a.native_label:
            out.append(dict(kind="heading", label="@also", mt=12))
            out.append(self._native_item(g))
        if not out:
            out.append(dict(kind="action", id="none", label="@no_settings", verb="", hint="@no_settings_hint",
                            detail=dict(kicker="@section.settings", title="@no_settings", lead="", rows=[])))
        return out

    # ------------------------------------------------------------------------------------ overlays
    def _ask(self, kind):
        self.overlay = "dialog"
        self.confirm_kind = kind
        self.exit_focus = 0

    def _dialog(self, a):
        if a in ("left", "right", "up", "down"):
            self.exit_focus = 1 - self.exit_focus
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            yes = self.exit_focus == 1
            self.overlay = None
            if yes and self.confirm_kind == "exit":
                if not self._dry("@dry_quit"):
                    self.on_quit()
            elif yes and self.confirm_kind == "cancel_build" and not self._dry("@dry_cancel_build"):
                self.game.a.build_cancel()
                self.say("@cancelling_build")

    def _drawer_items(self):
        out = [dict(label="@language", value="@language." + self.language, language=True)]
        for g in self.games:
            if g.a.found() and g.a.native_label:
                out.append(dict(label=g.a.native_label, value=g.short, game=g))
        return out

    def _drawer(self, a):
        items = self._drawer_items()
        if a == "up":
            self.drawer_focus = max(0, self.drawer_focus - 1)
        elif a == "down":
            self.drawer_focus = min(len(items) - 1, self.drawer_focus + 1)
        elif a in ("left", "right") and items[self.drawer_focus].get("language"):
            self._cycle_language(1 if a == "right" else -1)
        elif a in ("back", "social"):
            self.overlay = None
        elif a == "confirm":
            if items[self.drawer_focus].get("language"):
                self._cycle_language(1)
                return
            g = items[self.drawer_focus].get("game")
            if g and not self._dry(i18n.message("dry_open", name=g.a.native_label)):
                g.a.open_native()
                self.overlay = None
                self.say(i18n.message("opening", name=g.a.native_label))

    def _cycle_language(self, step):
        codes = i18n.LANGUAGES
        self.language = codes[(codes.index(self.language) + step) % len(codes)]
        self.on_language(self.language)

    def _fighter_list(self):
        return [dict(key="random", name="@random", image="")] + self.game.a.fighters()

    def _open_fighters(self):
        self.overlay = "fighters"
        keys = [f["key"] for f in self._fighter_list()]
        chosen = self.game.a.chosen_fighter()
        self.grid_focus = keys.index(chosen) if chosen in keys else 0

    def _fighters(self, a):
        items = self._fighter_list()
        n = len(items)
        i = self.grid_focus
        if a == "left" and i > 0:
            self.grid_focus = i - 1
        elif a == "right" and i + 1 < n:
            self.grid_focus = i + 1
        elif a == "up" and i - GRID_COLS >= 0:
            self.grid_focus = i - GRID_COLS
        elif a == "down":
            if i + GRID_COLS < n:
                self.grid_focus = i + GRID_COLS
            elif i // GRID_COLS < (n - 1) // GRID_COLS:
                self.grid_focus = n - 1
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            if not self._dry(i18n.message("dry_save", name=items[i]["name"])):
                self.game.a.set_fighter(items[i]["key"])
            self.overlay = None

    def _open_osk(self, tid):
        self.osk = dict(tid=tid, text=self.game.a.text_value(tid), row=1, col=0, title="@osk.player_name")
        self.overlay = "osk"

    def _osk(self, a):
        o = self.osk
        length = len(OSK_ACTIONS) if o["row"] == len(OSK) else len(OSK[o["row"]])
        if a == "left":
            o["col"] = (o["col"] - 1) % length
        elif a == "right":
            o["col"] = (o["col"] + 1) % length
        elif a in ("up", "down"):
            to = o["row"] + (-1 if a == "up" else 1)
            if 0 <= to <= len(OSK):
                if to == len(OSK):
                    o["col"] = min(2, o["col"] * 3 // 10)
                elif o["row"] == len(OSK):
                    o["col"] = o["col"] * 3 + 1
                o["row"] = to
        elif a == "x":
            o["text"] = o["text"][:-1]
        elif a == "play":
            self._osk_done()
        elif a == "back":
            self.overlay = None
        elif a == "confirm":
            if o["row"] == len(OSK):
                kind = OSK_ACTIONS[o["col"]][0]
                if kind == "space":
                    o["text"] += " "
                elif kind == "del":
                    o["text"] = o["text"][:-1]
                else:
                    self._osk_done()
            else:
                o["text"] += OSK[o["row"]][o["col"]]

    def type_text(self, text):
        """A physical keyboard in the on-screen keyboard."""
        if self.overlay == "osk":
            self.device = "kb"
            self.osk["text"] += text

    def _osk_done(self):
        if not self._dry("@dry_text"):
            self.game.a.set_text_value(self.osk["tid"], self.osk["text"].strip())
        self.overlay = None

    # ---- a file or folder, by pad
    def _open_picker(self, target, title, exts, dirs, kind):
        start = next((d for d in dirs if d and os.path.isdir(d)), "")
        self.picker = dict(target=target, title=title, exts=[e.lower() for e in exts], kind=kind, dir=start, focus=0)
        self.overlay = "picker"
        self._picker_first_file()

    def _picker_first_file(self):
        """The focus starts on the first file: usually the one the player came for."""
        entries = self._picker_entries()
        self.picker["focus"] = next((i for i, e in enumerate(entries) if e["kind"] == "file"), 0)

    def _picker_entries(self):
        p = self.picker
        out = []
        if not p["dir"]:
            for letter in string.ascii_uppercase:
                root = f"{letter}:\\"
                if os.path.exists(root):
                    out.append(dict(name=root, path=root, kind="dir"))
            return out
        if p["kind"] == "folder":
            out.append(dict(name="@picker.choose_folder", path=p["dir"], kind="pick"))
        parent = os.path.dirname(p["dir"].rstrip("\\/"))
        out.append(dict(name="..", path="" if parent == p["dir"].rstrip("\\/") or len(p["dir"]) <= 3 else parent, kind="dir"))
        folders, files = [], []
        try:
            with os.scandir(p["dir"]) as it:
                for e in it:
                    try:
                        if e.is_dir():
                            folders.append(dict(name=e.name, path=e.path, kind="dir"))
                        elif p["kind"] == "file" and os.path.splitext(e.name)[1].lower() in p["exts"]:
                            files.append(dict(name=e.name, path=e.path, kind="file"))
                    except OSError:
                        pass
        except OSError:
            pass
        key = lambda d: d["name"].casefold()  # noqa: E731
        return out + sorted(files, key=key) + sorted(folders, key=key)

    def _picker(self, a):
        p = self.picker
        entries = self._picker_entries()
        if a == "up":
            p["focus"] = max(0, p["focus"] - 1)
        elif a == "down":
            p["focus"] = min(len(entries) - 1, p["focus"] + 1)
        elif a == "back":
            self.overlay = None
        elif a == "confirm" and entries:
            e = entries[p["focus"]]
            if e["kind"] == "dir":
                p["dir"] = e["path"]
                self._picker_first_file()
            else:
                self.overlay = None
                self._picked(p["target"], e["path"])

    def _picked(self, target, path):
        if self._dry(i18n.message("dry_use", path=path)):
            return
        if target == "manifest":
            self.say(self.install(path) if self.install else "")
        elif target.startswith("source:"):
            message = self.game.a.set_source(target[7:], path)
            if message == "reload" and self.install:
                self.say(self.install(None))
            elif message:
                self.say(message)

    # ------------------------------------------------------------------------------------ what the screens show
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

    def _view_start(self, v):
        ids = self.tile_ids()
        widths = [SPINE_GAME if self.game_by_id(i) else SPINE_SLOT for i in ids]
        focus = min(self.start_focus, len(ids) - 1)
        others = sum(w + GAP for j, w in enumerate(widths) if j != focus)
        wide = max(WIDE, SCREEN_W - others)
        total = wide + others
        before = sum(widths[j] + GAP for j in range(focus))
        x = -max(0, min(total - SCREEN_W, before - (SCREEN_W - wide) // 2))
        tiles = []
        for j, tid in enumerate(ids):
            g = self.game_by_id(tid)
            foc = j == focus
            t = dict(id=tid, focused=foc, w=wide if foc else widths[j], free=g is None)
            if g:
                st = g.a.status()
                ready = g.a.ready()
                t.update(badge=badge(g), num=g.m["numeral"], name=g.m["title"], subtitle=g.m["subtitle"] if foc else st["status"], accent=g.accent, hero=uri(g.a.hero()),
                         rows=[dict(k="@status", v=st["status"]), dict(k="@version", v=st["version"]), dict(k="@section.online", v=st["players"]), dict(k="@last_played", v=st["last"])],
                         results=self._cells(g.a.recent_results()), empty="@no_sets", sections=["@" + SECTION_TITLES[s] for s in g.m["sections"]],
                         bar="@open" if ready else "@go_build")
            else:
                t.update(badge="", num="+", name="@free_slot" if not foc else "@add_recomp", subtitle="@another_game" if foc else "", accent="#ECE9E1", hero="",
                         rows=[dict(k="@name_colour", v="@manifest"), dict(k="@sections", v="@manifest"), dict(k="@build_exe", v="@manifest")],
                         results=[], empty="@manifest_screens", sections=[], bar="@choose_manifest")
            tiles.append(t)
        v["shelf"] = dict(tiles=tiles, x=x, w=total)
        g = self.game_by_id(ids[focus])
        if g:
            ready = g.a.ready()
            v["hint"] = g.a.status()["detail"]
            v["prompts"] = [self.prompt("confirm", "@open" if ready else "@go_build"), self.prompt("right", "@choose_game")]
            if ready:
                v["prompts"].append(self.prompt("play", "@play"))
            v["prompts"] += [self.prompt("social", "@quick_access"), self.prompt("back", "@quit")]
        else:
            v["hint"] = "@manifest_hint"
            v["prompts"] = [self.prompt("confirm", "@choose_manifest"), self.prompt("right", "@choose_game"), self.prompt("social", "@quick_access"), self.prompt("back", "@quit")]

    def _view_hub(self, v):
        g = self.game
        v["accent"], v["gameShort"], v["numeral"] = g.accent, g.short, g.m["numeral"]
        v["badge"] = badge(g)
        v["topline"] = g.a.status()["status"]
        v["hero"] = uri(g.a.hero())
        sec = self.section()
        v["tabs"] = [dict(id=s, label="@" + SECTION_TITLES[s], active=s == sec) for s in self.sections(g)]
        items = self.items()
        fi = self.focus_index(items)
        start = window(len(items), fi, ROWS_VISIBLE)
        rows = []
        for i in range(start, min(len(items), start + ROWS_VISIBLE)):
            it = items[i]
            foc = i == fi
            kind = it.get("kind", "action")
            cyc = kind == "cycler"
            value = it.get("value") or ""
            rows.append(dict(index=i, heading=kind == "heading", focused=foc, label=it.get("label", ""), mt=it.get("mt", 0), hold=kind == "hold", disabled=bool(it.get("disabled")),
                             missing=bool(it.get("missing")), value=(i18n.message("selected_option", name=value) if cyc and foc else value) if (cyc or not foc) else "", verb=(it.get("verb", "") if foc and not cyc else ""),
                             holdPct=self.hold if foc and kind == "hold" else 0))
        while rows and rows[-1]["heading"]:      # a group's title never stands alone at the bottom
            rows.pop()
        v["rows"] = rows
        v["more"] = dict(up=start > 0, down=start + ROWS_VISIBLE < len(items))
        it = items[fi] if items else {}
        d = it.get("detail") or dict(kicker="", title=it.get("label", ""), lead="", rows=[])
        v["detail"] = dict(kicker=d.get("kicker", ""), title=d.get("title", ""), lead=d.get("lead", ""),
                           rows=[dict(k=r["k"], v=r["v"], accent=bool(r.get("accent"))) for r in d.get("rows", [])],
                           results=self._cells(d.get("results", []) or []), primary=d.get("primary", ""), primaryG=self.glyph("confirm", True),
                           images=[uri(p) for p in d.get("images", []) if p], image=uri(d.get("image", "")), progress=d.get("progress", -1))
        v["hint"] = it.get("hint", "")
        prompts = []
        if it.get("kind") == "cycler":
            prompts.append(self.prompt("right", "@change"))
        elif it.get("verb"):
            prompts.append(self.prompt("confirm", it["verb"]))
        if it.get("replay") is not None:
            prompts.append(self.prompt("x", "@hide_result" if self.show_results else "@show_result"))
        prompts.append(self.prompt("back", "@games"))
        if g.a.ready():
            prompts.append(self.prompt("play", "@play"))
        prompts += [self.prompt("social", "@quick_access"), self.prompt("switchGame", "@switch_game")]
        v["prompts"] = prompts

    def _view_dialog(self, v):
        if self.confirm_kind == "exit":
            title, text = "@dialog.quit.title", "@dialog.quit.text"
        else:
            title, text = "@dialog.cancel.title", "@dialog.cancel.text"
        v["dialog"] = dict(title=title, text=text, options=[dict(label="@no", index=0, focused=self.exit_focus == 0), dict(label="@yes", index=1, focused=self.exit_focus == 1)])
        v["hint"] = "@dialog_hint"
        v["prompts"] = [self.prompt("confirm", "@confirm"), self.prompt("right", "@switch"), self.prompt("back", "@cancel")]

    def _view_drawer(self, v):
        items = self._drawer_items()
        v["drawer"] = dict(rows=[dict(index=i, label=it["label"], value=it["value"], focused=i == self.drawer_focus) for i, it in enumerate(items)])
        v["hint"] = "@drawer_hint"
        v["prompts"] = [self.prompt("confirm", "@open"), self.prompt("back", "@close")]

    def _view_fighters(self, v):
        items = self._fighter_list()
        chosen = self.game.a.chosen_fighter()
        main = self.game.a.main_fighter()
        v["grid"] = dict(main=main, cells=[dict(index=i, name=f["name"], main=f["name"] == main, image=uri(f["image"]), random=f["key"] == "random", focused=i == self.grid_focus, chosen=f["key"] == chosen)
                                           for i, f in enumerate(items)],
                         mosaic=[uri(f["image"]) for f in items[1:5] if f["image"]])
        v["hint"] = "@fighter_hint"
        v["prompts"] = [self.prompt("confirm", "@choose"), self.prompt("back", "@close")]

    def _view_osk(self, v):
        o = self.osk
        rows = [[dict(label=ch, row=r, col=c, focused=o["row"] == r and o["col"] == c) for c, ch in enumerate(line)] for r, line in enumerate(OSK)]
        rows.append([dict(label="@" + label, row=len(OSK), col=c, focused=o["row"] == len(OSK) and o["col"] == c) for c, (_k, label) in enumerate(OSK_ACTIONS)])
        v["osk"] = dict(rows=rows, text=o["text"] + "_", title=o["title"])
        v["hint"] = "@osk_hint"
        v["prompts"] = [self.prompt("confirm", "@enter"), self.prompt("x", "@osk.delete"), self.prompt("play", "@osk.done"), self.prompt("back", "@cancel")]

    def _view_picker(self, v):
        p = self.picker
        entries = self._picker_entries()
        start = window(len(entries), p["focus"], PICKER_VISIBLE)
        rows = [dict(index=i, name=e["name"], kind=e["kind"], focused=i == p["focus"]) for i, e in enumerate(entries[start:start + PICKER_VISIBLE], start)]
        v["picker"] = dict(rows=rows, title=p["title"], path=p["dir"] or "@picker.this_pc", up=start > 0, down=start + PICKER_VISIBLE < len(entries))
        v["hint"] = "@picker_files_hint" if p["kind"] == "file" else "@picker_folder_hint"
        v["prompts"] = [self.prompt("confirm", "@open"), self.prompt("back", "@cancel")]

    # ------------------------------------------------------------------------------------ mouse
    def click_row(self, index):
        items = self.items()
        if 0 <= index < len(items) and items[index].get("kind") != "heading":
            already = self.focus_index(items) == index
            self.focus[self.key()] = index
            if already or items[index].get("kind") != "hold":
                if items[index].get("kind") == "hold":
                    self.say("@hold_hint")
                else:
                    self._guard(self._activate, items[index])

    def _guard(self, fn, *args):
        try:
            fn(*args)
        except Exception as e:  # noqa: BLE001 -- as in act()
            self.say(i18n.error_message(e) or e.__class__.__name__)

    def click_tile(self, index):
        if self.start_focus == index:
            self.act("confirm")
        else:
            self.start_focus = index

    def click_tab(self, section):
        if section in self.sections():
            self.sec[self.game.id] = section

    def click_primary(self):
        items = self.items()
        if items:
            self._guard(self._activate, items[self.focus_index(items)])

    def click_cell(self, index):
        self.grid_focus = index
        self.act("confirm")

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

    def click_key(self, row, col):
        if self.overlay == "osk":
            self.osk["row"], self.osk["col"] = row, col
            self.act("confirm")
