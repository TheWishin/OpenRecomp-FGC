"""Casual health and match rule summaries through the installed lobby client."""
import importlib
import os

from .t5_coexist import readonly_imports


PREFIX = "feature_rules:"


def init(owner):
    if not hasattr(owner, "_online_rules_match"):
        owner._online_rules_match = {}
        owner._online_rules_match_id = None


def reset(owner):
    owner._online_rules_match = {}
    owner._online_rules_match_id = None


def _cap(client, name):
    check = getattr(client, name, None)
    try:
        return bool(callable(check) and check())
    except Exception:  # an older client's capability check may be unavailable
        return False


def _life(value, default=100):
    return value if isinstance(value, int) and not isinstance(value, bool) and value in range(30, 151, 10) else default


def _maximum(client):
    check = getattr(client, "life_max", None)
    try:
        return 150 if callable(check) and check() == 150 else 100
    except Exception:
        return 100


def client_options(owner):
    """Advertise only rules that the selected install's own game check confirms."""
    options = dict(match_rules=False, life150=False)
    owner._online_modules()
    try:
        with readonly_imports():
            module = importlib.import_module(owner.online_package + ".match_driver")
        root = os.path.normcase(os.path.realpath(os.path.join(owner.root, "lobby", owner.online_package)))
        origin = os.path.normcase(os.path.realpath(getattr(module, "__file__", "")))
        if os.path.commonpath((root, origin)) != root:
            return options
        paths = module.game_files(owner._online_out_dir())
        for key, method in (("match_rules", "game_supports_rules"), ("life150", "game_supports_life150")):
            check = getattr(module, method, None)
            options[key] = bool(callable(check) and check(paths))
        options["life150"] = options["life150"] and options["match_rules"]
    except (ImportError, AttributeError, OSError, TypeError, ValueError):
        return dict(match_rules=False, life150=False)
    return options


def logged_in(owner, client):
    if not _cap(client, "handicap_ok") or not callable(getattr(client, "set_life", None)):
        return
    generation = owner._online_generation
    life = min(_life(owner._online_config().get("life")), _maximum(client))
    owner._online_check_request(generation, client)
    if life != _life(getattr(client, "life", 100)):
        client.set_life(life)
        owner._online_check_request(generation, client)


def state(owner):
    init(owner)
    client = owner._online_client
    return dict(capabilities=dict(handicap=_cap(client, "handicap_ok")
                                  and callable(getattr(client, "set_life", None))),
                rules=dict(life=min(_life(getattr(client, "life", 100)), _maximum(client)),
                           maximum=_maximum(client)),
                match_rules=(dict(owner._online_rules_match) if owner._online_rules_match_id
                             == getattr(owner, "_online_match_id", None) else {}))


def action(owner, action, client):
    if not action.startswith("rules_life:"):
        return False
    if (client is not owner._online_client or owner._online_phase != "logged_in"
            or owner._online_busy):
        return True
    if not _cap(client, "handicap_ok") or not callable(getattr(client, "set_life", None)):
        owner._online_message = "@online.rules_unavailable"
        return True
    raw = action.partition(":")[2]
    try:
        value = int(raw)
    except ValueError:
        return True
    if str(value) != raw or _life(value, None) is None or value > _maximum(client):
        return True
    generation = owner._online_generation

    def work():
        owner._online_check_request(generation, client)
        confirmed = client.set_life(value)
        owner._online_check_request(generation, client)
        if _life(confirmed, None) is None or confirmed > _maximum(client):
            raise RuntimeError("@online.rules_unavailable")
        with owner._online_lock:
            owner._online_check_request(generation, client)
            owner._online_write_preferences(dict(life=confirmed))
        return confirmed

    owner._online_submit(PREFIX + "life", work)
    return True


def completion(owner, operation, value, error):
    if not operation.startswith(PREFIX):
        return False
    owner._online_message = owner._online_error(error) if error else "@online.life_updated"
    return True


def event(owner, event):
    init(owner)
    kind = event.get("t")
    current = getattr(owner, "_online_match_id", None)
    if kind in ("match_cancel", "set_end") and event.get("match") in (None, current):
        owner._online_rules_match = {}
        owner._online_rules_match_id = None
    elif kind in ("match_found", "match_reveal", "match_start"):
        if kind != "match_found" and current and event.get("match") not in (None, current):
            return False
        fight = event.get("fight") if isinstance(event.get("fight"), dict) else {}
        summary = dict(owner._online_rules_match) if kind != "match_found" else {}
        if "training" in event or "training" in fight:
            summary["training"] = event.get("training") is True or fight.get("training") is True
        life = event.get("life")
        if isinstance(life, dict) and all(_life(life.get(key), 0) for key in ("you", "opponent")):
            summary.update(you=life["you"], opponent=life["opponent"])
        elif (isinstance(fight.get("life"), list) and len(fight["life"]) == 2
              and all(_life(value, 0) for value in fight["life"])
              and type(event.get("slot")) is int and event["slot"] in (0, 1)):
            slot = event["slot"]
            summary.update(you=fight["life"][slot], opponent=fight["life"][1 - slot])
        owner._online_rules_match = summary
        owner._online_rules_match_id = event.get("match")
    # Rule metadata never consumes match authorization or game-driver events.
    return False
