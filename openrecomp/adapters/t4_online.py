"""T4's process-mode match flow over the common installed lobby client."""
import os
import re
import threading
import time

from .t5_online import Online, SearchRefused, game_process_running
from ..manifest import user_dir
from ..ranks import t4_rank_name


def ticket_env(ticket):
    """Only the ticket fields documented by the T4 lobby handoff; no T5 game driver."""
    if ticket.role not in ("host", "join") or ticket.ranked:
        raise RuntimeError("@online.refused")
    peer = f"{ticket.peer[0]}:{int(ticket.peer[1])}"
    port = str(int(ticket.local_port))
    delay = ticket.input_delay if ticket.input_delay is not None else "auto"
    env = dict(TEKKEN4_NET_BUILD=str(ticket.build), TEKKEN4_NET_KEY=str(ticket.key),
               TEKKEN4_NET_SEED=str(ticket.seed), TEKKEN4_NET_DELAY=str(delay),
               TEKKEN4_NET_TIMEOUT=str(ticket.timeout))
    if ticket.role == "host":
        env.update(TEKKEN4_NET="host:" + port, TEKKEN4_NET_PEER=peer)
    else:
        env.update(TEKKEN4_NET="join:" + peer, TEKKEN4_NET_PORT=port)
    return env


class T4Online(Online):
    online_package = "t4lobby"
    online_game = "t4"
    online_port = 7791
    online_ranked = False
    online_lobby = True
    online_match_flow = True
    online_legacy_config = False

    def online_cfg_path(self):
        # Endpoints, TLS pins and session tokens remain scoped to the T4 service.
        return os.path.join(user_dir(), "online-t4.json")

    def _online_build(self, api):
        if not self.ready():
            raise RuntimeError("@online.build_required")
        exe, _why = self.core.find_runtime(self.s)
        if not exe:
            raise RuntimeError("@online.build_required")
        try:
            return api["build"].from_out_dir(os.path.dirname(exe), "dev")
        except (OSError, ValueError):
            raise RuntimeError("@online.build_required") from None

    def _online_player_rank(self, rating):
        return t4_rank_name(rating)

    def online_state(self):
        state = super().online_state()
        state["rank"] = t4_rank_name(getattr(self, "_online_rating", None)) if state["name"] else ""
        return state

    def _online_client_options(self):
        options = super()._online_client_options()
        options.update(relays=False, friends=False, private_rooms=False, tournaments=False,
                       spectate=False, sets=False, match_rules=False)
        return options

    def _online_game_check(self):
        self._online_reap_owned()
        if (getattr(self, "_online_owned_run", None) is not None
                or self.running() or self.core.run_lock_holder()):
            return "@online.game_running"
        exe, _why = self.core.find_runtime(self.s)
        if not exe:
            return "@online.build_required"
        running = game_process_running(os.path.basename(exe))
        return "@online.process_unknown" if running is None else ("@online.game_running" if running else "")

    def text_value(self, tid):
        return self.online_text_value(tid) if tid.startswith("online_") else ""

    def set_text_value(self, tid, value):
        if tid.startswith("online_"):
            self.set_online_text_value(tid, value)

    def _online_match_found(self, event):
        self._online_reap_owned()
        if (self._online_phase not in ("logged_in", "searching")
                or getattr(self, "_online_owned_run", None) is not None):
            # An unsolicited second offer must never discard an owned game or its result.
            self.online_close()
            self._online_message = "@online.cancelled"
            return True
        self._online_ticket = None
        self._online_match_id = event.get("match")
        self._online_authorized = False
        self._online_owned_run = None
        self._online_pending_start = None
        self._online_result_message = "@online.result_sent"
        opponent = event.get("opponent") or {}
        ping = event.get("ping") or {}
        self._online_match = dict(opponent=str(opponent.get("name") or ""), ping=ping.get("ms"))
        self._online_phase, self._online_queue = "matched", ""
        self._online_message = "@online.t4_matched"
        return True

    def _online_event(self, event):
        kind = event.get("t")
        if kind == "match_reveal":
            current = getattr(self, "_online_match_id", None)
            if current and event.get("match") not in (None, current):
                return True
            opponent = event.get("opponent") or {}
            self._online_match["opponent"] = str(opponent.get("name") or "")
            return True
        if kind == "match_start":
            ticket = event.get("ticket")
            if not getattr(self, "_online_authorized", False) or ticket is None:
                return True
            if self._online_phase not in ("starting", "playing"):
                return True
            if getattr(self, "_online_match_id", None) and ticket.match_id != self._online_match_id:
                return True
            if getattr(self, "_online_ticket", None) is ticket:
                return True
            previous = getattr(self, "_online_ticket", None)
            if previous is not None and not (previous.path in ("direct", "lan")
                                              and ticket.path == "relay"):
                return True
            if self._online_busy:
                self._online_pending_start = event
                return True
            self._online_ticket = ticket
            self._online_match_id = ticket.match_id
            self._online_phase, self._online_message = "starting", "@online.starting"
            client = self._online_client
            generation = self._online_generation

            def launch():
                old_run = getattr(self, "_online_owned_run", None)
                if old_run is not None:
                    self._online_stop_owned(wait=True)
                else:
                    problem = self._online_game_check()
                    if problem:
                        raise SearchRefused(problem)
                self._online_log_offsets = {}
                self._online_log_prefixes = {}
                for name in ("net.log", "rb_frames.log"):
                    path = os.path.join(self.core.SAVE_DIR, name)
                    try:
                        stat = os.stat(path)
                        self._online_log_offsets[path] = (stat.st_size, stat.st_mtime_ns)
                        with open(path, "rb") as stream:
                            self._online_log_prefixes[path] = stream.read(4096)
                    except OSError:
                        self._online_log_offsets[path] = (0, 0)
                env = ticket_env(ticket)
                with self._online_lock:
                    if generation != self._online_generation or not self._online_authorized:
                        raise RuntimeError("@online.cancelled")
                    self.start(extra_env=env)
                    self._online_owned_run = self.run
                self._online_started_at = time.monotonic()
                self._online_connected = self._online_playing = self._online_fallback = False
                self._online_started_sent = self._online_playing_sent = False
                self._online_evidence = dict(frames=0, desync=0)
                self._online_log_pending = {}
                return client
            self._online_submit("start_game", launch)
            return True
        if kind == "match_cancel":
            current = getattr(self, "_online_match_id", None)
            if current and event.get("match") not in (None, current):
                return True
            # A quick-match cancellation may requeue automatically; disconnect to stop it.
            self.online_close()
            self._online_message = "@online.cancelled"
            return True
        if kind == "match_result":
            current = getattr(self, "_online_match_id", None)
            if current and event.get("match") not in (None, current):
                return True
            if self._online_phase == "starting":
                # The lobby can void a match while the launch worker is still pending.
                self.online_close()
                self._online_message = "@online.result_void"
                return True
            if self._online_phase in ("playing", "result", "result_sent"):
                self._online_stop_owned()
                self._online_phase = "result_sent"
                status = event.get("status")
                self._online_result_message = {
                    "confirmed": "@online.result_confirmed", "disputed": "@online.result_disputed",
                    "void": "@online.result_void"}.get(status, "@online.result_sent")
                self._online_message = self._online_result_message
                me = event.get("you") or {}
                self._online_rating = me.get("rating") if isinstance(me, dict) else None
            return True
        return False

    def online_action(self, action):
        self._online_init()
        if action == "search_ranked":
            self._online_message = "@online.ranked_unavailable"
            return
        client = self._online_client
        phase = self._online_phase
        if action == "start_match" and phase == "matched" and client and not self._online_busy:
            self._online_authorized = True
            self._online_phase, self._online_message = "starting", "@online.starting"

            def ready():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                return client.ready(True)
            self._online_submit(action, ready)
        elif action == "cancel_match" and phase in ("matched", "starting") and client:
            self._online_authorized = False
            self._online_stop_owned()
            # Closing also cancels an in-flight ready request and the client's NAT/bridge.
            self.online_close()
            self._online_message = "@online.cancelled"
        elif action == "stop_match" and phase == "playing":
            self._online_stop_owned()
        elif action in ("result_win", "result_loss", "result_none") and phase == "result" and client and not self._online_busy:
            ticket = self._online_ticket
            winner = None if action == "result_none" else (ticket.slot if action == "result_win" else 1 - ticket.slot)
            evidence = dict(getattr(self, "_online_evidence", {}))
            self._online_submit(action, lambda: client.report_result(
                winner=winner, match_id=ticket.match_id, source="manual", **evidence))
        elif action == "return_lobby" and phase == "result_sent":
            self._online_ticket = None
            self._online_authorized = False
            self._online_match = {}
            self._online_phase, self._online_message = "logged_in", "@online.logged_in"
        else:
            super().online_action(action)

    def _online_completion(self, action, value, error):
        if action.startswith("login_") and not error:
            self._online_rating = value["me"].get("rating")
        if action not in ("start_match", "start_game", "game_started", "game_playing", "nat_fallback",
                          "result_win", "result_loss", "result_none"):
            return False
        if error:
            self._online_stop_owned()
            message = self._online_error(error)
            self.online_close()
            self._online_message = message
        elif action == "start_game":
            self._online_phase, self._online_message = "playing", "@online.playing"
        elif action.startswith("result_"):
            self._online_phase = "result_sent"
            self._online_message = getattr(self, "_online_result_message", "@online.result_sent")
        elif action == "nat_fallback" and not value:
            self._online_fallback = True
        return True

    def _online_stop_submit(self, work):
        worker = threading.Thread(target=work, name="openrecomp-t4-stop", daemon=False)
        worker.start()
        return worker

    def _online_reap_owned(self):
        run = getattr(self, "_online_owned_run", None)
        waiter = getattr(self, "_run_waiter", None)
        if run is not None and run.proc.poll() is not None and (waiter is None or not waiter.is_alive()):
            with self._online_lock:
                if self._online_owned_run is run:
                    self._online_owned_run = None
                    self._online_stopper = None

    def _online_stop_owned(self, wait=False):
        run = getattr(self, "_online_owned_run", None)
        if run is None:
            return
        stopping = getattr(self, "_online_stopper", None)
        if stopping is not None and stopping[0] is run:
            if wait and stopping[1] is not None:
                stopping[1].join()
            self._online_reap_owned()
            if getattr(self, "_online_owned_run", None) is None:
                return
            if stopping[1] is not None and stopping[1].is_alive():
                return
            self._online_stopper = None

        def stop():
            try:
                run.stop()
                waiter = getattr(self, "_run_waiter", None)
                if waiter:
                    waiter.join(timeout=5)
                if run.proc.poll() is not None and (waiter is None or not waiter.is_alive()):
                    with self._online_lock:
                        if self._online_owned_run is run:
                            self._online_owned_run = None
            except Exception:  # noqa: BLE001 -- closing the lobby must still close its sockets
                pass
        if wait:
            stop()
            if getattr(self, "_online_owned_run", None) is run:
                raise RuntimeError("@online.game_running")
        else:
            self._online_stopper = (run, self._online_stop_submit(stop))

    def _online_read_evidence(self):
        for path, (offset, stamp) in list(self._online_log_offsets.items()):
            try:
                stat = os.stat(path)
                # The core/runtime may truncate a log on each start.
                baseline = self._online_log_prefixes.get(path)
                with open(path, "rb") as stream:
                    prefix = stream.read(len(baseline)) if baseline is not None else None
                if (stat.st_size < offset or (stat.st_mtime_ns != stamp and stat.st_size == offset)
                        or (baseline is not None and prefix != baseline)):
                    offset = 0
                if stat.st_mtime_ns != stamp:
                    self._online_log_prefixes.pop(path, None)
                with open(path, "r", encoding="utf-8", errors="replace") as stream:
                    stream.seek(offset)
                    chunk = stream.read(256 * 1024)
                    position = stream.tell()
                self._online_log_offsets[path] = (position, stat.st_mtime_ns)
            except OSError:
                continue
            text = self._online_log_pending.get(path, "") + chunk
            lines = text.split("\n")
            self._online_log_pending[path] = lines.pop()[-4096:]
            for line in lines:
                if re.search(r"\bconnected\b", line) and "disconnected" not in line:
                    self._online_connected = True
                if "NETSUMMARY" in line:
                    self._online_playing = True
                    for key, pattern in (("frames", r"(?:frames|frame)\s*[=: ]\s*(\d+)"),
                                         ("desync", r"mismatches\s*[=: ]\s*(\d+)")):
                        found = re.search(pattern, line)
                        if found:
                            self._online_evidence[key] = max(self._online_evidence[key], int(found.group(1)))
                for reason in ("peer_timeout", "peer_quit", "no_peer", "build_mismatch"):
                    if reason in line:
                        self._online_evidence["reason"] = reason

    def online_poll(self):
        if hasattr(self, "_online_lock"):
            self._online_reap_owned()
        changed = super().online_poll()
        pending = getattr(self, "_online_pending_start", None)
        if pending is not None and not self._online_busy:
            self._online_pending_start = None
            self._online_event(pending)
            return True
        if self._online_phase != "playing" or self._online_busy:
            return changed
        run = getattr(self, "_online_owned_run", None)
        self._online_read_evidence()
        if run is None:
            self._online_phase, self._online_message = "result", "@online.result_prompt"
            return True
        if run.proc.poll() is not None:
            self._online_phase, self._online_message = "result", "@online.result_prompt"
            return True
        client, ticket = self._online_client, self._online_ticket
        if self._online_connected and not getattr(self, "_online_started_sent", False):
            self._online_started_sent = True
            self._online_submit("game_started", lambda: client.game_started(ticket.match_id))
            return True
        if self._online_playing and not getattr(self, "_online_playing_sent", False):
            self._online_playing_sent = True
            self._online_submit("game_playing", lambda: client.game_playing(ticket.match_id))
            return True
        if (not self._online_connected and not self._online_fallback and ticket.path in ("direct", "lan")
                and time.monotonic() - self._online_started_at >= 20):
            self._online_fallback = True
            self._online_submit("nat_fallback", lambda: client.nat_fallback(ticket.match_id))
            return True
        return changed

    def online_close(self):
        self._online_init()
        with self._online_lock:
            self._online_authorized = False
            self._online_pending_start = None
            self._online_stop_owned()
            super().online_close()
