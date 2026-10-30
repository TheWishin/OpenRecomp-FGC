"""Tekken 5 DR: the installed T5DR Online's own Python (launcher/core.py, replays.py, lobby/t5lobby) does the work.

Nothing of it is copied: OpenRecomp-FGC imports it from the player's install. Pictures come from that install's cache
(read from the player's own built game by fighter_art.py) and stay on the PC.
"""
import collections
import glob
import importlib
import json
import os
import queue
import re
import subprocess
import threading

from .base import Adapter, NO_WINDOW, add_path, expand_locations
from ..manifest import art_dir

DISPLAY = [("window", "Window"), ("window1080", "Window 1080p"), ("window1440", "Window 1440p"),
           ("maximized", "Maximized"), ("borderless", "Borderless")]
RES_NAMES = {"lowest": "Lowest (0.5x)", "lower": "Lower (0.75x)", "native": "Native (720p)", "1080p": "1080p",
             "1440p": "1440p", "4k": "4K", "auto": "Auto"}
ON_OFF = [("on", "On"), ("off", "Off")]
YES_NO = [(False, "Off"), (True, "On")]
RANK_TAG = re.compile(r"\s*\[\d+\]$")


def version_key(root):
    try:
        with open(os.path.join(root, "release.json"), encoding="utf-8") as f:
            parts = json.load(f).get("version", "0").split(".")
        return tuple(int(p) for p in parts)
    except (OSError, ValueError, AttributeError):
        return (0,)


def find_root(manifest, config):
    """The newest installed T5DR Online with a built game; else the newest install."""
    chosen = (config.get("roots") or {}).get(manifest["id"]) or os.environ.get("OPENRECOMP_T5DR_ROOT")
    if chosen:
        return chosen if os.path.isfile(os.path.join(chosen, "launcher", "core.py")) else None
    found = [p for p in expand_locations(manifest.get("locations", []))
             if os.path.isfile(os.path.join(p, "launcher", "core.py"))]
    if not found:
        return None
    built = [p for p in found if os.path.isfile(os.path.join(p, "runtime", "t5dr.exe"))]
    return max(built or found, key=version_key)


class T5DR(Adapter):
    native_label = "T5DR Online launcher"

    def __init__(self, manifest, config, root, core=None, replays_mod=None):
        super().__init__(manifest, config)
        self.root = root
        if core is None:
            add_path(os.path.join(root, "lobby"))
            add_path(os.path.join(root, "tools"))
            add_path(os.path.join(root, "launcher"))
            core = importlib.import_module("core")
            replays_mod = importlib.import_module("replays")
        self.core = core
        self.rp = replays_mod
        self.s = core.Settings()
        self.game = None
        self.build = None
        self.build_steps = {}
        self.build_step = ""
        self.build_fraction = 0.0
        self.build_line = ""
        self.last_result = ""
        self._state = None
        self._replays = None
        self._fighters = None
        self._hero_busy = False

    def found(self):
        return True

    def state(self, fresh=False):
        if self._state is None or fresh:
            self._state = self.core.game_state(self.s.out_dir)
        return self._state

    def ready(self):
        return bool(self.state()["ok"])

    def release(self):
        try:
            with open(os.path.join(self.root, "release.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def status(self):
        st = self.state()
        entries = self.replay_entries()
        last = entries[0].when.strftime("%d.%m., %H:%M") if entries and entries[0].when else "Never"
        version = self.release().get("version") or "dev"
        if st["ok"]:
            status, detail = "Ready", "Your game runs locally on this PC. You pick your fighter in the game."
        elif st["needs_rebuild"]:
            status, detail = "Build again", "This version changes the game code: build once, about 2 minutes."
        else:
            status, detail = "Not built yet", "Choose your package and license in the Build section."
        return dict(status=status, version=f"v{version}", players="Lobby and ranked", last=last, detail=detail)

    # ---------------------------------------------------------------- pictures
    def face(self, gid):
        path = os.path.join(self.s.out_dir, "cache", "fighters", f"face_{gid:02d}.png")
        return path if os.path.isfile(path) else ""

    def hero(self):
        """The full-figure render of the player's main, read once from their own game into the user folder."""
        gid = self.main_id()
        if gid is None:
            gid = 9                                  # Jin
        path = os.path.join(art_dir("t5dr"), f"hero_{gid:02d}.png")
        if os.path.isfile(path):
            return path
        if not self._hero_busy and self.state()["built"]:
            self._hero_busy = True
            threading.Thread(target=self._make_hero, args=(gid, path), daemon=True).start()
        return ""

    def _make_hero(self, gid, path):
        try:
            fa = importlib.import_module("t5lobby.fighter_art")
            src = fa.ra.find_sources(self.s.out_dir)
            if not src:
                return
            dxt = fa.render_dxt(*src, gid, rows=fa.TEX_W)
            rgba = fa.dxt5_square(dxt, fa.TEX_W, 0, 0, fa.TEX_W)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fa._write(path, fa.ra.png_bytes(rgba, fa.TEX_W, fa.TEX_W))  # noqa: SLF001 -- the module's atomic write
        except Exception as e:  # noqa: BLE001 -- a missing picture must never stop the launcher
            self.problem = f"Picture not read: {e}"

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        if not self.ready():
            raise RuntimeError(self.status()["detail"])
        if self.running():
            raise RuntimeError("The game is already running.")
        self.game = self.core.GameRun(self.s.out_dir, self.s)
        return self.game.start(extra_env=extra_env)

    def running(self):
        return bool(self.game and self.game.running())

    def stop(self):
        if self.game:
            self.game.stop()

    def _exe_launcher(self, *args):
        exe = os.path.join(self.root, "T5DR Online.exe")
        if os.path.isfile(exe):
            cmd = [exe]
        else:
            script = os.path.join(self.root, "launcher", "t5dr_launcher.pyw")
            cmd = [self.core.sys.executable, script]
        return subprocess.Popen(cmd + list(args), cwd=self.root, creationflags=NO_WINDOW)

    def open_native(self):
        self._exe_launcher()

    # ---------------------------------------------------------------- settings
    def settings(self):
        s = self.s
        res = [(k, RES_NAMES.get(k, k)) for k in self.core.INTERNAL_RES_LABELS]
        delay = [("auto", "Auto"), ("0", "0 frames"), ("1", "1 frame"), ("2", "2 frames")]
        return [
            dict(id="display", label="Display", options=DISPLAY, value=s["display"],
                 hint="How the game window opens. F11 and Alt+Enter work in the game too.",
                 lead="Borderless fills the screen, a window keeps the PC usable."),
            dict(id="internal_res", label="Internal resolution", options=res, value=s["internal_res"],
                 hint="How sharply the game is rendered.",
                 lead="Higher steps need more graphics power. Online, each player may use another step."),
            dict(id="vsync", label="V-Sync", options=ON_OFF, value=s["vsync"],
                 hint="Off: least lag, the picture may tear.", lead="Only changes how the picture reaches the screen."),
            dict(id="shadows", label="Shadows", options=ON_OFF, value=s["shadows"],
                 hint="Shadows of fighters and stage.", lead="Off helps weak graphics cards."),
            dict(id="effects", label="Effects", options=ON_OFF, value=s["effects"],
                 hint="Hit sparks, flames, smoke, mist, waterfalls.", lead="Off helps weak graphics cards."),
            dict(id="stage_blur", label="Stage blur", options=ON_OFF, value=s["stage_blur"],
                 hint="Soft focus and glow of some stages.", lead="Looks only, no effect online."),
            dict(id="input_delay", label="Online input delay", options=delay, value=str(s["input_delay"]),
                 hint="Auto picks by ping. Both players set it.", lead="More delay means less rollback. In ranked the server sets it."),
            dict(id="training", label="Training display", options=[("off", "Off"), ("inputs", "Inputs"), ("frames", "Inputs + frames")],
                 value=s["training"], hint="Inputs and frame data in Practice. F2 switches in the game.", lead="Shows startup and advantage of every move."),
            dict(id="practice", label="Practice tools", options=YES_NO, value=bool(s["practice"]),
                 hint="SELECT combos, dummy and recordings in Practice.", lead="Offline in Practice only."),
            dict(id="always_left", label="Always left", options=YES_NO, value=bool(s["always_left"]),
                 hint="As P2 this PC shows the fight mirrored, you stand on the left.", lead="Only the picture on this PC changes."),
            dict(id="mute", label="Mute", options=YES_NO, value=bool(s["mute"]), hint="Mutes the game sound.", lead="Mutes the game sound."),
            dict(id="replays", label="Save replays", options=YES_NO, value=bool(s["replays"]),
                 hint="Online matches are saved as replays on this PC.", lead="A match takes only a few KB."),
            dict(id="unlock_stages", label="Old stages offline", options=YES_NO, value=bool(s["unlock_stages"]),
                 hint="Tekken 5 stages without clearing Arcade. Your save stays as it is.", lead="Offline only."),
            dict(id="unlock_items", label="Free items offline", options=YES_NO, value=bool(s["unlock_items"]),
                 hint="All shop items free. Your save is backed up first.", lead="Offline only."),
        ]

    def set_setting(self, sid, value):
        self.s[sid] = value
        if sid == "internal_res":
            self.s["internal_res_set"] = True
        self.s.save()

    def quick_settings(self):
        return ["display", "internal_res"]

    def text_value(self, tid):
        return self.s["nickname"] if tid == "nickname" else ""

    def set_text_value(self, tid, value):
        if tid == "nickname":
            self.s["nickname"] = value
            self.s.save()

    # ---------------------------------------------------------------- online: the T5DR launcher runs the lobby
    def online_items(self):
        chosen = self.fighter_name(self.chosen_fighter())
        main = self.fighter_name_id(self.main_id())
        return [
            dict(kind="heading", label="Your fighter"),
            dict(kind="action", id="fighter", label="Fighter", value=chosen, verb="Change", opens="fighters",
                 hint="Used if you do not pick in the game in time.",
                 detail=dict(kicker="Your fighter", title=chosen, image=self.fighter_image(self.chosen_fighter()),
                             lead="After a match is found you pick in the game (30 s, Select = random). The fighter here is used if you do not pick in time.",
                             rows=[dict(k="Your main", v=main or "none yet"),
                                   dict(k="Costume", v="Confirm button in the game"), dict(k="In a ranked set", v="Locked here")])),
            dict(kind="heading", label="Play", mt=12),
            dict(kind="action", id="ranked", label="Ranked", verb="Search",
                 hint="The search runs in the T5DR launcher, OpenRecomp-FGC opens it for you.",
                 detail=dict(kicker="T5DR Online", title="Ranked", lead="Counts for your rank. The search runs in the T5DR launcher, where you also see the match and ready check.",
                             rows=[dict(k="Mode", v="Best of 3"), dict(k="Sides", v="From the server"), dict(k="Stage", v="Random")], primary="Search")),
            dict(kind="action", id="casual", label="Quick Match", verb="Search",
                 hint="The search runs in the T5DR launcher, OpenRecomp-FGC opens it for you.",
                 detail=dict(kicker="T5DR Online", title="Quick Match", lead="Unrated, by ping. The search runs in the T5DR launcher.",
                             rows=[dict(k="Rating", v="None"), dict(k="Rematch", v="Yes")], primary="Search")),
            dict(kind="action", id="lobby", label="Lobby, rooms, friends", verb="Open",
                 hint="The T5DR launcher with lobby, rooms, tournaments, friends and leaderboard.",
                 detail=dict(kicker="T5DR Online", title="Lobby", lead="Rooms, tournaments, friends, spectating and leaderboard stay in the T5DR launcher.",
                             rows=[dict(k="State", v="Not in OpenRecomp-FGC yet")], primary="Open")),
            dict(kind="action", id="nickname", label="Player name", value=self.s["nickname"] or "none", verb="Change", opens="text:nickname",
                 hint="Your name for the lobby. The on-screen keyboard is enough.",
                 detail=dict(kicker="Your profile", title="Player name", lead="How you appear in the lobby.", rows=[dict(k="Current", v=self.s["nickname"] or "none")])),
        ]

    def search_on_start_works(self):
        """Up to 1.1.9 `--search` asks for the game's state before the launcher has read it and always says "build first"."""
        return version_key(self.root) > (1, 1, 9)

    def run_online(self, item_id):
        if item_id in ("ranked", "casual"):
            name = "Ranked" if item_id == "ranked" else "Quick Match"
            if self.search_on_start_works():
                self._exe_launcher("--search", item_id)
                return f"T5DR launcher is starting the search: {name}."
            self._exe_launcher()
            return f"T5DR launcher is opening. Start {name} there."
        if item_id == "lobby":
            self._exe_launcher()
            return "T5DR launcher is opening."
        return ""

    # ---------------------------------------------------------------- fighters
    def _fighter_table(self):
        if self._fighters is None:
            path = os.path.join(self.root, "lobby", "t5lobby", "data", "fighters.json")
            try:
                with open(path, encoding="utf-8") as f:
                    self._fighters = json.load(f)["fighters"]
            except (OSError, ValueError, KeyError):
                self._fighters = []
        return self._fighters

    def fighters(self):
        picks = [f for f in self._fighter_table() if not f.get("boss") and not f.get("unverified")]
        picks.sort(key=lambda f: f["name"].casefold())
        return [dict(key=f["key"], name=f["name"], image=self.face(f["id"])) for f in picks]

    def fighter_name(self, key):
        return next((f["name"] for f in self._fighter_table() if f["key"] == key), "Random")

    def fighter_name_id(self, gid):
        return next((f["name"] for f in self._fighter_table() if f["id"] == gid), "")

    def fighter_image(self, key):
        gid = next((f["id"] for f in self._fighter_table() if f["key"] == key), None)
        return self.face(gid) if gid is not None else ""

    def online_cfg_path(self):
        base = os.environ.get("T5_ONLINE_DIR")
        if base:
            return os.path.join(base, "online.json")
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "T5DROnline", "online.json")

    def _online_cfg(self):
        try:
            with open(self.online_cfg_path(), encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
        except (OSError, ValueError):
            return {}

    def chosen_fighter(self):
        return self._online_cfg().get("char") or "random"

    def set_fighter(self, key):
        """The same field of the same file the T5DR launcher's character grid writes; the rest stays as it is."""
        cfg = self._online_cfg()
        cfg["char"] = key
        path = self.online_cfg_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".openrecomp.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        os.replace(tmp, path)

    def main_id(self):
        """The fighter of most of this PC's replays (the lobby's "main" needs a login)."""
        counts = collections.Counter()
        for e in self.replay_entries():
            gid = e.p1 if e.slot == 0 else e.p2
            if isinstance(gid, int):
                counts[gid] += 1
        return counts.most_common(1)[0][0] if counts else None

    def main_fighter(self):
        return self.fighter_name_id(self.main_id())

    def recent_results(self):
        out = []
        for e in self.replay_entries():
            if e.complete and e.won is not None:
                out.append("W" if e.won else "L")
            if len(out) == 5:
                break
        return out

    # ---------------------------------------------------------------- replays
    def replay_entries(self):
        if self._replays is None:
            try:
                self._replays = self.rp.list_replays(self.s.replay_dir)
            except OSError:
                self._replays = []
        return self._replays

    def replays(self):
        out = []
        for i, e in enumerate(self.replay_entries()):
            a, b = self.rp.fighter_name(e.p1), self.rp.fighter_name(e.p2)
            score = f"{e.score[0]}:{e.score[1]}" if e.score else ""
            result = ("Win " if e.won else "Loss ") + score if e.won is not None else (score or "Open")
            opponent = RANK_TAG.sub("", e.opponent or "") or "Unknown"
            when = e.when.strftime("%d.%m.%Y, %H:%M") if e.when else "?"
            out.append(dict(id=str(i), label=f"{a} – {b}", when=e.when.strftime("%H:%M") if e.when else "",
                            date=when, group=f"{e.when.strftime('%d.%m.') if e.when else '?'} · {opponent}", opponent=opponent,
                            netcode="Rollback" if e.mode == "rollback" else "Lockstep", result=result,
                            images=[self.face(e.p1), self.face(e.p2)]))
        return out

    def play_replay(self, replay_id, extra_env=None):
        e = self.replay_entries()[int(replay_id)]
        env = self.rp.playback_env(e.path, match=e.index)
        env.update(extra_env or {})
        return self.start(extra_env=env)

    # ---------------------------------------------------------------- build
    def sources(self):
        home = os.path.expanduser("~")
        dirs = [os.path.dirname(self.s["pkg"]) if self.s["pkg"] else "", os.path.join(home, "Downloads"), os.path.join(home, "Desktop"), self.root]
        dirs = [d for d in dirs if d]
        pkg_ok, _level, pkg_text = self.core.describe_pkg(self.s["pkg"], self.s.out_dir) if self.s["pkg"] else (False, "", "")
        rap = self.s["rap"]
        rap_ok = bool(rap) and os.path.isfile(rap)
        return [
            dict(id="pkg", label="Package (.pkg)", value="Found" if pkg_ok else "Missing", ok=pkg_ok, kind="file", exts=[".pkg"], dirs=dirs,
                 hint="Your game package from your own account. Nothing leaves this PC.", note=pkg_text),
            dict(id="rap", label="License (.rap)", value="Found" if rap_ok else "Missing", ok=rap_ok, kind="file", exts=[".rap"], dirs=dirs,
                 hint="Your license file from your own account. Nothing leaves this PC.", note=""),
        ]

    def set_source(self, sid, path):
        self.s[sid] = path
        self.s.save()
        self._state = None
        return ""

    def build_options(self):
        return [dict(id="low_priority", label="Keep the PC responsive", options=YES_NO, value=bool(self.s["low_priority"]),
                     hint="The build is slower, the PC stays usable.", lead="The build is slower, but the PC stays usable meanwhile.")]

    def build_ready(self):
        if not self.s["pkg"] or not self.s["rap"]:
            return "Choose package and license first."
        return ""

    def build_start(self, force=False):
        self.build_steps = {}
        self.build_step = ""
        self.build_fraction = 0.0
        self.last_result = ""
        self.build = self.core.BuildRun(self.s["pkg"], self.s["rap"], self.s.out_dir, force=force, low_priority=bool(self.s["low_priority"]))
        own_python = os.path.join(self.root, "python", "python.exe")      # the build's tools run on the install's Python
        if os.path.isfile(own_python):
            self.build.cmd[0] = own_python
        self.build.start()

    def _pump_build(self):
        if not self.build:
            return
        while True:
            try:
                ev = self.build.events.get_nowait()
            except queue.Empty:
                return
            kind, value = ev[0], ev[1] if len(ev) > 1 else None
            if kind == "step":
                if self.build_step:
                    self.build_steps[self.build_step] = "Done"
                self.build_step = value
                self.build_steps[value] = "Running"
            elif kind == "skip":
                self.build_steps[value] = "Done"
            elif kind == "sub":
                self.build_fraction = float(value)
            elif kind == "line":
                self.build_line = str(value)
            elif kind == "error":
                self.last_result = str(value)
            elif kind == "end":
                if value == 0:
                    if self.build_step:
                        self.build_steps[self.build_step] = "Done"
                    self.last_result = "Build finished."
                elif value == -1:
                    self.last_result = "Cancelled."
                elif not self.last_result:
                    self.last_result = f"The build failed. Log: {self.build.log_path}"
                self.build = None
                self._state = None

    def build_state(self):
        self._pump_build()
        names = list(self.core.STEP_TITLES)
        steps = [dict(k=self.core.STEP_TITLES[n], v=self.build_steps.get(n, "Open")) for n in names]
        done = sum(1 for n in names if self.build_steps.get(n) == "Done")
        return dict(running=self.build is not None, fraction=done / len(names) if names else 0.0,
                    title=self.core.STEP_TITLES.get(self.build_step, ""), steps=steps, result=self.last_result, line=self.build_line)

    def build_cancel(self):
        if self.build:
            self.build.cancel()


def installed_copies(manifest):
    return [p for loc in manifest.get("locations", []) for p in glob.glob(os.path.expandvars(loc))]
