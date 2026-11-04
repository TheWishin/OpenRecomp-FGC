"""What a game must offer the launcher. The screens only ever talk to this interface."""
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile
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

    @staticmethod
    def message(key, **values):
        """The deferred catalog message understood by the view; no language in adapters."""
        return dict(_text=key, _values=values)

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
        return dict(status="@not_found", version="@none_lower", players="@no", last="@never",
                    detail=self.message("game_not_found", name=self.m["short"]))

    def coexistence_state(self):
        """An existing install reused in place: active, source folder and build compatibility."""
        return dict(active=False, source="", build="unknown")

    def hero(self):
        return ""

    def recent_results(self):
        return []

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        raise RuntimeError("@not_ready")

    def running(self):
        return False

    def stop(self):
        pass

    def open_native(self):
        raise RuntimeError("@no_native")

    def playtime(self):
        """Local totals only; never included in the game's online client state."""
        store = getattr(self, "playtime_store", None)
        if store is None:
            return dict(offline_seconds=0.0, online_seconds=0.0, last_played="", sessions=0)
        return store.snapshot(self.m["id"])

    def _track_playtime(self, running, process=None, extra_env=None):
        store = getattr(self, "playtime_store", None)
        if store is not None:
            from ..playtime import online_environment
            try:
                store.watch(self.m["id"], running, process=process,
                            online=bool(getattr(self, "_playtime_online_launch", False)) or online_environment(extra_env))
            except (OSError, RuntimeError):
                pass

    def _track_native_playtime(self, process, images):
        store = getattr(self, "playtime_store", None)
        if store is not None:
            try:
                store.watch_native(self.m["id"], process, images)
            except (OSError, RuntimeError):
                pass

    # ---------------------------------------------------------------- settings: dict(id, label, hint, lead, options, value)
    def settings(self):
        return []

    def set_setting(self, sid, value):
        pass

    def quick_settings(self):
        """Ids of the settings shown under "Start game"."""
        return []

    # ---------------------------------------------------------------- controls: optional per-pad bindings
    def controls_supported(self):
        return False

    def controls(self):
        """[dict(id, label, port, slots=[dict(id, label, value)])]."""
        return []

    def begin_binding(self, pad_id, slot_id):
        raise RuntimeError("@controls.unsupported")

    def poll_binding(self, active=True):
        """dict(state, source, conflicts): capture progress without blocking."""
        return dict(state="")

    def accept_binding(self):
        pass

    def cancel_binding(self):
        pass

    def controls_close(self):
        pass

    # ---------------------------------------------------------------- support: optional native check and local report
    def support_available(self):
        return False

    def support_start(self, kind):
        raise RuntimeError("@support.unavailable")

    def support_state(self):
        """dict(running, operation, checked, findings, report, error); no network sending."""
        return dict(running=False, operation="", checked=False, findings=[], report="", error="")

    # ---------------------------------------------------------------- online: rows for the online section
    def online_supported(self):
        return False

    def online_state(self):
        """Read-only online snapshot; reading it never starts a request.

        Direct-IP clients expose capabilities.direct_ip, role, busy and checks.
        Each check has id, label, value and ok; address editing uses text_value
        and set_text_value with online_address, never the public snapshot.

        Playable clients add capabilities, players, rooms, chat, challenge, room and a text rank.
        Optional social capabilities add friends, friend_incoming, friend_outgoing,
        invites and outgoing_invite. Rematch is offered only while its capability is true.
        Player main keys describe each player's most-played fighter (games, wins,
        then latest play); missing usage gives an empty key and silhouette. Only the
        local player may fall back to local match history. Match you_char/opp_char
        are explicit known picks, separate from each player's main.
        Installed T5DR clients can add capability-gated tournaments, profile, leaderboard,
        community_stats, spectating, community and challenge_preferences snapshots.
        Outgoing offers may include server supplied remaining seconds. challenge_updates
        contains only opaque offer ids and accepted/declined/expired/cancelled outcomes.
        Ranked sets expose set and character_locked; optional account tools expose blocks.
        Negotiated chat tools add moderation (mute rows and server notices) and private_chat
        (session threads, unread counts and explicitly selected report lines). Private-message
        receipts stay inside the adapter; only display text and opaque line ids reach screens.
        These are plain, allowlisted views of the selected install's client, never clients
        or game handles. Reading them does not authorize a request or a game launch.
        A room's invitation code is shown only to its member; room passwords stay private.
        Tickets, addresses, passwords and session tokens never belong in this snapshot.
        Registration may expose one-time recovery codes until the player acknowledges them.
        """
        return dict(phase="offline", message="", name="", account=False, queue="", match={}, saved_available=False)

    def online_action(self, action):
        """Request a controller-selectable action.

        Direct-IP actions are host, join, check, start_match, cancel_match,
        stop_match, collect_logs and disconnect. Checks never launch a game.
        """
        pass

    def online_poll(self):
        """Advance an explicitly requested login/search; never called by a dry Nav."""
        return False

    def online_close(self):
        pass

    def online_shown(self):
        """The Online section is on screen (called each time its rows are built). An adapter may log in with a
        remembered session once per launcher run; it must never use a password or start a search."""

    def online_account_sessions(self):
        """Remembered account logins a sister game may offer ({host, name, token, saved}); none by default."""
        return []

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

    def fighter_image(self, key):
        """A fighter's face picture (a file of the player's own build) for the online tables; "" = none."""
        return ""

    def fighter_label(self, key):
        """A fighter's name from the lobby's fighter key; the key itself when unknown."""
        return next((f["name"] for f in self.fighters() if f.get("key") == key), key or "")

    def rank_progress(self, rating):
        """(start of this rank, start of the next, next rank's name) for the ranked card's bar; None = no bar."""
        return None

    def rank_plate(self, tier):
        """The game's own rank plate picture for a lobby rank tier (from the player's build); "" = text only."""
        return ""

    # ---------------------------------------------------------------- replays
    def replays(self):
        """[dict(id, label, when, group, opponent, netcode, result, images)]"""
        return []

    def play_replay(self, replay_id, extra_env=None):
        raise RuntimeError("@no_replays_error")

    # ---------------------------------------------------------------- build
    def prerequisites(self):
        """Cached PC checks: [dict(id, label, value, ok, command, busy=False)]."""
        return []

    def refresh_prerequisites(self):
        """Explicitly recheck tools; never install them or run a build."""
        pass

    def prerequisite_install_state(self):
        """dict(running, done, total, current, result) of install_prerequisites()."""
        return dict(running=False, done=0, total=0, current="", result="")

    def install_prerequisites(self):
        """Install the missing tools after the player confirmed the list; False = nothing started."""
        return False

    def sources(self):
        """[dict(id, label, value, ok, hint, exts, dirs)]: the player's files the build needs."""
        return []

    def set_source(self, sid, path):
        return ""

    def source_state(self):
        """Optional background source check/import; result may be 'reload' after registration."""
        return dict(running=False, result="", id="", ok=False)

    def build_options(self):
        return []

    def build_ready(self):
        return "@no_build_here"

    def build_prepares(self):
        """build_ready() answers that build_start() solves by itself first (T4: missing tools it installs)."""
        return ()

    def build_resume_pending(self):
        """A build stopped for a Windows restart and should continue now (the launcher asks once per start)."""
        return False

    def build_resume(self):
        pass

    def build_start(self, force=False):
        raise RuntimeError("@no_build")

    def build_state(self):
        """dict(running, fraction, title, steps=[dict(k, v)], result, line); optional: lines (the last output lines),
        step_no ([n, total]), phase ("tools" / "build"), tools (dict(done, total)), failed ("tools" / "build")."""
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

    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self._source_state = dict(running=False, result="", id="", ok=False)

    def sources(self):
        t4 = self.m.get("adapter") == "t4"
        if t4:
            return [dict(id="folder", label="@t4.game_folder", title="@t4.choose_game_folder", value="@missing", ok=False,
                         kind="file_or_folder", exts=[".zip"], dirs=[], hint="@folder_hint",
                         note=self._source_state["result"] if self._source_state["result"] != "reload" else "")]
        return [dict(id="folder", label="@game_folder", value="@missing", ok=False, kind="folder", exts=[], dirs=[],
                     hint="@folder_hint", note="")]

    def set_source(self, sid, path):
        if self.m.get("adapter") == "t4":
            from .t4_install import install_source
            if self._source_state["running"]:
                return "@t4.installing"
            self._source_state = dict(running=True, result="", id=sid, ok=False)

            def install():
                try:
                    result = install_source(self.m, self.config, path)
                except Exception:  # noqa: BLE001 -- leave a controller-readable recovery path
                    result = "@t4.install_failed"
                self._source_state = dict(running=False, result=result, id=sid, ok=result == "reload")

            try:
                self._source_thread = threading.Thread(target=install, daemon=True)
                self._source_thread.start()
            except Exception:  # noqa: BLE001 -- a missing worker must not leave the launcher permanently busy
                self._source_state = dict(running=False, result="@t4.install_failed", id=sid, ok=False)
                return "@t4.install_failed"
            return "@t4.installing"
        if self.m.get("adapter") == "t5dr":
            from .t5dr import find_root
            root = find_root(self.m, {"roots": {self.m["id"]: path}})
            if not root:
                return "@t5.coexist.install_invalid"
            previous = (self.config.get("roots") or {}).get(self.m["id"])
            if not previous or os.path.normcase(os.path.realpath(previous)) != os.path.normcase(os.path.realpath(root)):
                self.config.pop("t5dr_settings_copy", None)
            path = root
        self.config.setdefault("roots", {})[self.m["id"]] = path
        return "reload"

    def source_state(self):
        return dict(self._source_state)


class Generic(Adapter):
    """A declarative game: read data, and run only its executable on an explicit action."""

    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self.proc = None
        self._source_state = dict(running=False, result="", id="", ok=False)

    @property
    def root(self):
        roots = self.config.get("roots")
        root = roots.get(self.m["id"], "") if isinstance(roots, dict) else ""
        return root if isinstance(root, str) else ""

    def _path(self, relative):
        from ..manifest import ManifestError, resolve_path
        if not self.root:
            raise RuntimeError("@generic.root_missing")
        try:
            return resolve_path(self.root, relative)
        except ManifestError as e:
            raise RuntimeError("@generic.root_missing") from e

    def exe(self):
        if self.m.get("schema_version") == 1:
            if not self.m["exe"].lower().endswith(".exe"):
                raise RuntimeError("@not_ready")
            return self._path(self.m["exe"])
        return os.path.expandvars(self.m["exe"])

    def found(self):
        if self.m.get("schema_version") == 1:
            return bool(self.root) and os.path.isdir(self.root)
        return os.path.isfile(self.exe())

    def ready(self):
        try:
            return os.path.isfile(self.exe())
        except (ValueError, RuntimeError):
            return False

    def status(self):
        from .. import i18n
        if self.ready():
            installed = (self.config.get("game_versions") or {}).get(self.m["id"], self.m.get("version"))
            version = i18n.literal(installed) if self.m.get("schema_version") == 1 and installed else str(self.m.get("version", "@unknown"))
            return dict(status="@ready", version=version, players="@no",
                        last="@unknown", detail="@generic_hint")
        return dict(status="@not_found", version="@none_lower", players="@no", last="@never",
                    detail="@generic.root_missing" if not self.found() else "@generic.build_manual")

    def start(self, extra_env=None):
        if self.running():
            raise RuntimeError("@generic.running")
        if not self.ready():
            raise RuntimeError("@not_ready")
        env = dict(os.environ)
        if self.m.get("schema_version") != 1:
            env.update({str(k): str(v) for k, v in (self.m.get("env") or {}).items()})
        env.update(extra_env or {})
        if self.m.get("schema_version") == 1:
            cwd = self._path(self.m["cwd"]) if self.m.get("cwd") else self.root
        else:
            cwd = os.path.expandvars(self.m.get("cwd") or os.path.dirname(self.exe()))
        self.proc = subprocess.Popen([self.exe()] + [str(a) for a in self.m.get("args") or []], cwd=cwd, env=env,
                                     shell=False)
        proc = self.proc
        self._track_playtime(lambda: proc.poll() is None, process=proc, extra_env=extra_env)
        return self.proc.pid

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.running():
            self.proc.terminate()

    def hero(self):
        try:
            path = self._path(self.m["logo"]) if self.m.get("logo") else ""
            if (path and path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                    and os.path.isfile(path) and os.path.getsize(path) <= 8 * 1024 * 1024):
                return path
            return ""
        except (OSError, ValueError, RuntimeError):
            return ""

    def settings(self):
        from .. import i18n
        declared = self.m.get("settings") or {}
        if not declared or not self.found():
            return []
        try:
            values = self._read_settings()
        except RuntimeError:
            self.problem = "@generic.settings_error"
            return []
        return [dict(id=c["id"], label=i18n.literal(c["label"]), hint="@generic.controls_hint" if c["id"] == "controls" else "",
                     lead="", options=[(o["value"], i18n.literal(o["label"])) for o in c["options"]],
                     value=values.get(c["key"], c["options"][0]["value"])) for c in declared["cyclers"]]

    def _read_settings(self):
        try:
            path = self._path(self.m["settings"]["file"])
            with open(path, "rb") as stream:
                data = stream.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise ValueError
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, RuntimeError) as e:
            raise RuntimeError("@generic.settings_error") from e

    def set_setting(self, sid, value):
        if self.running():
            raise RuntimeError("@generic.running")
        declared = self.m.get("settings") or {}
        cycler = next((c for c in declared.get("cyclers", []) if c["id"] == sid), None)
        if not cycler or not any(type(o["value"]) is type(value) and o["value"] == value for o in cycler["options"]):
            raise RuntimeError("@generic.settings_error")
        values = self._read_settings()
        values[cycler["key"]] = value
        temporary = None
        try:
            path = self._path(declared["file"])
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=os.path.dirname(path),
                                             suffix=".json", delete=False) as stream:
                temporary = stream.name
                json.dump(values, stream, ensure_ascii=False, indent=1, allow_nan=False)
            # Recheck containment immediately before replacing an existing file.
            os.replace(temporary, self._path(declared["file"]))
        except (OSError, ValueError, RuntimeError) as e:
            raise RuntimeError("@generic.settings_error") from e
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def sources(self):
        from .. import i18n
        out = [dict(id="folder", label="@game_folder", value=i18n.literal(self.root) if self.root else "@missing",
                    ok=self.found(), kind="folder", exts=[], dirs=[self.root] if self.root else [], hint="@folder_hint")]
        sources = self.config.get("generic_sources")
        supplied = sources.get(self.m["id"], {}) if isinstance(sources, dict) else {}
        if not isinstance(supplied, dict):
            supplied = {}
        for requirement in self.m.get("requirements") or []:
            checked = supplied.get(requirement["id"], {})
            if not isinstance(checked, dict):
                checked = {}
            out.append(dict(id=requirement["id"], label=i18n.literal(requirement["label"]),
                            value=i18n.literal(checked["path"]) if checked.get("path") else "@missing",
                            ok=checked.get("sha256") == requirement["sha256"].lower(), exts=[".iso"] if requirement["kind"] == "iso" else [],
                            dirs=[], kind="file", hint=self.message("generic.requirement_hint", version=i18n.literal(requirement["version"]),
                                                                   sha256=i18n.literal(requirement["sha256"]))))
        return out

    def set_source(self, sid, path):
        if self.running() or self._source_state["running"]:
            raise RuntimeError("@generic.running")
        if sid == "folder":
            if not os.path.isdir(path):
                raise RuntimeError("@generic.root_missing")
            self.config.setdefault("roots", {})[self.m["id"]] = os.path.realpath(path)
            return "reload"
        requirement = next((r for r in self.m.get("requirements", []) if r["id"] == sid), None)
        if not requirement or not os.path.isfile(path):
            raise RuntimeError("@generic.requirement_bad_hash")
        self.config.setdefault("generic_sources", {}).setdefault(self.m["id"], {}).pop(sid, None)
        self._source_state = dict(running=True, result="", id=sid, ok=False)

        def check():
            try:
                digest = hashlib.sha256()
                with open(path, "rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                ok = digest.hexdigest() == requirement["sha256"].lower()
                if ok:
                    self.config.setdefault("generic_sources", {}).setdefault(self.m["id"], {})[sid] = dict(path=path, sha256=digest.hexdigest())
                self._source_state = dict(running=False, result="reload" if ok else "@generic.requirement_bad_hash", id=sid, ok=ok)
            except OSError:
                self._source_state = dict(running=False, result="@generic.requirement_bad_hash", id=sid, ok=False)

        try:
            self._source_thread = threading.Thread(target=check, daemon=True)
            self._source_thread.start()
        except RuntimeError:
            self._source_state = dict(running=False, result="@generic.requirement_bad_hash", id=sid, ok=False)
        return "@generic.source_checking"

    def source_state(self):
        return dict(self._source_state)

    def build_ready(self):
        from .. import i18n
        return i18n.literal(self.m["build"]["instructions"]) if self.m.get("build") else "@no_build_here"

    def online_items(self):
        mode = (self.m.get("online") or {}).get("mode", "none")
        if mode == "own":
            return [dict(kind="action", id="own", label="@generic.own_online", verb="@start", hint="@generic.own_online_hint",
                         detail=dict(kicker="@section.online", title="@generic.own_online", lead="@generic.own_online_hint", rows=[]))]
        if mode == "lobby":
            return [dict(kind="action", id="none", label="@generic.lobby_arrangement", disabled=True,
                         hint="@generic.lobby_arrangement", detail=dict(kicker="@section.online", title="@generic.lobby_arrangement", lead="@generic.lobby_arrangement", rows=[]))]
        return []

    def run_online(self, item_id):
        if item_id == "own" and (self.m.get("online") or {}).get("mode") == "own":
            self._playtime_online_launch = True
            try:
                self.start()
            finally:
                self._playtime_online_launch = False
        return ""


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
