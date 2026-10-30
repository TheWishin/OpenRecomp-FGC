"""Tekken 5 DR: the installed T5DR Online's own Python (launcher/core.py, replays.py, lobby/t5lobby) does the work.

Nothing of it is copied: OpenRecomp-FGC imports it from the player's install. Pictures come from that install's cache
(read from the player's own built game by fighter_art.py) and stay on the PC.
"""
import collections
import importlib.util
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading

from .base import Adapter, NO_WINDOW, add_path, expand_locations
from .t5_controls import Controls
from .support import T5Support
from .t5_online import Online
from ..manifest import art_dir

DISPLAY = [("window", "@display.window"), ("window1080", "@display.1080"), ("window1440", "@display.1440"),
           ("maximized", "@display.max"), ("borderless", "@display.borderless")]
RES_NAMES = {"lowest": "@resolution.lowest", "lower": "@resolution.lower", "native": "@resolution.native", "1080p": "1080p",
             "1440p": "1440p", "4k": "4K", "auto": "@resolution.auto"}
ON_OFF = [("on", "@on"), ("off", "@off")]
YES_NO = [(False, "@off"), (True, "@on")]
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


def _runtime_path(root, name):
    path = os.path.realpath(os.path.join(root, "launcher", name + ".py"))
    cached = sys.modules.get(name)
    if cached is not None:
        origin = os.path.realpath(getattr(cached, "__file__", ""))
        if os.path.normcase(origin) != os.path.normcase(path):
            raise ImportError("@not_ready")
    return path


def load_runtime(root, name):
    """Never reuse a runtime module from a different selected install."""
    path = _runtime_path(root, name)
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("@not_ready")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


class T5DR(Controls, T5Support, Online, Adapter):
    native_label = "@t5.native_label"

    def __init__(self, manifest, config, root, core=None, replays_mod=None):
        super().__init__(manifest, config)
        self.root = root
        if core is None:
            # A core may itself import replays: reject conflicting caches before either executes.
            for name in ("core", "replays"):
                _runtime_path(root, name)
            add_path(os.path.join(root, "lobby"))
            add_path(os.path.join(root, "tools"))
            add_path(os.path.join(root, "launcher"))
            core = load_runtime(root, "core")
            replays_mod = load_runtime(root, "replays")
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
                release = json.load(f)
            return release if isinstance(release, dict) else {}
        except (OSError, ValueError):
            return {}

    def status(self):
        st = self.state()
        entries = self.replay_entries()
        last = entries[0].when.strftime("%d.%m., %H:%M") if entries and entries[0].when else "@never"
        version = self.release().get("version") or "@development"
        if st["ok"]:
            status, detail = "@ready", "@t5.ready_detail"
        elif st["needs_rebuild"]:
            status, detail = "@build_again", "@t5.rebuild_detail"
        else:
            status, detail = "@not_built", "@t5.build_detail"
        return dict(status=status, version=self.message("version_tag", version=version), players="@lobby_ranked", last=last, detail=detail)

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
            self.problem = self.message("picture_error", error=str(e))

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        if not self.ready():
            raise RuntimeError(self.status()["detail"])
        if self.running():
            raise RuntimeError("@already_running")
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
        delay = [("auto", "@resolution.auto"), ("0", "@delay.zero"), ("1", "@delay.one"), ("2", "@delay.two")]
        return [
            dict(id="display", label="@display", options=DISPLAY, value=s["display"],
                 hint="@display.hint",
                 lead="@display.lead"),
            dict(id="internal_res", label="@internal_resolution", options=res, value=s["internal_res"],
                 hint="@resolution.hint",
                 lead="@resolution.t5_lead"),
            dict(id="vsync", label="@vsync", options=ON_OFF, value=s["vsync"],
                 hint="@vsync.hint", lead="@vsync.lead"),
            dict(id="shadows", label="@shadows", options=ON_OFF, value=s["shadows"],
                 hint="@shadows.hint", lead="@weak_gpu"),
            dict(id="effects", label="@effects", options=ON_OFF, value=s["effects"],
                 hint="@effects.hint", lead="@weak_gpu"),
            dict(id="stage_blur", label="@stage_blur", options=ON_OFF, value=s["stage_blur"],
                 hint="@stage_blur.hint", lead="@visual_only"),
            dict(id="input_delay", label="@input_delay", options=delay, value=str(s["input_delay"]),
                 hint="@input_delay.hint", lead="@input_delay.lead"),
            dict(id="training", label="@training_display", options=[("off", "@off"), ("inputs", "@inputs"), ("frames", "@inputs_frames")],
                 value=s["training"], hint="@training.hint", lead="@training.lead"),
            dict(id="practice", label="@practice_tools", options=YES_NO, value=bool(s["practice"]),
                 hint="@practice.hint", lead="@practice.lead"),
            dict(id="always_left", label="@always_left", options=YES_NO, value=bool(s["always_left"]),
                 hint="@always_left.hint", lead="@always_left.lead"),
            dict(id="mute", label="@mute", options=YES_NO, value=bool(s["mute"]), hint="@mute.hint", lead="@mute.hint"),
            dict(id="replays", label="@save_replays", options=YES_NO, value=bool(s["replays"]),
                 hint="@save_replays.hint", lead="@save_replays.lead"),
            dict(id="unlock_stages", label="@old_stages", options=YES_NO, value=bool(s["unlock_stages"]),
                 hint="@old_stages.hint", lead="@offline_only"),
            dict(id="unlock_items", label="@free_items", options=YES_NO, value=bool(s["unlock_items"]),
                 hint="@free_items.hint", lead="@offline_only"),
        ]

    def set_setting(self, sid, value):
        self.s[sid] = value
        if sid == "internal_res":
            self.s["internal_res_set"] = True
        self.s.save()

    def quick_settings(self):
        return ["display", "internal_res"]

    def text_value(self, tid):
        if tid.startswith("online_"):
            return self.online_text_value(tid)
        return self.s["nickname"] if tid == "nickname" else ""

    def set_text_value(self, tid, value):
        if tid.startswith("online_"):
            self.set_online_text_value(tid, value)
            return
        if tid == "nickname":
            self.s["nickname"] = value
            self.s.save()

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
        return next((f["name"] for f in self._fighter_table() if f["key"] == key), "@random")

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
        path = self.online_cfg_path()
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
        except FileNotFoundError:
            cfg = {}
        if not isinstance(cfg, dict):
            raise ValueError("@not_ready")
        cfg["char"] = key
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path),
                                             prefix=".openrecomp-", suffix=".tmp", delete=False) as f:
                tmp = f.name
                json.dump(cfg, f, indent=1)
            os.replace(tmp, path)
        finally:
            if tmp is not None and os.path.exists(tmp):
                os.unlink(tmp)

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
            result = self.message("replay_win" if e.won else "replay_loss", score=score) if e.won is not None else (score or "@pending")
            opponent = RANK_TAG.sub("", e.opponent or "") or "@unknown_opponent"
            when = e.when.strftime("%d.%m.%Y, %H:%M") if e.when else "?"
            out.append(dict(id=str(i), label=f"{a} – {b}", when=e.when.strftime("%H:%M") if e.when else "",
                            date=when, group=self.message("replay_group", date=e.when.strftime("%d.%m.") if e.when else "?", name=opponent), opponent=opponent,
                            netcode="@rollback" if e.mode == "rollback" else "@lockstep", result=result,
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
            dict(id="pkg", label="@package", value="@found" if pkg_ok else "@missing", ok=pkg_ok, kind="file", exts=[".pkg"], dirs=dirs,
                 hint="@package.hint", note=pkg_text),
            dict(id="rap", label="@license", value="@found" if rap_ok else "@missing", ok=rap_ok, kind="file", exts=[".rap"], dirs=dirs,
                 hint="@license.hint", note=""),
        ]

    def set_source(self, sid, path):
        self.s[sid] = path
        self.s.save()
        self._state = None
        return ""

    def build_options(self):
        return [dict(id="low_priority", label="@responsive", options=YES_NO, value=bool(self.s["low_priority"]),
                     hint="@responsive.hint", lead="@responsive.lead")]

    def build_ready(self):
        if not self.s["pkg"] or not self.s["rap"]:
            return "@choose_package_license"
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
                    self.build_steps[self.build_step] = "@osk.done"
                self.build_step = value
                self.build_steps[value] = "@running"
            elif kind == "skip":
                self.build_steps[value] = "@osk.done"
            elif kind == "sub":
                self.build_fraction = float(value)
            elif kind == "line":
                self.build_line = str(value)
            elif kind == "error":
                self.last_result = str(value)
            elif kind == "end":
                if value == 0:
                    if self.build_step:
                        self.build_steps[self.build_step] = "@osk.done"
                    self.last_result = "@build_finished"
                elif value == -1:
                    self.last_result = "@cancelled"
                elif not self.last_result:
                    self.last_result = self.message("build_failed", path=self.build.log_path)
                self.build = None
                self._state = None

    def build_state(self):
        self._pump_build()
        names = list(self.core.STEP_TITLES)
        steps = [dict(k=self.core.STEP_TITLES[n], v=self.build_steps.get(n, "@pending")) for n in names]
        done = sum(1 for n in names if self.build_steps.get(n) == "@osk.done")
        return dict(running=self.build is not None, fraction=done / len(names) if names else 0.0,
                    title=self.core.STEP_TITLES.get(self.build_step, ""), steps=steps, result=self.last_result, line=self.build_line)

    def build_cancel(self):
        if self.build:
            self.build.cancel()
