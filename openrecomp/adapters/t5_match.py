"""Controller-facing lifecycle around the installed T5DR client's own match driver."""
import importlib
import os
import queue
import threading

from .t5_online import Online, SearchRefused


class T5Match(Online):
    online_lobby = True
    online_match_flow = True

    def _online_game_check(self):
        driver = getattr(self, "_online_driver", None)
        if (driver is not None and getattr(driver, "game", None) is getattr(self, "game", None)
                and getattr(self, "game", None) is not None and self.running()):
            # The native driver reuses its owned session for rematches and new opponents.
            return ""
        return super()._online_game_check()

    def _online_make_driver(self, client, generation):
        self._online_modules()
        module = importlib.import_module(self.online_package + ".match_driver")
        root = os.path.normcase(os.path.realpath(os.path.join(self.root, "lobby", self.online_package)))
        origin = os.path.normcase(os.path.realpath(getattr(module, "__file__", "")))
        try:
            local = os.path.commonpath((root, origin)) == root
        except ValueError:
            local = False
        if not local:
            raise RuntimeError("@online.client_missing")

        def launch(env):
            with self._online_lock:
                self._online_check_request(generation, client)
                if not self._online_authorized:
                    raise SearchRefused("@online.cancelled")
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self.start(extra_env=env)
                return self.game

        return module.MatchDriver(
            client, launch, os.path.join(self._online_out_dir(), "logs", "online"),
            mode="auto", game_files=module.game_files(self._online_out_dir()), async_calls=True,
            input_delay=self.s.get("input_delay"),
            always_left=lambda: bool(self.s.get("always_left")))

    def online_state(self):
        state = super().online_state()
        state["capabilities"]["rematch"] = bool(getattr(self, "_online_rematch", False))
        return state

    def _online_match_found(self, event):
        phase = self._online_phase
        mid = event.get("match")
        if not mid or mid == getattr(self, "_online_match_id", None):
            return True
        no_check = event.get("ready_check") is False
        continuation = (no_check and event.get("origin") in ("rematch", "set")
                        and getattr(self, "_online_next_authorized", False))
        if phase not in ("logged_in", "searching", "result_sent") and not (phase == "starting" and continuation):
            # A duplicate offer cannot authorize another start or replace a running match.
            return True
        self._online_match_id = mid
        self._online_authorized = continuation
        self._online_next_authorized = False
        self._online_ready_check = not no_check
        self._online_early_start = None
        self._online_start_seen = None
        self._online_match = self._online_match_view(event)
        self._online_phase, self._online_queue = "starting" if continuation else "matched", ""
        self._online_message = "@online.starting" if continuation else "@online.matched"
        self._online_rematch = False
        self._online_driver_events = getattr(self, "_online_driver_events", []) + [event]
        return True

    def _online_event(self, event):
        kind = event.get("t")
        if kind not in ("match_reveal", "match_start", "match_cancel", "match_result", "rematch",
                        "opponent_ready", "set_end", "nat", "nat_start", "nat_result", "nat_relay",
                        "nat_upgrade", "nat_status", "nat_fallback", "notice"):
            return False
        if kind == "notice" and event.get("code") not in ("nat_error", "version_mismatch"):
            return False
        current = getattr(self, "_online_match_id", None)
        if not current:
            return True
        if current and event.get("match") not in (None, current) and kind != "set_end":
            return True
        if kind == "notice":
            self.online_close()
            self._online_message = ("@online.game_build_mismatch" if event.get("code") == "version_mismatch"
                                    else "@online.connection_failed")
            return True
        if kind == "match_reveal":
            self._online_match.update(self._online_match_view(event))
            return True
        if kind == "match_cancel":
            self.online_close()
            self._online_message = {
                "ready_timeout": "@online.ready_expired", "relay_full": "@online.relay_full",
                "declined": "@online.peer_declined", "opponent_left": "@online.peer_quit",
                "peer_quit": "@online.peer_quit", "timeout": "@online.peer_timeout",
                "udp_unreachable": "@online.connection_failed", "no_connection": "@online.connection_failed",
            }.get(event.get("reason"), "@online.cancelled")
            return True
        if kind == "match_start":
            ticket = event.get("ticket")
            continued = bool(event.get("continue"))
            if not getattr(self, "_online_authorized", False):
                if self._online_phase == "matched" and not getattr(self, "_online_ready_check", True):
                    self._online_early_start = event
                return True
            if self._online_phase not in ("starting", "playing"):
                return True
            if ticket is None and not continued:
                return True
            mid = event.get("match") or getattr(ticket, "match_id", None)
            if mid != current:
                return True
            event = dict(event, match=mid)
            identity = (mid, id(ticket) if ticket is not None else "continue")
            previous = getattr(self, "_online_start_seen", None)
            if previous == identity:
                return True
            if previous is not None and previous[0] == identity[0]:
                # Only the client's explicit direct-to-relay fallback can replace a start.
                if getattr(ticket, "path", None) != "relay" or getattr(self, "_online_started_path", None) not in ("direct", "lan"):
                    return True
            self._online_start_seen = identity
            self._online_started_path = getattr(ticket, "path", None)
            self._online_phase = "starting"
            self._online_message = "@online.connection_relay" if self._online_started_path == "relay" else "@online.starting"
        elif kind == "match_result":
            self._online_phase = "result_sent"
            self._online_rematch = bool(event.get("rematch_window"))
            next_set = event.get("set") or {}
            self._online_next_authorized = bool(next_set.get("rated") and next_set.get("next"))
            self._online_message = {
                "peer_quit": "@online.peer_quit", "peer_timeout": "@online.peer_timeout",
                "peer_lost": "@online.peer_timeout", "no_peer": "@online.connection_failed",
                "build_mismatch": "@online.game_build_mismatch"}.get(event.get("reason"), {
                    "confirmed": "@online.result_confirmed", "disputed": "@online.result_disputed",
                    "void": "@online.result_void"}.get(event.get("status"), "@online.result_sent"))
        elif kind == "rematch":
            state = event.get("state")
            if state == "offered":
                self._online_rematch = True
                self._online_phase, self._online_message = "result_sent", "@online.rematch_offer"
            elif state in ("declined", "expired"):
                self._online_rematch = False
                self._online_next_authorized = False
                self._online_message = "@online.rematch_declined"
        elif kind == "set_end":
            self._online_rematch = False
            self._online_next_authorized = False
        elif kind == "opponent_ready":
            self._online_message = "@online.waiting_peer_ready"
        elif kind.startswith("nat"):
            path = event.get("path")
            self._online_message = ("@online.connection_relay" if kind == "nat_relay" or path == "relay" or event.get("phase") == "relay"
                                    else "@online.connection_direct" if path in ("direct", "lan")
                                    else "@online.connection_failed" if event.get("udp_blocked") or (kind == "nat_fallback" and event.get("ok") is False)
                                    else "@online.connection_fallback" if event.get("fallback") or kind == "nat_fallback"
                                    else "@online.starting")
        self._online_driver_events = getattr(self, "_online_driver_events", []) + [event]
        return True

    def online_action(self, action):
        self._online_init()
        client, phase = self._online_client, self._online_phase
        if action == "start_match" and phase == "matched" and client and not self._online_busy:
            self._online_authorized = True
            self._online_phase, self._online_message = "starting", "@online.waiting_peer_ready"
            generation = self._online_generation
            ready_check = getattr(self, "_online_ready_check", True)

            def ready():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self._online_check_request(generation, client)
                return client.ready(True) if ready_check else None
            self._online_submit("t5_ready", ready)
            early = getattr(self, "_online_early_start", None)
            if early is not None:
                self._online_early_start = None
                self._online_event(early)
        elif action == "cancel_match" and phase in ("matched", "starting"):
            self.online_close()
            self._online_message = "@online.cancelled"
        elif action == "stop_match" and phase == "playing":
            self.online_close()
            self._online_message = "@online.game_closed"
        elif action in ("result_win", "result_loss", "result_none") and phase == "result" and not self._online_busy:
            driver = getattr(self, "_online_driver", None)
            if driver:
                answer = {"result_win": "won", "result_loss": "lost", "result_none": "draw"}[action]
                self._online_submit("t5_answer", lambda: self._online_driver_call(driver, lambda: driver.answer(answer)))
        elif action == "rematch" and phase == "result_sent" and getattr(self, "_online_rematch", False) and not self._online_busy:
            driver = getattr(self, "_online_driver", None)
            if driver:
                mid = self._online_match_id
                self._online_authorized = True
                self._online_next_authorized = True
                self._online_rematch = False
                self._online_message = "@online.rematch_wait"
                self._online_submit("t5_rematch", lambda: self._online_driver_call(driver, lambda: driver.rematch(mid, True)))
        elif action == "return_lobby" and phase == "result_sent" and not self._online_busy:
            driver = getattr(self, "_online_driver", None)
            self._online_authorized = False
            self._online_next_authorized = False
            self._online_rematch = False
            if driver:
                mid = self._online_match_id
                def leave():
                    # A previously sent offer cannot be undone by a second driver.rematch call.
                    # The installed client's explicit leave ends its rematch window as well.
                    client.leave_set()
                    driver.rematch(mid, False)
                self._online_submit("t5_return", lambda: self._online_driver_call(driver, leave))
            else:
                self._online_phase, self._online_message = "logged_in", "@online.logged_in"
        else:
            super().online_action(action)

    def _online_driver_call(self, driver, work):
        with self._online_driver_lock:
            if driver is not getattr(self, "_online_driver", None) or self._online_client is None:
                raise SearchRefused("@online.cancelled")
            work()
            return driver.poll()

    def _online_completion(self, action, value, error):
        if not action.startswith("t5_"):
            return super()._online_completion(action, value, error)
        if error:
            message = self._online_error(error)
            self.online_close()
            self._online_message = message
            return True
        if action == "t5_driver":
            driver, notes = value
            self._online_driver = driver
            self._online_driver_notes(notes)
            if (self._online_phase == "starting" and getattr(driver, "ticket", None) is not None
                    and getattr(driver.ticket, "match_id", None) == getattr(self, "_online_match_id", None)
                    and driver.game_running()):
                self._online_phase = "playing"
                self._online_message = "@online.playing"
        elif action in ("t5_answer", "t5_rematch", "t5_return"):
            self._online_driver_notes(value or [])
            if action == "t5_answer":
                self._online_phase, self._online_message = "result_sent", "@online.result_sent"
            elif action == "t5_return":
                self._online_match = {}
                self._online_match_id = None
                self._online_phase, self._online_message = "logged_in", "@online.logged_in"
        return True

    def _online_driver_notes(self, notes):
        for note in notes:
            kind = note.get("kind")
            if (kind in ("ask_result", "rematch_offer", "set_next")
                    and note.get("match") not in (None, getattr(self, "_online_match_id", None))):
                continue
            if kind == "ask_result":
                self._online_phase, self._online_message = "result", "@online.result_prompt"
            elif kind == "rematch_offer":
                self._online_rematch = True
                self._online_phase, self._online_message = "result_sent", "@online.rematch_offer"
            elif kind == "set_next":
                self._online_authorized = True
                self._online_next_authorized = True
                self._online_phase, self._online_message = "starting", "@online.waiting_peer_ready"
            elif kind == "firewall_suspect":
                self._online_message = "@online.connection_fallback" if note.get("fallback") else "@online.connection_failed"
            elif kind == "game_closed":
                self._online_message = "@online.game_closed"
            elif kind == "game_state":
                state = note.get("state")
                self._online_message = ("@online.playing" if state == "fight" else "@online.loading"
                                        if state in ("loading", "stage") else "@online.select")
            # Native status strings can contain server text: only catalog messages reach the view.

    def online_poll(self):
        if not hasattr(self, "_online_driver_results"):
            self._online_driver_results = queue.Queue()
        changed = super().online_poll()
        while True:
            try:
                generation, value, error = self._online_driver_results.get_nowait()
            except queue.Empty:
                break
            if generation != self._online_generation:
                continue
            self._online_driver_busy = False
            self._online_completion("t5_driver", value, error)
            changed = True
        if self._online_client is None or self._online_busy or getattr(self, "_online_driver_busy", False):
            return changed
        events = getattr(self, "_online_driver_events", [])
        driver = getattr(self, "_online_driver", None)
        if not events and driver is None:
            return changed
        self._online_driver_events = []
        if not hasattr(self, "_online_driver_lock"):
            self._online_driver_lock = threading.Lock()
        client, generation = self._online_client, self._online_generation

        def advance():
            with self._online_driver_lock:
                self._online_check_request(generation, client)
                current = driver or self._online_make_driver(client, generation)
                try:
                    for event in events:
                        self._online_check_request(generation, client)
                        current.on_event(event)
                    notes = current.poll()
                    self._online_check_request(generation, client)
                    return current, notes
                except Exception:
                    current.close()
                    raise
        self._online_driver_submit(advance)
        return True

    def _online_driver_submit(self, work):
        generation = self._online_generation
        self._online_driver_busy = True

        def run():
            try:
                value, error = work(), None
            except Exception as exc:  # noqa: BLE001 -- runtime failure becomes a catalog message
                value, error = None, exc
            self._online_driver_results.put((generation, value, error))
        threading.Thread(target=run, name="openrecomp-t5-match", daemon=True).start()

    def online_close(self):
        self._online_init()
        with self._online_lock:
            self._online_authorized = False
            self._online_next_authorized = False
            self._online_early_start = None
            self._online_match_id = None
            self._online_driver_events = []
            self._online_driver_busy = False
            driver = getattr(self, "_online_driver", None)
            self._online_driver = None
            self._online_rematch = False
            super().online_close()
        if driver is not None:
            def close():
                with self._online_driver_lock:
                    driver.close()
            threading.Thread(target=close, name="openrecomp-t5-match-close", daemon=False).start()
