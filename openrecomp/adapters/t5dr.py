"""Tekken 5 DR: the installed T5DR Online's own Python (launcher/core.py, replays.py, lobby/t5lobby) does the work.

Nothing of it is copied: OpenRecomp-FGC imports it from the player's install. Pictures come from that install's cache
(read from the player's own built game by fighter_art.py) and stay on the PC.
"""
import glob
import hashlib
import importlib.util
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

from .base import Adapter, Missing, NO_WINDOW, add_path, expand_locations
from .t5_controls import Controls
from .support import T5Support
from .t5_match import T5Match
from .t5_online import game_process_running
from .launch_guard import LaunchGuard
from .t5_coexist import load_settings, readonly_imports
from .t5_compatibility import build_compatibility
from .t5_build_runtime import start_build_with_python
from . import t5_buildlock
from .. import t5_art_child, t5_startlog
from ..manifest import art_dir
from ..fighter_render import t5_cache_name
from ..game_releases import managed as _managed_install
from ..player_main import choose_main, local_main

RANK_BADGES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "assets", "ranks")

DISPLAY = [("window", "@display.window"), ("window1080", "@display.1080"), ("window1440", "@display.1440"),
           ("maximized", "@display.max"), ("borderless", "@display.borderless")]
RES_NAMES = {"lowest": "@resolution.lowest", "lower": "@resolution.lower", "native": "@resolution.native", "1080p": "1080p",
             "1440p": "1440p", "4k": "4K", "auto": "@resolution.auto"}
ON_OFF = [("on", "@on"), ("off", "@off")]
YES_NO = [(False, "@off"), (True, "@on")]
STATE_SECONDS = 3.0          # beside a T5DR launcher: how old the build state may get before it is read again
RANK_TAG = re.compile(r"\s*\[\d+\]$")
# Windows' 260-character path limit as the game's Python and the build tools report it (any language: the code is fixed)
PATH_ROOM = 70           # characters the game's Python files add below the folder (python\Lib\site-packages\Crypto\Cipher\...)
PATH_TOO_LONG = re.compile(r"WinError 206|filename or extension is too long|path too long|Errno 36", re.I)


def version_key(root):
    try:
        with open(os.path.join(root, "release.json"), encoding="utf-8") as f:
            version = json.load(f).get("version", "0")
        match = re.fullmatch(r"[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?", version)
        if match:
            return tuple(int(p) for p in match.group(1, 2, 3)) + (not bool(match.group(4)),)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return (0,)


def install_root(path):
    """An install, or the only install immediately inside its enclosing folder."""
    if os.path.isfile(os.path.join(path, "launcher", "core.py")):
        return os.path.abspath(path)
    try:
        with os.scandir(path) as entries:
            found = [entry.path for entry in entries if entry.is_dir()
                     and os.path.isfile(os.path.join(entry.path, "launcher", "core.py"))]
    except OSError:
        return None
    return os.path.abspath(found[0]) if len(found) == 1 else None


def root_candidates(path):
    """A player's folder, its three parents and direct children; never a recursive search."""
    def complete(root):
        return all(os.path.isfile(os.path.join(root, name)) for name in
                   ("T5DR Online.exe", "release.json", os.path.join("python", "python.exe")))

    path = os.path.realpath(path)
    if complete(path):
        return [path]
    nearby = []
    parent = path
    for _ in range(3):
        above = os.path.dirname(parent)
        if above == parent:
            break
        nearby.append(above)
        parent = above
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        nearby.append(entry.path)
                except OSError:
                    pass
    except OSError:
        pass
    found = {}
    for root in nearby:
        if complete(root):
            root = os.path.realpath(root)
            found[os.path.normcase(root)] = root
    return sorted(found.values(), key=str.casefold)


def legacy_install(root):
    return version_key(root)[:2] == (1, 1)


class LegacyT5DR(Missing):
    """An old release can be updated without importing its launcher modules."""
    def __init__(self, manifest, config, root):
        super().__init__(manifest, config)
        self.root = root
        self.problem = "@t5.folder_old"

    def setup_root(self):
        return self.root

    def sources(self):
        return [dict(id="folder", label="@t5.choose_install", value=self.root, ok=True,
                     kind="folder", exts=[], dirs=[self.root], hint="@t5.folder_old", note="")]


def _has_build(root):
    out_dir = os.path.join(root, "native")
    try:
        with open(os.path.join(root, "launcher.json"), encoding="utf-8") as stream:
            settings = json.load(stream)
        selected = settings.get("out_dir") or settings.get("out")
        if isinstance(selected, str) and selected:
            out_dir = selected if os.path.isabs(selected) else os.path.join(root, selected)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        with open(os.path.join(out_dir, "build", "t5dr_build.json"), encoding="utf-8") as stream:
            stamp = json.load(stream)
        return isinstance(stamp, dict) and bool(stamp.get("code_id"))
    except (OSError, ValueError):
        return False


def find_root(manifest, config):
    """The newest installed T5DR Online with a built game; else the newest install."""
    chosen = (config.get("roots") or {}).get(manifest["id"]) or os.environ.get("OPENRECOMP_T5DR_ROOT")
    if chosen:
        roots = root_candidates(chosen)
        return roots[0] if len(roots) == 1 else (None if roots else install_root(chosen))
    found = []
    locations = manifest.get("locations") or ["%USERPROFILE%/Downloads/T5DR-Online-*",
                                               "%USERPROFILE%/Desktop/T5DR-Online-*"]
    # Beside the launcher's own folder: where Setup and the launcher's Install put T5DR (docs/INSTALLER.md)
    beside = glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), "T5DR-Online-*"))
    for path in expand_locations(locations) + sorted(beside):
        root = install_root(path)
        if root and root not in found:
            found.append(root)
    if not found:
        return None
    built = [p for p in found if _has_build(p)]
    return max(built or found, key=version_key)


_find_root_anywhere = find_root


def sibling_locations():
    """T5DR-Online-* folders beside this launcher's folder, as the test bundle (and Setup) place them."""
    launcher = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pattern = os.path.basename("%USERPROFILE%/Downloads/T5DR-Online-*")     # the same folder name as below
    return [os.path.join(glob.escape(os.path.dirname(launcher)), pattern)]


def find_root(manifest, config):  # noqa: F811 -- the search above, with the folder beside this launcher first
    """The chosen install; else one beside this launcher; else the newest found, a built one first."""
    chosen = (config.get("roots") or {}).get(manifest["id"]) or os.environ.get("OPENRECOMP_T5DR_ROOT")
    if chosen:
        roots = root_candidates(chosen)
        return roots[0] if len(roots) == 1 else (None if roots else install_root(chosen))
    return _find_root_anywhere(dict(manifest, locations=sibling_locations()), {}) or _find_root_anywhere(manifest, config)


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
        with readonly_imports():
            spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


class T5DR(Controls, T5Support, T5Match, Adapter):
    native_label = "@t5.native_label"
    other_launcher_game = "t5dr"           # its own launcher open too: other_launchers

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
        self.s = load_settings(core, root, settings_source=config.get("t5dr_settings_copy"))
        # An install this launcher downloaded is its own: building in it changes no other launcher's game.
        self.managed = _managed_install("t5dr", root)
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
        """The build's state. Beside a T5DR launcher (coexistence) that launcher can rebuild the shared game at any
        time, so the answer is read again -- but on a worker every STATE_SECONDS: reading it hashes the patch series
        and took 100-450 ms, and the window asked several times per redraw (the launcher froze while scrolling)."""
        coexist = getattr(self.s, "coexistence", False)
        if self._state is None or fresh:
            self._state = self._read_state()
            self._state_at = time.monotonic()
        elif coexist and time.monotonic() - getattr(self, "_state_at", 0.0) >= STATE_SECONDS                 and not getattr(self, "_state_busy", False):
            self._state_busy = True
            threading.Thread(target=self._refresh_state, name="openrecomp-t5-state", daemon=True).start()
        return self._state

    def _read_state(self):
        state = dict(self.core.game_state(self.s.out_dir))
        if getattr(self.s, "coexistence", False):
            compatibility = self.coexistence_state()["build"]
            state["compatibility"] = compatibility
            if compatibility == "different":
                state.update(ok=False, needs_rebuild=True)
            elif compatibility == "unknown" and state.get("built"):
                state["ok"] = False
        return state

    def _refresh_state(self):
        try:
            state = self._read_state()
            if self._state is not None:      # a reset (new package, finished build) asks again itself
                self._state = state
        except Exception:  # noqa: BLE001 -- the last answer stays; the next refresh tries again
            pass
        finally:
            self._state_at = time.monotonic()
            self._state_busy = False

    def coexistence_state(self):
        # can_build: a folder set up by T5DR's own launcher is built here too (docs/T5DR_COEXISTENCE.md "Building");
        # both launchers keep using it, which is why `active` stays on.
        return dict(active=self._borrowed(), source=self.root, can_build=True,
                    build=build_compatibility(self.release(), self.s.out_dir))

    def _borrowed(self):
        """A folder set up by T5DR's own launcher (no OpenRecomp install marker): shared with that launcher."""
        return bool(getattr(self.s, "coexistence", False)) and not getattr(self, "managed", False)

    def foreign_notice_pending(self):
        """True until the player has been told (once per folder) that OpenRecomp builds a T5DR launcher folder."""
        return self._borrowed() and self._folder_id() not in (self.config.get("t5dr_folder_notice") or [])

    def foreign_notice_done(self):
        seen = list(self.config.get("t5dr_folder_notice") or [])
        if self._folder_id() not in seen:
            seen.append(self._folder_id())
        self.config["t5dr_folder_notice"] = seen        # OpenRecomp's own config; nothing is written into the folder

    def _folder_id(self):
        return hashlib.sha256(os.path.normcase(os.path.realpath(self.root)).encode("utf-8")).hexdigest()[:24]

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
            status, detail = "@ready", "@t5.coexist.build_match" if st.get("compatibility") == "same" else "@t5.ready_detail"
        elif st.get("compatibility") == "different":
            status, detail = "@build_again", "@t5.coexist.build_differs"
        elif st.get("compatibility") == "unknown" and st.get("built"):
            status, detail = "@not_ready", "@t5.coexist.build_unknown"
        elif st["needs_rebuild"]:
            status, detail = "@build_again", "@t5.rebuild_detail"
        else:
            status, detail = "@not_built", "@t5.build_detail"
        return dict(status=status, version=self.message("version_tag", version=version), players="@lobby_ranked", last=last, detail=detail)

    # ---------------------------------------------------------------- pictures
    def face(self, gid):
        faces = self.__dict__.setdefault("_faces", {})      # asked for every lobby row on every redraw
        if faces.get(gid):
            return faces[gid]
        path = os.path.join(self.s.out_dir, "cache", "fighters", f"face_{gid:02d}.png")
        faces[gid] = path if os.path.isfile(path) else ""
        return faces[gid]

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
            with readonly_imports():
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
        previous = getattr(self, "_game_guard", None)
        if previous is not None:
            previous.release()
        guard = LaunchGuard("t5dr")
        guard.acquire()
        game = None
        try:
            running = game_process_running()
            if running is None:
                raise RuntimeError("@online.process_unknown")
            if running:
                raise RuntimeError("@online.game_running")
            game = self.core.GameRun(self.s.out_dir, self.s)
            self.game = game
            result = game.start(extra_env=extra_env)
            t5_startlog.write(self, result, extra_env)
            self._track_playtime(game.running, process=getattr(game, "proc", None), extra_env=extra_env)
            self._game_guard = guard
            guard.watch(game.running)
        except Exception:
            if game is None:
                guard.release()
            else:
                self._game_guard = guard
                try:
                    game.stop()
                except Exception:  # retain ownership even when stopping fails
                    pass
                try:
                    if game.running():
                        guard.watch(game.running)
                    else:
                        guard.release()
                except Exception:  # an unknown child or failed monitor must keep its reservation
                    pass
            raise
        return result

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
        process = self._exe_launcher()
        self._track_native_playtime(process, ("t5dr.exe",))

    # ---------------------------------------------------------------- settings
    def _input_delay_options(self):
        supported = getattr(self.core, "INPUT_DELAYS", ("auto", "0", "1", "2"))
        labels = {"auto": "@resolution.auto", "0": "@delay.zero", "1": "@delay.one", "2": "@delay.two"}
        return [(value, labels.get(value) or self.message("t5.delay_frames", count=int(value)))
                for value in ("auto",) + tuple(str(n) for n in range(9)) if value in supported]

    def settings(self):
        s = self.s
        res = [(k, RES_NAMES.get(k, k)) for k in self.core.INTERNAL_RES_LABELS]
        delay = self._input_delay_options()
        out = [
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
            self._screen_side_setting(),
            dict(id="mute", label="@mute", options=YES_NO, value=bool(s["mute"]), hint="@mute.hint", lead="@mute.hint"),
            dict(id="replays", label="@save_replays", options=YES_NO, value=bool(s["replays"]),
                 hint="@save_replays.hint", lead="@save_replays.lead"),
            dict(id="unlock_stages", label="@old_stages", options=YES_NO, value=bool(s["unlock_stages"]),
                 hint="@old_stages.hint", lead="@offline_only"),
            dict(id="unlock_items", label="@free_items", options=YES_NO, value=bool(s["unlock_items"]),
                 hint="@free_items.hint", lead="@offline_only"),
        ]
        supported = getattr(self.core, "DEFAULTS", s)
        for sid, label, hint in (("replay_names", "@t5.replay_names", "@t5.replay_names_hint"),
                                 ("spectators", "@t5.spectators", "@t5.spectators_hint"),
                                 ("spectators_ranked", "@t5.spectators_ranked", "@t5.spectators_ranked_hint"),
                                 ("auto_spectate", "@t5.auto_spectate", "@t5.auto_spectate_hint")):
            if sid in supported:
                out.append(dict(id=sid, label=label, options=YES_NO, value=bool(s.get(sid, False)),
                                hint=hint, lead=hint))
        if "replay_dir" in supported:
            folder = s.get("replay_dir") or ""
            out.append(dict(id="replay_dir", kind="folder", label="@t5.replay_folder", value=folder,
                            display=folder or "@t5.replay_folder_default", hint="@t5.replay_folder_hint"))
        return out

    def _screen_sides(self):
        """1.2.0 has dealt / left / right (screen_side); older installs only the always_left flag."""
        sides = getattr(self.core, "SCREEN_SIDES", None)
        if "screen_side" in getattr(self.core, "DEFAULTS", {}) and isinstance(sides, dict):
            labels = {"dealt": "@t5.side_server", "left": "@t5.side_left", "right": "@t5.side_right"}
            return [(side, labels[side]) for side in ("dealt", "left", "right") if side in sides]
        return None

    def _screen_side_setting(self):
        sides = self._screen_sides()
        if sides is None:
            return dict(id="always_left", label="@t5.screen_side", options=[(False, "@t5.side_server"), (True, "@t5.side_left")],
                        value=bool(self.s["always_left"]), hint="@always_left.hint", lead="@always_left.lead")
        value = self.s.get("screen_side")
        if value not in {side for side, _label in sides}:
            value = "left" if self.s.get("always_left") is True else "dealt"
        return dict(id="screen_side", label="@t5.screen_side", options=sides, value=value,
                    hint="@t5.screen_side.hint", lead="@always_left.lead")

    def screen_side(self):
        """The token the game gets as T5_SCREEN_SIDE (1.2.0), also for each online match of a persistent game."""
        return self._screen_side_setting()["value"] if self._screen_sides() else (
            "left" if self.s.get("always_left") else "dealt")

    def set_setting(self, sid, value):
        if sid == "screen_side":
            if value not in {side for side, _label in (self._screen_sides() or ())}:
                raise ValueError("@not_ready")
            # Keep the legacy flag in step, as the installed Settings.save() does for older readers.
            self.s["always_left"] = value == "left"
        elif sid == "always_left" and self._screen_sides():
            value = bool(value)
            self.s["screen_side"] = "left" if value else "dealt"
        if sid == "input_delay":
            value = str(value)
            if value not in {option for option, _label in self._input_delay_options()}:
                raise ValueError("@not_ready")
        if sid == "replay_dir":
            if not isinstance(value, str) or (value and not os.path.isdir(value)):
                raise ValueError("@t5.replay_folder_missing")
            self._replays = None
        self.s[sid] = value
        if sid == "internal_res":
            self.s["internal_res_set"] = True
        self.s.save()

    def quick_settings(self):
        return ["display", "internal_res"]

    def text_value(self, tid):
        if tid.startswith("online_"):
            return self.online_text_value(tid)
        if tid.startswith("support_"):
            return self.support_text_value(tid)
        if tid == "replay_dir":
            return self.s.get("replay_dir") or ""
        return self.s["nickname"] if tid == "nickname" else ""

    def set_text_value(self, tid, value):
        if tid.startswith("online_"):
            self.set_online_text_value(tid, value)
            return
        if tid.startswith("support_"):
            self.set_support_text_value(tid, value)
            return
        if tid == "replay_dir":
            self.set_setting(tid, value)
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

    def fighter_label(self, key):
        return next((f["name"] for f in self._fighter_table() if f["key"] == key), key or "")

    def rank_plate(self, tier):
        """The plate the T5DR launcher reads from this build (output folder, cache, ranks). Looked up once per tier:
        the online table asks for every player on every redraw. A build whose plates were never read (this launcher
        built it, T5DR's own never ran) gets them read once in the background (0.1.5); until they are there -- or when
        they cannot be read -- the drawn badge of the same tier stands in, so a rank never shows without an emblem."""
        if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier < 64:
            return ""
        plates = self.__dict__.setdefault("_plates", {})
        if plates.get(tier):
            return plates[tier]
        path = os.path.join(self.s.out_dir, "cache", "ranks", "rank_%02d.png" % tier)
        if os.path.isfile(path):
            plates[tier] = path
            return path
        self._start_rank_plates()
        badge = os.path.join(RANK_BADGES, "t4_rank_%02d.svg" % tier)       # the same 37-rank ladder
        return badge if os.path.isfile(badge) else ""

    def _art_idle(self):
        """Pictures are read before a match or after it, never while a game runs or an online match is being set up."""
        try:
            game = getattr(self, "game", None)
            return not (game and game.running()) and getattr(self, "_online_driver", None) is None
        except Exception:  # noqa: BLE001 -- unknown state: wait
            return False

    def _art_child(self, job):
        """One picture job in a child process (t5_art_child.run): (exit code, last error line)."""
        return t5_art_child.run(self.root, self.s.out_dir, job)

    def _start_rank_plates(self):
        """Read the game's own plates once per launcher run: in a child process, and only while no match runs."""
        try:
            if self.__dict__.get("_plates_tried") or not self.state().get("built") or not self._art_idle():
                return
        except Exception:  # noqa: BLE001 -- not a built game yet: nothing to read
            return
        self._plates_tried = True
        threading.Thread(target=self._make_rank_plates, daemon=True).start()

    def _make_rank_plates(self):
        try:
            self._art_child(t5_art_child.plates())
        except Exception:  # noqa: BLE001 -- the drawn badges stay; a missing picture never stops the launcher
            pass

    def fighter_image(self, key):
        gid = next((f["id"] for f in self._fighter_table() if f["key"] == key), None)
        return self.face(gid) if gid is not None else ""

    def fighter_render(self, key, mirrored=False):
        gid = next((f["id"] for f in self._fighter_table() if f["key"] == key), None)
        if not isinstance(gid, int) or gid < 0:
            return ""
        token = (gid, bool(mirrored))
        path = os.path.join(art_dir("t5dr"), "fighters", t5_cache_name(gid, mirrored=mirrored))
        if os.path.isfile(path):
            return path
        lock = self.__dict__.setdefault("_render_lock", threading.Lock())
        with lock:
            tried = self.__dict__.setdefault("_render_tried", set())
            busy = self.__dict__.setdefault("_render_busy", set())
            if token in tried or token in busy or not self.state().get("built") or not self._art_idle():
                return ""
            busy.add(token)
            tried.add(token)
        try:
            threading.Thread(target=self._make_fighter_render, args=(gid, path, bool(mirrored)), daemon=True).start()
        except Exception as error:  # noqa: BLE001 -- optional pictures never stop a screen
            with lock:
                busy.discard(token)
                tried.discard(token)
            self.problem = self.message("picture_error", error=str(error))
        return ""

    def _make_fighter_render(self, gid, path, mirrored=False):
        try:
            code, last = self._art_child(t5_art_child.render(gid, path, mirrored))
            if code:
                self.problem = self.message("picture_error", error=last or str(code))
        except Exception as error:  # noqa: BLE001 -- optional pictures never stop a screen
            self.problem = self.message("picture_error", error=str(error))
        finally:
            with self._render_lock:
                self._render_busy.discard((gid, mirrored))

    def online_cfg_path(self):
        if getattr(self.s, "coexistence", False):
            return self.s.online_config_path
        base = os.environ.get("T5_ONLINE_DIR")
        if base:
            return os.path.join(base, "online.json")
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "T5DROnline", "online.json")

    def _online_cfg(self):
        if getattr(self.s, "coexistence", False):
            return self._online_config()
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
        if getattr(self, "_online_character_locked", False):
            raise RuntimeError("@online.character_locked")
        if getattr(getattr(self, "s", None), "coexistence", False):
            self._online_write_preferences(dict(char=key))
            return
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
        """This player's server main, falling back to their local match history."""
        key = choose_main(getattr(self, "_online_me", {})) or local_main(self)
        return next((row["id"] for row in self._fighter_table() if row.get("key") == key), None)

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
            # 0.1.3: the folder in use, always on the page; choosing another T5DR folder switches to it at any time.
            dict(id="folder", label="@t5.game_folder", title="@t5.choose_install", value=self.root, ok=True, kind="folder",
                 exts=[], dirs=[os.path.dirname(self.root), os.path.join(home, "Downloads")],
                 hint="@t5.folder_change_hint", note=""),
            dict(id="pkg", label="@package", value="@found" if pkg_ok else "@missing", ok=pkg_ok, kind="file", exts=[".pkg"], dirs=dirs,
                 title="@t5.choose_pkg", filter="@t5.pkg_filter",
                 hint="@package.hint", note=pkg_text),
            dict(id="rap", label="@license", value="@found" if rap_ok else "@missing", ok=rap_ok, kind="file", exts=[".rap"], dirs=dirs,
                 title="@t5.choose_rap", filter="@t5.rap_filter",
                 hint="@license.hint", note=""),
        ]

    def source_choices(self, sid, path):
        return root_candidates(path) if sid == "folder" else None

    def existing_installs(self, parent=""):
        from .t5_discovery import existing_installs
        return existing_installs(self.m, self.config, parent)

    def set_source(self, sid, path):
        if sid == "folder":
            choices = root_candidates(path)
            if len(choices) != 1:
                return "@t5.install_incomplete_python"
            root = choices[0]
            if os.path.normcase(os.path.realpath(root)) != os.path.normcase(os.path.realpath(self.root)):
                self.config.pop("t5dr_settings_copy", None)
            from ..known_installs import remember
            remember(self.config, self.m["id"], root, self.root or "")
            self.config.setdefault("roots", {})[self.m["id"]] = root
            return "reload"
        self.s[sid] = path
        self.s.save()
        self._state = None
        return ""

    def build_options(self):
        return [dict(id="low_priority", label="@responsive", options=YES_NO, value=bool(self.s["low_priority"]),
                     hint="@responsive.hint", lead="@responsive.lead")]

    def build_install_problem(self):
        own_python = os.path.join(self.root, "python", "python.exe")
        try:
            exe = os.stat(own_python)
            folder = os.stat(os.path.dirname(own_python))
            key = (os.path.normcase(os.path.realpath(self.root)), exe.st_mtime_ns, exe.st_size, folder.st_mtime_ns)
        except OSError:
            return "@t5.install_incomplete_python"
        # Redraws and Check my problem share the probe. Replacing the release's Python invalidates it.
        lock = self.__dict__.setdefault("_build_python_lock", threading.Lock())
        with lock:
            if getattr(self, "_build_python_probe", (None,))[0] != key:
                problem = "@t5.install_incomplete_python"
                # The first start of a freshly unpacked python.exe can take seconds (antivirus scan, cold disk, a busy
                # PC): a timeout earns one longer try before the install is called damaged. A failed import or a
                # missing/unstartable program is final at once.
                for timeout in (3, 25):
                    try:
                        subprocess.run([own_python, "-I", "-c", "from Crypto.Cipher import AES"], cwd=self.root,
                                       timeout=timeout, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.PIPE, creationflags=NO_WINDOW)
                        problem = ""
                        break
                    except subprocess.TimeoutExpired:
                        continue
                    except subprocess.CalledProcessError as error:
                        # A path past Windows' limit breaks the native module's load (WinError 206): the Python is
                        # fine, so the answer is "move the folder", not "reinstall".
                        text = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else str(error.stderr or "")
                        if PATH_TOO_LONG.search(text) or len(os.path.abspath(self.root)) + PATH_ROOM >= 260:
                            problem = "@t5.install_path_too_long"
                        break
                    except (OSError, subprocess.SubprocessError):
                        break
                self._build_python_probe = (key, problem)
            if self._build_python_probe[1]:
                return self._build_python_probe[1]
        if (not os.path.isfile(os.path.join(self.root, "tools", "build_game.py"))
                or not os.path.isdir(os.path.join(self.root, "toolchain"))
                or not os.path.isdir(os.path.join(self.root, "deps", "ps3recomp"))):
            return "@t5.install_incomplete_tools"
        return ""

    def build_ready(self):
        problem = self.build_install_problem()
        if problem:
            return problem
        if getattr(self, "build", None) is None:
            problem = t5_buildlock.blocker(self.root, self.s.out_dir)
            if problem:
                return problem
        if not self.s["pkg"] or not self.s["rap"]:
            return "@choose_package_license"
        return ""

    def _support_install_findings(self):
        problem = self.build_install_problem()
        return [dict(id="t5_install", label="@support.finding.t5_install.title", seen="", fix=problem,
                     kind="problem")] if problem else []

    def build_start(self, force=False):
        problem = self.build_install_problem()
        if problem:
            raise RuntimeError(problem)
        t5_buildlock.acquire(self.root, self.s.out_dir)       # one build at a time, whichever launcher starts it
        try:
            self._build_start(force)
        except BaseException:
            t5_buildlock.release(self.root)
            raise

    def _build_start(self, force):
        self.build_steps = {}
        self.build_step = ""
        self.build_fraction = 0.0
        self.build_lines = []
        self.last_result = ""
        self.build = self.core.BuildRun(self.s["pkg"], self.s["rap"], self.s.out_dir, force=force, low_priority=bool(self.s["low_priority"]))
        own_python = os.path.join(self.root, "python", "python.exe")      # the build's tools run on the install's Python
        start_build_with_python(self.build, own_python)

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
                self.build_fraction = 0.0
            elif kind == "skip":
                self.build_steps[value] = "@osk.done"
            elif kind == "sub":
                self.build_fraction = float(value)
            elif kind == "line":
                self.build_line = str(value)
                self.build_lines = (getattr(self, "build_lines", []) + [self.build_line])[-14:]
                if PATH_TOO_LONG.search(self.build_line):
                    self._path_too_long = True
            elif kind == "error":
                self.last_result = str(value)
            elif kind == "end":
                t5_buildlock.release(getattr(self, "root", ""))
                if value not in (0, -1) and getattr(self, "_path_too_long", False):
                    # Not "reinstall": the folder is fine, its path is too long for Windows
                    self.last_result = "@t5.build_path_too_long"
                self._path_too_long = False
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
                return          # the run is gone: reading its queue again raised AttributeError in the window's tick

    def build_state(self):
        self._pump_build()
        names = list(self.core.STEP_TITLES)
        steps = [dict(k=self.core.STEP_TITLES[n], v=self.build_steps.get(n, "@pending")) for n in names]
        done = sum(1 for n in names if self.build_steps.get(n) == "@osk.done")
        running = self.build is not None
        # The step's own progress ("sub", 0..1) moves the bar between steps too: a long lift no longer looks stuck.
        sub = min(1.0, max(0.0, self.build_fraction)) if running and self.build_steps.get(self.build_step) == "@running" else 0.0
        state = dict(running=running, fraction=(done + sub) / len(names) if names else 0.0,
                     title=self.core.STEP_TITLES.get(self.build_step, ""), steps=steps, result=self.last_result,
                     line=self.build_line, lines=list(getattr(self, "build_lines", [])),
                     phase="build" if running else "",
                     failed="build" if not running and self.last_result and self.last_result not in ("@build_finished", "@cancelled") else "")
        if running and self.build_step in names:
            state["step_no"] = [names.index(self.build_step) + 1, len(names)]
        return state

    def build_cancel(self):
        if self.build:
            self.build.cancel()
