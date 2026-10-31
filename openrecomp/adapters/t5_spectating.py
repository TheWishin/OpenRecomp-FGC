"""Live watching through the selected install's spectator client and policy."""
import importlib
import inspect
import json
import math
import os
import threading
import time
from types import SimpleNamespace

from .t5_coexist import readonly_imports


def init(owner):
    if hasattr(owner, "_spec_epoch"):
        return
    owner._spec_epoch = 0
    owner._spec_pending = None
    owner._spec_view = None
    owner._spec_count = 0
    owner._spec_policy = None
    owner._spec_auto_unavailable = False
    owner._spec_prefs = None


def _module(owner, name):
    owner._online_modules()
    with readonly_imports():
        module = importlib.import_module(owner.online_package + "." + name)
    root = os.path.normcase(os.path.realpath(os.path.join(owner.root, "lobby", owner.online_package)))
    origin = os.path.normcase(os.path.realpath(getattr(module, "__file__", "")))
    if os.path.commonpath((root, origin)) != root:
        raise RuntimeError("@online.client_missing")
    return module


def client_options(owner):
    return dict(spectate=True, watch_dir=os.path.join(owner._online_out_dir(), "logs", "online"))


def client_created(owner, client):
    init(owner)
    setter = getattr(client, "set_spectate_prefs", None)
    if callable(setter):
        prefs = (bool(owner.s.get("spectators", True)), bool(owner.s.get("spectators_ranked", False)))
        setter(*prefs)
        owner._spec_prefs = prefs


def _supported(client):
    has = getattr(client, "has_spectate", None)
    try:
        return bool(callable(has) and has() and callable(getattr(client, "watch", None)))
    except Exception:
        return False


def _targets(owner):
    client = owner._online_client
    if not _supported(client):
        return []
    out = []
    friends = getattr(client, "friend_list", None)
    friends = friends.get("friends") if isinstance(friends, dict) else None
    for friend in friends if isinstance(friends, list) else ():
        if isinstance(friend, dict) and friend.get("watch") and isinstance(friend.get("name"), str):
            name = friend["name"][:64]
            out.append(dict(id="spec_watch_friend:" + name, kind="friend", name=name,
                            target=dict(name=name)))
    rooms = getattr(client, "rooms", None)
    rooms = [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []
    mine = getattr(client, "my_room", None)
    if isinstance(mine, dict) and mine and not any(r.get("id") == mine.get("id") for r in rooms):
        rooms.append(mine)
    for room in rooms:
        rid = str(room.get("id") or "")[:80]
        if not rid:
            continue
        name = str(room.get("name") or rid)[:80]
        if room.get("mode") == "tables":
            tables = room.get("tables")
            for table in tables if isinstance(tables, list) else ():
                if not isinstance(table, dict):
                    continue
                tid = table.get("id")
                if table.get("watch") and isinstance(tid, (str, int)):
                    out.append(dict(id="spec_watch_table:" + rid + ":" + str(tid), kind="table",
                                    name=name + " · " + str(tid), target=dict(room=rid, table=tid)))
        elif room.get("watch"):
            out.append(dict(id="spec_watch_room:" + rid, kind="room", name=name, target=dict(room=rid)))
    return out


def state(owner):
    init(owner)
    view = owner._spec_view or {}
    snapshot = {key: view[key] for key in ("state", "ranked", "end", "delay") if key in view}
    snapshot.update(pending=owner._spec_pending is not None, active=bool(view), count=owner._spec_count,
                    players=[dict(name=str(p.get("name") or "")[:64]) for p in (view.get("players") or ())[:2]
                             if isinstance(p, dict)],
                    targets=[{k: v for k, v in row.items() if k != "target"} for row in _targets(owner)])
    return dict(capabilities=dict(spectating=_supported(owner._online_client)), spectating=snapshot)


def _busy(owner):
    client = owner._online_client
    return (owner._online_phase != "logged_in" or bool(getattr(owner, "_online_match", None))
            or bool(getattr(owner, "_online_challenge", None)) or bool(getattr(owner, "_online_invites", None))
            or bool(getattr(owner, "_online_outgoing_invite", None))
            or bool((getattr(owner, "_online_tours", None) or {}).get("call"))
            or bool(getattr(owner, "_online_character_locked", False))
            or getattr(getattr(owner, "_online_driver", None), "ticket", None) is not None
            or bool(getattr(client, "match", None)))


def _cancel(client):
    if client is None:
        return
    cancel = getattr(client, "cancel_watch", None)
    if callable(cancel):
        cancel()
    else:
        unwatch = getattr(client, "unwatch", None)
        if callable(unwatch):
            def stop():
                try:
                    unwatch()
                except Exception:
                    pass
            threading.Thread(target=stop, name="openrecomp-unwatch", daemon=True).start()


def _stop_game(owner, view):
    game = (view or {}).get("game")
    driver = getattr(owner, "_online_driver", None)
    if game is not None and game is not getattr(driver, "game", None) and game.running():
        game.stop()


def _preempt(owner, reason):
    init(owner)
    with owner._online_lock:
        owner._spec_epoch += 1
        pending, view = owner._spec_pending, owner._spec_view
        owner._spec_pending = None
        if pending or view:
            _cancel(owner._online_client)
            _stop_game(owner, view)
        if view:
            view.update(state="over", end=reason)
        if owner._spec_policy is not None:
            owner._spec_policy.pause()


def _request(owner, client, target, automatic=False):
    if owner._spec_pending is not None or owner._spec_view is not None or _busy(owner) or owner._online_busy:
        return
    problem = owner._online_game_check()
    if problem:
        owner._online_message = problem
        return
    owner._spec_epoch += 1
    epoch, generation = owner._spec_epoch, owner._online_generation
    owner._spec_pending = (epoch, client, automatic)
    native_generation = getattr(client, "spec_generation", None)

    def work():
        owner._online_check_request(generation, client)
        if owner._spec_pending != (epoch, client, automatic):
            return None
        if _busy(owner):
            raise RuntimeError("@online.cancelled")
        problem = owner._online_game_check()
        if problem:
            raise RuntimeError(problem)
        owner._online_check_request(generation, client)
        if owner._spec_pending != (epoch, client, automatic) or _busy(owner):
            return None
        kwargs = dict(target)
        # The older client has no table argument or generation barrier.
        params = inspect.signature(client.watch).parameters
        if "table" in kwargs and "table" not in params:
            raise RuntimeError("@online.watch_unavailable")
        if "generation" in params:
            kwargs["generation"] = native_generation
        return epoch, client.watch(**kwargs)
    owner._online_submit("feature_spectate:watch", work)


def action(owner, action, client):
    init(owner)
    if action == "spec_stop":
        _preempt(owner, "left")
        owner._spec_view = None
        owner._online_message = "@online.watch_stopped"
        return True
    if not action.startswith("spec_watch_"):
        return False
    if not _supported(client):
        owner._online_message = "@online.watch_unavailable"
        return True
    target = next((row["target"] for row in _targets(owner) if row["id"] == action), None)
    if action.startswith("spec_watch_tour:"):
        from . import t5_tournaments
        parts = action.split(":", 2)
        detail = (t5_tournaments.state(owner).get("tournaments") or {}).get("detail") or {}
        selected = (t5_tournaments.state(owner).get("tournaments") or {}).get("selected")
        if len(parts) == 3 and str(selected) == parts[1]:
            sets = (detail.get("bracket") or {}).get("sets") or ()
            if any(str(s.get("id")) == parts[2] and s.get("watch") and s.get("live") == "playing"
                   and getattr(owner, "_online_name", "") not in (s.get("p") or ()) for s in sets):
                target = dict(tournament=parts[1], set_id=parts[2])
    if target is None:
        owner._online_message = "@online.watch_unavailable"
    else:
        _request(owner, client, target)
    return True


def _start(owner):
    view = owner._spec_view
    client = owner._online_client
    if not view or view.get("game") is not None or view.get("state") != "waiting":
        return
    current = getattr(client, "spec_watch", None) or {}
    path = current.get("path")
    if current.get("stream") != view.get("stream") or not path:
        return
    epoch, generation = owner._spec_epoch, owner._online_generation
    view["state"] = "starting"

    def work():
        with owner._online_lock:
            owner._online_check_request(generation, client)
            current = getattr(client, "spec_watch", None) or {}
            if (epoch != owner._spec_epoch or owner._spec_view is not view or _busy(owner)
                    or view.get("state") != "starting" or current.get("stream") != view.get("stream")):
                return None
            problem = owner._online_game_check()
            if problem:
                raise RuntimeError(problem)
            folder = os.path.join(owner._online_out_dir(), "logs", "online")
            os.makedirs(folder, exist_ok=True)
            result = os.path.join(folder, "watch-verdict.json")
            status = os.path.join(folder, "watch-status.json")
            for previous in (result, status):
                try:
                    os.remove(previous)
                except FileNotFoundError:
                    pass
            env = _module(owner, "spectate").watch_env(path, result, status)
            owner.start(extra_env=env)
            view.update(game=owner.game, result=result, status=status)
            return epoch
    owner._online_submit("feature_spectate:start", work)


def completion(owner, operation, value, error):
    if not operation.startswith("feature_spectate:"):
        return False
    init(owner)
    if error:
        _preempt(owner, "stopped")
        owner._online_message = owner._online_error(error)
        return True
    if operation == "feature_spectate:watch":
        pending = owner._spec_pending
        if not pending or not value or value[0] != pending[0]:
            return True
        owner._spec_pending = None
        epoch, reply = value
        client = pending[1]
        if (not isinstance(reply, dict) or client is not owner._online_client or _busy(owner)
                or (pending[2] and not owner.s.get("auto_spectate", False))):
            _cancel(client)
            return True
        current = getattr(client, "spec_watch", None) or {}
        if current.get("stream") != reply.get("stream"):
            _cancel(client)
            return True
        owner._spec_view = dict(stream=reply.get("stream"), state="waiting", players=reply.get("players") or [],
                                ranked=bool(reply.get("ranked")), end="", delay=None, game=None,
                                automatic=pending[2], client=client)
        _start(owner)
    return True


def event(owner, ev):
    init(owner)
    kind = ev.get("t")
    if kind in ("match_found", "match_reveal", "match_start", "challenged", "invited", "tour_call",
                "disconnected", "reconnecting", "kicked"):
        _preempt(owner, "your_match" if kind not in ("disconnected", "reconnecting", "kicked") else "stopped")
    if kind == "spectators":
        count = ev.get("count")
        owner._spec_count = max(0, count) if isinstance(count, int) else 0
        return True
    if kind == "spec_ready":
        if owner._spec_view and ev.get("stream") == owner._spec_view.get("stream"):
            _start(owner)
        return True
    if kind == "spec_end":
        view = owner._spec_view
        if view and ev.get("stream") == view.get("stream"):
            view["end"] = str(ev.get("reason") or "over")[:40]
            if owner._spec_policy is not None:
                owner._spec_policy.pause()
            if view.get("game") is None or view["end"] in ("your_match", "not_allowed", "bumped", "damaged"):
                _preempt(owner, view["end"])
        return True
    return False


def _tab(owner):
    """The native policy's small read-only input contract; no Tk dependency."""
    return SimpleNamespace(client=owner._online_client, driver=getattr(owner, "_online_driver", None),
                           app=SimpleNamespace(settings=owner.s, game=getattr(owner, "game", None)),
                           match=getattr(owner, "_online_match", None) or None,
                           challenge=getattr(owner, "_online_challenge", None) or None,
                           invite=getattr(owner, "_online_invites", None) or None,
                           outgoing_invite=getattr(owner, "_online_outgoing_invite", None) or None,
                           set_locked=bool(getattr(owner, "_online_character_locked", False)),
                           tours=SimpleNamespace(call=(getattr(owner, "_online_tours", None) or {}).get("call") or None))


def poll(owner):
    init(owner)
    client = owner._online_client
    if client is None or not _supported(client):
        return False
    enabled = bool(owner.s.get("auto_spectate", False))
    if ((owner._spec_pending and owner._spec_pending[2] and not enabled)
            or (owner._spec_view and owner._spec_view.get("automatic") and not enabled)):
        action(owner, "spec_stop", client)
        return True
    view = owner._spec_view
    if view and view.get("game") is not None and view.get("state") in ("starting", "playing"):
        if not view["game"].running():
            view.update(state="over", end=view.get("end") or "stopped")
            _cancel(client)
            return True
        if time.monotonic() - view.get("checked", 0) >= 1:
            view["checked"] = time.monotonic()
            try:
                with open(view["status"], encoding="utf-8") as stream:
                    status = json.load(stream)
                if not isinstance(status, dict):
                    return False
                delay = status.get("delay")
                view["state"] = "playing"
                view["delay"] = delay if isinstance(delay, (int, float)) and math.isfinite(delay) else None
                return True
            except (OSError, ValueError, TypeError):
                pass
    prefs = (bool(owner.s.get("spectators", True)), bool(owner.s.get("spectators_ranked", False)))
    if prefs != owner._spec_prefs and not owner._online_busy:
        owner._spec_prefs = prefs
        generation = owner._online_generation

        def update_prefs():
            owner._online_check_request(generation, client)
            return client.set_spectate_prefs(*prefs)
        owner._online_submit("feature_spectate:prefs", update_prefs)
        return True
    if (enabled and not owner._spec_auto_unavailable and not owner._online_busy
            and not _busy(owner) and owner._spec_pending is None):
        if view and view.get("automatic") and view.get("state") == "over":
            owner._spec_view = None
        if owner._spec_view is None:
            try:
                if owner._spec_policy is None:
                    owner._spec_policy = _module(owner, "auto_spectate").Policy()
                target = owner._spec_policy.due(_tab(owner))
                if target:
                    owner._spec_policy.attempted()
                    _request(owner, client, target, automatic=True)
                    return True
            except (ImportError, OSError, AttributeError, ValueError, RuntimeError):
                owner._spec_auto_unavailable = True
                owner._online_message = "@online.watch_unavailable"
                return True
    return False


def close(owner):
    _preempt(owner, "stopped")
    owner._spec_view = None
    owner._spec_count = 0
    owner._spec_policy = None
    owner._spec_auto_unavailable = False
