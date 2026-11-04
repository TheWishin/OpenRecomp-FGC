"""Shared login, search and lobby calls through each game's installed lobby client."""
import csv
import importlib
from importlib.machinery import PathFinder
import io
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
import uuid

from .base import NO_WINDOW, add_path
from .t5_coexist import readonly_imports
from . import other_launchers, t5_features, t5_netext
from .. import i18n


SERVERS_FORMAT = "t5dr-servers/1"


class SearchRefused(RuntimeError):
    """A local check stopped the request before any queue call was sent."""


def close_client(client):
    try:
        client.close()
    except Exception:  # noqa: BLE001 -- an incompatible client must still leave our UI disconnected
        pass


def game_process_running(image="t5dr.exe"):
    """Conservatively include matching game processes, whoever started them. None means unknown."""
    if os.name != "nt":
        return None
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq " + image, "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=5, check=False)
        if result.returncode:
            return None
        return any(row and row[0].casefold() == image.casefold()
                   for row in csv.reader(io.StringIO(result.stdout)))
    except (OSError, subprocess.TimeoutExpired, csv.Error):
        return None



def entry_tls(entry):
    """A servers.json entry's TLS mode as the lobby client's resolver reads it (ServerEntry.from_json): "pin" with a
    fingerprint, else what "tls" says, else "off" -- never "ca" for an entry that names no TLS."""
    fingerprint = str(entry.get("fingerprint") or "").replace(":", "").replace(" ", "").strip()
    return str(entry.get("tls") or ("pin" if fingerprint else "off"))

class Online:
    online_package = "t5lobby"
    online_game = ""
    online_port = 7781
    online_ranked = True
    online_lobby = False
    online_match_flow = False
    online_legacy_config = True
    online_registration = None  # None: only the T5DR client registers accounts
    online_server_env = "OPENRECOMP_T5_SERVER"
    online_server_setting = "t5_lobby_server"
    # The game whose own launcher (and other OpenRecomp windows) this adapter looks for (other_launchers); "" = none.
    other_launcher_game = ""
    other_launcher_detector = None              # None: the app's detector (other_launchers.DETECTOR)

    def online_supported(self):
        return True

    # ---------------------------------------------------------------- another launcher of this game on this PC
    # Owner: "it should say: hey, you are logged in, but you can really only play in one launcher." The lobby lets one
    # connection per account (the newer login wins). So: while another launcher is open, OpenRecomp never logs in by
    # itself (no automatic login, no relogin after a drop) until the player chose "Use OpenRecomp here"; "Keep the
    # other one" logs out here and stays out. A kick says which launcher took the login. Never a logout ping-pong.
    def _other_kind(self):
        detector = self.other_launcher_detector or other_launchers.DETECTOR
        found = other_launchers.kind(self.other_launcher_game, detector)
        if not found:
            self._other_choice = None           # it closed: the next one asks again
        return found

    def _other_native_logs_in(self):
        # T5DR's own launcher logs in to the same lobby; Tekken 4's Easy Launcher plays by direct IP only (still one
        # launcher at a time: a game started there takes this one out of its search).
        return self.other_launcher_game == "t5dr"

    def _other_state(self):
        found = self._other_kind()
        if not found:
            return None
        return dict(kind=found, game=self.other_launcher_game, choice=getattr(self, "_other_choice", None),
                    logs_in=found != "native" or self._other_native_logs_in())

    def _other_holds_back(self):
        """Another launcher is open and the player has not chosen OpenRecomp: no login by itself here."""
        return bool(self._other_kind()) and getattr(self, "_other_choice", None) != "here"

    def _other_action(self, action):
        """other_here / other_keep from the note. -> True when handled."""
        if action not in ("other_here", "other_keep"):
            return False
        self._online_init()
        if action == "other_here":
            self._other_choice = "here"
            if self._online_phase in ("offline", "error", "kicked") and self._online_client is None:
                # The player's own choice: the next redraw's online_shown logs in with this launcher's remembered
                # login (Remember me on), as at the start; else the login rows are there.
                self._online_auto_tried = False
                self._online_message = "@other_launcher.chosen_here"
            return True
        self._other_choice = "other"
        self._online_auto_tried = True
        if self._online_phase in ("connecting", "logged_in", "searching", "error", "kicked") or self._online_relogin:
            self.online_close()
        self._online_message = "@other_launcher.kept_other"
        return True

    def _other_kick_message(self):
        """The kick's message when this PC has another launcher of the game open, else None."""
        detector = self.other_launcher_detector or other_launchers.DETECTOR
        if detector.enabled:
            try:
                detector.refresh()              # the other one has just logged in: look now, not in 3 s
            except Exception:  # noqa: BLE001 -- the plain kick message then
                pass
        found = detector.others(self.other_launcher_game) if self.other_launcher_game else {}
        if found.get("native") and self._other_native_logs_in():
            key = "@other_launcher.kicked_native"
        elif found.get("online") or found.get("window"):
            key = "@other_launcher.kicked_window"
        else:
            return None
        self._other_choice = "other"            # stay out here until the player logs in by hand
        return key

    def _other_presence(self, on):
        if not self.other_launcher_game:
            return
        detector = self.other_launcher_detector or other_launchers.DETECTOR
        try:
            detector.online(self.other_launcher_game, on)
        except OSError:
            pass

    def _online_init(self):
        if hasattr(self, "_online_phase"):
            return
        cfg = self._online_config()
        self._online_fields = dict(online_name=str(cfg.get("name") or self._online_nickname() or ""),
                                   online_password="", online_server=str(cfg.get("server") or ""), online_chat="",
                                   online_room_name="", online_room_password="", online_room_code="",
                                   online_friend_name="")
        self._online_name_prefill = not bool(cfg.get("name"))
        self._online_phase = "offline"
        self._online_message = "@online.offline"
        self._online_name = ""
        self._online_account = False
        self._online_recovery_codes = []
        self._online_queue = ""
        self._online_match = {}
        self._online_players = []
        self._online_other_builds = 0
        self._online_me = {}
        self._online_rooms = []
        self._online_chat = []
        self._online_challenge = {}
        self._online_room = {}
        self._online_friends = []
        self._online_friend_incoming = []
        self._online_friend_outgoing = []
        self._online_invites = []
        self._online_outgoing_invite = {}
        self._online_client = None
        self._online_busy = False
        self._online_generation = 0
        self._online_results = queue.Queue()
        self._online_guard_at = 0.0
        self._online_lock = threading.RLock()
        # A queue request and the request that leaves the queue again go out in the order they were made: a Cancel
        # pressed while the search request is still on its way is sent after it (or the search is never sent).
        self._online_queue_lock = threading.Lock()
        self._online_relogin = None
        explicit = self._online_explicit_server()
        if explicit:
            # An override beats the address saved by the last login, as for T4 (docs/T5DR_ONLINE.md "Lobby address").
            self._online_fields["online_server"] = explicit
        elif not self._online_fields["online_server"].strip():
            # A new player sees the lobby an empty field means: the default entry of the servers lists.
            self._online_fields["online_server"] = self._online_default_server()
        t5_features.init(self)

    def _online_nickname(self):
        identity = self.config.get("online_identity") or {}
        return identity.get("name") or self.s.get("nickname")

    def _online_out_dir(self):
        return self.s.out_dir

    def _online_release(self):
        return self.release().get("version") or "dev"

    def _online_build(self, api):
        if not self.ready():
            raise RuntimeError("@online.build_required")
        if not api["build"].has_online(self._online_out_dir()):
            raise RuntimeError("@online.no_online")
        try:
            return api["build"].from_out_dir(self._online_out_dir(), self._online_release())
        except (OSError, ValueError):
            raise RuntimeError("@online.build_required") from None

    def _online_explicit_server(self):
        """OPENRECOMP_T5_SERVER, else the launcher config's t5_lobby_server, else ""."""
        configured = (os.environ.get(self.online_server_env, "").strip()
                      or str((getattr(self, "config", None) or {}).get(self.online_server_setting) or "").strip())
        return configured[:256]

    def _online_default_server(self):
        """What an empty Lobby address means: an override (OPENRECOMP_T5_SERVER, t5_lobby_server), else the
        default entry of the servers lists the client resolves names from (the install's lobby/servers.json, then
        the player's own, whose default wins), else the first listed entry; "" when nothing is listed (an invalid
        address, never a guessed one). A loopback lobby is used only when a test names it."""
        return self._online_explicit_server() or self._online_listed_default()

    def _online_user_servers_dir(self):
        """The folder of the player's own servers.json, as the client loads it."""
        directory = self._online_servers_dir()
        if getattr(self.s, "coexistence", False) and not os.path.isfile(os.path.join(directory, "servers.json")):
            sources = self.s.legacy_online_paths
            if sources:
                source = next((path for path in sources if os.path.isfile(path)), sources[0])
                directory = os.path.dirname(source)
        return directory

    def _online_listed_default(self):
        """The default entry's name from the servers.json files (read as files: no installed code runs here)."""
        paths = (os.path.join(self._online_lobby_dir(), "servers.json"),
                 os.path.join(self._online_user_servers_dir(), "servers.json"))
        stamps = []
        for path in paths:
            try:
                info = os.stat(path)
                stamps.append((path, info.st_mtime_ns, info.st_size))
            except OSError:
                stamps.append((path, None, None))
        cached = getattr(self, "_online_listed_cache", None)
        if cached and cached[0] == stamps:
            return cached[1]
        entries = {}
        for path in paths:
            try:
                with open(path, encoding="utf-8") as stream:
                    doc = json.load(stream)
            except (OSError, ValueError):
                continue
            servers = doc.get("servers") if isinstance(doc, dict) and doc.get("format") == SERVERS_FORMAT else None
            for entry in servers[:100] if isinstance(servers, list) else []:
                if not isinstance(entry, dict) or not str(entry.get("host") or "").strip():
                    continue
                name = str(entry.get("name") or entry.get("host"))[:64]
                if name != name.strip():
                    continue                        # the client's resolver would never match it by name
                entries.pop(name, None)
                entries[name] = entry
        found = next((name for name, entry in reversed(entries.items()) if entry.get("default") is True),
                     next(iter(entries), ""))
        self._online_listed_cache = (stamps, found)
        return found

    # The lobby keeps a dropped player's session this long (server T5L_RESUME_WINDOW, 600 s); the client keeps trying
    # to resume it a little less (a 60 s window gave up during a 90 s outage that the server would have survived).
    RECONNECT_SECONDS = 540
    UNQUEUE_TRIES, UNQUEUE_WAIT = 10, 1.0
    # A connection the client could not resume (the server restarted, or forgot the session): log in again by
    # itself, as the T5DR launcher does -- first after RELOGIN_FIRST s, then every RELOGIN_EVERY s for RELOGIN_FOR s.
    # Never after a kick or a ban, a logout, or a login by hand; an expired saved login stops it.
    RELOGIN_FIRST, RELOGIN_EVERY, RELOGIN_FOR = 3.0, 10.0, 600.0

    def _online_client_options(self):
        # reconnect: a dropped connection (Wi-Fi, a router) resumes the same session in the background, as in the
        # T5DR launcher; with 0 every short drop was a logout. A kick ("logged in from another place") never resumes.
        return dict(auto_ready=False, reconnect=self.RECONNECT_SECONDS, blind_ready=True, port_mapping=False)

    def _online_config_paths(self, writable=False):
        path = self.online_cfg_path()
        if getattr(self.s, "coexistence", False):
            sources = tuple(self.s.legacy_online_paths)
            if writable:
                target = os.path.normcase(os.path.realpath(path))
                if any(target == os.path.normcase(os.path.realpath(source)) for source in sources):
                    raise ValueError("@online.save_failed")
                return (path,)
            return (path,) + sources
        old = os.path.join(os.path.dirname(getattr(self.s, "path", "") or self.root), "online.json")
        return (path, old) if self.online_legacy_config else (path,)

    def _online_config(self):
        paths = self._online_config_paths()
        private = None
        for index, path in enumerate(paths):
            try:
                with open(path, encoding="utf-8") as stream:
                    cfg = json.load(stream)
                if isinstance(cfg, dict):
                    if getattr(self.s, "coexistence", False):
                        if index == 0:
                            private = cfg
                            continue
                        # The old launcher's preferred file wins over its legacy fallback.
                        # Overrides are merged only in memory; no old sessions are copied.
                        if private is not None:
                            sessions = cfg.get("sessions")
                            own_sessions = private.get("sessions")
                            merged = dict(cfg, **private)
                            if isinstance(sessions, dict) and isinstance(own_sessions, dict):
                                merged["sessions"] = dict(sessions, **own_sessions)
                            return merged
                    return cfg
            except (OSError, ValueError):
                continue
        return private or {}

    def _online_lobby_dir(self):
        """The folder that holds the client package: the selected install's own lobby."""
        return os.path.join(self.root, "lobby")

    def _online_servers_dir(self):
        return os.path.dirname(self.online_cfg_path())

    def _online_can_register(self):
        if self.online_registration is None:
            return self.online_package == "t5lobby"
        return bool(self.online_registration)

    def _online_modules(self):
        if not hasattr(self, "_online_api"):
            lobby = self._online_lobby_dir()
            package_root = os.path.normcase(os.path.realpath(os.path.join(lobby, self.online_package)))

            def local_origin(origin):
                try:
                    return (isinstance(origin, str) and os.path.commonpath(
                        (package_root, os.path.normcase(os.path.realpath(origin)))) == package_root)
                except ValueError:
                    return False

            spec = PathFinder.find_spec(self.online_package, [lobby])
            if spec is None or not local_origin(spec.origin):
                raise RuntimeError("@online.client_missing")
            # A second install must not reuse a previously imported client's server/config code.
            for name, module in tuple(sys.modules.items()):
                if name == self.online_package or name.startswith(self.online_package + "."):
                    if not local_origin(getattr(module, "__file__", None)):
                        raise RuntimeError("@online.client_missing")
            if lobby in sys.path:
                sys.path.remove(lobby)
            add_path(lobby)
            with readonly_imports():
                client = importlib.import_module(self.online_package + ".client")
                buildid = importlib.import_module(self.online_package + ".buildid")
                servers = importlib.import_module(self.online_package + ".servers")
                proto = importlib.import_module(self.online_package + ".proto")
            if not all(local_origin(getattr(module, "__file__", None))
                       for module in (client, buildid, servers, proto)):
                raise RuntimeError("@online.client_missing")
            if proto.PROTO_VERSION != 1 or (self.online_game and getattr(proto, "GAME", None) != self.online_game):
                raise RuntimeError("@online.client_missing")
            self._online_api = dict(client=client.LobbyClient, build=buildid.BuildInfo, servers=servers)
        return self._online_api

    def online_account_sessions(self):
        """This game's remembered account logins with the host each belongs to, for a sister game's lobby
        (T4 Online shares T5DR's accounts). Reads files only: no import, no connection. Plain-TCP logins and
        logins this session already saw refused are left out; the caller decides whether a host is trusted."""
        if self.online_package != "t5lobby":
            return []
        self._online_init()
        sessions = self._online_config().get("sessions")
        if not isinstance(sessions, dict):
            return []
        listed = {}
        for path in (os.path.join(self._online_lobby_dir(), "servers.json"),
                     os.path.join(self._online_servers_dir(), "servers.json")):
            try:
                with open(path, encoding="utf-8") as stream:
                    doc = json.load(stream)
            except (OSError, ValueError):
                continue
            for entry in (doc.get("servers") if isinstance(doc, dict) else None) or []:
                if isinstance(entry, dict) and entry.get("name") and entry.get("host"):
                    listed[str(entry["name"]).strip().lower()] = (str(entry["host"]).strip().lower(),
                                                                  entry_tls(entry))
        rejected = set(getattr(self, "_online_rejected_sessions", {}).values())
        out = []
        for key, saved in sessions.items():
            if (not isinstance(saved, dict) or not isinstance(saved.get("token"), str) or not saved["token"]
                    or saved["token"] in rejected):
                continue
            text = str(key).strip().lower()
            if text in listed:
                host, tls = listed[text]
            else:
                secure = text.startswith("tls://") or "#" in text
                address = (text[6:] if text.startswith("tls://") else text).split("#", 1)[0]
                host = address.rsplit(":", 1)[0] if ":" in address else address
                tls = "ca" if secure else "off"
            if tls == "off" or not host:
                continue
            saved_at = saved.get("saved")
            out.append(dict(host=host, name=str(saved.get("name") or "")[:64], token=saved["token"],
                            saved=saved_at if isinstance(saved_at, (int, float)) and not isinstance(saved_at, bool)
                            else 0))
        return out

    def _online_saved(self):
        key = (self._online_fields["online_server"].strip() or self._online_default_server()).strip().lower()
        sessions = self._online_config().get("sessions") or {}
        saved = sessions.get(key) if isinstance(sessions, dict) else None
        rejected = getattr(self, "_online_rejected_sessions", {})
        if isinstance(saved, dict) and saved.get("token") == rejected.get(key):
            return None
        return saved if isinstance(saved, dict) and isinstance(saved.get("token"), str) and saved["token"] else None

    def online_state(self):
        self._online_init()
        capabilities = dict(ranked=self.online_ranked, lobby=self.online_lobby,
                            match_flow=self.online_match_flow)
        if self._online_can_register():
            capabilities["registration"] = True
        if self.online_lobby and self.online_game != "t4":
            capabilities.update(private_rooms=self._online_social_cap("private_rooms"),
                                friends=self._online_social_cap("friends"))
        message = self._online_message
        others = getattr(self, "_online_other_builds", 0)
        if self._online_phase == "searching" and others:
            # Somebody is searching too, but the server pairs only the same build: say it instead of searching silently.
            message = i18n.message("online.searching_other_build", count=others)
        snapshot = dict(phase=self._online_phase, message=message, other_builds=others,
                    name=self._online_name, account=self._online_account,
                    recovery_codes=list(self._online_recovery_codes),
                    queue=self._online_queue, match=dict(self._online_match),
                    saved_available=bool(self._online_saved()),
                    capabilities=capabilities,
                    players=[dict(p) for p in self._online_players], rooms=[dict(r) for r in self._online_rooms],
                    chat=[dict(line) for line in self._online_chat], challenge=dict(self._online_challenge),
                    room=dict(self._online_room), friends=[dict(f) for f in self._online_friends],
                    friend_incoming=[dict(f) for f in self._online_friend_incoming],
                    friend_outgoing=[dict(f) for f in self._online_friend_outgoing],
                    invites=[dict(inv) for inv in self._online_invites],
                    outgoing_invite=dict(self._online_outgoing_invite))
        snapshot["remember"] = bool(getattr(self, "_online_remember", True))
        other = self._other_state()
        if other:
            snapshot["other_launcher"] = other
        if self.online_ranked:
            snapshot["capabilities"]["strict"] = True
            snapshot["strict"] = bool(getattr(self, "_online_strict", False))
        if self._online_client is not None:
            # The profile card: this player's own lobby entry, the round trip to the server, encryption.
            snapshot["me"] = dict(getattr(self, "_online_me", None) or {})
            rtt = getattr(self._online_client, "server_rtt", None)
            if isinstance(rtt, (int, float)) and not isinstance(rtt, bool) and 0 <= rtt < 100000:
                snapshot["server_ping"] = round(rtt)
            snapshot["secure"] = bool(getattr(self._online_client, "tls", False))
            # Two players can compare at a glance: a match needs the same build (and the same game folder's build).
            build = getattr(getattr(self._online_client, "build", None), "build_id", None)
            if isinstance(build, str) and build:
                snapshot["build_id"] = build[:24]
            if isinstance(getattr(self, "root", None), str) and self.root:
                snapshot["game_folder"] = self.root[-120:]
        return t5_features.state(self, snapshot)

    def _online_social_cap(self, capability):
        if not self.online_lobby or self.online_game == "t4" or self._online_client is None:
            return False
        if capability == "friends" and not self._online_account:
            return False
        check = (getattr(self._online_client, "has_friends", None) if capability == "friends"
                 else getattr(self._online_client, "private_rooms_ok", None))
        try:
            return bool(check and check())
        except Exception:  # noqa: BLE001 -- unknown installed/server capabilities stay hidden
            return False

    def online_text_value(self, tid):
        self._online_init()
        if (tid == "online_name" and self._online_name_prefill and self._online_client is None
                and not self._online_busy):
            self._online_fields[tid] = str(self._online_nickname() or "")
        return self._online_fields.get(tid, "")

    def set_online_text_value(self, tid, value):
        self._online_init()
        # These requests capture drafts before submitting and never clear them on completion.
        draft = self._online_phase == "logged_in" and tid in (
            "online_room_name", "online_room_password", "online_room_code",
            "online_tour_name", "online_tour_clock", "online_tour_dq")
        if (tid in self._online_fields and (not self._online_busy or draft)
                and (self._online_client is None or tid not in (
                     "online_name", "online_password", "online_server", "online_fingerprint"))):
            self._online_fields[tid] = str(value)
            if tid == "online_name":
                self._online_name_prefill = False

    def _online_submit(self, operation, work):
        generation = self._online_generation
        self._online_busy = True
        self._online_pending = operation

        def run():
            try:
                value, error = work(), None
            except Exception as exc:  # noqa: BLE001 -- a runtime client may be absent or refuse a request
                value, error = None, exc
            self._online_results.put((generation, operation, value, error))
        threading.Thread(target=run, name="openrecomp-lobby", daemon=True).start()

    def lobby_release(self):
        """The lobby's announced release (GitHub's release JSON) from this session's welcome, or from the refusal
        of an old build; None when the lobby said nothing. The launcher's game setup reads it: no extra connection."""
        welcome = getattr(self._online_client, "welcome", None)
        if isinstance(welcome, dict) and isinstance(welcome.get("latest_release"), dict):
            return welcome["latest_release"]
        return getattr(self, "_online_release_seen", None)

    def _online_error(self, error, saved=False):
        extra = getattr(error, "extra", None)
        if isinstance(extra, dict) and isinstance(extra.get("latest_release"), dict):
            self._online_release_seen = extra["latest_release"]
        if t5_features.enabled(self):
            from . import t5_moderation
            notice = t5_moderation.refusal(self, error)
            if notice:
                return notice
        code = getattr(error, "code", "")
        if not isinstance(code, str):
            code = ""
        if saved and code == "auth_failed":
            return "@online.saved_expired"
        keys = dict(auth_failed="@online.auth_failed", insecure="@online.insecure", bad_name="@online.bad_name",
                    name_taken="@online.name_taken", timeout="@online.unavailable", rate_limited="@online.rate_limited",
                    version_mismatch="@online.version_mismatch", proto_mismatch="@online.version_mismatch",
                    server_full="@online.server_full", busy="@online.busy_server",
                    room_locked="@online.room_locked", bad_password="@online.room_locked",
                    # The connection never came about or broke (refused, timed out, unknown name, TLS handshake): the
                    # lobby did not refuse anything. A certificate other than the pinned one is a server setting.
                    connect_failed="@online.unreachable", not_connected="@online.unreachable",
                    disconnected="@online.unreachable", tls_mismatch="@online.server_invalid")
        local = ("@online.client_missing", "@online.build_required", "@online.no_online",
                 "@online.server_invalid", "@online.game_running", "@online.process_unknown", "@online.cancelled",
                 "@online.watch_unavailable", "@online.rules_unavailable", "@online.insecure")
        if isinstance(error, RuntimeError) and str(error) in local:
            return str(error)
        if isinstance(error, (ImportError, AttributeError, TypeError)):
            return "@online.client_missing"
        if isinstance(error, (OSError, ConnectionError)):
            return "@online.unavailable"
        return keys.get(code, "@online.refused")

    def _online_write_session(self, server, name, token, expected=None):
        """Merge a fresh file; no password is ever stored, and unrelated native settings survive."""
        path = self.online_cfg_path()
        paths = self._online_config_paths(writable=True)
        cfg = {}
        for candidate in paths:
            try:
                with open(candidate, encoding="utf-8") as stream:
                    cfg = json.load(stream)
                break
            except FileNotFoundError:
                continue
        if not isinstance(cfg, dict) or ("sessions" in cfg and not isinstance(cfg["sessions"], dict)):
            raise ValueError("@online.save_failed")
        sessions = cfg.get("sessions", {})
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
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + "." + uuid.uuid4().hex + ".tmp"
        try:
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(cfg, stream, indent=1)
            os.replace(temporary, path)
        finally:
            if os.path.isfile(temporary):
                os.remove(temporary)

    def _online_write_preferences(self, changes):
        """Merge only non-session preferences into the writable file, preserving saved logins."""
        if not isinstance(changes, dict) or any(key in changes for key in (
                "sessions", "password", "token", "session")):
            raise ValueError("@online.save_failed")
        with self._online_lock:
            path = self.online_cfg_path()
            paths = self._online_config_paths(writable=True)
            cfg = {}
            for candidate in paths:
                try:
                    with open(candidate, encoding="utf-8") as stream:
                        cfg = json.load(stream)
                    break
                except FileNotFoundError:
                    continue
            if not isinstance(cfg, dict) or ("sessions" in cfg and not isinstance(cfg["sessions"], dict)):
                raise ValueError("@online.save_failed")
            cfg.update(changes)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            temporary = path + "." + uuid.uuid4().hex + ".tmp"
            try:
                with open(temporary, "w", encoding="utf-8") as stream:
                    json.dump(cfg, stream, indent=1)
                os.replace(temporary, path)
            finally:
                if os.path.isfile(temporary):
                    os.remove(temporary)

    def _online_new_client(self, server, cfg=None):
        """Construct from this install; the caller owns connect, authorization and close."""
        cfg = self._online_config() if cfg is None else cfg
        api = self._online_modules()
        build = self._online_build(api)
        entries, _problems = api["servers"].load(user_dir=self._online_user_servers_dir())
        # A blank field means the same server as the saved-session lookup (_online_saved): a login saved for one
        # server is never sent to another.
        target = server or self._online_default_server()
        try:
            entry = api["servers"].resolve(target, entries)
            kwargs = entry.client_kwargs()
        except (ValueError, TypeError):
            raise RuntimeError("@online.server_invalid") from None
        fingerprint = self._online_fields.get("online_fingerprint", cfg.get("fingerprint"))
        if entry.tls != "pin" and fingerprint:
            kwargs["tls_fingerprint"] = fingerprint
        options = t5_features.options(self, api["client"], self._online_client_options())
        client = api["client"](build=build, **options, **kwargs)
        try:
            t5_features.client_created(self, client)
        except Exception:
            close_client(client)
            raise
        return client, target

    def _online_login(self, action):
        name = self.online_text_value("online_name").strip()
        password = self._online_fields["online_password"]
        self._online_fields["online_password"] = ""
        saved = self._online_saved() if action == "login_saved" else None
        if action == "login_saved" and saved is None:
            self._online_message = "@online.saved_missing"
            return
        if action in ("login_account", "login_register") and not password:
            self._online_message = "@online.password_required"
            return
        server = self._online_fields["online_server"].strip()
        cfg = self._online_config()
        generation = self._online_generation
        remember = bool(getattr(self, "_online_remember", True))     # "Remember me": keep the login for next time
        self._online_phase, self._online_message = "connecting", "@online.connecting"
        self._online_match = {}

        def work():
            client = None
            try:
                client, target = self._online_new_client(server, cfg)
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
                    if saved.get("shared") and not getattr(client, "tls", False):
                        raise RuntimeError("@online.insecure")     # another game's login only over TLS
                    me = client.login_session(saved["token"])
                elif action == "login_register":
                    me = client.register(name, password, remember=remember)
                else:
                    me = client.login(name, password, remember=remember)
                if not isinstance(me, dict):
                    raise RuntimeError("@online.client_missing")
                self._online_check_request(generation, client)
                t5_features.logged_in(self, client)
                warning = ""
                with self._online_lock:
                    if generation != self._online_generation:
                        raise RuntimeError("@online.cancelled")
                    if action in ("login_account", "login_register") and client.session and remember:
                        try:
                            self._online_write_session(target, me["name"], client.session)
                        except (OSError, ValueError, TypeError):
                            warning = "@online.save_failed"
                return dict(me=me, server=target, warning=warning)
            except Exception as error:
                if client:
                    close_client(client)
                if action == "login_saved" and getattr(error, "code", "") == "auth_failed":
                    with self._online_lock:
                        if generation == self._online_generation:
                            if getattr(self.s, "coexistence", False):
                                rejected = getattr(self, "_online_rejected_sessions", {})
                                rejected[(server or self._online_default_server()).strip().lower()] = saved["token"]
                                self._online_rejected_sessions = rejected
                            try:
                                self._online_write_session(server or self._online_default_server(), None, None,
                                                           expected=saved["token"])
                            except (OSError, ValueError, TypeError):
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
        if action == "spec_stop" and t5_features.action(self, action, self._online_client):
            return
        if self._other_action(action):
            return
        if action == "logout":
            self.online_close()
            self._online_auto_tried = True        # no automatic login after the player logged out
            self._online_message = "@online.logged_out"
            return
        if action == "acknowledge_recovery":
            self._online_recovery_codes = []
            return
        if action == "login_remember":
            # Remember me: an account login is kept for the next start (and can log in by itself there).
            self._online_remember = not getattr(self, "_online_remember", True)
            return
        if action == "ranked_strict":
            # Ranked only against players within the server's strict range (150 rating points): a choice of this
            # launcher, sent with the next ranked search.
            self._online_strict = not getattr(self, "_online_strict", False)
            return
        if action == "cancel" and self._online_phase == "searching" and self._online_client is not None:
            # Leave the queue and stay logged in (a closed connection here was a logout after every cancelled
            # search), also while the search request is still on its way: the queue lock sends the leave after it,
            # or the search is never sent. Only a leave request the server never answers detaches (_online_to_lobby).
            self._online_to_lobby("@online.cancelled")
            return
        if action == "cancel" and self._online_phase in ("connecting", "searching"):
            # A queue acknowledgement can race a match offer or never arrive. Detach now;
            # the closed connection also prevents an automatic server-side requeue.
            self.online_close()
            self._online_message = "@online.cancelled"
            return
        if self._online_busy:
            return
        if self._online_client is None and t5_features.offline_action(self, action):
            return
        if action in ("login_guest", "login_account", "login_register", "login_saved"):
            if action == "login_register" and not self._online_can_register():
                return
            if self._online_client is None:
                self._online_relogin = None       # the player logs in by hand
                self._online_auto_tried = True
                if self._other_kind():
                    self._other_choice = "here"   # a login by hand is the choice: this launcher
                self._online_login(action)
            return
        client = self._online_client
        if client is None or self._online_phase in ("offline", "kicked", "error", "matched"):
            self._online_message = "@online.login_required"
            return
        if action in ("search_casual", "search_ranked"):
            if self._online_phase != "logged_in":
                return
            if action == "search_ranked" and not self.online_ranked:
                self._online_message = "@online.ranked_unavailable"
                return
            if action == "search_ranked" and not self._online_account:
                self._online_message = "@online.account_required"
                return
            mode = "ranked" if action == "search_ranked" else "casual"
            self._online_phase, self._online_queue = "searching", mode
            self._online_message = "@online.searching_ranked" if mode == "ranked" else "@online.searching_casual"
            self._online_search_submit(mode)
        elif self.online_lobby and self._online_phase == "logged_in":
            if not t5_features.action(self, action, client):
                self._online_lobby_action(action, client)

    def _online_search_submit(self, mode):
        client, generation, char = self._online_client, self._online_generation, self.chosen_fighter()
        strict = bool(getattr(self, "_online_strict", False))
        options = t5_netext.options(self, client) if t5_features.enabled(self) else {}

        def work():
            problem = self._online_game_check()
            if problem:
                raise SearchRefused(problem)
            with self._online_queue_lock:
                self._online_check_request(generation, client)
                if mode == "ranked" and strict:
                    client.ranked_match(char, strict=True, **options)
                elif mode == "ranked":
                    client.ranked_match(char, **options)
                else:
                    client.quick_match(char, **options)
            return mode
        self._online_submit("search_ranked" if mode == "ranked" else "search_casual", work)

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise SearchRefused("@online.cancelled")

    def _online_player_rank(self, rating):
        return ""

    def rank_progress(self, rating):
        """The ranked card's bar: (start of this rank, start of the next, the next rank's name) from the installed
        client's own rank table, or None (no table, a guest, the top rank)."""
        if (self.online_package != "t5lobby" or "_online_api" not in self.__dict__
                or isinstance(rating, bool) or not isinstance(rating, (int, float))):
            return None
        ranks = self.__dict__.get("_online_ranks")
        if ranks is None:
            try:
                with readonly_imports():
                    ranks = importlib.import_module(self.online_package + ".ranks")
                if not all(callable(getattr(ranks, name, None)) for name in ("tier_for", "threshold", "name")):
                    ranks = False
            except Exception:  # noqa: BLE001 -- an older client: no bar
                ranks = False
            self._online_ranks = ranks
        if not ranks:
            return None
        try:
            tier = ranks.tier_for(rating)
            low, high = ranks.threshold(tier), ranks.threshold(tier + 1)
            if not (math.isfinite(high)):
                return None
            low = low if math.isfinite(low) else high - 50
            return float(low), float(high), str(ranks.name(tier + 1))
        except Exception:  # noqa: BLE001 -- the top rank (no next one) or an unexpected table
            return None

    def _online_player(self, player):
        if not isinstance(player, dict):
            return {}
        rating = player.get("rating")
        if isinstance(rating, bool) or not isinstance(rating, (int, float)):
            rating = None
        out = dict(id=str(player.get("id") or "")[:80], name=str(player.get("name") or "")[:64],
                   rating=rating, rank=self._online_player_rank(rating))
        out.update(t5_netext.tags(player))
        # What the lobby table shows beside the name (all optional: older servers send less).
        if not out["rank"] and isinstance(player.get("rank"), str):
            out["rank"] = player["rank"][:40]
        if player.get("guest") is True:
            out["guest"] = True
        if player.get("status") in ("idle", "room", "queue", "match", "playing"):
            out["status"] = player["status"]
        record = player.get("record")
        if (isinstance(record, (list, tuple)) and 2 <= len(record) <= 3
                and all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in record)):
            out["record"] = [min(n, 10 ** 7) for n in record]
        tier = player.get("tier")
        if isinstance(tier, int) and not isinstance(tier, bool) and 0 <= tier < 64:
            out["tier"] = tier
        if player.get("provisional") is True:
            out["provisional"] = True
        placement = player.get("placement")
        if (isinstance(placement, (list, tuple)) and len(placement) == 2
                and all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 100 for n in placement)):
            out["placement"] = list(placement)
        if isinstance(player.get("main"), str) and player["main"]:
            out["main"] = player["main"][:40]
        ping_to = getattr(self._online_client, "ping_to", None)
        if callable(ping_to):
            try:
                ping, measured = ping_to(player)
            except Exception:  # noqa: BLE001 -- an older client: no ping column
                ping, measured = None, False
            if isinstance(ping, (int, float)) and not isinstance(ping, bool) and 0 <= ping < 100000:
                out["ping"] = round(ping)
                out["ping_measured"] = bool(measured)
        return out

    def _online_room_view(self, room):
        if not isinstance(room, dict):
            return {}
        owner = room.get("owner") or {}
        out = dict(id=str(room.get("id") or "")[:80], name=str(room.get("name") or "")[:64],
                    host=str(owner.get("name") or "")[:64] if isinstance(owner, dict) else "",
                    status=str(room.get("status") or "")[:20])
        out.update(t5_netext.tags(room))
        if self._online_social_cap("private_rooms"):
            lock = room.get("lock") or room.get("private") or "none"
            out["lock"] = lock if lock in ("none", "password", "code") else "none"
        return out

    def _online_own_room(self, room):
        room = room[0] if isinstance(room, tuple) and room else room
        self._online_room = self._online_room_view(room)
        if self._online_room.get("id") and self._online_social_cap("private_rooms"):
            code = getattr(self._online_client, "room_code", None)
            if isinstance(code, str):
                self._online_room["code"] = code[:40]

    def _online_friends_snapshot(self, event):
        if not self._online_social_cap("friends") or not isinstance(event, dict):
            return
        friends = event.get("friends") or []
        self._online_friends = []
        for friend in friends[:200] if isinstance(friends, list) else []:
            if not isinstance(friend, dict) or not friend.get("name"):
                continue
            retry = friend.get("retry")
            retry = max(0, min(retry, 86400)) if isinstance(retry, int) and not isinstance(retry, bool) else 0
            retry = self._online_invite_wait(friend["name"], retry)
            self._online_friends.append(dict(name=str(friend["name"])[:64],
                status=friend.get("status") if friend.get("status") in ("online", "in_match", "offline") else "offline",
                activity=str(friend.get("activity") or "")[:64], invite=friend.get("invite") == "ok", retry=retry))
        for field in ("incoming", "outgoing"):
            entries = event.get(field) or []
            setattr(self, "_online_friend_" + field, [dict(name=str(entry["name"])[:64])
                for entry in entries[:200] if isinstance(entry, dict) and entry.get("name")]
                if isinstance(entries, list) else [])

    def _online_social_event(self, event):
        if not self._online_social_cap("friends"):
            return False
        kind = event.get("t")
        if kind == "friends":
            self._online_friends_snapshot(event)
        elif kind in ("friend_status", "friend_request", "friend_update"):
            self._online_friends_snapshot(getattr(self._online_client, "friend_list", None))
            self._online_message = "@online.friend_updated"
        elif kind == "invited":
            sender, room = event.get("from"), event.get("room")
            sender = sender if isinstance(sender, dict) else {}
            room = room if isinstance(room, dict) else {}
            iid = str(event.get("invite") or "")[:80]
            if iid:
                self._online_invites = [inv for inv in self._online_invites if inv["id"] != iid][-19:]
                self._online_invites.append(dict(id=iid, name=str(sender.get("name") or "")[:64],
                    kind="room" if event.get("kind") == "room" else "casual", room=str(room.get("name") or "")[:64]))
        elif kind == "invite_update":
            iid = str(event.get("invite") or "")[:80]
            self._online_invites = [inv for inv in self._online_invites if inv["id"] != iid]
            if self._online_outgoing_invite.get("id") == iid:
                self._online_outgoing_invite = {}
            self._online_friends_snapshot(getattr(self._online_client, "friend_list", None))
            self._online_message = "@online.invite_ended"
        else:
            return False
        return True

    def _online_invite_wait(self, name, fallback=0):
        wait = getattr(self._online_client, "invite_wait", None)
        if not callable(wait):
            return fallback
        try:
            retry = wait(name)
            if isinstance(retry, (int, float)) and not isinstance(retry, bool) and math.isfinite(retry):
                return max(0, min(retry, 86400))
        except Exception:  # an incompatible installed timer must not crash polling or permit an invite
            pass
        return 86400

    def _online_invite_waits(self):
        wait = getattr(self._online_client, "invite_wait", None)
        if not callable(wait):
            return False
        changed = False
        for friend in self._online_friends:
            retry = self._online_invite_wait(friend["name"], friend["retry"])
            if retry != friend["retry"]:
                friend["retry"] = retry
                changed = True
        return changed

    def _online_lobby_snapshot(self, event):
        me = getattr(self._online_client, "me", None) or {}
        me = me if isinstance(me, dict) else {}
        players, rooms = event.get("players"), event.get("rooms")
        players = players if isinstance(players, (list, tuple)) else []
        rooms = rooms if isinstance(rooms, (list, tuple)) else []
        self._online_players = [self._online_player(p) for p in players
                                if isinstance(p, dict) and p.get("id") != me.get("id")][:200]
        self._online_other_builds = sum(1 for p in players if isinstance(p, dict) and p.get("id") != me.get("id")
                                        and p.get("status") == "queue" and not self._online_same_build(p))
        own = next((p for p in players if isinstance(p, dict) and me.get("id") and p.get("id") == me.get("id")), None)
        self._online_me = self._online_player(own) if own else {}
        self._online_rooms = [self._online_room_view(r) for r in rooms
                              if isinstance(r, dict) and not (r.get("hidden") or r.get("ranked") or r.get("training"))
                              and (self._online_social_cap("private_rooms") or not (
                                  r.get("private") or r.get("lock") not in (None, "", "none", False)))][:200]

    def _online_same_build(self, player):
        """Could the server pair this lobby entry with us? The client's own rule (exact build or an accepted
        compatibility group) when it has one, else the exact build id."""
        client = self._online_client
        check = getattr(client, "compatible", None)
        if callable(check):
            try:
                return bool(check(player))
            except Exception:  # noqa: BLE001 -- an older or odd client: fall back to the build id
                pass
        mine = getattr(getattr(client, "build", None), "build_id", None)
        theirs = player.get("build")
        return not (mine and theirs) or theirs == mine

    def _online_lobby_action(self, action, client):
        generation = self._online_generation
        work = None
        if action in ("refresh_players", "refresh_rooms"):
            work = client.refresh
        elif action.startswith("challenge:"):
            target = action.split(":", 1)[1]
            if any(p["id"] == target for p in self._online_players):
                def work():
                    problem = self._online_game_check()
                    if problem:
                        raise SearchRefused(problem)
                    self._online_check_request(generation, client)
                    return client.challenge(target)
        elif action in ("accept_challenge", "decline_challenge") and self._online_challenge:
            challenge = self._online_challenge["id"]
            def work():
                if action == "accept_challenge":
                    problem = self._online_game_check()
                    if problem:
                        raise SearchRefused(problem)
                self._online_check_request(generation, client)
                return client.answer_challenge(challenge, accept=action == "accept_challenge")
        elif action in ("create_room", "create_password_room", "create_code_room"):
            private = {"create_password_room": "password", "create_code_room": "code"}.get(action)
            if private and not self._online_social_cap("private_rooms"):
                self._online_message = "@online.social_unavailable"
                return
            password = self._online_fields["online_room_password"][:128]
            name = self._online_fields["online_room_name"].strip()[:64]
            if private == "password" and not password:
                self._online_message = "@online.room_password_required"
                return
            self._online_fields["online_room_password"] = ""
            def work():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self._online_check_request(generation, client)
                if private:
                    return client.create_room(name=name or None, ranked=False, private=private,
                                              **(dict(password=password) if private == "password" else {}))
                if name and self._online_social_cap("private_rooms"):
                    return client.create_room(name=name, ranked=False)
                return client.create_room(ranked=False)
        elif action.startswith("join_room:"):
            target = action.split(":", 1)[1]
            if any(r["id"] == target for r in self._online_rooms):
                room = next(r for r in self._online_rooms if r["id"] == target)
                password = self._online_fields["online_room_password"][:128]
                code = self._online_fields["online_room_code"].strip()[:40]
                if room.get("lock") == "password" and not password:
                    self._online_message = "@online.room_password_required"
                    return
                if room.get("lock") == "code" and not code:
                    self._online_message = "@online.room_code_required"
                    return
                self._online_fields["online_room_password"] = ""
                def work():
                    problem = self._online_game_check()
                    if problem:
                        raise SearchRefused(problem)
                    self._online_check_request(generation, client)
                    if room.get("lock") == "password":
                        return client.join_room(target, password=password)
                    if room.get("lock") == "code":
                        return client.join_room(target, code=code)
                    return client.join_room(target)
        elif action == "join_room_code" and self._online_social_cap("private_rooms"):
            code = self._online_fields["online_room_code"].strip()[:40]
            if not code:
                self._online_message = "@online.room_code_required"
                return
            def work():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self._online_check_request(generation, client)
                return client.join_room(code=code)
        elif action == "leave_room":
            work = client.leave_room
        elif action == "send_chat":
            text = self._online_fields["online_chat"].strip()[:300]
            if not text:
                self._online_message = "@online.chat_required"
                return
            work = lambda: client.chat(text)
        elif self._online_social_cap("friends"):
            work = self._online_friend_action(action, client)
        if work:
            def checked():
                self._online_check_request(generation, client)
                return work()
            self._online_submit(action, checked)

    def _online_friend_action(self, action, client):
        generation = self._online_generation
        prefix, _, target = action.partition(":")
        if action == "refresh_friends":
            return client.friends_list
        if action == "add_friend":
            name = self._online_fields["online_friend_name"].strip()[:64]
            if not name:
                self._online_message = "@online.friend_name_required"
                return None
            return lambda: client.add_friend(name)
        incoming = {entry["name"] for entry in self._online_friend_incoming}
        outgoing = {entry["name"] for entry in self._online_friend_outgoing}
        friends = {entry["name"]: entry for entry in self._online_friends}
        if prefix in ("accept_friend", "decline_friend") and target in incoming:
            return lambda: client.answer_friend(target, accept=prefix == "accept_friend")
        if prefix == "cancel_friend" and target in outgoing:
            return lambda: client.cancel_friend_request(target)
        if prefix == "remove_friend" and target in friends:
            return lambda: client.remove_friend(target)
        if prefix in ("invite_friend", "invite_room") and target in friends:
            friend = friends[target]
            retry = self._online_invite_wait(target, friend.get("retry", 0))
            if retry:
                self._online_message = "@online.invite_wait"
                return None
            if friend.get("status") != "online" or not friend.get("invite"):
                return None
            if prefix == "invite_room" and not self._online_room.get("id"):
                return None
            def work():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self._online_check_request(generation, client)
                return client.invite(target, kind="room" if prefix == "invite_room" else "casual")
            return work
        if prefix in ("accept_invite", "decline_invite") and any(inv["id"] == target for inv in self._online_invites):
            def work():
                if prefix == "accept_invite":
                    problem = self._online_game_check()
                    if problem:
                        raise SearchRefused(problem)
                self._online_check_request(generation, client)
                return client.answer_invite(target, accept=prefix == "accept_invite")
            return work
        if action == "cancel_invite" and self._online_outgoing_invite:
            iid = self._online_outgoing_invite["id"]
            return lambda: client.cancel_invite(iid)
        return None

    @staticmethod
    def _online_match_request(action):
        return (action.startswith(("search_", "challenge:", "join_room:", "accept_invite:",
                                   "invite_friend:", "invite_room:")) or action in (
            "accept_challenge", "create_room", "create_password_room", "create_code_room", "join_room_code"))

    def _online_event(self, event):
        """A game-specific match flow can consume events without exposing tickets to screens."""
        return False

    def _online_match_found(self, event):
        return False

    def _online_match_view(self, event):
        opponent, ping = event.get("opponent"), event.get("ping")
        opponent = opponent if isinstance(opponent, dict) else {}
        ping = ping if isinstance(ping, dict) else {}
        return dict(opponent=str(opponent.get("name") or "")[:64], ping=ping.get("ms"))

    def _online_completion(self, action, value, error):
        return t5_features.completion(self, action, value, error)

    def _online_events(self):
        """Read one queue snapshot. A kick wins over a simultaneous request failure or disconnect."""
        if getattr(self, "_netext_removing", False):
            # forget_me closes the connection after its reply. Finish that request before handling the close.
            return False, False
        client = self._online_client
        if client is None:
            return False, False
        events = []
        for _ in range(client.events.qsize()):
            try:
                event = client.events.get_nowait()
                if isinstance(event, dict):
                    events.append(event)
            except queue.Empty:
                break
        if getattr(self, "_online_leaving", False):
            # The player left the queue, but the server may have paired them before the leave arrived: say no to
            # such an offer instead of showing a match after Cancel (the other player goes back to the queue).
            late = [event for event in events if event.get("t") == "match_found"]
            events = [event for event in events if event.get("t") != "match_found"]
            for event in late:
                self._online_decline_late(client, event.get("match"))
        retained = False
        priority = ("kicked", "disconnected") if self.online_match_flow else (
            "kicked", "match_found", "disconnected")
        for event in events:
            # The kick itself can be missed (the connection closed before its line was read): the installed client
            # still names it in the disconnect ("removed from the lobby: ..."). Never relogin against that.
            reason = str(event.get("reason") or "").lower()
            if event.get("t") == "disconnected" and reason.startswith("removed from the lobby"):
                event["t"], event["reason"] = "kicked", reason.partition(":")[2].strip()
        for kind in priority:
            event = next((event for event in events if event.get("t") == kind), None)
            if event is None:
                continue
            if kind == "match_found" and self._online_match_found(event):
                # A playable adapter retains the client through ready, NAT and the game.
                events = [ev for ev in events if ev is not event]
                retained = True
                break
            name, account = self._online_name, self._online_account
            self.online_close()
            if kind == "kicked":
                reason = str(event.get("reason") or "").lower()
                self._online_phase = "kicked"
                elsewhere = "logged in from another place" in reason
                self._online_message = ((elsewhere and self._other_kick_message()) or
                                        ("@online.kicked" if elsewhere else "@online.removed"))
            elif kind == "match_found":
                # Closing also prevents the server requeueing this client after a ready timeout.
                self._online_phase = "matched"
                self._online_match = self._online_match_view(event)
                self._online_name, self._online_account = name, account
                self._online_message = "@online.matched"
            else:
                self._online_message = "@online.disconnected"
                self._online_relogin_start(name, account)
            return True, True
        changed = retained
        for event in events:
            if event.get("t") in ("reconnecting", "reconnected"):
                # The connection broke and the client resumes the same session by itself: still logged in.
                self._online_message = "@online.reconnecting" if event["t"] == "reconnecting" else "@online.reconnected"
                changed = True
                if event["t"] == "reconnected":
                    self._online_resumed()
            if t5_features.event(self, event):
                changed = True
            elif self.online_match_flow and event.get("t") == "match_found":
                self._online_invites = []
                self._online_outgoing_invite = {}
                self._online_challenge = {}
                if not self._online_match_found(event):
                    name, account = self._online_name, self._online_account
                    self.online_close()
                    self._online_phase, self._online_message = "matched", "@online.matched"
                    self._online_match = self._online_match_view(event)
                    self._online_name, self._online_account = name, account
                    return True, True
                changed = True
            elif self._online_event(event):
                changed = True
            elif self._online_social_event(event):
                changed = True
            elif self.online_lobby and event.get("t") == "lobby_state":
                self._online_lobby_snapshot(event)
                changed = True
            elif self.online_lobby and event.get("t") == "room":
                self._online_own_room(event.get("room"))
                changed = True
            elif self.online_lobby and event.get("t") == "chat":
                sender = event.get("from") or {}
                line = dict(name=str(sender.get("name") or "")[:64] if isinstance(sender, dict) else "",
                            text=str(event.get("text") or "")[:300])
                if isinstance(sender, dict) and sender.get("badge") == "dev":
                    line["badge"] = "dev"
                self._online_chat.append(line)
                self._online_chat = self._online_chat[-50:]
                changed = True
            elif self.online_lobby and event.get("t") == "challenged":
                sender = event.get("from") or {}
                self._online_challenge = dict(id=str(event.get("challenge") or "")[:80],
                                              name=str(sender.get("name") or "")[:64]
                                              if isinstance(sender, dict) else "")
                changed = True
            elif self.online_lobby and event.get("t") == "challenge_update":
                if event.get("challenge") == self._online_challenge.get("id"):
                    self._online_challenge = {}
                    changed = True
            elif event.get("t") == "error":
                self._online_message = self._online_error(type("RequestError", (Exception,), {
                    "code": event.get("code", "")})())
                changed = True
        return changed, False

    def online_poll(self):
        self._online_init()
        relogin = self._online_relogin_tick()
        changed, terminal = self._online_events()
        if terminal:
            return True
        changed = changed or relogin
        while True:
            try:
                generation, action, value, error = self._online_results.get_nowait()
            except queue.Empty:
                break
            if generation != self._online_generation:
                continue
            changed = True
            self._online_busy = False
            if t5_features.match_request(action):
                if error:
                    event_changed, terminal = self._online_events()
                    changed = changed or event_changed
                    if terminal:
                        return True
                if (self.online_match_flow and self._online_phase in (
                        "matched", "starting", "playing", "result", "result_sent")):
                    continue
                local = isinstance(error, SearchRefused) or (isinstance(error, RuntimeError) and str(error) in (
                    "@online.game_running", "@online.process_unknown", "@online.cancelled"))
                if error and not local:
                    # A lost acknowledgement may have reserved a match: leave the queue again, logged in.
                    self._online_request_failed(action, error)
                    continue
            if self._online_completion(action, value, error):
                continue
            match_request = self._online_match_request(action)
            if error:
                # The client can receive a terminal event while a blocking request is finishing.
                event_changed, terminal = self._online_events()
                changed = changed or event_changed
                if terminal:
                    return True
                if (self.online_match_flow and match_request
                        and self._online_phase in ("matched", "starting", "playing", "result", "result_sent")):
                    # A match event confirms the request even when its acknowledgement was lost.
                    continue
                if action.startswith("login_") and self._online_relogin_failed(error):
                    continue
                self._online_message = self._online_error(error, action == "login_saved")
                if action.startswith("login_"):
                    self._online_client = None
                    self._online_phase = "error"
                elif action.startswith("search_"):
                    if isinstance(error, SearchRefused):
                        self._online_phase, self._online_queue = "logged_in", ""
                    else:
                        # A lost acknowledgement can mean the server queued us: leave the queue, logged in.
                        self._online_request_failed(action, error)
                elif action in ("cancel", "guard", "unqueue"):
                    if action == "unqueue":
                        self._online_leaving = False
                    self._online_unqueue_failed(error)
                elif match_request and not isinstance(error, SearchRefused):
                    # A timed-out reply may still have reserved a match or room on the server.
                    self._online_request_failed(action, error)
            elif (self.online_match_flow and match_request
                  and self._online_phase in ("matched", "starting", "playing", "result", "result_sent")):
                if action == "join_room_code" or action.startswith("join_room:"):
                    room = value[0] if isinstance(value, tuple) and value else value
                    if isinstance(room, dict) and room.get("id"):
                        self._online_own_room(room)
                continue
            elif action.startswith("login_"):
                me = value["me"]
                self._online_name = str(me.get("name") or "")
                self._online_account = not bool(me.get("guest", True))
                if action == "login_register":
                    codes = getattr(self._online_client, "recovery_codes", None)
                    self._online_recovery_codes = ([code[:64] for code in codes[:32] if isinstance(code, str)]
                                                   if isinstance(codes, (list, tuple)) else [])
                    self._online_client.recovery_codes = None
                if self._online_account:
                    self.config["online_identity"] = dict(name=self._online_name)
                # The native reader may push friends before the login worker's
                # result reaches us. Its cached snapshot survives that ordering.
                self._online_friends_snapshot(getattr(self._online_client, "friend_list", None))
                self._online_fields["online_name"] = self._online_name
                self._online_name_prefill = False
                self._online_fields["online_server"] = value["server"]
                self._online_phase = "logged_in"
                self._online_message = value["warning"] or (
                    "@online.reconnected" if self._online_relogin else "@online.logged_in")
                self._online_relogin = None
                self._other_presence(True)
                other = self._other_state()
                if not value["warning"] and other and other["logs_in"] and self._online_account:
                    # The lobby moved this account's login here; the other launcher shows its kick.
                    self._online_message = "@other_launcher.logged_in_here"
            elif action.startswith("search_"):
                if self._online_phase != "searching":
                    continue
                self._online_phase, self._online_queue = "searching", value
                self._online_message = "@online.searching_ranked" if value == "ranked" else "@online.searching_casual"
                self._online_guard_at = time.monotonic() + 1
            elif action == "unqueue":
                self._online_unqueue_tries = 0
                self._online_leaving = False
            elif action == "guard" and value:
                # A game started while searching: leave the queue, stay logged in. One failed process check
                # (tasklist busy on a loaded PC) is not a reason; three in a row are.
                unknown = getattr(self, "_online_guard_unknown", 0) + 1 if value == "@online.process_unknown" else 0
                self._online_guard_unknown = unknown
                if value != "@online.process_unknown" or unknown >= 3:
                    self._online_guard_unknown = 0
                    self._online_to_lobby(value)
            elif action == "guard":
                self._online_guard_unknown = 0
            elif action in ("refresh_players", "refresh_rooms"):
                if isinstance(value, dict):
                    self._online_lobby_snapshot(value)
                self._online_message = "@online.lobby_updated"
            elif action.startswith("challenge:"):
                self._online_message = "@online.challenge_sent"
            elif action in ("accept_challenge", "decline_challenge"):
                self._online_challenge = {}
                self._online_message = "@online.challenge_answered"
            elif action in ("create_room", "create_password_room", "create_code_room", "join_room_code") or action.startswith("join_room:"):
                self._online_own_room(value)
                self._online_message = "@online.room_joined"
            elif action == "leave_room":
                self._online_room = {}
                self._online_message = "@online.room_left"
            elif action == "send_chat":
                self._online_fields["online_chat"] = ""
                self._online_message = "@online.chat_sent"
            elif action == "refresh_friends":
                self._online_friends_snapshot(value)
                self._online_message = "@online.friend_updated"
            elif action == "add_friend":
                self._online_fields["online_friend_name"] = ""
                self._online_message = "@online.friend_requested"
            elif action.startswith(("accept_friend:", "decline_friend:")):
                target = action.partition(":")[2]
                self._online_friend_incoming = [f for f in self._online_friend_incoming if f["name"] != target]
                self._online_message = "@online.friend_answered"
            elif action.startswith("remove_friend:"):
                target = action.partition(":")[2]
                self._online_friends = [f for f in self._online_friends if f["name"] != target]
                self._online_message = "@online.friend_removed"
            elif action.startswith("cancel_friend:"):
                target = action.partition(":")[2]
                self._online_friend_outgoing = [f for f in self._online_friend_outgoing if f["name"] != target]
                self._online_message = "@online.friend_cancelled"
            elif action.startswith(("invite_friend:", "invite_room:")):
                if isinstance(value, dict) and value.get("invite"):
                    self._online_outgoing_invite = dict(id=str(value["invite"])[:80],
                        name=str(value.get("name") or "")[:64], kind="room" if value.get("kind") == "room" else "casual")
                self._online_message = "@online.invite_sent"
            elif action.startswith(("accept_invite:", "decline_invite:")):
                target = action.partition(":")[2]
                self._online_invites = [inv for inv in self._online_invites if inv["id"] != target]
                self._online_message = "@online.invite_answered"
            elif action == "cancel_invite":
                self._online_outgoing_invite = {}
                self._online_message = "@online.invite_ended"
        event_changed, terminal = self._online_events()
        changed = changed or event_changed
        if terminal:
            return True
        if (self._online_phase == "searching" and not self._online_busy
                and time.monotonic() >= self._online_guard_at):
            self._online_guard_at = time.monotonic() + 1
            self._online_submit("guard", self._online_game_check)
        changed = t5_features.poll(self) or changed
        return self._online_invite_waits() or changed

    def _online_match_reset(self):
        """A match that ends before it started: forget it, keep the lobby connection (the adapters add theirs)."""

    def _online_to_lobby(self, message, decline=None, leave=None, leave_room=False):
        """Back to the lobby, still logged in: after a cancelled search, a cancelled match or a declined ready check.
        The server is asked to take this player out of the queue (it re-queues the innocent side of a cancelled
        queue match), a ready check this player declines is answered with no, and a match this player accepted
        but that has not started is left (leave = its id: the server cancels it for both). Only if leaving the
        queue fails for good is the connection closed, as it always was."""
        client = self._online_client
        if client is None:
            return
        with self._online_lock:
            self._online_generation += 1          # results of the match's own requests are no longer wanted
            self._online_match_reset()
        self._online_busy = False
        self._online_phase, self._online_queue = "logged_in", ""
        self._online_match = {}
        self._online_message = message
        self._online_leaving = True               # until the server has taken the player out of the queue
        if leave_room:
            self._online_room = {}
        requests = []
        if decline is not None:
            requests.append(lambda: client.ready(False, match_id=decline))
        if leave:
            requests.append(lambda: client.leave_match(leave))
        if leave_room:
            requests.append(client.leave_room)

        def work():
            with self._online_queue_lock:
                for request in requests:
                    try:
                        request()
                    except Exception:  # noqa: BLE001 -- the match/room may be gone already; the queue is what counts
                        pass
                for attempt in range(self.UNQUEUE_TRIES):
                    try:
                        client.cancel_queue()
                        break
                    except Exception as error:  # noqa: BLE001 -- only "too many requests" is asked again
                        # Fast search/cancel presses meet the lobby's request limit (2 a second): the search before
                        # may still hold a place in the queue, so the leave is asked again shortly (offers that
                        # arrive meanwhile are declined). Before, this left the player queued behind "Search stopped".
                        if (getattr(error, "code", "") not in ("rate_limited", "busy")
                                or attempt == self.UNQUEUE_TRIES - 1):
                            raise
                        time.sleep(self.UNQUEUE_WAIT)
            return message
        self._online_submit("unqueue", work)

    def _online_decline_late(self, client, mid):
        if not mid:
            return

        def decline():
            try:
                with self._online_queue_lock:
                    client.ready(False, match_id=mid)
            except Exception:  # noqa: BLE001 -- the offer may be gone already
                pass
        threading.Thread(target=decline, name="openrecomp-lobby", daemon=True).start()

    @staticmethod
    def _online_transport_error(error):
        """The connection broke under the request: the server took the player out of its queue and rooms itself."""
        return getattr(error, "code", "") in ("not_connected", "disconnected", "connect_failed") or (
            isinstance(error, (OSError, ConnectionError)) and not getattr(error, "code", ""))

    def _online_reconnecting(self):
        return bool(getattr(self._online_client, "_reconnecting", False))

    def _online_request_failed(self, action, error):
        """A search, challenge, room or invite request failed: the player stays logged in (closing here was a
        logout after every refused or lost request). A refusal from the server (rate limited, busy, not allowed)
        reserved nothing; a broken connection took the player out of every queue and room on the server, and the
        client resumes it by itself; only a request whose answer never came may have queued or seated the player,
        so the launcher leaves the queue (and the room it asked for) again."""
        message = self._online_error(error)
        if getattr(error, "code", "") == "timeout":
            self._online_to_lobby(message, leave_room=action in (
                "create_room", "create_password_room", "create_code_room", "join_room_code")
                or action.startswith("join_room:"))
            return
        if self._online_transport_error(error):
            message = "@online.reconnecting" if self._online_reconnecting() else "@online.unavailable"
        if self._online_phase in ("searching", "logged_in"):
            self._online_phase, self._online_queue = "logged_in", ""
        self._online_message = message

    def _online_unqueue_failed(self, error):
        """Leaving the queue failed. A broken connection already took the player out of it (the client resumes);
        a refusal means there was nothing to leave; an answer that never came is asked again, twice, before the
        connection is closed as the last safety (a launcher that says "in the lobby" must not stay queued)."""
        code = getattr(error, "code", "")
        if code in ("rate_limited", "busy") and self._online_client is not None:
            # Still refused after UNQUEUE_TRIES: the player may still be queued (the last safety, as below).
            message = self._online_error(error)
            self.online_close()
            self._online_message = message
            return
        if code == "timeout" and self._online_client is not None:
            tries = getattr(self, "_online_unqueue_tries", 0) + 1
            self._online_unqueue_tries = tries
            if tries <= 2:
                self._online_to_lobby(self._online_message)
                return
            self._online_unqueue_tries = 0
            message = self._online_error(error)
            self.online_close()
            self._online_message = message
            return
        self._online_unqueue_tries = 0
        if self._online_transport_error(error) and self._online_reconnecting():
            self._online_message = "@online.reconnecting"

    def _online_match_started(self):
        """Has the server started the current match (a game may run)? Adapters with a match flow say so."""
        return False

    def _online_resumed(self):
        """The client resumed the session after a drop. While the connection was gone the server took the player
        out of its queue and its room and cancelled a match that had not started: a search goes on (queued again);
        a ready check or a room is over; a started match goes on (the server sends its start again)."""
        phase = self._online_phase
        if phase == "searching" and self._online_queue in ("casual", "ranked"):
            with self._online_lock:
                self._online_generation += 1      # a search or guard request from before the drop is not wanted
            self._online_busy = False
            self._online_search_submit(self._online_queue)
            return
        if phase == "matched" or (phase == "starting" and not self._online_match_started()):
            self._online_to_lobby("@online.reconnected")
        if self._online_phase == "logged_in":
            self._online_room = {}

    def _online_relogin_start(self, name, account):
        """After online_close() for a connection the client could not resume: the account's remembered login, or
        the same guest name, logs in again by itself (RELOGIN_*). -> True when it will."""
        if not name or (account and self._online_saved() is None):
            return False
        now = time.monotonic()
        self._online_relogin = dict(at=now + self.RELOGIN_FIRST, until=now + self.RELOGIN_FOR, name=name,
                                    account=bool(account))
        self._online_phase, self._online_message = "connecting", "@online.reconnecting"
        return True

    def _online_relogin_tick(self):
        plan = self._online_relogin
        if not plan or self._online_client is not None or self._online_busy:
            return False
        if self._other_holds_back():
            # Another launcher is open: logging in again by itself could take the login from it (the newer login
            # wins), and it would take it back. The player logs in here by hand if this is the launcher to use.
            self._online_relogin = None
            self._online_phase, self._online_message = "offline", "@other_launcher.relogin_paused"
            return True
        now = time.monotonic()
        if now > plan["until"] or (plan["account"] and self._online_saved() is None):
            self._online_relogin = None
            self._online_phase, self._online_message = "offline", "@online.disconnected"
            return True
        if now < plan["at"]:
            return False
        plan["at"] = now + self.RELOGIN_EVERY
        if not plan["account"]:
            self._online_fields["online_name"] = plan["name"]
        self._online_login("login_saved" if plan["account"] else "login_guest")
        if self._online_phase == "connecting":
            self._online_message = "@online.reconnecting"
        return True

    RELOGIN_FINAL = ("auth_failed", "version_mismatch", "proto_mismatch", "insecure", "bad_name")

    def _online_relogin_failed(self, error):
        """A login of the automatic relogin failed. -> True when it tries again later (the lobby is still away,
        busy or full, the name not free yet); a refused login (expired saved login, old build, ban) ends it with
        its message."""
        if not self._online_relogin:
            return False
        code = getattr(error, "code", "")
        if not isinstance(code, str):
            code = ""
        message = self._online_error(error, True)
        retry = (message in ("@online.unavailable", "@online.unreachable", "@online.busy_server",
                             "@online.server_full", "@online.rate_limited", "@online.name_taken")
                 or self._online_transport_error(error) or code == "timeout")
        if code in self.RELOGIN_FINAL or not retry:
            self._online_relogin = None
            return False
        self._online_client = None
        self._online_phase, self._online_message = "connecting", "@online.reconnecting"
        return True

    def _online_saved_own(self):
        """The remembered login this launcher saved itself for the selected server; never one borrowed from the
        native launcher's file (coexistence) or from the sister game (that one is used only when chosen)."""
        saved = self._online_saved()
        if saved is None or saved.get("shared"):
            return None
        if not getattr(self.s, "coexistence", False):
            return saved
        key = (self._online_fields["online_server"].strip() or self._online_default_server()).strip().lower()
        try:
            with open(self.online_cfg_path(), encoding="utf-8") as stream:
                own = (json.load(stream).get("sessions") or {}).get(key)
        except (OSError, ValueError, AttributeError):
            return None
        return saved if isinstance(own, dict) and own.get("token") == saved.get("token") else None

    def online_shown(self):
        """The Online section is on screen: once per launcher run, log in with the remembered login by itself, as
        the T5DR launcher does when its Online tab is first shown. Only a saved session token is used, never a
        password; never again after a logout, a kick or a login by hand."""
        self._online_init()
        if getattr(self, "_online_auto_tried", False):
            return
        if self._other_holds_back():
            return                                # asked again once the player chose (or the other one closed)
        self._online_auto_tried = True
        if (self._online_client is not None or self._online_busy or self._online_phase != "offline"
                or getattr(self, "online_direct_ip", False)):
            return
        if self._online_saved_own() is None:
            return
        try:
            if not self.ready():
                return
        except Exception:  # noqa: BLE001 -- an unreadable install just shows the login rows
            return
        self.online_action("login_saved")

    def online_close(self):
        self._online_init()
        with self._online_lock:
            self._online_generation += 1
            t5_features.close(self)
            client, self._online_client = self._online_client, None
        self._other_presence(False)
        self._online_busy = False
        self._online_relogin = None
        self._online_leaving = False
        self._online_phase, self._online_queue = "offline", ""
        self._online_account = False
        self._online_recovery_codes = []
        self._online_name = ""
        self._online_match = {}
        self._online_players = []
        self._online_other_builds = 0
        self._online_me = {}
        self._online_rooms = []
        self._online_chat = []
        self._online_challenge = {}
        self._online_room = {}
        self._online_friends = []
        self._online_friend_incoming = []
        self._online_friend_outgoing = []
        self._online_invites = []
        self._online_outgoing_invite = {}
        self._online_fields["online_password"] = ""
        self._online_fields["online_chat"] = ""
        self._online_fields["online_room_password"] = ""
        self._online_fields["online_room_code"] = ""
        if client:
            threading.Thread(target=close_client, args=(client,), name="openrecomp-lobby-close", daemon=True).start()
