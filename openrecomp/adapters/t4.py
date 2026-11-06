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
from .launch_guard import LaunchGuard
from . import t4_region
from .t4_online import T4Online
from .t4_support import T4Support
from .t4_controls import T4Controls
from .t5_online import game_process_running
from .t4_install import install_root, install_source, source_root
from .. import t4_art, wine
from ..fighter_render import t4_cache_token
from ..manifest import art_dir, save_config
from ..game_releases import clear_rebuild, rebuild_required

STEP_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(\w+)\s+-\s+(.*)$")
GRAPHICS_OPTIONS = {
    "aa": [("off", "@off"), ("fxaa", "@aa.fxaa"), ("smaa", "@aa.smaa"),
           ("ssaa2", "@aa.ssaa2"), ("ssaa3", "@aa.ssaa3"), ("ssaa4", "@aa.ssaa4"),
           ("msaa2", "@aa.msaa2"), ("msaa4", "@aa.msaa4"), ("msaa8", "@aa.msaa8"),
           ("ssaa2+fxaa", "@aa.ssaa2_fxaa")],
    "hud": [("soft", "@hud.soft"), ("sharp", "@hud.sharp")],
    "anisotropic": [("1", "@off"), ("2", "@anisotropic.two"), ("4", "@anisotropic.four"),
                    ("8", "@anisotropic.eight"), ("16", "@anisotropic.sixteen")],
    # TEKKEN4_WIDESCREEN: picture only (the game simulates the same either way), so each player picks their own,
    # online too, with any mix of 4:3 and 16:9 (T4 docs/WIDESCREEN.md).
    "aspect": [("4:3", "@aspect.4_3"), ("16:9", "@aspect.16_9")],
}
BETA_DISABLED_SWITCHES = (
    "TEKKEN4_RUNAHEAD", "TEKKEN4_NET_HASH_PROFILE", "TEKKEN4_NET_COST_PROFILE",
    "TEKKEN4_NET_COALESCE", "TEKKEN4_NET_STRICT_HELLO", "TEKKEN4_RB_AUDIO_TIMELINE",
    "TEKKEN4_NET_DELAY_MATCH", "TEKKEN4_NET_SIM_SAFE_WAIT",
)
BETA_HARNESS_SWITCHES = (
    "TEKKEN4_NET_END", "TEKKEN4_NET_SHOTS", "TEKKEN4_NET_DESYNC_DUMP", "TEKKEN4_NET_SIM",
)
DEFAULT_SOURCE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "T4")


def find_root(manifest, config):
    """ONE folder for Play, Build, Online, Direct IP and logs (0.1.3). The folder the player chose (config roots) is
    the only one ever used when it is set: when it is not a T4 install the page says so (configured_problem) and
    nothing else is tried -- no Pictures\\, dev tree or old folder beside the launcher. Only without a choice: the
    developer override OPENRECOMP_T4_ROOT, the manifest's folders, then the T4 folder a bundle zip put beside this
    launcher (the fresh install itself)."""
    chosen = (config.get("roots") or {}).get(manifest["id"])
    if chosen:
        return install_root(chosen) if isinstance(chosen, str) else None
    env = os.environ.get("OPENRECOMP_T4_ROOT")
    for path in ([env] if env else []) + expand_locations(manifest.get("locations", [])) + [DEFAULT_SOURCE_ROOT]:
        root = install_root(path)
        if root:
            return root
    return None


def configured_problem(manifest, config):
    """The chosen folder, when it is set but is not a T4 install ("" otherwise)."""
    chosen = (config.get("roots") or {}).get(manifest["id"])
    return chosen if isinstance(chosen, str) and chosen and not install_root(chosen) else ""


def release_version(root):
    """The T4 release this folder holds: release.json (portable release zip) or the launcher's marker; "" = a source
    tree / unknown."""
    for name, key in (("release.json", "version"), ("openrecomp-release.json", "version")):
        try:
            with open(os.path.join(root, name), encoding="utf-8") as stream:
                value = json.load(stream).get(key)
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(value, str) and re.fullmatch(r"[0-9A-Za-z.+-]{1,40}", value):
            return value
    return ""


def folder_problem(root):
    """What is wrong with a found T4 folder for this launcher, or "": an old source-only release (0.1.2 and older
    built with the PC's Visual Studio -- another compiler, another build id) or a release zip missing its compiler.
    A developer checkout (.git) builds as before."""
    if not root:
        return ""
    portable = os.path.isfile(os.path.join(root, "toolchain", "toolchain.json"))
    if portable:
        return ""
    if os.path.exists(os.path.join(root, ".git")):
        return ""
    if os.path.isfile(os.path.join(root, "release.json")):
        return "@t4.folder_incomplete"
    return "@t4.folder_old"


def load_core(root):
    """A newly selected install must not reuse the previous install's cached t4core."""
    launcher = os.path.join(os.path.realpath(root), "launcher")
    path = os.path.join(launcher, "t4core.py")
    # T4's own core (launcher/t4core.py) builds only with the toolchain a portable release carries. A source tree that
    # also ships launcher/ for T4's own Tk launcher (T4 release zips since 99b95b9) is built like any source tree.
    portable = os.path.isfile(os.path.join(os.path.realpath(root), "toolchain", "toolchain.json"))
    if source_root(root) and not (os.path.isfile(path) and portable):
        from .t4_source import create_core
        return create_core(root)
    # Keyed by the file's size and time too: after a game update the same folder has a NEW t4core.py, and the old
    # module (e.g. 0.1.2's, which knows no bundled compiler) must not be reused until the launcher restarts.
    try:
        st = os.stat(path)
        stamp = f"|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        stamp = ""
    name = "_openrecomp_t4core_" + hashlib.sha256((os.path.normcase(path) + stamp).encode("utf-8")).hexdigest()
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


class T4(T4Controls, T4Support, T4Online, Adapter):
    native_label = "@t4.native_label"
    other_launcher_game = "t4"           # its own launcher open too: other_launchers

    def __init__(self, manifest, config, root, core=None):
        super().__init__(manifest, config)
        self.root = root
        if core is None:
            core = load_core(root)
        self.core = core
        self.s = core.load_settings()
        self._play_lock = threading.RLock()
        self._settings_lock = threading.RLock()
        self.run = None
        self.build = None
        self.build_lines = []
        self.build_error = ""
        self.build_step = ""
        self.build_step_no = (0, 0)
        self.build_done = {}
        self.iso_note = ""
        self._source_state = dict(running=False, result="", id="iso", ok=False)
        self._verified_iso = None
        self.last_result = ""
        self._prerequisite_rows = []
        self._prerequisite_worker = None
        self._art_busy = False
        self._art_tried = None
        self._fighter_art_lock = threading.Lock()
        self._fighter_art_busy = set()
        self._fighter_art_tried = {}
        self.art_note = ""
        self._tool_install = dict(running=False, done=0, total=0, current="", result="")
        # Build pressed with tools missing: install them, check again, then build (one worker; see build_start).
        self._pipeline = dict(running=False, cancel=False)
        self.build_failed = ""                    # "tools" or "build": where the last attempt stopped
        self._iso_save_pending = None             # (install key, [path, size, time]) to keep in the launcher config
        self._verified_iso = self._remembered_iso()
        if getattr(core, "source_only", False):
            self.native_label = ""
            self._prerequisite_rows = [dict(id=key, label="@t4.tools." + key, value="@t4.tools.checking",
                                            ok=False, command="", busy=True)
                                       for key in ("python", "git", "cmake", "ninja", "vs2022", "msvc")]
            self.refresh_prerequisites()

    def found(self):
        return True

    def release_version(self):
        return release_version(self.root)

    def folder_problem(self):
        return folder_problem(self.root)

    def problems(self):
        problems = list(self.core.play_problems(self.s))
        region = self.region_problem()
        if region and region not in problems:
            problems.insert(0, region)               # a native core accepts its own (PAL) build: Play is US only too
        if rebuild_required("t4", self.root):
            problems.insert(0, "@setup.build_again")     # updated from its release: the old build is the old code
        return problems

    def ready(self):
        return not self.problems()

    def status(self):
        problems = self.problems()
        last = self.s.get("last_run")
        if not isinstance(last, dict):
            last = {}
        # An old source-only release still plays its own build offline; the page says what it is (0.1.3).
        detail = problems[0] if problems else (self.folder_problem() or "@t4.ready_detail")
        if not problems and last.get("ok") is False:
            detail = self.message("t4.play_failed", error=last.get("note") or str(last.get("exit", "?")))
        release = self.release_version()
        return dict(status="@ready" if not problems else "@not_built",
                    version=self.message("t4.version_release", release=release) if release else "SLUS-20328",
                    folder=self.root, release=release,
                    players="@t4.lobby_mode", last=friendly_time(last.get("time", "")),
                    detail=detail)

    def hero(self):
        """The tile's picture, never shipped: <user folder>/art/t4/hero.png if the player put one there, else Jin's
        select portrait read once from their own verified ISO (t4_art) into the same folder."""
        own = os.path.join(art_dir("t4"), "hero.png")
        if os.path.isfile(own):
            return own
        path = os.path.join(art_dir("t4"), t4_art.FILE_NAME)
        if os.path.isfile(path):
            return path
        self._start_art(path)
        return ""

    def _start_art(self, path):
        """One try per ISO (path, size, time): a disc that is not SLUS-20328 just keeps the plain tile."""
        effective = getattr(self.core, "effective_iso", None)
        if self._art_busy or not callable(effective):
            return
        try:
            iso = effective(self.s)
        except Exception:  # noqa: BLE001 -- the picture never stops the launcher
            return
        stamp = self._iso_stamp(iso) if iso else None
        if stamp is None or stamp == self._art_tried:
            return
        self._art_tried = stamp
        self._art_busy = True
        threading.Thread(target=self._make_art, args=(iso, path), daemon=True).start()

    def fighter_image(self, key):
        """A square select portrait, decoded once from the player's built game's own data."""
        return self._fighter_picture(key)

    def fighter_render(self, key, mirrored=False):
        return self._fighter_picture(key, render=True, mirrored=mirrored)

    def _fighter_picture(self, key, render=False, mirrored=False):
        if not isinstance(key, str) or key not in t4_art.FIGHTER_PORTRAITS:
            return ""
        token = t4_cache_token(key, render=render, mirrored=mirrored)
        path = os.path.join(art_dir("t4"), "fighters", token + ".png")
        if os.path.isfile(path):
            return path
        try:
            if self._building() or not self.ready():
                return ""
            source = os.path.join(self.root, "game", "disc")
            stamp = t4_art.source_stamp(source)
            if stamp is None:
                effective = getattr(self.core, "effective_iso", None)
                source = effective(self.s) if callable(effective) else ""
                stamp = t4_art.source_stamp(source) if source else None
            if stamp is None:
                return ""
            with self._fighter_art_lock:
                if token in self._fighter_art_busy or self._fighter_art_tried.get(token) == stamp:
                    return ""
                self._fighter_art_tried[token] = stamp
                self._fighter_art_busy.add(token)
            try:
                args = (source, key, path, render, mirrored) if render else (source, key, path)
                threading.Thread(target=self._make_fighter_art, args=args, daemon=True).start()
            except Exception:
                with self._fighter_art_lock:
                    self._fighter_art_busy.discard(token)
                raise
        except Exception as error:  # noqa: BLE001 -- optional art never stops a screen
            self.art_note = str(error) or error.__class__.__name__
        return ""

    def _make_fighter_art(self, source, key, path, render=False, mirrored=False):
        try:
            if render:
                t4_art.make_fighter_render(source, key, path, mirrored=mirrored)
            else:
                t4_art.make_fighter(source, key, path)
        except Exception as error:  # noqa: BLE001 -- a missing picture must never stop the launcher
            self.art_note = str(error) or error.__class__.__name__
        finally:
            with self._fighter_art_lock:
                token = t4_cache_token(key, render=render, mirrored=mirrored)
                self._fighter_art_busy.discard(token)

    def _make_art(self, iso, path):
        try:
            t4_art.make_hero(iso, path)
        except Exception as error:  # noqa: BLE001 -- a missing picture must never stop the launcher
            self.art_note = str(error) or error.__class__.__name__
        finally:
            self._art_busy = False

    # ---------------------------------------------------------------- playing
    def _online_work_active(self):
        return (getattr(self, "_direct_busy", False)
                or getattr(self, "_online_phase", "") in ("checking", "checked", "starting", "playing"))

    def start(self, extra_env=None):
        with self._play_lock:
            if self._source_state["running"] or self._building():
                raise RuntimeError("@t4.work_busy")
            if self._online_work_active() and not (extra_env or {}).get("TEKKEN4_NET"):
                raise RuntimeError("@online.game_running")
            proc = getattr(self.run, "proc", None)
            if callable(getattr(proc, "poll", None)) and self.running():
                raise RuntimeError("@online.game_running")
            previous = getattr(self, "_launch_guard", None)
            if previous is not None and proc is not None and proc.poll() is not None:
                previous.release()
            reservation = LaunchGuard("t4").acquire()
            started = False
            try:
                exe, _why = self.core.find_runtime(self.s)
                if not exe:
                    raise RuntimeError("@online.build_required")
                active = game_process_running(os.path.basename(exe))
                if active is None:
                    raise RuntimeError("@online.process_unknown")
                if active:
                    raise RuntimeError("@online.game_running")
                pid = self._start(extra_env)
                started = True
                self._launch_guard = reservation
                run = self.run
                reservation.watch(lambda: self._launch_active(run))
            except Exception:
                run = self.run
                proc = getattr(run, "proc", None)
                try:
                    active = callable(getattr(proc, "poll", None)) and self._launch_active(run)
                except Exception:
                    active = True
                if active:
                    if started:
                        try:
                            run.stop()
                        except Exception:  # noqa: BLE001 -- preserve the handle for another stop
                            pass
                    self._launch_guard = reservation
                    try:
                        reservation.watch(lambda: self._launch_active(run))
                    except Exception:  # noqa: BLE001 -- an unwatched reservation must stay held
                        pass
                else:
                    reservation.release()
                raise
            return pid

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
            # A normal Play must not inherit a previous direct-IP session.
            env = {key: value for key, value in real_env(s, exe).items()
                   if key.upper() != "TEKKEN4_NET" and not key.upper().startswith("TEKKEN4_NET_")}
            if self.core.graphics_support(exe)["aa"]:
                env["TEKKEN4_AA"] = graphics["aa"]
            env["TEKKEN4_HUD"] = graphics["hud"]
            env["TEKKEN4_ANISO"] = graphics["anisotropic"]
            env["TEKKEN4_WIDESCREEN"] = "1" if graphics["aspect"] == "16:9" else "0"
            if getattr(self.core, "SAVE_DIR", ""):
                env["TEKKEN4_CONTROLS"] = self._t4c_path()        # the Pad bindings page's file (a missing file = default)
            env.update(extra_env or {})
            env.update(self._beta_env())
            if getattr(self.core, "source_only", False) and (extra_env or {}).get("TEKKEN4_NET"):
                for name in list(env):
                    if name == "TEKKEN4_RAND_SEED" or (name.startswith("TEKKEN4_RB_")
                                                       and name != "TEKKEN4_RB_AUDIO_TIMELINE"):
                        env.pop(name, None)
                env.update(extra_env)
            for name in BETA_HARNESS_SWITCHES:
                env.pop(name, None)
            return env
        self.core.game_env = env_with_extra
        lock_acquired = False
        try:
            try:
                run.start()
            finally:
                self.core.game_env = real_env
            self._track_playtime(lambda: run.proc.poll() is None, process=run.proc, extra_env=extra_env)
            self.run = run
            self.core.take_run_lock("openrecomp")
            lock_acquired = True
            self._run_waiter = threading.Thread(target=self._wait, args=(run,), daemon=True)
            self._run_waiter.start()
        except Exception:
            if lock_acquired:
                self._unwaited_run = run
            proc = getattr(run, "proc", None)
            try:
                active = callable(getattr(proc, "poll", None)) and proc.poll() is None
            except Exception:
                active = True
            if active:
                self.run = run
                try:
                    run.stop()
                except Exception:  # noqa: BLE001 -- keep the handle and reservation for another stop
                    pass
            if lock_acquired:
                try:
                    self._launch_active(run)
                except Exception:  # noqa: BLE001 -- unknown exit/lock state must keep the reservation
                    pass
            raise
        return run.proc.pid

    def _launch_active(self, run):
        active = run.proc.poll() is None
        # A failed waiter cannot release the native lock; do so only after confirmed exit.
        if not active and getattr(self, "_unwaited_run", None) is run:
            with self._settings_lock:
                if self._unwaited_run is run:
                    self.core.release_run_lock()
                    self._unwaited_run = None
        return active

    def _wait(self, run):
        try:
            record = run.wait()
        finally:
            self.core.release_run_lock()
        with self._settings_lock:
            self.s["last_run"] = record
            self.core.save_settings(self.s)

    def running(self):
        return bool(self.run and self.run.proc and self._launch_active(self.run))

    def stop(self):
        if self.run:
            self.run.stop()
            if getattr(self, "_unwaited_run", None) is self.run:
                self._launch_active(self.run)

    def open_native(self):
        if getattr(self.core, "source_only", False):
            raise RuntimeError("@no_native")
        script = os.path.join(self.root, "launcher", "t4_launcher.pyw")
        python = self.core.find_python()
        process = self.core.subprocess.Popen([python, script], cwd=self.root, creationflags=self.core.NO_WINDOW)
        if getattr(self, "playtime_store", None) is not None:
            try:
                exe, _why = self.core.find_runtime(self.s)
                self._track_native_playtime(process, (os.path.basename(exe),) if exe else ())
            except (OSError, RuntimeError):
                pass

    # ---------------------------------------------------------------- settings
    def _net_diagnostics(self):
        saved = self.config.get("t4_diagnostics")
        return isinstance(saved, dict) and saved.get("net_diagnostics") is True

    def _beta_env(self):
        # The Sunday experiments have no two-PC acceptance evidence yet.
        env = {name: "0" for name in BETA_DISABLED_SWITCHES}
        env["TEKKEN4_NET_DIAG"] = "1" if self._net_diagnostics() else "0"
        return env

    def _graphics_values(self):
        # The core only saves boolean AA; advanced choices belong to this launcher's config.
        saved = self.config.get("t4_graphics") or {}
        defaults = dict(aa=GRAPHICS_OPTIONS["aa"][1 if self.s.get("aa", True) else 0][0],
                        hud=GRAPHICS_OPTIONS["hud"][0][0], anisotropic=GRAPHICS_OPTIONS["anisotropic"][2][0],
                        aspect=GRAPHICS_OPTIONS["aspect"][0][0])
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
            dict(id="aspect", label="@aspect", options=GRAPHICS_OPTIONS["aspect"], value=graphics["aspect"],
                 hint="@aspect.hint", lead="@aspect.lead"),
            dict(id="progressive", label="@progressive", options=yes_no, value=bool(self.s.get("progressive", True)),
                 hint="@progressive.hint", lead="@progressive.lead"),
            dict(id="unlock_all", label="@unlock_all", options=yes_no, value=bool(self.s.get("unlock_all", True)),
                 hint="@unlock_all.hint", lead="@unlock_all.lead"),
            dict(id="debug_panel", label="@debug_window", options=yes_no, value=bool(self.s.get("debug_panel")),
                 hint="@debug.hint", lead="@debug.lead"),
            dict(id="name_plates", label="@t4.name_plates", options=yes_no,
                 value=self.config.get("t4_name_plates", True) is not False,
                 hint="@t4.name_plates_hint", lead="@t4.name_plates_lead"),
            dict(id="net_diagnostics", label="@t4.net_diagnostics", options=yes_no,
                 value=self._net_diagnostics(),
                 hint="@t4.net_diagnostics_hint", lead="@t4.net_diagnostics_lead"),
        ]

    def set_setting(self, sid, value):
        if self._online_work_active():
            raise RuntimeError("@t4.work_busy")
        if sid == "name_plates":
            # Online name plates in the game (TEKKEN4_HUD_PLATES): each player's name and rank badge on their side.
            if type(value) is not bool:
                return
            self.config["t4_name_plates"] = value
            save_config(self.config)
            return
        if sid == "net_diagnostics":
            if type(value) is not bool:
                return
            if not isinstance(self.config.get("t4_diagnostics"), dict):
                self.config["t4_diagnostics"] = {}
            self.config["t4_diagnostics"][sid] = value
            save_config(self.config)
            return
        if sid in GRAPHICS_OPTIONS:
            if value not in [v for v, _label in GRAPHICS_OPTIONS[sid]]:
                return
            self.config.setdefault("t4_graphics", {})[sid] = value
            save_config(self.config)
            if sid == "aa":
                with self._settings_lock:
                    self.s[sid] = value != GRAPHICS_OPTIONS[sid][0][0]
                    self.core.save_settings(self.s)
            return
        with self._settings_lock:
            self.s[sid] = value
            self.core.save_settings(self.s)

    def quick_settings(self):
        return ["resolution", "fullscreen"]

    # ---------------------------------------------------------------- build
    def sources(self):
        iso = self.core.effective_iso(self.s) or self.s.get("iso") or ""
        ok = bool(iso) and os.path.isfile(iso)
        home = os.path.expanduser("~")
        # The ISO's own folder first, then Downloads: the T4 game folder is never where a disc image is kept.
        out = [dict(id="iso", label="@t4.iso_row", value=os.path.basename(iso) if ok else "@missing", ok=ok, kind="file",
                     title="@t4.choose_iso", filter="@t4.iso_filter", exts=[".iso"],
                     dirs=[os.path.dirname(iso) if iso else "", os.path.join(home, "Downloads"), os.path.join(home, "Desktop"), self.root],
                     hint="@iso.hint", note=self.iso_note, busy=self._source_state["running"])]
        folder_note = self._source_state["result"] if self._source_state["id"] == "folder" else ""
        if self._needs_toolchain():
            out.insert(0, dict(id="folder", label="@t4.complete_release", title="@t4.choose_game_folder", value="@missing", ok=False,
                               kind="file_or_folder", exts=[".zip"], dirs=[os.path.join(home, "Downloads")],
                               hint="@t4.portable_required", note=folder_note if folder_note != "reload" else "",
                               busy=self._source_state["running"]))
        else:
            # 0.1.3: the folder in use, always on the page, and "use an existing install" at any time: picking another
            # T4 folder (or a release zip) makes it THE folder for Play, Build and Online.
            out.append(dict(id="folder", label="@t4.folder_row", title="@t4.choose_game_folder", value=self.root,
                               ok=not self.folder_problem(), kind="file_or_folder", exts=[".zip"],
                               dirs=[os.path.dirname(self.root), os.path.join(home, "Downloads")],
                               hint="@t4.folder_change_hint", note=folder_note if folder_note != "reload" else "",
                               busy=self._source_state["running"]))
        return out

    def _needs_toolchain(self):
        if getattr(self.core, "source_only", False):
            return False
        bundled = getattr(self.core, "bundled_toolchain", None)
        return callable(bundled) and not bundled()

    def prerequisites(self):
        return [dict(row) for row in self._prerequisite_rows]

    def prerequisite_install_state(self):
        return dict(self._tool_install)

    def install_prerequisites(self, run=None):
        """Install missing tools on a worker, falling back to verified vendor downloads, then recheck.

        Only what the launcher's dialog listed (the missing rows' COMMANDS) is run; the player confirmed it there."""
        from . import t4_prerequisites as tools
        plan = tools.install_plan(self._prerequisite_rows)
        if (not plan or self._tool_install["running"] or self._prerequisite_worker and self._prerequisite_worker.is_alive()
                or self.running() or self._building()):
            return False
        self._tool_install = dict(running=True, done=0, total=len(plan), current=plan[0][0], result="")

        def work():
            def progress(index, total, label):
                self._tool_install.update(done=index, current=label)
            try:
                statuses = tools.install_tools(plan, progress=progress, run=run)
                result = ("@t4.tools.reboot" if "reboot" in statuses else
                          "@t4.tools.install_done" if all(s == "ok" for s in statuses) else "@t4.tools.install_failed")
            except Exception as error:  # noqa: BLE001 -- always leave a retry path
                result = str(error) if str(error).startswith("@t4.tools.") else "@t4.tools.install_failed"
            try:
                tools.refresh_path()
            except Exception:  # noqa: BLE001 -- the re-check still runs with the old PATH
                pass
            self._tool_install = dict(running=False, done=len(plan), total=len(plan), current="",
                                      result=result)
            self.refresh_prerequisites()
        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception:  # noqa: BLE001 -- the action stays available
            self._tool_install = dict(running=False, done=0, total=0, current="", result="@t4.tools.install_failed")
            return False
        return True

    def refresh_prerequisites(self):
        if not getattr(self.core, "source_only", False):
            return False
        if (self._tool_install["running"] or self._prerequisite_worker and self._prerequisite_worker.is_alive()
                or self._source_state["running"] or self.running() or self._online_work_active()
                or self._building()):
            return False
        self._prerequisite_rows = [dict(row, value="@t4.tools.checking", ok=False, busy=True)
                                   for row in self._prerequisite_rows]

        def check():
            try:
                from .t4_prerequisites import check_prerequisites
                rows = check_prerequisites()
            except Exception:  # noqa: BLE001 -- a failed tool probe must leave a retry path
                rows = [dict(row, value="@t4.tools.unknown", ok=False) for row in self._prerequisite_rows]
            self._prerequisite_rows = [dict(row, busy=False) for row in rows]
        try:
            self._prerequisite_worker = threading.Thread(target=check, daemon=True)
            self._prerequisite_worker.start()
        except Exception:  # noqa: BLE001 -- retry stays available when a worker cannot start
            self._prerequisite_worker = None
            self._prerequisite_rows = [dict(row, value="@t4.tools.unknown", ok=False, busy=False)
                                       for row in self._prerequisite_rows]
            return False
        return True

    # ---------------------------------------------------------------- Build = missing tools first, then the build
    def _building(self):
        return bool(self._pipeline["running"] or self.build and self.build.running())

    def _tools_ok(self):
        return bool(self._prerequisite_rows) and all(row.get("ok") is True for row in self._prerequisite_rows)

    def build_prepares(self):
        """Problems build_start solves by itself: missing build tools are installed first, then it builds."""
        return ("@t4.tools.required",) if getattr(self.core, "source_only", False) else ()

    def _tools_then_build(self, force, run=None, check=None, wait=0.2):
        """The worker behind Build when tools are missing: one installer after the other (the player sees only
        "Installing build tools (x of y)"), the new PATH, a fresh check, then the build itself. A restart Windows
        asks for is remembered: the launcher continues after it (build_resume_pending)."""
        from . import t4_prerequisites as tools
        check = check or tools.check_prerequisites
        state = self._tool_install
        try:
            worker = self._prerequisite_worker
            while worker is not None and worker.is_alive() and not self._pipeline["cancel"]:
                worker.join(wait)                    # the check started with the launcher is still running
            rows = [dict(row) for row in self._prerequisite_rows]
            if not all(row.get("ok") is True for row in rows) and not tools.install_plan(rows):
                rows = check()                       # an earlier check failed: ask again before installing
            plan = tools.install_plan(rows) if not all(row.get("ok") is True for row in rows) else []

            def progress(index, total, label):
                state.update(running=True, done=index, total=total, current=label, result="")

            statuses = tools.install_tools(plan, progress=progress, cancelled=lambda: self._pipeline["cancel"], run=run)
            reboot = "reboot" in statuses
            failed = [label for (label, _command), status in zip(plan, statuses) if status == "failed"]
            if reboot and not self._pipeline["cancel"]:
                self._remember_resume()
                self._tool_install = dict(running=False, done=statuses.index("reboot") + 1,
                                          total=len(plan), current="", result="@t4.tools.reboot")
                self._build_stopped("tools", "@t4.tools.reboot")
                return
            if plan:
                try:
                    tools.refresh_path()
                except Exception:  # noqa: BLE001 -- the re-check still runs with the old PATH
                    pass
                rows = check()
            self._prerequisite_rows = [dict(row, busy=False) for row in rows]
            self._tool_install = dict(running=False, done=len(plan), total=len(plan), current="",
                                      result="@t4.tools.install_done" if plan else "")
            if self._pipeline["cancel"]:
                self._build_stopped("tools", "@t4.build_cancelled")
                return
            missing = [row for row in rows if row.get("ok") is not True]
            if missing:
                if not plan:
                    self._build_stopped("tools", "@t4.tools.check_failed")
                else:
                    name = (failed or [missing[0]["label"]])[0]
                    self._build_stopped("tools", self.message("t4.tools.not_installed", name=name))
                return
            self._forget_resume()
            self._pipeline["running"] = False        # the build process takes over (_building() stays true)
            self._start_process(force)
        except Exception as error:  # noqa: BLE001 -- Build must end with a message, never stay "running"
            self._tool_install = dict(self._tool_install, running=False)
            result = (str(error) if str(error).startswith("@t4.tools.") else
                      self.message("t4.build_start_failed", error=str(error) or error.__class__.__name__))
            self._tool_install["result"] = result
            self._build_stopped("build" if self.build else "tools", result)
        finally:
            self._pipeline["running"] = False

    def _build_stopped(self, phase, result):
        self.build_failed = phase
        self.last_result = result

    def _remember_resume(self):
        self._resume_save = dict(self.config.get("build_resume") or {}, t4=int(time.time()))
        self._resume_dirty = True

    def _forget_resume(self):
        if "t4" in (self.config.get("build_resume") or {}) or getattr(self, "_resume_save", None):
            saved = dict(self.config.get("build_resume") or {})
            saved.pop("t4", None)
            self._resume_save = saved
            self._resume_dirty = True

    def _save_pending(self):
        """What workers found goes into the launcher's config here, on the window's thread (nav asks build_state
        there). The file itself is written by the launcher (config_dirty -> Backend), never by the adapter: an
        adapter made in a test must not touch the player's real config.json."""
        if getattr(self, "_resume_dirty", False):
            self._resume_dirty = False
            if self._resume_save:
                self.config["build_resume"] = self._resume_save
            else:
                self.config.pop("build_resume", None)
            self._resume_save = None
            self.config_dirty = True
        if getattr(self, "_iso_save_pending", None):
            key, stamp = self._iso_save_pending
            self._iso_save_pending = None
            saved = self.config.get("t4_iso_verified")
            self.config["t4_iso_verified"] = dict(saved if isinstance(saved, dict) else {}, **{key: stamp})
            self.config_dirty = True

    def build_resume_pending(self):
        """Windows was restarted to finish installing the build tools (within two weeks): continue the build."""
        stamp = (self.config.get("build_resume") or {}).get("t4")
        return (isinstance(stamp, int) and 0 <= time.time() - stamp < 14 * 86400 and not self._building()
                and not any(row.get("busy") for row in self._prerequisite_rows))

    def build_resume(self):
        self._forget_resume()
        self._save_pending()
        self.build_start()

    def _remembered_iso(self):
        """An ISO this launcher verified before stays verified while it is the same file (path, size, time): a
        restart (for example after installing the build tools) must not send the player back to choosing it."""
        try:
            iso = self.core.effective_iso(self.s) or ""
        except Exception:  # noqa: BLE001 -- unknown = check again
            return None
        saved = (self.config.get("t4_iso_verified") or {}).get(os.path.normcase(os.path.abspath(self.root)))
        stamp = self._iso_stamp(iso) if iso else None
        if stamp is not None and isinstance(saved, list) and [stamp[0], stamp[1], stamp[2]] == saved:
            return stamp
        return None

    def set_source(self, sid, path):
        if self._source_state["running"]:
            return "@t4.installing" if self._source_state["id"] == "folder" else "@iso.checking"
        if self._online_work_active() or self.running() or self._building():
            return "@t4.work_busy"
        if sid == "folder":
            self._source_state = dict(running=True, result="", id=sid, ok=False)
            try:
                self._source_thread = threading.Thread(target=self._replace_install, args=(path,), daemon=True)
                self._source_thread.start()
            except Exception:  # noqa: BLE001 -- keep source selection available if the worker cannot start
                self._source_state = dict(running=False, result="@t4.install_failed", id=sid, ok=False)
                return "@t4.install_failed"
            return "@t4.installing"
        self.iso_note = "@iso.checking"
        self._source_state = dict(running=True, result="", id=sid, ok=False)
        try:
            self._source_thread = threading.Thread(target=self._check_iso, args=(path,), daemon=True)
            self._source_thread.start()
        except Exception as error:  # noqa: BLE001 -- do not strand the source row in Checking
            self.iso_note = self.message("iso.check_failed", error=str(error) or error.__class__.__name__)
            self._source_state = dict(running=False, result=self.iso_note, id=sid, ok=False)
            return self.iso_note
        return "@iso.checking"

    def _replace_install(self, path):
        try:
            result = install_source(self.m, self.config, path)
        except Exception:  # noqa: BLE001 -- the registration result is shown by the source picker
            result = "@t4.install_failed"
        self._source_state = dict(running=False, result=result, id="folder", ok=result == "reload")

    @staticmethod
    def _iso_stamp(path):
        try:
            info = os.stat(path)
            return os.path.normcase(os.path.abspath(path)), info.st_size, info.st_mtime_ns
        except OSError:
            return None

    def region_problem(self):
        """US release only (t4_region): the source core checks its tree; a portable install is checked here."""
        check = getattr(self.core, "region_problem", None)
        return check() if callable(check) else t4_region.tree_problem(self.root)

    def _check_iso(self, path):
        accepted = False
        try:
            before = self._iso_stamp(path)
            region = self.region_problem()
            ok, reason = (False, region) if region else self.core.verify_iso(path)
            if not ok:
                result = self.message("iso.refused", error=reason)
            elif before is None or before != self._iso_stamp(path):
                result = "@iso.changed"
            else:
                with self._settings_lock:
                    settings = dict(self.s, iso=path)
                    self.core.save_settings(settings)
                    self.s["iso"] = path
                self._verified_iso = before
                self._iso_save_pending = (os.path.normcase(os.path.abspath(self.root)), list(before))
                accepted = True
                result = "@iso.confirmed"
        except Exception as error:  # noqa: BLE001 -- verifier or storage failures remain visible in Build
            result = self.message("iso.check_failed", error=str(error) or error.__class__.__name__)
        self.iso_note = result
        self._source_state = dict(running=False, result=result, id="iso", ok=accepted)

    def source_state(self):
        self._save_pending()
        return dict(self._source_state)

    def build_ready(self):
        if self._online_work_active():
            return "@t4.work_busy"
        if self._source_state["running"]:
            return "@t4.installing" if self._source_state["id"] == "folder" else "@iso.checking"
        region = self.region_problem()
        if region:
            return region
        if self._needs_toolchain():
            return "@t4.portable_required"
        iso = self.core.effective_iso(self.s)
        if not (iso and self._verified_iso == self._iso_stamp(iso) and self._verified_iso):
            return "@iso.choose_first"
        # Last on purpose: when only tools are missing, Build installs them first (build_prepares) and the ISO is
        # already known to be right -- nobody waits half an hour for Visual Studio and then hears "choose your ISO".
        if getattr(self.core, "source_only", False) and not self._tools_ok():
            return "@t4.tools.required"
        return ""

    def build_start(self, force=False):
        if self._online_work_active() or self.running() or self._building():
            raise RuntimeError("@t4.work_busy")
        if not wine.powershell_works():          # Wine/Proton: build_game.ps1 cannot run there (always True on Windows)
            raise RuntimeError("@t4.no_powershell")
        problem = self.build_ready()
        if problem and problem not in self.build_prepares():
            raise RuntimeError(problem)
        self.last_result = ""
        self.build_failed = ""
        self.build_lines = []
        if problem:
            self._pipeline = dict(running=True, cancel=False)
            self._tool_install = dict(running=True, done=0, total=0, current="", result="")
            try:
                threading.Thread(target=self._tools_then_build, args=(force,), daemon=True).start()
            except Exception:
                self._pipeline = dict(running=False, cancel=False)
                self._tool_install = dict(running=False, done=0, total=0, current="", result="")
                raise
            return
        self._start_process(force)

    def _start_process(self, force=False):
        iso = self.core.effective_iso(self.s)
        if self._bundled_release():
            # The release's bundled compiler needs Microsoft's C++ headers/libraries, fetched once from Microsoft
            # with fixed checksums (never in our zip). The Build card names the licence before this press.
            cmd = self.core.build_command(iso, accept_microsoft_license=True)
        else:
            cmd = self.core.build_command(iso)
        if force:
            cmd.append("-Force")
        self.build_lines = []
        self.build_error = ""
        self.build_done = {}
        self.build_step = ""
        self.build_step_no = (0, 0)
        self.last_result = ""
        try:
            kwargs = dict(cwd=self.root, on_line=self._on_line)
            if getattr(self.core, "source_only", False):
                kwargs["env"] = self.core.build_env()
            self.build = ProcessBuild(cmd, **kwargs)
        except Exception as error:
            self.build = None
            self.build_failed = "build"
            self.last_result = self.message("t4.build_start_failed", error=str(error) or error.__class__.__name__)
            raise
        threading.Thread(target=self._build_end, args=(self.build,), daemon=True).start()

    def _on_line(self, line):
        self.build_lines = (self.build_lines + [line])[-40:]
        if line.lstrip().startswith("FAILED at step "):
            # The script repeats its output tail after this diagnostic.
            self.build_error = line.strip()
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
        if self.build is not build:
            return
        if build.cancelled:
            self.last_result = "@t4.build_cancelled"
        elif build.code == 0:
            self.build_done[self.build_step] = True
            clear_rebuild("t4", self.root)
            self.refresh_after_build()
            self.last_result = "@t4.build_finished" if self.ready() else "@t4.build_incomplete"
        else:
            error = self.build_error or next((line for line in reversed(self.build_lines)
                                               if line.strip() and not line.lstrip().startswith(("Full log:", "---"))),
                                              "@t4.no_build_output")
            self.build_failed = "build"
            self.last_result = self.message("t4.build_failed", name=self.build_step or "?", error=error)

    def refresh_after_build(self):
        """The build changed files on disk: nothing remembered from before it may stay (0.1.5). A match started right
        after a build once did not start the game until the launcher was restarted. Settings are read again (the
        saved values win, nothing is dropped), the tool check runs again, and an Online error that only said "build
        first" is cleared."""
        try:
            fresh = self.core.load_settings()
        except Exception:  # noqa: BLE001 -- the old settings still work
            fresh = None
        if isinstance(fresh, dict):
            with self._settings_lock:
                self.s = dict(self.s, **fresh)
        if getattr(self.core, "source_only", False):
            self.refresh_prerequisites()
        if (self.__dict__.get("_online_phase") == "error" and self.__dict__.get("_online_message") == "@online.build_required"
                and self.__dict__.get("_online_client") is None and not self.__dict__.get("_online_busy")):
            self._online_phase, self._online_message = "offline", "@online.offline"

    def _bundled_release(self):
        if getattr(self.core, "source_only", False):
            return False
        bundled = getattr(self.core, "bundled_toolchain", None)
        return bool(callable(bundled) and bundled())

    def microsoft_note(self):
        """The Build card's line: what is wrong with this folder (an old source-only release builds with the PC's
        own Visual Studio: another build id than everyone on 0.1.3), else the licence line while Microsoft's headers
        are not on this PC yet ("" once they are)."""
        folder = self.folder_problem()
        if folder:
            return folder
        if not self._bundled_release():
            return ""
        ready = getattr(self.core, "sysroot_ready", None)
        if callable(ready) and ready():
            return ""
        return "@t4.microsoft_note"

    def build_state(self):
        """Also: phase ("tools" while missing tools are installed, "build"), tools (done, total), lines (the last
        output lines for the collapsible log) and failed ("tools"/"build": where the last attempt stopped)."""
        self._save_pending()
        tools_phase = self._pipeline["running"]
        running = bool(tools_phase or self.build and self.build.running())
        steps = []
        for name, label in self.core.STEPS:
            if name in self.build_done:
                value = "@osk.done"
            elif running and name == self.build_step:
                value = "@running"
            elif self.build and self.build.code not in (None, 0) and name == self.build_step:
                value = "@t4.step_failed"
            else:
                value = "@pending"
            steps.append(dict(k=label, v=value))
        n, total = self.build_step_no
        fraction = 1.0 if self.last_result == "@t4.build_finished" else (max(0, n - 1) / total) if total else 0.0
        install = self._tool_install
        state = dict(running=running, fraction=0.0 if tools_phase else fraction,
                     title="" if tools_phase else self.build_step,
                     steps=steps, result=self.last_result, line=self.build_lines[-1] if self.build_lines else "",
                     lines=list(self.build_lines[-14:]), phase="tools" if tools_phase else ("build" if running else ""),
                     tools=dict(done=install.get("done", 0), total=install.get("total", 0),
                                current=install.get("current", "")),
                     failed=self.build_failed if not running else "")
        if total and not tools_phase:
            state["step_no"] = [n, total]
        return state

    def build_cancel(self):
        if self._pipeline["running"]:
            self._pipeline["cancel"] = True          # stops after the tool being installed now (never mid-install)
        elif self.build:
            self.build.cancel()


def friendly_time(stamp):
    """2026-10-30 02:06:42 -> 30.10., 02:06"""
    if not isinstance(stamp, str):
        return "@never"
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
