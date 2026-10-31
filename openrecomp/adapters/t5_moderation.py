"""Personal chat controls and known moderation notices from the installed lobby."""
import math
import time


PREFIX = "feature_moderation:"
NOTICES = {
    "Message blocked: hate terms are not allowed.": "@online_chat.filter_blocked",
    "Chat is muted for this account.": "@online_chat.chat_muted",
    "This name is not allowed.": "@online_chat.name_blocked",
    "This room name is not allowed.": "@online_chat.room_name_blocked",
}


def init(owner):
    if not hasattr(owner, "_online_mutes"):
        owner._online_mutes = []
        owner._online_moderation_notice = ""


def _cap(client, name):
    check = getattr(client, name, None)
    try:
        return bool(callable(check) and check())
    except Exception:
        return False


def _blocks(client):
    welcome = getattr(client, "welcome", None)
    features = welcome.get("features") if isinstance(welcome, dict) else None
    return bool(isinstance(features, (list, tuple, set)) and "blocks" in features
                and all(callable(getattr(client, name, None)) for name in ("block", "blocks")))


def _rows(value):
    result, seen = [], set()
    for row in (value if isinstance(value, list) else [])[:200]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        name = row["name"][:64]
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            result.append(dict(name=name, guest=row.get("guest") is True))
    return result


def _muted_until(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > time.time())


def state(owner):
    init(owner)
    client = owner._online_client
    mutes = _cap(client, "mutes_ok")
    return dict(capabilities=dict(mutes=mutes, blocks=_blocks(client)),
                moderation=dict(mutes=[dict(row) for row in owner._online_mutes] if mutes else [],
                                notice=owner._online_moderation_notice))


def logged_in(owner, client):
    init(owner)
    owner._online_mutes = _rows(getattr(client, "mute_rows", None)) if _cap(client, "mutes_ok") else []
    moderation = getattr(client, "chat_moderation", None)
    if _cap(client, "mutes_ok") and isinstance(moderation, dict) and _muted_until(moderation.get("muted_until")):
        owner._online_moderation_notice = "@online_chat.chat_muted"


def _target(client, target):
    roster = getattr(client, "players", None)
    me = getattr(client, "me", None)
    own_id = me.get("id") if isinstance(me, dict) else None
    for row in roster if isinstance(roster, list) else []:
        if (isinstance(row, dict) and str(row.get("id")) == target and row.get("id") != own_id
                and isinstance(row.get("name"), str) and row["name"]):
            return row["name"][:64]
    return ""


def action(owner, requested, client):
    if requested != "moderation_refresh_mutes" and not requested.startswith((
            "moderation_mute:", "moderation_unmute:", "moderation_block:")):
        return False
    init(owner)
    if owner._online_busy or owner._online_phase != "logged_in" or client is not owner._online_client:
        return True
    blocking = requested.startswith("moderation_block:")
    supported = _blocks(client) if blocking else _cap(client, "mutes_ok")
    if not supported:
        owner._online_message = "@online_chat.moderation_unavailable"
        return True
    target = requested.partition(":")[2]
    unmuting = requested.startswith("moderation_unmute:")
    name = target if unmuting else _target(client, target)
    if requested != "moderation_refresh_mutes":
        if not name or (unmuting and not any(row["name"] == name for row in owner._online_mutes)):
            return True
    generation = owner._online_generation

    def work():
        owner._online_check_request(generation, client)
        if owner._online_phase != "logged_in" or not (_blocks(client) if blocking else _cap(client, "mutes_ok")):
            raise RuntimeError("@online.cancelled")
        if requested != "moderation_refresh_mutes" and not unmuting and _target(client, target) != name:
            raise RuntimeError("@online.cancelled")
        if blocking:
            client.block(name)
            owner._online_check_request(generation, client)
            return client.blocks()
        if requested == "moderation_refresh_mutes":
            return client.mutes()
        return client.mute(name, not unmuting)

    owner._online_submit(PREFIX + ("blocks" if blocking else "mutes"), work)
    return True


def completion(owner, operation, value, error):
    if not operation.startswith(PREFIX):
        return False
    init(owner)
    if error:
        owner._online_message = refusal(owner, error) or owner._online_error(error)
    elif operation == PREFIX + "mutes":
        owner._online_mutes = _rows(value.get("rows")) if isinstance(value, dict) else []
        owner._online_message = "@online_chat.mute_updated"
    elif operation == PREFIX + "blocks":
        owner._account_blocks = _rows(value)
        owner._online_message = "@online_chat.block_updated"
    return True


def refusal(owner, error):
    init(owner)
    code = error.get("code") if isinstance(error, dict) else getattr(error, "code", None)
    message = error.get("msg") if isinstance(error, dict) else getattr(error, "msg", None)
    key = NOTICES.get(message) if code == "not_allowed" and isinstance(message, str) else ""
    if key:
        owner._online_moderation_notice = key
    return key or ""


def event(owner, incoming):
    init(owner)
    kind = incoming.get("t")
    if kind == "error":
        key = refusal(owner, incoming)
        if key:
            owner._online_message = key
        return bool(key)
    if kind == "mutes" and _cap(owner._online_client, "mutes_ok"):
        owner._online_mutes = _rows(incoming.get("rows"))
        return True
    if kind == "chat_moderation" and _cap(owner._online_client, "mutes_ok"):
        owner._online_moderation_notice = "@online_chat.chat_muted" if _muted_until(incoming.get("muted_until")) else ""
        return True
    return False


def reset(owner):
    init(owner)
    owner._online_mutes = []
    owner._online_moderation_notice = ""
