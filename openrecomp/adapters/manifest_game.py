"""A game from a version 2 manifest (openrecomp/game_manifest.py): everything a screen needs, from data only.

Found: the chosen folder, else the first folder from `install.search` that has every `install.detect` file.
Start: `start.exe` inside that folder with its arguments, working folder and environment (plus the settings that
go to arguments / the environment); never a shell. Stop: ask the game's windows to close (WM_CLOSE, like
Process.CloseMainWindow), wait `stop.close_window_seconds`, then end it; a second Stop ends it at once.
Updates: `check_updates()` (the launcher calls it once after start; never in tests) asks the release's GitHub
repository for the newest release of its channel and, for `ed25519`, checks the release's SHA256SUMS signature
with the manifest's key before it says "update available". Installing it is the game's own business (its updater,
or the adapter named in `code_adapter`): the manifest only tells the player.
"""
import os
import subprocess
import threading

from .base import Adapter
from .. import game_manifest as gm
from .. import i18n
from ..manifest import art_dir, resolve_path, save_config, ManifestError


def is_install(path, detect):
    if not path or not os.path.isdir(path):
        return False
    try:
        return all(os.path.isfile(resolve_path(path, rel)) for rel in detect)
    except ManifestError:
        return False


def detect_files(m):
    return m.get("install", {}).get("detect") or [m["start"]["exe"]]


def find_root(m, config):
    detect = detect_files(m)
    chosen = (config.get("roots") or {}).get(m["id"])
    if isinstance(chosen, str) and chosen:
        return os.path.abspath(chosen) if is_install(chosen, detect) else None
    for path in gm.search_paths(m.get("install", {}).get("search")):
        if is_install(path, detect):
            return os.path.abspath(path)
    return None


class Broken(Adapter):
    """A manifest that could not be used: the shelf shows its title and why."""

    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self.problem = i18n.literal(manifest.get("broken", ""))

    def status(self):
        return dict(status="@manifest.broken", version="@none_lower", players="@no", last="@never",
                    detail=self.problem)

    def build_ready(self):
        return self.problem


class ManifestGame(Adapter):
    KILL_WAIT = 5

    def __init__(self, manifest, config=None, *, popen=None, close=None, fetch=None):
        super().__init__(manifest, config)
        self.root = find_root(manifest, self.config) or ""
        self.proc = None
        self.stopping = None
        self.lock = threading.Lock()
        self.popen = popen or subprocess.Popen
        self.close_windows = close or gm.close_windows
        self.fetch = fetch                      # tests: a fake GitHub (game_releases' opener)
        self.update = gm.cached_update(manifest) if manifest.get("updates") else None

    # ---------------------------------------------------------------- where it is
    def text(self, label):
        return i18n.literal(gm.label_text(label, i18n.normalize(self.config.get("language") or "")))

    def _path(self, rel):
        if not self.root:
            raise RuntimeError("@generic.root_missing")
        try:
            return resolve_path(self.root, rel)
        except ManifestError as e:
            raise RuntimeError("@generic.root_missing") from e

    def found(self):
        return bool(self.root)

    def ready(self):
        try:
            return self.found() and os.path.isfile(self._path(self.m["start"]["exe"]))
        except RuntimeError:
            return False

    def installed_version(self):
        if not self.root:
            return ""
        from .. import game_releases as gr
        marker = gr._read_json(os.path.join(self.root, gr.MARKER))
        if marker and marker.get("game") == self.m["id"] and marker.get("version"):
            return str(marker["version"])
        return gm.installed_version(self.root, (self.m.get("updates") or {}).get("installed_version"))

    def status(self):
        version = self.installed_version()
        shown = i18n.literal(version) if version else "@unknown"
        if not self.ready():
            return dict(status="@not_found", version="@none_lower", players="@no", last="@never",
                        detail="@generic.root_missing" if not self.found() else self.message(
                            "manifest.exe_missing", exe=i18n.literal(self.m["start"]["exe"])))
        offer = self.update_offer()
        if offer:
            return dict(status="@setup.update_available", version=shown, players="@no", last="@unknown",
                        detail=self._update_text(offer))
        return dict(status="@ready", version=shown, players="@no", last="@unknown", detail="@manifest.ready_hint")

    def hero(self):
        art = self.m.get("art") or {}
        candidates = []
        if art.get("cache"):
            candidates.append(os.path.join(art_dir(self.m["id"]), art["cache"]))
        if art.get("file") and self.root:
            try:
                candidates.append(self._path(art["file"]))
            except RuntimeError:
                pass
        for path in candidates:
            try:
                if path.lower().endswith(gm.IMAGE_TYPES) and os.path.isfile(path) and os.path.getsize(path) <= gm.MAX_IMAGE:
                    return path
            except OSError:
                continue
        return ""

    def sources(self):
        return [dict(id="folder", label="@game_folder", value=i18n.literal(self.root) if self.root else "@missing",
                     ok=self.found(), kind="folder", exts=[], dirs=[self.root] if self.root else [],
                     hint=self.message("manifest.folder_hint", exe=i18n.literal(self.m["start"]["exe"])))]

    def set_source(self, sid, path):
        if self.running():
            raise RuntimeError("@generic.running")
        detect = detect_files(self.m)
        if sid != "folder" or not is_install(path, detect):
            raise RuntimeError(self.message("manifest.not_install", exe=i18n.literal(detect[0])))
        self.config.setdefault("roots", {})[self.m["id"]] = os.path.realpath(path)
        return "reload"

    def build_ready(self):
        offer = self.update_offer()
        return self._update_text(offer) if offer else "@manifest.no_build"

    def _update_text(self, offer):
        unsigned = self.m["updates"]["verification"]["method"] == "unsigned"
        return self.message("manifest.update_unsigned" if unsigned else "manifest.update_available",
                            version=i18n.literal(offer["version"]), repository=i18n.literal(self.m["updates"]["repository"]))

    # ---------------------------------------------------------------- playing
    def _command(self, extra_env=None):
        start = self.m["start"]
        args = [str(a) for a in start.get("args") or []]
        env = dict(os.environ)
        env.update(start.get("env") or {})
        values = self._stored()
        for s in self.m.get("settings") or ():
            t = s["target"]
            value = self._value(s, values)
            if "env" in t:
                env[t["env"]] = gm.setting_text(value)
            elif "arg" in t:
                args.append(gm.arg_text(t["arg"], value))
        env.update(extra_env or {})
        cwd = self._path(start["cwd"]) if start.get("cwd") else self.root
        return [self._path(start["exe"])] + args, cwd, env

    def start(self, extra_env=None):
        with self.lock:
            if self.running():
                raise RuntimeError("@generic.running")
            if not self.ready():
                raise RuntimeError("@not_ready")
            argv, cwd, env = self._command(extra_env)
            self.proc = self.popen(argv, cwd=cwd, env=env, shell=False)
            proc = self.proc
            self._track_playtime(lambda: proc.poll() is None, process=proc, extra_env=extra_env)
            return self.proc.pid

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        with self.lock:
            proc = self.proc
            if proc is None or proc.poll() is not None:
                return
            wait = int((self.m.get("stop") or {}).get("close_window_seconds", 0))
            if self.stopping is proc or wait <= 0:
                self._terminate(proc)
                return
            self.stopping = proc
        threading.Thread(target=self._stop_work, args=(proc, wait), daemon=True).start()

    def _stop_work(self, proc, wait):
        try:
            try:
                asked = self.close_windows(proc.pid)
            except OSError:
                asked = 0
            if asked:
                try:
                    proc.wait(wait)
                except subprocess.TimeoutExpired:
                    pass
            if proc.poll() is None:
                self._terminate(proc)
        finally:
            with self.lock:
                if self.stopping is proc:
                    self.stopping = None

    def _terminate(self, proc):
        try:
            proc.terminate()
            proc.wait(self.KILL_WAIT)
        except (OSError, subprocess.TimeoutExpired):
            pass

    # ---------------------------------------------------------------- settings
    def _stored(self):
        stored = (self.config.get("manifest_settings") or {}).get(self.m["id"])
        return stored if isinstance(stored, dict) else {}

    @staticmethod
    def _default(s):
        if "default" in s:
            return s["default"]
        return False if s["type"] == "toggle" else s["options"][0]["value"]

    @staticmethod
    def _allowed(s, value):
        if s["type"] == "toggle":
            return type(value) is bool
        return any(type(o["value"]) is type(value) and o["value"] == value for o in s["options"])

    @staticmethod
    def _from_text(s, text):
        """A value read back from an INI / JSON file, matched to the setting's values."""
        if s["type"] == "toggle":
            if isinstance(text, bool):
                return text
            return {"1": True, "0": False, "true": True, "false": False}.get(str(text).strip().lower())
        for o in s["options"]:
            if o["value"] == text or gm.setting_text(o["value"]) == str(text):
                return o["value"]
        return None

    def _value(self, s, stored=None):
        t = s["target"]
        try:
            if "ini" in t:
                found = gm.ini_read(self._path(t["ini"]), t["section"], t["key"])
                value = self._from_text(s, found) if found is not None else None
            elif "json" in t:
                value = self._from_text(s, gm.json_read(self._path(t["json"])).get(t["key"]))
            else:
                value = (stored if stored is not None else self._stored()).get(s["id"])
        except (OSError, ValueError, RuntimeError):
            value = None
        return value if value is not None and self._allowed(s, value) else self._default(s)

    def settings(self):
        out = []
        for s in self.m.get("settings") or ():
            if ("ini" in s["target"] or "json" in s["target"]) and not self.found():
                continue
            options = ([(False, "@off"), (True, "@on")] if s["type"] == "toggle"
                       else [(o["value"], self.text(o["label"])) for o in s["options"]])
            out.append(dict(id=s["id"], label=self.text(s["label"]), hint="", lead="", options=options,
                            value=self._value(s)))
        return out

    def set_setting(self, sid, value):
        s = next((x for x in self.m.get("settings") or () if x["id"] == sid), None)
        if s is None or not self._allowed(s, value):
            raise RuntimeError("@generic.settings_error")
        t = s["target"]
        if "ini" in t or "json" in t:
            if self.running():
                raise RuntimeError("@generic.running")
            try:
                if "ini" in t:
                    gm.ini_write(self._path(t["ini"]), t["section"], t["key"], gm.setting_text(value))
                else:
                    gm.json_write(self._path(t["json"]), t["key"], value)
            except (OSError, ValueError, RuntimeError) as e:
                raise RuntimeError("@generic.settings_error") from e
            return
        self.config.setdefault("manifest_settings", {}).setdefault(self.m["id"], {})[sid] = value
        try:
            save_config(self.config)
        except (OSError, ValueError):
            pass

    # ---------------------------------------------------------------- online
    def online_items(self):
        online = self.m.get("online") or {}
        if online.get("mode") != "external":
            return []
        lead = self.text(online["note"]) if online.get("note") else "@manifest.online_external_hint"
        return [dict(kind="action", id="own", label="@manifest.online_external", verb="@start", hint=lead,
                     disabled=not self.ready(),
                     detail=dict(kicker="@section.online", title="@manifest.online_external", lead=lead, rows=[]))]

    def run_online(self, item_id):
        if item_id == "own" and (self.m.get("online") or {}).get("mode") == "external":
            self._playtime_online_launch = True
            try:
                self.start()
            finally:
                self._playtime_online_launch = False
        return ""

    # ---------------------------------------------------------------- update check
    def update_offer(self):
        """The newer release found by the last check (dict(version, tag, signed, ...)), else None."""
        from .. import game_releases as gr
        offer = (self.update or {}).get("offer")
        current = self.installed_version()
        if not offer or not current or not gr.is_newer(offer.get("version"), current):
            return None
        return offer

    def check_updates(self, wait=False):
        """Ask GitHub once (cached for an hour); on a thread unless wait. False = nothing to ask now."""
        if not self.m.get("updates") or not self.root or gm.cached_update(self.m):
            return False

        def work():
            self.update = gm.check_release(self.m, opener=self.fetch)
            gm.store_update(self.m, self.update)
        if wait:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()
        return True
