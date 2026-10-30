"""Tekken 4 (PS2 recomp): the project's own launcher core (launcher/t4core.py) does the work; nothing of it is copied."""
import glob
import importlib
import json
import os
import re
import threading
import time

from .base import Adapter, ProcessBuild, add_path, expand_locations, onoff
from ..manifest import art_dir

STEP_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(\w+)\s+-\s+(.*)$")


def find_root(manifest, config):
    chosen = (config.get("roots") or {}).get(manifest["id"]) or os.environ.get("OPENRECOMP_T4_ROOT")
    for path in ([chosen] if chosen else []) + expand_locations(manifest.get("locations", [])):
        if os.path.isfile(os.path.join(path, "launcher", "t4core.py")):
            return path
    return None


class T4(Adapter):
    native_label = "Tekken 4 launcher"

    def __init__(self, manifest, config, root, core=None):
        super().__init__(manifest, config)
        self.root = root
        if core is None:
            add_path(os.path.join(root, "launcher"))
            core = importlib.import_module("t4core")
        self.core = core
        self.s = core.load_settings()
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
        return dict(status="Ready" if not problems else "Not built yet", version="SLUS-20328",
                    players="Not yet", last=friendly_time(last.get("time", "")),
                    detail=problems[0] if problems else "Tekken 4 (USA) runs natively on this PC.")

    def hero(self):
        """A picture the player made of their own game: <user folder>/art/t4/hero.png (never shipped)."""
        path = os.path.join(art_dir("t4"), "hero.png")
        return path if os.path.isfile(path) else ""

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        problems = self.problems()
        if problems:
            raise RuntimeError(problems[0])
        holder = self.core.run_lock_holder()
        if holder:
            raise RuntimeError(f"Tekken 4 is already running ({holder}).")
        run = self.core.GameRun(self.s)
        if extra_env:
            real_env = self.core.game_env

            def env_with_extra(s, exe=None):
                env = real_env(s, exe)
                env.update(extra_env)
                return env
            self.core.game_env = env_with_extra
            try:
                run.start()
            finally:
                self.core.game_env = real_env
        else:
            run.start()
        self.core.take_run_lock("openrecomp")
        self.run = run
        threading.Thread(target=self._wait, args=(run,), daemon=True).start()
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
    def settings(self):
        res = [(k, label.split(" (")[0]) for k, label, _x in self.core.RESOLUTIONS]
        yes_no = [(False, "Off"), (True, "On")]
        return [
            dict(id="resolution", label="Internal resolution", options=res, value=self.s.get("resolution", "auto"),
                 hint="How sharply the game is rendered.", lead="Higher steps need more graphics power. Auto takes the step of your screen."),
            dict(id="fullscreen", label="Fullscreen", options=yes_no, value=bool(self.s.get("fullscreen")),
                 hint="F11 or Alt+Enter in the game work too.", lead="Borderless fullscreen for the game."),
            dict(id="fullscreen_exclusive", label="Exclusive fullscreen", options=yes_no,
                 value=bool(self.s.get("fullscreen_exclusive")), hint="A little less input lag.",
                 lead="Only when fullscreen is on."),
            dict(id="sound", label="Sound", options=yes_no, value=bool(self.s.get("sound", True)),
                 hint="The real game sound on the emulated IOP.", lead="Without sound the game runs with a silent stand-in."),
            dict(id="aa", label="Anti-aliasing", options=yes_no, value=bool(self.s.get("aa", True)),
                 hint="FXAA over the finished picture.", lead="Smooths edges, costs almost nothing."),
            dict(id="progressive", label="Progressive (480p)", options=yes_no, value=bool(self.s.get("progressive", True)),
                 hint="The game's 480p mode, no interlacing.", lead="Removes the interlace lines."),
            dict(id="unlock_all", label="All fighters unlocked", options=yes_no, value=bool(self.s.get("unlock_all", True)),
                 hint="Your save is not changed.", lead="All fighters from the start, without changing your save."),
            dict(id="debug_panel", label="Debug window", options=yes_no, value=bool(self.s.get("debug_panel")),
                 hint="F1 in the game opens the debug window.", lead="For troubleshooting only."),
        ]

    def set_setting(self, sid, value):
        self.s[sid] = value
        self.core.save_settings(self.s)

    def quick_settings(self):
        return ["resolution", "fullscreen"]

    # ---------------------------------------------------------------- build
    def sources(self):
        iso = self.core.effective_iso(self.s) or self.s.get("iso") or ""
        ok = bool(iso) and os.path.isfile(iso)
        home = os.path.expanduser("~")
        return [dict(id="iso", label="Game ISO", value=os.path.basename(iso) if ok else "Missing", ok=ok, kind="file",
                     exts=[".iso"], dirs=[self.root, os.path.join(home, "Downloads"), os.path.join(home, "Desktop")],
                     hint="Tekken 4 USA as an ISO (SLUS-20328). No BIOS needed.", note=self.iso_note)]

    def set_source(self, sid, path):
        ok, message = self.core.verify_iso(path)
        self.iso_note = message
        if not ok:
            return message
        self.s["iso"] = path
        self.core.save_settings(self.s)
        return "This is Tekken 4 (USA), SLUS-20328."

    def build_ready(self):
        iso = self.core.effective_iso(self.s)
        return "" if iso else "Choose your Tekken 4 ISO first."

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
            self.last_result = "Cancelled."
        elif build.code == 0:
            self.build_done[self.build_step] = True
            self.last_result = "Build finished."
        else:
            self.last_result = f"Step {self.build_step or '?'} failed. Log: logs\\build_game.log"

    def build_state(self):
        running = bool(self.build and self.build.running())
        steps = []
        for name, label in self.core.STEPS:
            if name in self.build_done:
                value = "Done"
            elif running and name == self.build_step:
                value = "Running"
            else:
                value = "Open"
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
    return f"{m.group(2)}.{m.group(1)}., {m.group(3)}" if m else "Never"


def state_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def has_iso(root):
    return bool(glob.glob(os.path.join(glob.escape(root), "*.iso")))


__all__ = ["T4", "find_root", "onoff"]
