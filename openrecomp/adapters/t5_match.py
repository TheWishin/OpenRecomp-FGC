"""Controller-facing lifecycle around the installed T5DR client's own match driver."""
import importlib
import inspect
import math
import os
import queue
import threading
import time

from .t5_online import Online, SearchRefused
from .t5_coexist import readonly_imports
from . import t5_features, t5_netext
from .. import i18n


MATCH_CANCEL_REASONS = {
    "ready_timeout": "@online.ready_expired", "relay_full": "@online.relay_full",
    "declined": "@online.peer_declined", "opponent_left": "@online.peer_quit",
    "peer_quit": "@online.peer_quit", "timeout": "@online.peer_timeout",
    "udp_unreachable": "@online.connection_failed", "no_connection": "@online.connection_failed",
}
MATCH_CANCEL_MESSAGES = frozenset(MATCH_CANCEL_REASONS.values()) | {"@online.cancelled"}


class _DriverClient:
    """Keep native game-menu actions subject to the same session reservation."""
    def __init__(self, owner, client, generation):
        object.__setattr__(self, "owner", owner)
        object.__setattr__(self, "client", client)
        object.__setattr__(self, "generation", generation)

    def __getattr__(self, name):
        return getattr(self.client, name)

    def __setattr__(self, name, value):
        setattr(self.client, name, value)

    def _request(self, name, accept, *args, **kwargs):
        owner = self.owner
        with owner._online_lock:
            owner._online_check_request(self.generation, self.client)
            if getattr(owner, "_online_leaving_set", False):
                raise SearchRefused("@online.cancelled")
            old_ready = owner._online_match.get("my_ready", False)
            old = (getattr(owner, "_online_authorized", False),
                   getattr(owner, "_online_next_authorized", False), owner._online_phase)
            if accept:
                owner._online_authorized = True
                owner._online_next_authorized = name == "rematch"
                if name == "ready":
                    owner._online_match["my_ready"] = True
                if name == "ready" and owner._online_phase == "matched":
                    owner._online_phase = "starting"
            else:
                owner._online_authorized = False
                owner._online_next_authorized = False
        try:
            return getattr(self.client, name)(*args, **kwargs)
        except Exception:
            with owner._online_lock:
                if self.generation == owner._online_generation and self.client is owner._online_client:
                    owner._online_authorized, owner._online_next_authorized, owner._online_phase = old
                    owner._online_match["my_ready"] = old_ready
            raise

    def ready(self, accept=True, *args, **kwargs):
        mid = args[0] if args else kwargs.get("match_id")
        if mid is not None and mid != getattr(self.owner, "_online_match_id", None):
            raise SearchRefused("@online.cancelled")
        return self._request("ready", accept, accept, *args, **kwargs)

    def rematch(self, match_id=None, accept=True, *args, **kwargs):
        if match_id is not None and match_id != getattr(self.owner, "_online_match_id", None):
            raise SearchRefused("@online.cancelled")
        return self._request("rematch", accept, match_id, accept, *args, **kwargs)


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

    def _online_driver_module(self):
        self._online_modules()
        with readonly_imports():
            module = importlib.import_module(self.online_package + ".match_driver")
        root = os.path.normcase(os.path.realpath(os.path.join(self.root, "lobby", self.online_package)))
        origin = os.path.normcase(os.path.realpath(getattr(module, "__file__", "")))
        try:
            local = os.path.commonpath((root, origin)) == root
        except ValueError:
            local = False
        if not local:
            raise RuntimeError("@online.client_missing")
        return module

    def _online_match_client_options(self):
        options = dict(sets=True)
        try:
            module = self._online_driver_module()
            paths = module.game_files(self._online_out_dir())
            for flag, helper in (("ingame_pick", "game_supports_pick"),
                                 ("ingame_rematch", "game_supports_ingame_ui")):
                check = getattr(module, helper, None)
                options[flag] = bool(check and check(paths))
            # 1.2.0's in-game rematch is opt-in: its own launcher announces it only with T5_INGAME_REMATCH=1
            # (tk_tab._game_has_ingame_ui), so both launchers offer the same matches on the same build.
            options["ingame_rematch"] = options["ingame_rematch"] and os.environ.get("T5_INGAME_REMATCH") == "1"
            check = getattr(module, "game_supports_auto_skip", None)
            options["auto_skip_after_round"] = bool(options["ingame_rematch"] and check and check(paths))
        except (ImportError, OSError, RuntimeError, AttributeError, ValueError):
            # Old installs keep their original game/launcher interaction.
            pass
        return options

    def _online_new_client(self, server, cfg=None):
        client, target = super()._online_new_client(server, cfg)
        # As the native Online tab: this PC's speed goes with the login (the lobby warns about a slow PC and keeps
        # one below its minimum out of ranked); the last online match's, else the newest game log's.
        if hasattr(client, "perf_fps") and not client.perf_fps:
            client.perf_fps = self._online_last_fps(self._online_config() if cfg is None else cfg)
        return client, target

    def _online_last_fps(self, cfg):
        try:
            fps = float(cfg.get("last_fps")) if isinstance(cfg, dict) and cfg.get("last_fps") else None
        except (TypeError, ValueError):
            fps = None
        if fps is not None and 0 < fps < 1000:
            return round(fps, 1)
        try:
            module = self._online_driver_module()
            fps = module.fps_from_logs(os.path.join(self._online_out_dir(), "logs"))
        except (ImportError, OSError, RuntimeError, AttributeError, ValueError, TypeError):
            return None
        return fps if type(fps) in (int, float) and 0 < fps < 1000 else None

    def _online_remember_fps(self, driver):
        fps = getattr(driver, "last_fps", None)
        if type(fps) not in (int, float) or not 0 < fps < 1000 or fps == getattr(self, "_online_saved_fps", None):
            return
        self._online_saved_fps = fps
        try:
            self._online_write_preferences(dict(last_fps=fps))
        except (OSError, ValueError, TypeError):
            pass

    def _online_make_driver(self, client, generation):
        module = self._online_driver_module()

        def launch(env):
            with self._online_lock:
                self._online_check_request(generation, client)
                if not self._online_authorized:
                    raise SearchRefused("@online.cancelled")
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                if t5_features.enabled(self):
                    env = dict(env, **t5_netext.launch_env(self))
                self.start(extra_env=env)
                return self.game

        options = dict(mode="auto", game_files=module.game_files(self._online_out_dir()), async_calls=True,
                       input_delay=self.s.get("input_delay"),
                       always_left=lambda: bool(self.s.get("always_left")))
        try:
            parameters = inspect.signature(module.MatchDriver).parameters
            if "ingame_rematch" in parameters:
                options["ingame_rematch"] = bool(getattr(client, "ingame_rematch", False))
            side = getattr(self, "screen_side", None)
            if "screen_side" in parameters and callable(side):
                # 1.2.0: dealt / left / right per match (T5_SCREEN_SIDE); always_left alone sends only 0/1.
                options["screen_side"] = side
        except (TypeError, ValueError):
            pass
        return module.MatchDriver(_DriverClient(self, client, generation), launch,
                                  os.path.join(self._online_out_dir(), "logs", "online"), **options)

    def online_state(self):
        state = super().online_state()
        state["capabilities"]["rematch"] = bool(getattr(self, "_online_rematch", False))
        info = getattr(self, "_online_set", {})
        state["set"] = dict(info, wins=list(info.get("wins", []))) if info else {}
        if isinstance(info.get("next"), dict):
            state["set"]["next"] = dict(info["next"])
        if isinstance(info.get("rating"), dict):
            state["set"]["rating"] = dict(info["rating"])
        failure = getattr(self, "_online_match_failure", {})
        if failure:
            remaining = max(0, math.ceil(failure["until"] - time.monotonic()))
            if remaining:
                state["match_failure"] = dict(message=failure["message"], remaining=remaining)
        state["character_locked"] = bool(getattr(self, "_online_character_locked", False))
        state["capabilities"]["leave_set"] = bool(
            info.get("state") == "active" and (info.get("rated") or info.get("casual"))
            and self._online_phase in ("result_sent", "starting") and info.get("next")
            and callable(getattr(self._online_client, "leave_set", None)))
        state["capabilities"]["ingame_rematch"] = bool(getattr(self, "_online_ingame_menu", False))
        return state

    def _online_unplayed(self):
        info = getattr(self, "_online_set", {})
        return not (getattr(self, "_online_set_played", False) or sum(info.get("wins", [])))

    def _online_match_failed(self, reason, message=None, **requests):
        name = self._online_match.get("opponent")
        if reason == "ready_timeout" and not self._online_match.get("my_ready"):
            name = self._online_name
        peer = i18n.literal(name) if name else "@online.opponent"
        key = {"ready_timeout": "@online.could_not_start_ready", "declined": "@online.could_not_start_declined",
               "opponent_left": "@online.could_not_start_left", "peer_quit": "@online.could_not_start_left",
               "build_mismatch": "@online.could_not_start_build", "version_mismatch": "@online.could_not_start_build"}.get(
                   reason, "@online.could_not_start_connection")
        notice = i18n.message(key[1:], name=peer)
        self._online_to_lobby(message or MATCH_CANCEL_REASONS.get(reason, "@online.connection_failed"), **requests)
        self._online_set = {}
        self._online_character_locked = False
        self._online_rematch = False
        self._online_leaving_set = False
        self._online_match_failure = dict(message=notice, until=time.monotonic() + 3)

    def _online_set_view(self, info, slot=None, ended=False):
        if not isinstance(info, dict):
            return {}
        out = {key: bool(info.get(key)) for key in ("rated", "casual", "locked")}
        out["id"] = str(info.get("id") or getattr(self, "_online_set", {}).get("id") or "")[:80]
        out["state"] = "ended" if ended or info.get("state") == "ended" else "active"
        for key in ("first_to", "best_of", "number", "games", "wins_needed"):
            if type(info.get(key)) is int and 0 <= info[key] <= 10000:
                out[key] = info[key]
        wins = info.get("wins")
        if isinstance(wins, (list, tuple)) and len(wins) == 2 and all(type(w) is int and 0 <= w <= 10000 for w in wins):
            out["wins"] = list(reversed(wins)) if slot == 1 and not ended else list(wins)
        nxt = info.get("next")
        if isinstance(nxt, dict):
            out["next"] = {key: nxt[key] for key in ("number", "in")
                           if type(nxt.get(key)) in (int, float) and 0 <= nxt[key] <= 10000}
            out["next"]["replay"] = bool(nxt.get("replay"))
        if info.get("result") in ("win", "loss"):
            out["result"] = info["result"]
        if info.get("status") in ("confirmed", "forfeit", "void", "disputed"):
            out["status"] = info["status"]
        rating = info.get("rating")
        if isinstance(rating, dict):
            after, before = rating.get("after"), rating.get("before")
            values = dict(after=after.get("r") if isinstance(after, dict) else None,
                          before=before.get("r") if isinstance(before, dict) else None,
                          delta=rating.get("delta"))
            out["rating"] = {key: value for key, value in values.items()
                             if type(value) in (int, float) and -1000000 <= value <= 1000000}
        return out

    def _online_ingame_labels(self, event):
        """Resolve catalog text only at the installed game's local menu boundary."""
        language = self.config.get("language")
        text = lambda key, **values: i18n.text(language, key, **values)
        template = lambda key: i18n.template(language, key)
        rule = event.get("rematch_ui") if isinstance(event.get("rematch_ui"), dict) else {}
        community = rule.get("kind") == "community"
        ready = event.get("t") == "match_found"
        return dict(title=text("online.start_match" if ready else "online.community" if community else "online.rematch"),
                    body=text("online.ready_hint" if ready else "online.community_hint" if community else
                              "online.rematch_auto" if rule.get("policy") == "auto_unless_declined" else "online.rematch_confirm"),
                    confirm=text("online.start_match" if ready else "online.ingame_back_in_line" if community else "online.rematch"),
                    cancel=text("online.ingame_sit_out" if community else "cancel"),
                    next="" if community else text("online.ingame_next"),
                    waiting=text("online.waiting_peer_ready"), expired=text("online.ingame_expired"),
                    auto=template("online.rematch_countdown"),
                    community_title=text("online.community"), community_waiting=text("online.community_hint"),
                    community_sitting_out=text("online.ingame_sit_out"),
                    community_next=template("online.set_next"),
                    rotation=text("online.rotation_winner" if rule.get("rotation") == "winner" else "online.rotation_queue"),
                    sit_out=text("online.ingame_sit_out"), back_to_line=text("online.ingame_back_in_line"))

    def _online_match_found(self, event):
        phase = self._online_phase
        mid = event.get("match")
        if not mid or mid == getattr(self, "_online_match_id", None):
            return True
        if getattr(self, "_online_leaving_set", False):
            return True
        no_check = event.get("ready_check") is False
        continuation = (no_check and event.get("origin") in ("rematch", "set")
                        and getattr(self, "_online_next_authorized", False))
        if phase not in ("logged_in", "searching", "result_sent") and not (phase == "starting" and continuation):
            # A duplicate offer cannot authorize another start or replace a running match.
            return True
        self._online_match_failure = {}
        previous_set = getattr(self, "_online_set", {})
        offered_set = event.get("set") or {}
        if event.get("origin") not in ("set", "rematch") or offered_set.get("id") != previous_set.get("id"):
            self._online_set_played = False
        self._online_match_id = mid
        self._online_authorized = continuation
        self._online_next_authorized = False
        self._online_ready_check = not no_check
        self._online_early_start = None
        self._online_start_seen = None
        self._online_match = dict(self._online_match_view(event), my_ready=continuation, peer_ready=False)
        self._online_set_slot = event.get("slot") if event.get("slot") in (0, 1) else 0
        info = event.get("set")
        if isinstance(info, dict):
            self._online_set = self._online_set_view(info, self._online_set_slot)
            if info.get("locked"):
                self._online_character_locked = True
        elif not getattr(self, "_online_character_locked", False):
            self._online_set = {}
        self._online_phase, self._online_queue = "starting" if continuation else "matched", ""
        self._online_message = "@online.starting" if continuation else "@online.matched"
        self._online_rematch = False
        self._online_driver_events = getattr(self, "_online_driver_events", []) + [event]
        return True

    def _online_event(self, event):
        kind = event.get("t")
        if kind == "room" and getattr(self, "_online_driver", None) is not None:
            self._online_driver_events = getattr(self, "_online_driver_events", []) + [event]
            return False
        if kind not in ("match_reveal", "match_start", "match_cancel", "match_result", "rematch",
                        "opponent_ready", "set_end", "nat", "nat_start", "nat_result", "nat_relay",
                        "nat_upgrade", "nat_status", "nat_fallback", "notice"):
            return False
        if kind == "notice" and event.get("code") not in ("nat_error", "version_mismatch"):
            return False
        current = getattr(self, "_online_match_id", None)
        if kind == "set_end":
            info = getattr(self, "_online_set", {})
            sid = event.get("set")
            if not info or (sid and info.get("id") and sid != info["id"]):
                return True
            if self._online_unplayed() and not sum(self._online_set_view(event).get("wins", [])):
                self._online_match_failed(event.get("reason"))
                return True
            self._online_character_locked = False
            self._online_set = self._online_set_view(dict(event, id=info.get("id")), ended=True)
            self._online_rematch = bool(event.get("reason") == "decided" and getattr(self, "_online_rematch", False))
            self._online_next_authorized = False
            # A casual set of one ends with the ready check its match never passed: the player keeps reading why
            # (QA: "The other player declined the match." was overwritten by "The set has ended." at once).
            if not (event.get("reason") != "decided" and not info.get("rated")
                    and self._online_message in MATCH_CANCEL_MESSAGES):
                self._online_message = {"win": "@online.set_won", "loss": "@online.set_lost"}.get(
                    event.get("result"), "@online.set_ended")
            self._online_driver_events = getattr(self, "_online_driver_events", []) + [event]
            return True
        if not current:
            return True
        if current and event.get("match") not in (None, current) and kind != "set_end":
            return True
        if kind == "notice":
            # This match cannot be played (the games cannot reach each other, or another game build): leave it and
            # stay in the lobby (closing here was a logout).
            message = "@online.game_build_mismatch" if event.get("code") == "version_mismatch" else "@online.connection_failed"
            if self._online_unplayed():
                self._online_match_failed(event.get("code"), message, leave=current)
            else:
                self._online_to_lobby(message, leave=current)
            return True
        if kind == "match_reveal":
            self._online_match.update(self._online_match_view(event))
            return True
        if kind == "match_cancel":
            # Back to the lobby, still logged in (closing here logged the player out after every declined or
            # timed-out ready check).
            if self._online_unplayed():
                self._online_match_failed(event.get("reason"), MATCH_CANCEL_REASONS.get(event.get("reason"), "@online.cancelled"))
            else:
                self._online_to_lobby(MATCH_CANCEL_REASONS.get(event.get("reason"), "@online.cancelled"))
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
            if ticket is not None and getattr(ticket, "match_id", current) != current:
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
            score = event.get("score")
            scored = (isinstance(score, (list, tuple)) and len(score) == 2
                      and all(type(n) is int and 0 <= n <= 10000 for n in score) and any(score))
            next_info = self._online_set_view(event.get("set"))
            if (self._online_unplayed() and not scored and not sum(next_info.get("wins", []))
                    and event.get("status") not in ("confirmed", "disputed")):
                self._online_match_failed(event.get("reason"))
                return True
            self._online_set_played = True
            self._online_phase = "result_sent"
            self._online_rematch = bool(event.get("rematch_window"))
            next_set = event.get("set")
            next_set = next_set if isinstance(next_set, dict) else {}
            if next_set:
                self._online_set = self._online_set_view(next_set, getattr(self, "_online_set_slot", 0))
            self._online_next_authorized = bool(
                getattr(self, "_online_authorized", False)
                and not getattr(self, "_online_leaving_set", False)
                and (next_set.get("rated") or next_set.get("casual")) and next_set.get("next"))
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
        elif kind == "opponent_ready":
            self._online_match["peer_ready"] = True
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
        if action == "leave_set" and not self._online_busy and self.online_state()["capabilities"]["leave_set"]:
            generation = self._online_generation
            self._online_authorized = False
            self._online_next_authorized = False
            self._online_leaving_set = True
            self._online_rematch = False
            def leave_set():
                self._online_check_request(generation, client)
                return client.leave_set()
            self._online_submit("t5_leave_set", leave_set)
        elif action == "start_match" and phase == "matched" and client and not self._online_busy:
            self._online_authorized = True
            self._online_match["my_ready"] = True
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
        elif action == "cancel_match" and phase == "matched" and self._online_client is not None:
            # Declined at the ready check: say no and stay in the lobby.
            self._online_to_lobby("@online.cancelled", decline=getattr(self, "_online_match_id", None) or "")
        elif action == "cancel_match" and phase == "starting" and self._online_client is not None:
            # Cancelled after Start, before the game: leave the match (the server cancels it for both players; in a
            # running set it starts that game again later) and stay in the lobby. The match reset stops a game the
            # driver may already have started.
            self._online_to_lobby("@online.cancelled", leave=getattr(self, "_online_match_id", None) or None)
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
                set_over = (getattr(self, "_online_set", None) or {}).get("state") == "ended"

                def leave():
                    # A previously sent offer cannot be undone by a second driver.rematch call.
                    # The installed client's explicit leave ends its rematch window as well.
                    # Only a running set can be left: after a decided set (every 1.2.0 casual game is an
                    # FT1 set) or a match without one the server answers bad_state, which must not
                    # log this player out of the lobby.
                    if not set_over:
                        try:
                            client.leave_set()
                        except Exception as exc:  # noqa: BLE001 -- only "not in a set" is expected here
                            if getattr(exc, "code", None) != "bad_state":
                                raise
                    driver.rematch(mid, False)
                self._online_submit("t5_return", lambda: self._online_driver_call(driver, leave))
            else:
                self._online_phase, self._online_message = "logged_in", "@online.logged_in"
        else:
            super().online_action(action)

    def _online_match_started(self):
        return getattr(self, "_online_start_seen", None) is not None

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
            # The match could not go on (the game did not start, a request was refused or lost): back to the lobby,
            # logged in. A match that has not started is left; the match reset stops the driver and its game.
            message = self._online_error(error)
            if action in ("t5_answer", "t5_rematch", "t5_return", "t5_leave_set") and self._online_client is not None:
                # After a game (result, rematch, leaving the set): the request can be made again from the same
                # screen. The set the server still runs stays as it is.
                self._online_leaving_set = False
                self._online_message = message
                return True
            mid = getattr(self, "_online_match_id", None)
            pending = self._online_phase in ("matched", "starting") and not self._online_match_started()
            requests = dict(decline=mid if self._online_phase == "matched" and mid else None,
                            leave=mid if pending and self._online_phase == "starting" else None)
            if self._online_unplayed() and mid:
                self._online_match_failed("no_peer", message, **requests)
            else:
                self._online_to_lobby(message, **requests)
            return True
        if action == "t5_driver":
            driver, notes = value
            self._online_driver = driver
            self._online_driver_notes(notes)
            self._online_remember_fps(driver)
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
        elif action == "t5_leave_set":
            self._online_character_locked = False
            # Retain its identity until the server's set_end reaches the driver.
            # The native driver then releases the persistent game connection.
            self._online_set = dict(getattr(self, "_online_set", {}), state="ended", locked=False)
            self._online_set.pop("next", None)
            self._online_match = {}
            self._online_match_id = None
            self._online_leaving_set = False
            self._online_phase, self._online_message = "logged_in", "@online.set_left"
        return True

    def _online_driver_notes(self, notes):
        for note in notes:
            kind = note.get("kind")
            if (kind in ("ask_result", "rematch_offer", "set_next")
                    and note.get("match") not in (None, getattr(self, "_online_match_id", None))):
                continue
            if not getattr(self, "_online_match_id", None) and kind in ("ask_result", "rematch_offer", "set_next", "game_state"):
                continue
            if kind == "ask_result":
                if self._online_unplayed():
                    self._online_match_failed("no_peer", "@online.game_closed",
                                              leave=getattr(self, "_online_match_id", None))
                    continue
                self._online_phase, self._online_message = "result", "@online.result_prompt"
            elif kind == "rematch_offer":
                self._online_rematch = True
                self._online_phase, self._online_message = "result_sent", "@online.rematch_offer"
            elif kind == "set_next":
                if not getattr(self, "_online_authorized", False) or getattr(self, "_online_leaving_set", False):
                    continue
                self._online_next_authorized = True
                self._online_phase, self._online_message = "starting", "@online.waiting_peer_ready"
            elif kind == "firewall_suspect":
                self._online_message = "@online.connection_fallback" if note.get("fallback") else "@online.connection_failed"
            elif kind == "game_closed":
                self._online_message = "@online.game_closed"
            elif kind == "game_state":
                if self._online_phase in ("result", "result_sent"):
                    # A persistent game goes back to its select screen right after the fight: the result
                    # (confirmed, set won/lost, rematch offer) stays the message until the next game starts.
                    continue
                state = note.get("state")
                if state == "fight":
                    self._online_set_played = True
                self._online_message = ("@online.playing" if state == "fight" else "@online.loading"
                                        if state in ("loading", "stage") else "@online.select")
            elif kind in ("ingame_ui_ready", "ingame_ui_fallback"):
                self._online_ingame_menu = kind == "ingame_ui_ready"
            # Native status strings can contain server text: only catalog messages reach the view.

    def online_poll(self):
        failure = getattr(self, "_online_match_failure", {})
        expired = bool(failure and time.monotonic() >= failure["until"])
        if expired:
            self._online_match_failure = {}
            if self._online_phase == "logged_in":
                self._online_message = "@online.room_joined" if self._online_room else "@online.logged_in"
        if not hasattr(self, "_online_driver_results"):
            self._online_driver_results = queue.Queue()
        changed = super().online_poll() or expired
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
                    with self._online_lock:
                        self._online_check_request(generation, client)
                        # Cancellation must own a new driver even before its worker result
                        # reaches the UI thread, including any game it has started.
                        self._online_driver = current
                    for event in events:
                        self._online_check_request(generation, client)
                        offer = getattr(current, "offer_ingame_ui", None)
                        if callable(offer):
                            if event.get("t") in ("match_found", "match_result"):
                                offer(event, self._online_ingame_labels(event))
                            else:
                                offer(event)
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

    def _online_match_reset(self):
        if self._online_unplayed():
            self._online_set = {}
            self._online_character_locked = False
            self._online_rematch = False
        self._online_authorized = False
        self._online_next_authorized = False
        self._online_early_start = None
        self._online_match_id = None
        self._online_driver_events = []
        driver = getattr(self, "_online_driver", None)
        self._online_driver = None
        self._online_driver_busy = False
        if driver is not None:
            def close():
                with self._online_driver_lock:
                    driver.close()
            threading.Thread(target=close, name="openrecomp-t5-match-close", daemon=False).start()

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
            self._online_set = {}
            self._online_set_played = False
            self._online_match_failure = {}
            self._online_character_locked = False
            self._online_leaving_set = False
            self._online_ingame_menu = False
            super().online_close()
        if driver is not None:
            def close():
                with self._online_driver_lock:
                    driver.close()
            threading.Thread(target=close, name="openrecomp-t5-match-close", daemon=False).start()
