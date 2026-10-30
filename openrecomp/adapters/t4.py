"""Tekken 4 (PS2 recomp): the project's own launcher core (launcher/t4core.py) does the work; nothing of it is copied."""
import glob
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time

from .base import Adapter, ProcessBuild, add_path, expand_locations, onoff
from .t4_online import T4Online
from .t4_install import install_root
from ..manifest import art_dir, save_config

STEP_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(\w+)\s+-\s+(.*)$")
GRAPHICS_OPTIONS = {
    "aa": [("off", "@off"), ("fxaa", "@aa.fxaa"), ("smaa", "@aa.smaa"),
           ("ssaa2", "@aa.ssaa2"), ("ssaa3", "@aa.ssaa3"), ("ssaa4", "@aa.ssaa4"),
           ("msaa2", "@aa.msaa2"), ("msaa4", "@aa.msaa4"), ("msaa8", "@aa.msaa8"),
           ("ssaa2+fxaa", "@aa.ssaa2_fxaa")],
    "hud": [("soft", "@hud.soft"), ("sharp", "@hud.sharp")],
    "anisotropic": [("1", "@off"), ("2", "@anisotropic.two"), ("4", "@anisotropic.four"),
                    ("8", "@anisotropic.eight"), ("16", "@anisotropic.sixteen")],
}


def find_root(manifest, config):
    chosen = (config.get("roots") or {}).get(manifest["id"]) or os.environ.get("OPENRECOMP_T4_ROOT")
    for path in ([chosen] if chosen else []) + expand_locations(manifest.get("locations", [])):
        root = install_root(path)
        if root:
            return root
    return None


def load_core(root):
    """A newly selected install must not reuse the previous install's cached t4core."""
    launcher = os.path.join(os.path.realpath(root), "launcher")
    path = os.path.join(launcher, "t4core.py")
    name = "_openrecomp_t4core_" + hashlib.sha256(os.path.normcase(path).encode("utf-8")).hexdigest()
    if launcher in sys.path:
        sys.path.remove(launcher)
    add_path(launcher)
    if name in sys.modules:
        core = sys.modules[name]
        sys.modules["t4core"] = core
        return core
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("@t4.install_invalid")
    core = importlib.util.module_from_spec(spec)
    previous = sys.modules.get("t4core")
    sys.modules[name] = sys.modules["t4core"] = core
    try:
        spec.loader.exec_module(core)
    except BaseException:
        sys.modules.pop(name, None)
        if previous is None:
            sys.modules.pop("t4core", None)
        else:
            sys.modules["t4core"] = previous
        raise
    return core


class T4(T4Online, Adapter):
    native_label = "@t4.native_label"

    def __init__(self, manifest, config, root, core=None):
        super().__init__(manifest, config)
        self.root = root
        if core is None:
            core = load_core(root)
        self.core = core
        self.s = core.load_settings()
        self._play_lock = threading.RLock()
        self.run = None
        self.build = None
        self.build_lines = []
        self.build_step = ""
        self.build_step_no = (0, 0)
        self.build_done = {}
        self.iso_note = ""
        self.last_result = ""

    def found(self):
        return True

    def problems(self):
        return self.core.play_problems(self.s)

    def ready(self):
        return not self.problems()

    def status(self):
        problems = self.problems()
        last = self.s.get("last_run") or {}
        return dict(status="@ready" if not problems else "@not_built", version="SLUS-20328",
                    players="@not_yet", last=friendly_time(last.get("time", "")),
                    detail=problems[0] if problems else "@t4.ready_detail")

    def hero(self):
        """A picture the player made of their own game: <user folder>/art/t4/hero.png (never shipped)."""
        path = os.path.join(art_dir("t4"), "hero.png")
        return path if os.path.isfile(path) else ""

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        with self._play_lock:
            if (getattr(self, "_online_phase", "") in ("starting", "playing")
                    and not (extra_env or {}).get("TEKKEN4_NET")):
                raise RuntimeError("@online.game_running")
            proc = getattr(self.run, "proc", None)
            if callable(getattr(proc, "poll", None)) and self.running():
                raise RuntimeError("@online.game_running")
            return self._start(extra_env)

    def _start(self, extra_env=None):
        problems = self.problems()
        if problems:
            raise RuntimeError(problems[0])
        holder = self.core.run_lock_holder()
        if holder:
            raise RuntimeError(self.message("t4.locked", holder=holder))
        run = self.core.GameRun(self.s)
        real_env = self.core.game_env
        graphics = self._graphics_values()

        def env_with_extra(s, exe=None):
            env = real_env(s, exe)
            if self.core.graphics_support(exe)["aa"]:
                env["TEKKEN4_AA"] = graphics["aa"]
            env["TEKKEN4_HUD"] = graphics["hud"]
            env["TEKKEN4_ANISO"] = graphics["anisotropic"]
            env.update(extra_env or {})
            return env
        self.core.game_env = env_with_extra
        try:
            run.start()
        finally:
            self.core.game_env = real_env
        self.core.take_run_lock("openrecomp")
        self.run = run
        self._run_waiter = threading.Thread(target=self._wait, args=(run,), daemon=True)
        self._run_waiter.start()
        return run.proc.pid

    def _wait(self, run):
        record = run.wait()
        self.core.release_run_lock()
        self.s["last_run"] = record
        self.core.save_settings(self.s)

    def running(self):
        return bool(self.run and self.run.proc and self.run.proc.poll() is None)

    def stop(self):
        if self.run:
            self.run.stop()

    def open_native(self):
        script = os.path.join(self.root, "launcher", "t4_launcher.pyw")
        python = self.core.find_python()
        self.core.subprocess.Popen([python, script], cwd=self.root, creationflags=self.core.NO_WINDOW)

    # ---------------------------------------------------------------- settings
    def _graphics_values(self):
        # The core only saves boolean AA; advanced choices belong to this launcher's config.
        saved = self.config.get("t4_graphics") or {}
        defaults = dict(aa=GRAPHICS_OPTIONS["aa"][1 if self.s.get("aa", True) else 0][0],
                        hud=GRAPHICS_OPTIONS["hud"][0][0], anisotropic=GRAPHICS_OPTIONS["anisotropic"][2][0])
        return {sid: saved.get(sid, default) if saved.get(sid, default) in [v for v, _label in GRAPHICS_OPTIONS[sid]]
                else default for sid, default in defaults.items()}

    def settings(self):
        res = [(k, "@resolution.auto" if k == "auto" else label.split(" (")[0]) for k, label, _x in self.core.RESOLUTIONS]
        yes_no = [(False, "@off"), (True, "@on")]
        graphics = self._graphics_values()
        return [
            dict(id="resolution", label="@internal_resolution", options=res, value=self.s.get("resolution", "auto"),
                 hint="@resolution.hint", lead="@resolution.t4_lead"),
            dict(id="fullscreen", label="@fullscreen", options=yes_no, value=bool(self.s.get("fullscreen")),
                 hint="@fullscreen.hint", lead="@fullscreen.lead"),
            dict(id="fullscreen_exclusive", label="@exclusive", options=yes_no,
                 value=bool(self.s.get("fullscreen_exclusive")), hint="@exclusive.hint",
                 lead="@exclusive.lead"),
            dict(id="sound", label="@sound", options=yes_no, value=bool(self.s.get("sound", True)),
                 hint="@sound.hint", lead="@sound.lead"),
            dict(id="aa", label="@aa", options=GRAPHICS_OPTIONS["aa"], value=graphics["aa"],
                 hint="@aa.hint", lead="@aa.lead"),
            dict(id="hud", label="@hud", options=GRAPHICS_OPTIONS["hud"], value=graphics["hud"],
                 hint="@hud.hint", lead="@hud.lead"),
            dict(id="anisotropic", label="@anisotropic", options=GRAPHICS_OPTIONS["anisotropic"], value=graphics["anisotropic"],
                 hint="@anisotropic.hint", lead="@anisotropic.lead"),
            dict(id="progressive", label="@progressive", options=yes_no, value=bool(self.s.get("progressive", True)),
                 hint="@progressive.hint", lead="@progressive.lead"),
            dict(id="unlock_all", label="@unlock_all", options=yes_no, value=bool(self.s.get("unlock_all", True)),
                 hint="@unlock_all.hint", lead="@unlock_all.lead"),
            dict(id="debug_panel", label="@debug_window", options=yes_no, value=bool(self.s.get("debug_panel")),
                 hint="@debug.hint", lead="@debug.lead"),
        ]

    def set_setting(self, sid, value):
        if sid in GRAPHICS_OPTIONS:
            if value not in [v for v, _label in GRAPHICS_OPTIONS[sid]]:
                return
            self.config.setdefault("t4_graphics", {})[sid] = value
            save_config(self.config)
            if sid == "aa":
                self.s[sid] = value != GRAPHICS_OPTIONS[sid][0][0]
                self.core.save_settings(self.s)
            return
        self.s[sid] = value
        self.core.save_settings(self.s)

    def quick_settings(self):
        return ["resolution", "fullscreen"]

    # ---------------------------------------------------------------- build
    def sources(self):
        iso = self.core.effective_iso(self.s) or self.s.get("iso") or ""
        ok = bool(iso) and os.path.isfile(iso)
        home = os.path.expanduser("~")
        return [dict(id="iso", label="@game_iso", value=os.path.basename(iso) if ok else "@missing", ok=ok, kind="file",
                     exts=[".iso"], dirs=[self.root, os.path.join(home, "Downloads"), os.path.join(home, "Desktop")],
                     hint="@iso.hint", note=self.iso_note)]

    def set_source(self, sid, path):
        ok, message = self.core.verify_iso(path)
        self.iso_note = message
        if not ok:
            return message
        self.s["iso"] = path
        self.core.save_settings(self.s)
        return "@iso.confirmed"

    def build_ready(self):
        iso = self.core.effective_iso(self.s)
        return "" if iso else "@iso.choose_first"

    def build_start(self, force=False):
        iso = self.core.effective_iso(self.s)
        cmd = self.core.build_command(iso)
        if force:
            cmd.append("-Force")
        self.build_lines = []
        self.build_done = {}
        self.build_step = ""
        self.last_result = ""
        self.build = ProcessBuild(cmd, cwd=self.root, on_line=self._on_line)
        threading.Thread(target=self._build_end, args=(self.build,), daemon=True).start()

    def _on_line(self, line):
        self.build_lines = (self.build_lines + [line])[-40:]
        m = STEP_RE.match(line)
        if m:
            n, total, name = int(m.group(1)), int(m.group(2)), m.group(3)
            if self.build_step:
                self.build_done[self.build_step] = True
            self.build_step = name
            self.build_step_no = (n, total)

    def _build_end(self, build):
        while build.running():
            time.sleep(0.2)
        if build.cancelled:
            self.last_result = "@cancelled"
        elif build.code == 0:
            self.build_done[self.build_step] = True
            self.last_result = "@build_finished"
        else:
            self.last_result = self.message("step_failed", name=self.build_step or "?", path="logs\\build_game.log")

    def build_state(self):
        running = bool(self.build and self.build.running())
        steps = []
        for name, label in self.core.STEPS:
            if name in self.build_done:
                value = "@osk.done"
            elif running and name == self.build_step:
                value = "@running"
            else:
                value = "@pending"
            steps.append(dict(k=label, v=value))
        n, total = self.build_step_no
        return dict(running=running, fraction=(max(0, n - 1) / total) if total else 0.0, title=self.build_step,
                    steps=steps, result=self.last_result, line=self.build_lines[-1] if self.build_lines else "")

    def build_cancel(self):
        if self.build:
            self.build.cancel()


def friendly_time(stamp):
    """2026-10-30 02:06:42 -> 30.10., 02:06"""
    m = re.match(r"\d{4}-(\d\d)-(\d\d) (\d\d:\d\d)", stamp or "")
    return f"{m.group(2)}.{m.group(1)}., {m.group(3)}" if m else "@never"


def state_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def has_iso(root):
    return bool(glob.glob(os.path.join(glob.escape(root), "*.iso")))


__all__ = ["T4", "find_root", "onoff"]
