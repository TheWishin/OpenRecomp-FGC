"""Small runtime bridge for the source-only T4 test catalog.

The selected source supplies its verifier and build scripts. No T4 launcher code
or generated game code is included in this module.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from . import t4_region
from .base import NO_WINDOW
from .launch_guard import LaunchGuard
from .. import i18n
from ..manifest import user_dir


class SourceCore:
    source_only = True
    source_checkout = True
    NO_WINDOW = NO_WINDOW
    subprocess = subprocess
    RESOLUTIONS = [(key, label, None) for key, label in (
        ("lowest", "@resolution.lowest"), ("native", "@t4.source.resolution_native"), ("1080p", "1080p"),
        ("1440p", "1440p"), ("4k", "4K"), ("auto", "@resolution.auto"))]
    STEPS = [(key, label) for key, label in (
        ("prereq", "@t4.source.step_prereq"), ("verify", "@t4.source.step_verify"),
        ("extract", "@t4.source.step_extract"), ("fork", "@t4.source.step_fork"),
        ("tools", "@t4.source.step_tools"), ("recomp", "@t4.source.step_recomp"),
        ("stage", "@t4.source.step_stage"), ("runtime", "@t4.source.step_runtime"))]

    def __init__(self, root):
        self.ROOT = str(Path(root).resolve())
        identity = hashlib.sha256(os.path.normcase(self.ROOT).encode("utf-8")).hexdigest()[:16]
        self._home = Path(user_dir()).resolve() / "t4-source" / identity
        for protected in (Path(__file__).resolve().parents[2], Path(self.ROOT)):
            if self._home.is_relative_to(protected):
                raise RuntimeError("@t4.source.data_outside")
        self.SAVE_DIR = str(self._home / "save")
        self.GAME_ELF = str(Path(self.ROOT) / "game" / "disc" / "SLUS_203.28")
        self._settings = self._home / "settings.json"
        self._guard = None
        self.GameRun = lambda settings: SourceRun(self, settings)

    def load_settings(self):
        settings = dict(iso="", resolution="auto", fullscreen=False, fullscreen_exclusive=False,
                        sound=True, debug_panel=False, unlock_all=True, aa=True, progressive=True)
        try:
            with self._settings.open(encoding="utf-8") as stream:
                saved = json.load(stream)
            if isinstance(saved, dict):
                settings.update(saved)
        except (OSError, ValueError):
            pass
        return settings

    def save_settings(self, settings):
        self._home.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self._home,
                                             suffix=".json", delete=False) as stream:
                temporary = stream.name
                json.dump(settings, stream, ensure_ascii=False, allow_nan=False)
            os.replace(temporary, self._settings)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def effective_iso(self, settings):
        path = settings.get("iso")
        return path if isinstance(path, str) and os.path.isfile(path) else ""

    def region_problem(self):
        """The launcher's T4 is the US release: a tree made for another disc is refused, never built quietly."""
        return t4_region.tree_problem(self.ROOT)

    def verify_iso(self, path):
        region = self.region_problem()
        if region:
            return False, region
        if not isinstance(path, str) or not os.path.isfile(path):
            return False, "@t4.source.iso_missing"
        command = [sys.executable, "-I", "-B", str(Path(self.ROOT) / "tools" / "iso_extract.py"),
                   path, "--check"]
        try:
            result = subprocess.run(command, cwd=self.ROOT, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=600, creationflags=NO_WINDOW, check=False)
        except subprocess.TimeoutExpired:
            return False, "@t4.source.iso_timeout"
        except OSError:
            return False, "@t4.source.iso_start_failed"
        if result.returncode == 0 and "OK" in result.stdout.splitlines():
            elf = t4_region.checked_disc_problem(result.stdout)
            return (False, elf) if elf else (True, "")
        if result.returncode == 3:
            return False, "@t4.source.iso_checksum"
        if result.returncode == 2:
            return False, "@t4.source.iso_wrong"
        return False, "@t4.source.iso_unreadable"

    def bundled_toolchain(self):
        # Source tests deliberately use the player's installed build tools.
        return True

    def build_command(self, iso):
        region = self.region_problem()
        if region:
            raise RuntimeError(region)
        return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(Path(self.ROOT) / "tools" / "build_game.ps1"), "-Iso", iso]

    def build_env(self):
        env = dict(os.environ)
        env["TEKKEN4_SRC"] = str(Path(self.ROOT) / "deps" / "ps2recomp")
        env["TEKKEN4_BUILD_DIR"] = "runtime"
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def find_runtime(self, settings):
        runtime = Path(self.ROOT) / "deps" / "ps2recomp" / "out" / "runtime" / "ps2xRuntime" / "ps2EntryRunner.exe"
        return (str(runtime), "source") if runtime.is_file() else (None, "@online.build_required")

    def play_problems(self, settings):
        region = self.region_problem()
        if region:
            return [region]
        out = []
        if not self.find_runtime(settings)[0] or not os.path.isfile(self.GAME_ELF):
            out.append("@online.build_required")
        if not self.effective_iso(settings):
            out.append("@iso.choose_first")
        return out

    def find_python(self):
        return sys.executable

    def graphics_support(self, exe):
        return dict(aa=True, progressive=True, fullscreen=True)

    def game_env(self, settings, exe=None):
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("TEKKEN4_", "PS2X_"))}
        resolution = settings.get("resolution", "auto")
        if resolution not in {row[0] for row in self.RESOLUTIONS}:
            resolution = "auto"
        # Auto is intentionally conservative on an unmeasured test PC.
        env.update(TEKKEN4_ISO=self.effective_iso(settings), PS2X_GS_BACKEND="gl", PS2X_GS_THREADS="auto",
                   TEKKEN4_INTERNAL_RES="1080p" if resolution == "auto" else resolution,
                   TEKKEN4_WINDOW_TITLE="TEKKEN 4", TEKKEN4_AA="fxaa" if settings.get("aa", True) else "off")
        for option, name, default in (("sound", "TEKKEN4_SOUND", True),
                                      ("unlock_all", "TEKKEN4_UNLOCK_ALL", True),
                                      ("progressive", "TEKKEN4_PROGRESSIVE", True),
                                      ("debug_panel", "PS2X_DEBUG_PANEL", False)):
            env[name] = "1" if settings.get(option, default) else "0"
        env["TEKKEN4_FULLSCREEN"] = ("exclusive" if settings.get("fullscreen_exclusive") else "1") if settings.get("fullscreen") else "0"
        return env

    def run_lock_holder(self):
        if self._guard is not None:
            return "OpenRecomp"
        if not (self._home / "locks").is_dir():
            return ""
        probe = LaunchGuard("source", directory=str(self._home / "locks"))
        try:
            probe.acquire()
        except RuntimeError:
            return "OpenRecomp"
        finally:
            probe.release()
        return ""

    def take_run_lock(self, label):
        self._guard = LaunchGuard("source", directory=str(self._home / "locks")).acquire()

    def release_run_lock(self):
        guard, self._guard = self._guard, None
        if guard is not None:
            guard.release()


class SourceRun:
    def __init__(self, core, settings):
        self.core, self.settings = core, dict(settings)
        self.proc = None
        self._streams = []
        self._stopped = False

    def start(self):
        problems = self.core.play_problems(self.settings)
        if problems:
            raise RuntimeError(problems[0])
        folder = Path(self.core.SAVE_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        executable = self.core.find_runtime(self.settings)[0]
        try:
            for name in ("stdout.txt", "stderr.txt"):
                self._streams.append((folder / name).open("wb"))
            self._started = time.monotonic()
            self.proc = subprocess.Popen([executable, self.core.GAME_ELF], cwd=str(folder),
                                         env=self.core.game_env(self.settings, executable),
                                         stdin=subprocess.DEVNULL, stdout=self._streams[0], stderr=self._streams[1],
                                         creationflags=NO_WINDOW)
        except BaseException:
            for stream in self._streams:
                stream.close()
            raise

    def wait(self):
        try:
            code = self.proc.wait()
        finally:
            for stream in self._streams:
                stream.close()
        return dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), seconds=round(time.monotonic() - self._started, 1),
                    exit=code, ok=self._stopped or code == 0,
                    note="@t4.source.ended" if code == 0 or self._stopped else i18n.message("t4.source.game_failed", code=code))

    def stop(self):
        self._stopped = True
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()


def create_core(root):
    return SourceCore(root)
