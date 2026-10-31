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
        Installed T5DR clients can add capability-gated tournaments, profile, leaderboard,
        community_stats, spectating, community and challenge_preferences snapshots.
        Ranked sets expose set and character_locked; optional account tools expose blocks.
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
        raise RuntimeError("@no_replays_error")

    # ---------------------------------------------------------------- build
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

    def build_start(self, force=False):
        raise RuntimeError("@no_build")

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

    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self._source_state = dict(running=False, result="", id="", ok=False)

    def sources(self):
        t4 = self.m.get("adapter") == "t4"
        return [dict(id="folder", label="@game_folder", value="@missing", ok=False,
                     kind="file_or_folder" if t4 else "folder", exts=[".zip"] if t4 else [], dirs=[],
                     hint="@folder_hint", note=self._source_state["result"] if t4 and self._source_state["result"] != "reload" else "")]

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
            return dict(status="@ready", version=str(self.m.get("version", "@unknown")), players="@no",
                        last="@unknown", detail="@generic_hint")
        return dict(status="@not_found", version="@none_lower", players="@no", last="@never",
                    detail=self.message("file_missing", path=self.exe()))

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
