"""Shared login, search and lobby calls through each game's installed lobby client."""
import csv
import importlib
from importlib.machinery import PathFinder
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid

from .base import NO_WINDOW, add_path
from . import t5_features


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


class Online:
    online_package = "t5lobby"
    online_game = ""
    online_port = 7781
    online_ranked = True
    online_lobby = False
    online_match_flow = False
    online_legacy_config = True

    def online_supported(self):
        return True

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

    def _online_default_server(self):
        return "127.0.0.1:" + str(self.online_port)

    def _online_client_options(self):
        return dict(auto_ready=False, reconnect=0, blind_ready=True, port_mapping=False)

    def _online_config(self):
        old = os.path.join(os.path.dirname(getattr(self.s, "path", "") or self.root), "online.json")
        paths = (self.online_cfg_path(), old) if self.online_legacy_config else (self.online_cfg_path(),)
        for path in paths:
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
            lobby = os.path.join(self.root, "lobby")
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

    def _online_saved(self):
        key = self._online_fields["online_server"].strip().lower() or self._online_default_server()
        sessions = self._online_config().get("sessions") or {}
        saved = sessions.get(key) if isinstance(sessions, dict) else None
        return saved if isinstance(saved, dict) and isinstance(saved.get("token"), str) and saved["token"] else None

    def online_state(self):
        self._online_init()
        capabilities = dict(ranked=self.online_ranked, lobby=self.online_lobby,
                            match_flow=self.online_match_flow)
        if self.online_package == "t5lobby":
            capabilities["registration"] = True
        if self.online_lobby and self.online_game != "t4":
            capabilities.update(private_rooms=self._online_social_cap("private_rooms"),
                                friends=self._online_social_cap("friends"))
        snapshot = dict(phase=self._online_phase, message=self._online_message,
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
        if (tid in self._online_fields and not self._online_busy
                and (self._online_client is None or tid not in (
                     "online_name", "online_password", "online_server", "online_fingerprint"))):
            self._online_fields[tid] = str(value)
            if tid == "online_name":
                self._online_name_prefill = False

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
        if not isinstance(code, str):
            code = ""
        if saved and code == "auth_failed":
            return "@online.saved_expired"
        keys = dict(auth_failed="@online.auth_failed", insecure="@online.insecure", bad_name="@online.bad_name",
                    name_taken="@online.name_taken", timeout="@online.unavailable", rate_limited="@online.rate_limited",
                    version_mismatch="@online.version_mismatch", proto_mismatch="@online.version_mismatch",
                    server_full="@online.server_full", busy="@online.busy_server",
                    room_locked="@online.room_locked", bad_password="@online.room_locked")
        local = ("@online.client_missing", "@online.build_required", "@online.no_online",
                 "@online.server_invalid", "@online.game_running", "@online.process_unknown", "@online.cancelled",
                 "@online.watch_unavailable", "@online.rules_unavailable")
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
        old = os.path.join(os.path.dirname(getattr(self.s, "path", "") or self.root), "online.json")
        paths = (path, old) if self.online_legacy_config else (path,)
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
        """Merge only non-session preferences into the native file, preserving saved logins."""
        if not isinstance(changes, dict) or any(key in changes for key in (
                "sessions", "password", "token", "session")):
            raise ValueError("@online.save_failed")
        with self._online_lock:
            path = self.online_cfg_path()
            old = os.path.join(os.path.dirname(getattr(self.s, "path", "") or self.root), "online.json")
            paths = (path, old) if self.online_legacy_config else (path,)
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
        entries, _problems = api["servers"].load(user_dir=os.path.dirname(self.online_cfg_path()))
        default = api["servers"].default_entry(entries)
        target = server or (default.name if default else self._online_default_server())
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
                    me = client.login_session(saved["token"])
                elif action == "login_register":
                    me = client.register(name, password, remember=True)
                else:
                    me = client.login(name, password, remember=True)
                if not isinstance(me, dict):
                    raise RuntimeError("@online.client_missing")
                self._online_check_request(generation, client)
                t5_features.logged_in(self, client)
                warning = ""
                with self._online_lock:
                    if generation != self._online_generation:
                        raise RuntimeError("@online.cancelled")
                    if action in ("login_account", "login_register") and client.session:
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
        if action == "logout":
            self.online_close()
            self._online_message = "@online.logged_out"
            return
        if action == "acknowledge_recovery":
            self._online_recovery_codes = []
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
            if action == "login_register" and self.online_package != "t5lobby":
                return
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
            if action == "search_ranked" and not self.online_ranked:
                self._online_message = "@online.ranked_unavailable"
                return
            if action == "search_ranked" and not self._online_account:
                self._online_message = "@online.account_required"
                return
            mode = "ranked" if action == "search_ranked" else "casual"
            char = self.chosen_fighter()
            self._online_phase, self._online_queue = "searching", mode
            self._online_message = "@online.searching_ranked" if mode == "ranked" else "@online.searching_casual"
            generation = self._online_generation

            def work():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self._online_check_request(generation, client)
                if mode == "ranked":
                    client.ranked_match(char)
                else:
                    client.quick_match(char)
                return mode
            self._online_submit(action, work)
        elif self.online_lobby and self._online_phase == "logged_in":
            if not t5_features.action(self, action, client):
                self._online_lobby_action(action, client)

    def _online_check_request(self, generation, client):
        if generation != self._online_generation or client is not self._online_client:
            raise SearchRefused("@online.cancelled")

    def _online_player_rank(self, rating):
        return ""

    def _online_player(self, player):
        if not isinstance(player, dict):
            return {}
        rating = player.get("rating")
        if isinstance(rating, bool) or not isinstance(rating, (int, float)):
            rating = None
        return dict(id=str(player.get("id") or "")[:80], name=str(player.get("name") or "")[:64],
                    rating=rating, rank=self._online_player_rank(rating))

    def _online_room_view(self, room):
        if not isinstance(room, dict):
            return {}
        owner = room.get("owner") or {}
        out = dict(id=str(room.get("id") or "")[:80], name=str(room.get("name") or "")[:64],
                    host=str(owner.get("name") or "")[:64] if isinstance(owner, dict) else "",
                    status=str(room.get("status") or "")[:20])
        if self._online_social_cap("private_rooms"):
            lock = room.get("lock") or room.get("private") or "none"
            out["lock"] = lock if lock in ("none", "password", "code") else "none"
        return out

    def _online_own_room(self, room):
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
            wait = getattr(self._online_client, "invite_wait", None)
            if callable(wait):
                retry = wait(friend["name"])
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

    def _online_invite_waits(self):
        wait = getattr(self._online_client, "invite_wait", None)
        if not callable(wait):
            return False
        changed = False
        for friend in self._online_friends:
            retry = wait(friend["name"])
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
        self._online_rooms = [self._online_room_view(r) for r in rooms
                              if isinstance(r, dict) and not (r.get("hidden") or r.get("ranked") or r.get("training"))
                              and (self._online_social_cap("private_rooms") or not (
                                  r.get("private") or r.get("lock") not in (None, "", "none", False)))][:200]

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
            wait = getattr(client, "invite_wait", None)
            retry = wait(target) if callable(wait) else friend.get("retry", 0)
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
        retained = False
        priority = ("kicked", "disconnected") if self.online_match_flow else (
            "kicked", "match_found", "disconnected")
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
                self._online_message = ("@online.kicked" if "logged in from another place" in reason
                                        else "@online.removed")
            elif kind == "match_found":
                # Closing also prevents the server requeueing this client after a ready timeout.
                self._online_phase = "matched"
                self._online_match = self._online_match_view(event)
                self._online_name, self._online_account = name, account
                self._online_message = "@online.matched"
            else:
                self._online_message = "@online.disconnected"
            return True, True
        changed = retained
        for event in events:
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
                self._online_chat.append(dict(name=str(sender.get("name") or "")[:64]
                                              if isinstance(sender, dict) else "",
                                              text=str(event.get("text") or "")[:300]))
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
                    # A lost acknowledgement may have reserved a match. Detach rather than
                    # leaving an offer or room able to start after the UI reported failure.
                    message = self._online_error(error)
                    self.online_close()
                    self._online_message = message
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
                elif match_request and not isinstance(error, SearchRefused):
                    # A timed-out reply may still have reserved a match or room on the server.
                    message = self._online_message
                    self.online_close()
                    self._online_message = message
            elif (self.online_match_flow and match_request
                  and self._online_phase in ("matched", "starting", "playing", "result", "result_sent")):
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
                self._online_message = value["warning"] or "@online.logged_in"
            elif action.startswith("search_"):
                if self._online_phase != "searching":
                    continue
                self._online_phase, self._online_queue = "searching", value
                self._online_message = "@online.searching_ranked" if value == "ranked" else "@online.searching_casual"
                self._online_guard_at = time.monotonic() + 1
            elif action == "guard" and value:
                message = value
                self.online_close()
                self._online_message = message
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

    def online_close(self):
        self._online_init()
        with self._online_lock:
            self._online_generation += 1
            t5_features.close(self)
            client, self._online_client = self._online_client, None
        self._online_busy = False
        self._online_phase, self._online_queue = "offline", ""
        self._online_account = False
        self._online_recovery_codes = []
        self._online_name = ""
        self._online_match = {}
        self._online_players = []
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
