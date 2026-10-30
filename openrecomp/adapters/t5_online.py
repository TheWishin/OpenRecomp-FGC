"""Login and queue calls through the installed lobby client, without a match driver."""
import csv
import importlib
import io
import json
import os
import queue
import subprocess
import threading
import time
import uuid

from .base import NO_WINDOW, add_path


class SearchRefused(RuntimeError):
    """A local check stopped the request before any queue call was sent."""


def close_client(client):
    try:
        client.close()
    except Exception:  # noqa: BLE001 -- an incompatible client must still leave our UI disconnected
        pass


def game_process_running():
    """Conservatively include every T5DR process, whoever started it. None means unknown."""
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq t5dr.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=5, check=False)
        if result.returncode:
            return None
        return any(row and row[0].casefold() == "t5dr.exe"
                   for row in csv.reader(io.StringIO(result.stdout)))
    except (OSError, subprocess.TimeoutExpired, csv.Error):
        return None


class Online:
    def online_supported(self):
        return True

    def _online_init(self):
        if hasattr(self, "_online_phase"):
            return
        cfg = self._online_config()
        self._online_fields = dict(online_name=str(cfg.get("name") or self.s.get("nickname") or ""),
                                   online_password="", online_server=str(cfg.get("server") or ""))
        self._online_phase = "offline"
        self._online_message = "@online.offline"
        self._online_name = ""
        self._online_account = False
        self._online_queue = ""
        self._online_match = {}
        self._online_client = None
        self._online_busy = False
        self._online_generation = 0
        self._online_results = queue.Queue()
        self._online_cancel_pending = False
        self._online_guard_at = 0.0
        self._online_lock = threading.RLock()

    def _online_config(self):
        old = os.path.join(os.path.dirname(getattr(self.s, "path", "") or self.root), "online.json")
        for path in (self.online_cfg_path(), old):
            try:
                with open(path, encoding="utf-8") as stream:
                    cfg = json.load(stream)
                if isinstance(cfg, dict):
                    return cfg
            except (OSError, ValueError):
                continue
        return {}

    def _online_modules(self):
        if not hasattr(self, "_online_api"):
            add_path(os.path.join(self.root, "lobby"))
            client = importlib.import_module("t5lobby.client")
            buildid = importlib.import_module("t5lobby.buildid")
            servers = importlib.import_module("t5lobby.servers")
            proto = importlib.import_module("t5lobby.proto")
            if proto.PROTO_VERSION != 1:
                raise RuntimeError("@online.client_missing")
            self._online_api = dict(client=client.LobbyClient, build=buildid.BuildInfo, servers=servers)
        return self._online_api

    def _online_saved(self):
        key = self._online_fields["online_server"].strip().lower() or "127.0.0.1:7781"
        sessions = self._online_config().get("sessions") or {}
        saved = sessions.get(key) if isinstance(sessions, dict) else None
        return saved if isinstance(saved, dict) and isinstance(saved.get("token"), str) and saved["token"] else None

    def online_state(self):
        self._online_init()
        return dict(phase=self._online_phase, message=self._online_message,
                    name=self._online_name, account=self._online_account,
                    queue=self._online_queue, match=dict(self._online_match),
                    saved_available=bool(self._online_saved()))

    def online_text_value(self, tid):
        self._online_init()
        return self._online_fields.get(tid, "")

    def set_online_text_value(self, tid, value):
        self._online_init()
        if tid in self._online_fields and not self._online_busy and self._online_client is None:
            self._online_fields[tid] = str(value)

    def _online_submit(self, operation, work):
        generation = self._online_generation
        self._online_busy = True

        def run():
            try:
                value, error = work(), None
            except Exception as exc:  # noqa: BLE001 -- a runtime client may be absent or refuse a request
                value, error = None, exc
            self._online_results.put((generation, operation, value, error))
        threading.Thread(target=run, name="openrecomp-lobby", daemon=True).start()

    def _online_error(self, error, saved=False):
        code = getattr(error, "code", "")
        if saved and code == "auth_failed":
            return "@online.saved_expired"
        keys = dict(auth_failed="@online.auth_failed", insecure="@online.insecure", bad_name="@online.bad_name",
                    name_taken="@online.name_taken", timeout="@online.unavailable", rate_limited="@online.rate_limited",
                    version_mismatch="@online.version_mismatch", proto_mismatch="@online.version_mismatch",
                    server_full="@online.server_full", busy="@online.busy_server")
        local = ("@online.client_missing", "@online.build_required", "@online.no_online",
                 "@online.server_invalid", "@online.game_running", "@online.process_unknown", "@online.cancelled")
        if isinstance(error, RuntimeError) and str(error) in local:
            return str(error)
        if isinstance(error, (ImportError, AttributeError, TypeError)):
            return "@online.client_missing"
        if isinstance(error, (OSError, ConnectionError)):
            return "@online.unavailable"
        return keys.get(code, "@online.refused")

    def _online_write_session(self, server, name, token, expected=None):
        """Merge a fresh file; no password is ever stored, and unrelated native settings survive."""
        cfg = self._online_config()
        sessions = cfg.get("sessions")
        if not isinstance(sessions, dict):
            sessions = {}
        key = server.strip().lower()
        if token:
            sessions[key] = dict(name=name, token=token, saved=time.time())
            cfg.update(sessions=sessions, server=server, name=name)
        else:
            previous = sessions.get(key)
            if not isinstance(previous, dict) or previous.get("token") != expected:
                return
            sessions.pop(key)
            cfg["sessions"] = sessions
        path = self.online_cfg_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + "." + uuid.uuid4().hex + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(cfg, stream, indent=1)
            os.replace(temporary, path)
        finally:
            if os.path.isfile(temporary):
                os.remove(temporary)

    def _online_login(self, action):
        name = self._online_fields["online_name"].strip()
        password = self._online_fields["online_password"]
        self._online_fields["online_password"] = ""
        saved = self._online_saved() if action == "login_saved" else None
        if action == "login_saved" and saved is None:
            self._online_message = "@online.saved_missing"
            return
        if action == "login_account" and not password:
            self._online_message = "@online.password_required"
            return
        server = self._online_fields["online_server"].strip()
        cfg = self._online_config()
        generation = self._online_generation
        self._online_phase, self._online_message = "connecting", "@online.connecting"
        self._online_match = {}

        def work():
            client = None
            try:
                api = self._online_modules()
                if not self.ready():
                    raise RuntimeError("@online.build_required")
                if not api["build"].has_online(self.s.out_dir):
                    raise RuntimeError("@online.no_online")
                try:
                    build = api["build"].from_out_dir(self.s.out_dir, self.release().get("version") or "dev")
                except (OSError, ValueError):
                    raise RuntimeError("@online.build_required") from None
                entries, _problems = api["servers"].load(user_dir=os.path.dirname(self.online_cfg_path()))
                default = api["servers"].default_entry(entries)
                target = server or (default.name if default else "127.0.0.1:7781")
                try:
                    entry = api["servers"].resolve(target, entries)
                    kwargs = entry.client_kwargs()
                except (ValueError, TypeError):
                    raise RuntimeError("@online.server_invalid") from None
                if entry.tls != "pin" and cfg.get("fingerprint"):
                    kwargs["tls_fingerprint"] = cfg["fingerprint"]
                client = api["client"](build=build, auto_ready=False, reconnect=0,
                                       blind_ready=True, port_mapping=False, **kwargs)
                with self._online_lock:
                    if generation != self._online_generation:
                        raise RuntimeError("@online.cancelled")
                    self._online_client = client
                client.connect()
                if generation != self._online_generation:
                    raise RuntimeError("@online.cancelled")
                if action == "login_guest":
                    me = client.login_guest(name)
                elif action == "login_saved":
                    me = client.login_session(saved["token"])
                else:
                    me = client.login(name, password, remember=True)
                warning = ""
                with self._online_lock:
                    if generation != self._online_generation:
                        raise RuntimeError("@online.cancelled")
                    if action == "login_account" and client.session:
                        try:
                            self._online_write_session(target, me["name"], client.session)
                        except OSError:
                            warning = "@online.save_failed"
                return dict(me=me, server=target, warning=warning)
            except Exception as error:
                if client:
                    close_client(client)
                if action == "login_saved" and getattr(error, "code", "") == "auth_failed":
                    with self._online_lock:
                        if generation == self._online_generation:
                            try:
                                self._online_write_session(server or "127.0.0.1:7781", None, None,
                                                           expected=saved["token"])
                            except OSError:
                                pass
                raise
        self._online_submit(action, work)

    def _online_game_check(self):
        if self.running():
            return "@online.game_running"
        running = game_process_running()
        if running is None:
            return "@online.process_unknown"
        return "@online.game_running" if running else ""

    def online_action(self, action):
        self._online_init()
        if action == "logout":
            self.online_close()
            self._online_message = "@online.logged_out"
            return
        if self._online_busy:
            if action == "cancel":
                if self._online_phase == "connecting":
                    self.online_close()
                    self._online_message = "@online.cancelled"
                else:
                    self._online_cancel_pending = True
                    self._online_message = "@online.cancelling"
            return
        if action in ("login_guest", "login_account", "login_saved"):
            if self._online_client is None:
                self._online_login(action)
            return
        client = self._online_client
        if client is None or self._online_phase in ("offline", "kicked", "error", "matched"):
            self._online_message = "@online.login_required"
            return
        if action in ("search_casual", "search_ranked"):
            if self._online_phase != "logged_in":
                return
            if action == "search_ranked" and not self._online_account:
                self._online_message = "@online.account_required"
                return
            mode = "ranked" if action == "search_ranked" else "casual"
            char = self.chosen_fighter()
            self._online_phase, self._online_queue = "searching", mode
            self._online_message = "@online.searching_ranked" if mode == "ranked" else "@online.searching_casual"

            def work():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                if mode == "ranked":
                    client.ranked_match(char)
                else:
                    client.quick_match(char)
                return mode
            self._online_submit(action, work)
        elif action == "cancel" and self._online_phase == "searching":
            self._online_message = "@online.cancelling"
            self._online_submit(action, client.cancel_queue)

    def _online_events(self):
        """Read one queue snapshot. A kick wins over a simultaneous request failure or disconnect."""
        client = self._online_client
        if client is None:
            return False, False
        events = []
        for _ in range(client.events.qsize()):
            try:
                events.append(client.events.get_nowait())
            except queue.Empty:
                break
        for kind in ("kicked", "match_found", "disconnected"):
            event = next((event for event in events if event.get("t") == kind), None)
            if event is None:
                continue
            name, account = self._online_name, self._online_account
            self.online_close()
            if kind == "kicked":
                reason = str(event.get("reason") or "").lower()
                self._online_phase = "kicked"
                self._online_message = ("@online.kicked" if "logged in from another place" in reason
                                        else "@online.removed")
            elif kind == "match_found":
                opponent = event.get("opponent") or {}
                ping = event.get("ping") or {}
                # Closing also prevents the server requeueing this client after a ready timeout.
                self._online_phase = "matched"
                self._online_match = dict(opponent=str(opponent.get("name") or ""), ping=ping.get("ms"))
                self._online_name, self._online_account = name, account
                self._online_message = "@online.matched"
            else:
                self._online_message = "@online.disconnected"
            return True, True
        changed = False
        for event in events:
            if event.get("t") == "error":
                self._online_message = self._online_error(type("RequestError", (Exception,), {
                    "code": event.get("code", "")})())
                changed = True
        return changed, False

    def online_poll(self):
        self._online_init()
        changed, terminal = self._online_events()
        if terminal:
            return True
        while True:
            try:
                generation, action, value, error = self._online_results.get_nowait()
            except queue.Empty:
                break
            if generation != self._online_generation:
                continue
            changed = True
            self._online_busy = False
            if error:
                # The client can receive a terminal event while a blocking request is finishing.
                event_changed, terminal = self._online_events()
                changed = changed or event_changed
                if terminal:
                    return True
                self._online_message = self._online_error(error, action == "login_saved")
                if action.startswith("login_"):
                    self._online_client = None
                    self._online_phase = "error"
                elif action.startswith("search_"):
                    if isinstance(error, SearchRefused):
                        self._online_phase, self._online_queue = "logged_in", ""
                    else:
                        # A lost acknowledgement can mean the server queued us. Disconnect to stop it.
                        message = self._online_message
                        self.online_close()
                        self._online_message = message
                elif action in ("cancel", "guard"):
                    message = self._online_message
                    self.online_close()
                    self._online_message = message
            elif action.startswith("login_"):
                me = value["me"]
                self._online_name = str(me.get("name") or "")
                self._online_account = not bool(me.get("guest", True))
                self._online_fields["online_name"] = self._online_name
                self._online_fields["online_server"] = value["server"]
                self._online_phase = "logged_in"
                self._online_message = value["warning"] or "@online.logged_in"
            elif action.startswith("search_"):
                self._online_phase, self._online_queue = "searching", value
                self._online_message = "@online.searching_ranked" if value == "ranked" else "@online.searching_casual"
                self._online_guard_at = time.monotonic() + 1
            elif action == "cancel":
                self._online_phase, self._online_queue = "logged_in", ""
                self._online_message = "@online.cancelled"
            elif action == "guard" and value:
                message = value
                self.online_close()
                self._online_message = message
        event_changed, terminal = self._online_events()
        changed = changed or event_changed
        if terminal:
            return True
        if self._online_cancel_pending and not self._online_busy:
            self._online_cancel_pending = False
            self.online_action("cancel")
            changed = True
        if (self._online_phase == "searching" and not self._online_busy
                and time.monotonic() >= self._online_guard_at):
            self._online_guard_at = time.monotonic() + 1
            self._online_submit("guard", self._online_game_check)
        return changed

    def online_close(self):
        self._online_init()
        with self._online_lock:
            self._online_generation += 1
            client, self._online_client = self._online_client, None
        self._online_busy = False
        self._online_cancel_pending = False
        self._online_phase, self._online_queue = "offline", ""
        self._online_account = False
        self._online_name = ""
        self._online_match = {}
        self._online_fields["online_password"] = ""
        if client:
            threading.Thread(target=close_client, args=(client,), name="openrecomp-lobby-close", daemon=True).start()
