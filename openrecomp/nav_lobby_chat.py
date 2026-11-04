"""Safe received chat presentation. No HTML, networking or fabricated history."""
import re
from . import i18n


def available(state):
    return bool((state.get("capabilities") or {}).get("lobby") and state.get("phase") in (
        "logged_in", "searching", "cancelling", "matched", "starting", "playing", "result", "result_sent"))


def ensure_rows(nav, game, state, rows):
    """The same chat actions remain present during the match cards and main menu."""
    if not available(state) or any(item.get("region") == "chat" for item in rows):
        return rows
    from . import nav_private_chat
    def action(iid, label, hint="@online.chat_hint"):
        return dict(kind="action", id=iid, label=label, verb="@confirm", hint=hint,
                    detail=dict(title=label, lead=hint, rows=[]),
                    run=lambda: nav._online_action(game, iid))
    chat = []
    nav._online_chat_items(game, state, chat, action)
    chat.extend(nav_private_chat.rows(nav, game, state, action))
    projected = nav._online_layout_items(game, dict(state, phase="logged_in", recovery_codes=[]), chat)
    return [dict(item, region=item.get("region", "find")) for item in rows] + [
        item for item in projected if item.get("region") == "chat"]


def plain(value):
    return str(value.get("_literal") or "") if isinstance(value, dict) else str(value or "")


def segments(text, name):
    text, name = plain(text), plain(name)
    if not name:
        return [dict(text=i18n.literal(text), mention=False)]
    pattern = re.compile(r"(?<![\w@])@" + re.escape(name) + r"(?![\w])", re.IGNORECASE)
    out, start = [], 0
    for match in pattern.finditer(text):
        if match.start() > start:
            out.append(dict(text=i18n.literal(text[start:match.start()]), mention=False))
        out.append(dict(text=i18n.literal(match.group()), mention=True))
        start = match.end()
    if start < len(text) or not out:
        out.append(dict(text=i18n.literal(text[start:]), mention=False))
    return out


def identities(nav, game, messages):
    """Keep received message identities through prefix trimming; duplicate text uses occurrence order."""
    memory = nav.__dict__.setdefault("_chat_identity", {}).setdefault(game.id, dict(next=0, keys={}))
    seen, current, out = {}, {}, []
    for message in messages:
        base = (str(message.get("id") or ""), str(message.get("name") or ""),
                str(message.get("text") or ""), str(message.get("time") or ""))
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        key = base + (occurrence,)
        identity = memory["keys"].get(key)
        if identity is None:
            identity = memory["next"]
            memory["next"] += 1
        current[key] = identity
        out.append(str(identity))
    memory["keys"] = current
    return out
