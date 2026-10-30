"""What a game must offer the launcher. The screens only ever talk to this interface."""
import glob
import os
import subprocess
import sys
import threading

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def expand_locations(locations):
    """The manifest's folders, with %VARS% and * resolved, existing ones only."""
    out = []
    for loc in locations:
        for path in sorted(glob.glob(os.path.expandvars(loc))):
            if os.path.isdir(path) and path not in out:
                out.append(path)
    return out


def onoff(value):
    return 1 if value else 0


class Adapter:
    """A game that is not there (yet). Every method has the answer of a game with nothing to show."""
    native_label = ""

    def __init__(self, manifest, config=None):
        self.m = manifest
        self.config = config if config is not None else {}
        self.problem = ""

    # ---------------------------------------------------------------- state
    def found(self):
        return False

    def ready(self):
        return False

    def status(self):
        """dict(status=short line, version, players, last, detail=one sentence)."""
        return dict(status="Not found", version="none", players="No", last="Never",
                    detail=f"OpenRecomp-FGC did not find {self.m['short']} on this PC.")

    def hero(self):
        return ""

    def recent_results(self):
        return []

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        raise RuntimeError("The game is not ready.")

    def running(self):
        return False

    def stop(self):
        pass

    def open_native(self):
        raise RuntimeError("This game has no launcher of its own.")

    # ---------------------------------------------------------------- settings: dict(id, label, hint, lead, options, value)
    def settings(self):
        return []

    def set_setting(self, sid, value):
        pass

    def quick_settings(self):
        """Ids of the settings shown under "Start game"."""
        return []

    # ---------------------------------------------------------------- online: rows for the online section
    def online_items(self):
        return []

    def run_online(self, item_id):
        return ""

    # ---------------------------------------------------------------- fighters
    def fighters(self):
        """[dict(key, name, image)] without Random; empty = this game has no character choice in the launcher."""
        return []

    def chosen_fighter(self):
        return "random"

    def set_fighter(self, key):
        pass

    def main_fighter(self):
        return ""

    # ---------------------------------------------------------------- replays
    def replays(self):
        """[dict(id, label, when, group, opponent, netcode, result, images)]"""
        return []

    def play_replay(self, replay_id, extra_env=None):
        raise RuntimeError("No replays.")

    # ---------------------------------------------------------------- build
    def sources(self):
        """[dict(id, label, value, ok, hint, exts, dirs)]: the player's files the build needs."""
        return []

    def set_source(self, sid, path):
        return ""

    def build_options(self):
        return []

    def build_ready(self):
        return "This game is not built through OpenRecomp-FGC."

    def build_start(self, force=False):
        raise RuntimeError("No build.")

    def build_state(self):
        """dict(running, fraction, title, steps=[dict(k, v)], result, line)."""
        return dict(running=False, fraction=0.0, title="", steps=[], result="", line="")

    def build_cancel(self):
        pass

    # ---------------------------------------------------------------- text field settings
    def text_value(self, tid):
        return ""

    def set_text_value(self, tid, value):
        pass


class Missing(Adapter):
    """The game's folder was not found: the player can point at it."""

    def sources(self):
        return [dict(id="folder", label="Game folder", value="Missing", ok=False, kind="folder", exts=[], dirs=[],
                     hint="Show OpenRecomp-FGC where the game is.")]

    def set_source(self, sid, path):
        self.config.setdefault("roots", {})[self.m["id"]] = path
        return "reload"


class Generic(Adapter):
    """Any finished recomp: the manifest names its exe (and optionally args, cwd and environment)."""

    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self.proc = None

    def exe(self):
        return os.path.expandvars(self.m["exe"])

    def found(self):
        return os.path.isfile(self.exe())

    def ready(self):
        return self.found()

    def status(self):
        if self.found():
            return dict(status="Ready", version=str(self.m.get("version", "unknown")), players="No",
                        last="unknown", detail="Starts the file the manifest names.")
        return dict(status="Not found", version="none", players="No", last="Never",
                    detail=f"{self.exe()} is missing.")

    def start(self, extra_env=None):
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (self.m.get("env") or {}).items()})
        env.update(extra_env or {})
        cwd = os.path.expandvars(self.m.get("cwd") or os.path.dirname(self.exe()))
        self.proc = subprocess.Popen([self.exe()] + [str(a) for a in self.m.get("args") or []], cwd=cwd, env=env)
        return self.proc.pid

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.running():
            self.proc.terminate()


class ProcessBuild:
    """A build as a child process: lines go to `on_line` on a thread; `code` is set when it ended."""

    def __init__(self, cmd, cwd=None, env=None, on_line=None):
        self.on_line = on_line or (lambda _line: None)
        self.code = None
        self.cancelled = False
        self.proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                     creationflags=NO_WINDOW)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.on_line(line.rstrip("\r\n"))
        self.code = self.proc.wait()

    def running(self):
        return self.code is None

    def cancel(self):
        self.cancelled = True
        if self.proc.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True,
                           creationflags=NO_WINDOW, check=False)


def add_path(path):
    if path and path not in sys.path:
        sys.path.insert(0, path)
