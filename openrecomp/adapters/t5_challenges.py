"""Casual preferences and challenge choices delegated to the installed lobby client."""
import copy
import inspect


PREFIX = "feature_challenges:"
FIRST_TO = (1, 2, 3, 5, 10)


def init(owner):
    if hasattr(owner, "_t5_challenge_prefs"):
        return
    cfg = owner._online_config()
    delay = str(cfg.get("challenge_delay") or "auto")
    side = cfg.get("casual_side")
    target = cfg.get("casual_first_to", 1)
    owner._t5_challenge_prefs = dict(
        delay=delay if delay in ("auto", *(str(n) for n in range(9))) else "auto",
        side=side if type(side) is int and side in (0, 1) else None,
        stage=str(cfg.get("casual_stage") or "random")[:80],
        first_to=target if type(target) is int and target in FIRST_TO else 1,
        auto_skip=bool(cfg.get("auto_skip_after_round", False)))
    owner._t5_open_challenges = {}
    owner._t5_ended_challenges = {}
    owner._t5_incoming_challenge = {}


def reset(owner):
    init(owner)
    owner._t5_open_challenges.clear()
    owner._t5_ended_challenges.clear()
    owner._t5_incoming_challenge = {}


def _ok(client, method):
    check = getattr(client, method, None)
    try:
        return bool(callable(check) and check())
    except Exception:  # noqa: BLE001 -- unknown installed capabilities remain unavailable
        return False


def _maximum(client, player=None):
    check = getattr(client, "challenge_delay_max", None)
    try:
        return 8 if callable(check) and check(player) == 8 else 2
    except Exception:  # noqa: BLE001 -- older clients only know the legacy delay range
        return 2


def _stages(client):
    get = getattr(client, "casual_stages", None)
    try:
        values = get() if callable(get) else []
    except Exception:  # noqa: BLE001 -- a missing server list must not break navigation
        values = []
    return [key[:80] for key in values[:200] if isinstance(key, str) and key != "random"] if isinstance(values, list) else []


def state(owner):
    init(owner)
    client = owner._online_client
    ready = client is not None and callable(getattr(client, "send_challenge", None))
    prefs = dict(owner._t5_challenge_prefs)
    prefs.update(delay_max=_maximum(client), delay_supported=_ok(client, "multi_challenge_ok"),
                 casual_supported=_ok(client, "casual_ok"), sets_supported=_ok(client, "casual_sets_ok"),
                 auto_skip_supported=_ok(client, "auto_skip_ok"), stages=_stages(client),
                 incoming=copy.deepcopy(owner._t5_incoming_challenge),
                 peer_delay_max={str(p["id"]): _maximum(client, p["id"])
                                 for p in owner._online_players if p.get("id")})
    return dict(capabilities=dict(challenge_preferences=ready), challenge_preferences=prefs,
                open_challenges=[dict(value, id=key) for key, value in owner._t5_open_challenges.items()])


def client_options(owner):
    return dict(casual_sets=True, input_delay8=True)


def client_created(owner, client):
    init(owner)
    _apply(client, owner._t5_challenge_prefs)


def _apply(client, prefs):
    setter = getattr(client, "set_casual_prefs", None)
    if callable(setter):
        stage = prefs["stage"]
        if _ok(client, "casual_ok") and stage != "random" and stage not in _stages(client):
            stage = "random"
        setter(prefs["side"], stage)
    client.casual_first_to = prefs["first_to"]
    setter = getattr(client, "set_auto_skip_after_round", None)
    if callable(setter):
        setter(prefs["auto_skip"])


def _preferences(owner, action, client):
    prefs = dict(owner._t5_challenge_prefs)
    field, _, value = action.removeprefix("challenge_option:").partition(":")
    if field == "delay" and _ok(client, "multi_challenge_ok"):
        if value not in ("auto", *(str(n) for n in range(_maximum(client) + 1))):
            return None
        prefs[field] = value
    elif field == "first_to" and _ok(client, "casual_sets_ok"):
        if value not in tuple(str(n) for n in FIRST_TO):
            return None
        prefs[field] = int(value)
    elif field == "side" and _ok(client, "casual_ok"):
        if value not in ("any", "0", "1"):
            return None
        prefs[field] = None if value == "any" else int(value)
    elif field == "stage" and _ok(client, "casual_ok"):
        if value != "random" and value not in _stages(client):
            return None
        prefs[field] = value
    elif field == "auto_skip" and _ok(client, "auto_skip_ok"):
        if value not in ("on", "off"):
            return None
        prefs[field] = value == "on"
    else:
        return None
    return prefs


def _send(client, target, delay, first_to):
    send = client.send_challenge
    parameters = inspect.signature(send).parameters
    kwargs = {}
    if "delay" in parameters:
        kwargs["delay"] = delay
    if "first_to" in parameters:
        kwargs["first_to"] = first_to
    return send(target, **kwargs)


def action(owner, action, client):
    init(owner)
    if not (action.startswith(("challenge:", "challenge_option:", "cancel_challenge:"))):
        return False
    if not callable(getattr(client, "send_challenge", None)):
        return False
    if owner._online_phase != "logged_in" or owner._online_busy:
        return True
    generation = owner._online_generation
    if action.startswith("challenge_option:"):
        prefs = _preferences(owner, action, client)
        if prefs is None:
            return True

        def work():
            owner._online_check_request(generation, client)
            owner._online_write_preferences(dict(challenge_delay=prefs["delay"], casual_side=prefs["side"],
                casual_stage=prefs["stage"], casual_first_to=prefs["first_to"],
                auto_skip_after_round=prefs["auto_skip"]))
            owner._online_check_request(generation, client)
            _apply(client, prefs)
            return prefs
        owner._online_submit(PREFIX + "preferences", work)
    elif action.startswith("cancel_challenge:"):
        target = action.partition(":")[2]
        if target not in owner._t5_open_challenges or not callable(getattr(client, "cancel_challenge", None)):
            return True

        def work():
            owner._online_check_request(generation, client)
            client.cancel_challenge(target)
            return target
        owner._online_submit(PREFIX + "cancel", work)
    else:
        target = action.partition(":")[2]
        player = next((p for p in owner._online_players if str(p.get("id")) == target), None)
        if not player or any(row["player"] == target for row in owner._t5_open_challenges.values()):
            return True
        prefs = dict(owner._t5_challenge_prefs)
        choice = prefs["delay"]
        delay = int(choice) if choice != "auto" and int(choice) <= _maximum(client, target) and _ok(client, "multi_challenge_ok") else None
        first_to = prefs["first_to"] if _ok(client, "casual_sets_ok") else 1
        name = str(player.get("name") or "")[:64]

        def work():
            from .t5_online import SearchRefused
            owner._online_check_request(generation, client)
            problem = owner._online_game_check()
            if problem:
                raise SearchRefused(problem)
            owner._online_check_request(generation, client)
            return dict(reply=_send(client, target, delay, first_to), player=target, name=name,
                        first_to=first_to, delay=delay)
        owner._online_submit(PREFIX + "send", work)
    return True


def _delay(value):
    if not isinstance(value, dict):
        return {}
    out = {}
    frames = value.get("frames")
    if type(frames) is int and 0 <= frames <= 8:
        out["frames"] = frames
    if type(value.get("auto")) is bool:
        out["auto"] = value["auto"]
    return out


def completion(owner, operation, value, error):
    if not operation.startswith(PREFIX):
        return False
    init(owner)
    if error:
        from .t5_online import SearchRefused
        if operation == PREFIX + "send" and not isinstance(error, SearchRefused):
            _changed, terminal = owner._online_events()
            if terminal or owner._online_phase in ("matched", "starting", "playing", "result", "result_sent"):
                return True
            message = owner._online_error(error)
            owner.online_close()
            owner._online_message = message
            return True
        owner._online_message = owner._online_error(error)
        return True
    if operation == PREFIX + "preferences":
        owner._t5_challenge_prefs = dict(value)
        owner._online_message = "@online.challenge_preferences_saved"
    elif operation == PREFIX + "cancel":
        owner._t5_open_challenges.pop(value, None)
        owner._online_message = "@online.challenge_cancelled"
    elif operation == PREFIX + "send":
        reply = value["reply"]
        cid = reply.get("challenge") if isinstance(reply, dict) else reply
        if (owner._online_phase == "logged_in" and isinstance(cid, str) and cid
                and cid not in owner._t5_ended_challenges):
            owner._t5_open_challenges[cid[:80]] = dict(player=value["player"], name=value["name"],
                first_to=value["first_to"], delay=_delay(reply.get("delay")) if isinstance(reply, dict) else {})
        owner._online_message = "@online.challenge_sent"
    return True


def event(owner, event):
    init(owner)
    kind = event.get("t")
    if kind == "challenged":
        cid = event.get("challenge")
        info = dict(id=cid[:80] if isinstance(cid, str) else "", delay=_delay(event.get("delay")))
        if type(event.get("first_to")) is int and event["first_to"] in FIRST_TO:
            info["first_to"] = event["first_to"]
        wish = event.get("wish")
        if isinstance(wish, dict):
            info["wish"] = {}
            if type(wish.get("side")) is int and wish["side"] in (0, 1):
                info["wish"]["side"] = wish["side"]
            if isinstance(wish.get("stage"), str):
                info["wish"]["stage"] = wish["stage"][:80]
        owner._t5_incoming_challenge = info
    elif kind == "challenge_update":
        cid = event.get("challenge")
        if isinstance(cid, str):
            owner._t5_open_challenges.pop(cid, None)
            owner._t5_ended_challenges[cid[:80]] = True
            if len(owner._t5_ended_challenges) > 64:
                owner._t5_ended_challenges.pop(next(iter(owner._t5_ended_challenges)))
        if cid == owner._t5_incoming_challenge.get("id"):
            owner._t5_incoming_challenge = {}
    elif kind == "match_found":
        owner._t5_open_challenges.clear()
        owner._t5_incoming_challenge = {}
    # The base adapter still handles incoming challenge acceptance and expiry.
    return False
