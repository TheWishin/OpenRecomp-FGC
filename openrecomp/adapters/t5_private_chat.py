"""Bounded private conversations through the installed lobby client; never persisted."""
from collections import OrderedDict
import copy
import math


PREFIX = "feature_private:"
MAX_THREADS = 32
MAX_LINES = 100
REPORT_LIMIT = 5
TEXT_LIMIT = 200


def init(owner):
    if not hasattr(owner, "_online_private_threads"):
        owner._online_private_threads = OrderedDict()
        owner._online_private_selected = ""
        owner._online_private_lines = set()
    owner._online_fields.setdefault("online_private_chat", "")
    owner._online_fields.setdefault("online_private_report_reason", "")


def client_options(owner):
    return dict(private_chat=True)


def _cap(client):
    check = getattr(client, "private_chat_ok", None)
    try:
        return bool(callable(check) and check())
    except Exception:
        return False


def _muted(client, name):
    check = getattr(client, "is_muted", None)
    try:
        return bool(callable(check) and check(name))
    except Exception:
        return False


def _mine(client):
    me = getattr(client, "me", None)
    return me.get("name", "") if isinstance(me, dict) and isinstance(me.get("name"), str) else ""


def _thread(owner, name):
    key = name.lower()
    threads = owner._online_private_threads
    if key not in threads:
        if len(threads) >= MAX_THREADS:
            oldest = next(k for k in threads if k != owner._online_private_selected)
            del threads[oldest]
        threads[key] = dict(name=name, unread=0, messages=[])
    threads.move_to_end(key)
    return threads[key]


def _receive(owner, message):
    if not isinstance(message, dict):
        return False
    sender, recipient = message.get("from"), message.get("to")
    if not isinstance(sender, dict) or not isinstance(recipient, dict):
        return False
    mine = _mine(owner._online_client).lower()
    sender_name, recipient_name = sender.get("name"), recipient.get("name")
    if not mine or not all(isinstance(name, str) and 1 <= len(name) <= 64
                           for name in (sender_name, recipient_name)):
        return False
    outgoing = sender_name.lower() == mine
    if not outgoing and recipient_name.lower() != mine:
        return False
    name = recipient_name if outgoing else sender_name
    if name.lower() == mine or (not outgoing and _muted(owner._online_client, name)):
        return False
    mid, text = message.get("id"), message.get("text")
    if not isinstance(mid, str) or not 1 <= len(mid) <= 80 or not isinstance(text, str) or len(text) > TEXT_LIMIT:
        return False
    # Keep only the signed envelope in private session memory. The view gets no receipt.
    envelope = {key: copy.deepcopy(message[key]) for key in
                ("id", "from", "to", "text", "time", "receipt") if key in message}
    row = _thread(owner, name)
    if any(line["id"] == mid for line in row["messages"]):
        return False
    row["messages"].append(envelope)
    del row["messages"][:-MAX_LINES]
    if owner._online_private_selected == name.lower():
        owner._online_private_lines.intersection_update(line["id"] for line in row["messages"])
    if not outgoing:
        row["unread"] = min(MAX_LINES, row["unread"] + 1)
    return True


def state(owner):
    init(owner)
    client = owner._online_client
    available = _cap(client)
    mine = _mine(client).lower()
    threads = []
    if available:
        for key, row in owner._online_private_threads.items():
            muted = _muted(client, row["name"])
            messages = [dict(id=line["id"], name=line["from"]["name"], text=line["text"],
                             selected=key == owner._online_private_selected and
                                 line["id"] in owner._online_private_lines)
                        for line in row["messages"] if not muted or line["from"]["name"].lower() == mine]
            threads.append(dict(id=key, name=row["name"], unread=0 if muted else row["unread"], messages=messages))
    return dict(capabilities=dict(private_chat=available,
                                 private_reports=available and callable(getattr(client, "private_report", None))),
                private_chat=dict(threads=threads, selected=owner._online_private_selected if available else "",
                                  unread=sum(row["unread"] for row in threads), report_limit=REPORT_LIMIT))


def _target(owner, target):
    client = owner._online_client
    players = getattr(client, "players", None)
    for player in players if isinstance(players, list) else ():
        if isinstance(player, dict) and str(player.get("id")) == target:
            name = player.get("name")
            return name if isinstance(name, str) and 1 <= len(name) <= 64 else ""
    row = owner._online_private_threads.get(target)
    return row["name"] if row else ""


def action(owner, requested, client):
    if not requested.startswith("private_"):
        return False
    init(owner)
    if owner._online_busy or owner._online_phase != "logged_in" or client is not owner._online_client:
        return True
    if not _cap(client):
        owner._online_message = "@online_chat.private_unavailable"
        return True
    if requested == "private_close":
        owner._online_private_selected = ""
        owner._online_private_lines.clear()
        return True
    if requested.startswith("private_open:"):
        name = _target(owner, requested.partition(":")[2])
        if name and name.lower() != _mine(client).lower():
            row = _thread(owner, name)
            if owner._online_private_selected != name.lower():
                owner._online_fields["online_private_chat"] = ""
                owner._online_fields["online_private_report_reason"] = ""
                owner._online_private_lines.clear()
            owner._online_private_selected = name.lower()
            row["unread"] = 0
        return True
    row = owner._online_private_threads.get(owner._online_private_selected)
    if row is None:
        return True
    mine = _mine(client).lower()
    visible = [line for line in row["messages"] if not _muted(client, row["name"])
               or line["from"]["name"].lower() == mine]
    owner._online_private_lines.intersection_update(line["id"] for line in visible)
    if requested == "private_read":
        row["unread"] = 0
        return True
    if requested.startswith("private_select:"):
        mid = requested.partition(":")[2]
        if any(line["id"] == mid for line in visible):
            if mid in owner._online_private_lines:
                owner._online_private_lines.remove(mid)
            elif len(owner._online_private_lines) < REPORT_LIMIT:
                owner._online_private_lines.add(mid)
            else:
                owner._online_message = "@online_chat.report_selection"
        return True
    generation = owner._online_generation
    name = row["name"]
    text = owner._online_fields["online_private_chat"].strip()[:TEXT_LIMIT]
    reason = owner._online_fields["online_private_report_reason"].strip()[:TEXT_LIMIT]
    if requested == "private_send":
        if not text:
            owner._online_message = "@online_chat.private_blank"
            return True
        work = lambda: dict(reply=client.private_message(name, text), name=name, text=text)
        operation = "send"
    elif requested == "private_report" and callable(getattr(client, "private_report", None)):
        lines = [copy.deepcopy(line) for line in visible if line["id"] in owner._online_private_lines]
        if (not 1 <= len(lines) <= REPORT_LIMIT or any(not isinstance(line.get("receipt"), str)
                or not line["receipt"] or not isinstance(line.get("time"), (int, float))
                or isinstance(line["time"], bool) or not math.isfinite(line["time"]) for line in lines)):
            owner._online_message = "@online_chat.report_selection"
            return True
        work = lambda: dict(reply=client.private_report(name, lines, reason), name=name,
                            ids=[line["id"] for line in lines], reason=reason)
        operation = "report"
    else:
        return True

    def checked():
        owner._online_check_request(generation, client)
        if owner._online_phase != "logged_in" or not _cap(client):
            raise RuntimeError("@online.cancelled")
        return work()
    owner._online_submit(PREFIX + operation, checked)
    return True


def completion(owner, operation, value, error):
    if not operation.startswith(PREFIX):
        return False
    if error:
        owner._online_message = owner._online_error(error)
        return True
    init(owner)
    if not isinstance(value, dict):
        return True
    current = owner._online_private_selected == str(value.get("name", "")).lower()
    if operation == PREFIX + "send":
        reply = value.get("reply")
        if isinstance(reply, dict):
            _receive(owner, reply.get("message"))
        if current and owner._online_fields["online_private_chat"].strip() == value.get("text"):
            owner._online_fields["online_private_chat"] = ""
        owner._online_message = "@online_chat.private_sent"
    elif operation == PREFIX + "report":
        if current:
            owner._online_private_lines.difference_update(value.get("ids") or [])
            if owner._online_fields["online_private_report_reason"].strip() == value.get("reason"):
                owner._online_fields["online_private_report_reason"] = ""
        owner._online_message = "@online_chat.report_sent"
    return True


def event(owner, incoming):
    if incoming.get("t") == "mutes":
        init(owner)
        for row in owner._online_private_threads.values():
            if _muted(owner._online_client, row["name"]):
                row["unread"] = 0
        return False
    if incoming.get("t") != "private_message":
        return False
    init(owner)
    if _cap(owner._online_client):
        _receive(owner, incoming)
    return True


def close(owner):
    init(owner)
    owner._online_private_threads.clear()
    owner._online_private_selected = ""
    owner._online_private_lines.clear()
    owner._online_fields["online_private_chat"] = ""
    owner._online_fields["online_private_report_reason"] = ""
