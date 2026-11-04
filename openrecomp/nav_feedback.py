"""Transient action receipts at the adapter boundary. No timers, Qt or network here."""
import math

from . import i18n


TERMINAL = {"accepted": "@feedback.accepted", "declined": "@feedback.declined",
            "expired": "@feedback.expired", "cancelled": "@feedback.cancelled"}
SUCCESS = {"@online.room_joined", "@online.friend_requested", "@online.invite_sent",
           "@online.challenge_sent", "@online.challenge_cancelled", "@online.searching_ranked",
           "@online.searching_casual", "@online.community_updated"}


def records(nav, game):
    return nav.__dict__.setdefault("_action_receipts", {}).setdefault(game, {})


def tracked(action):
    return (action in ("create_room", "create_password_room", "create_code_room", "community_create",
                       "join_room_code", "add_friend", "search_ranked", "search_casual")
            or action.startswith(("challenge:", "cancel_challenge:", "join_room:", "invite_friend:", "invite_room:")))


def begin(nav, g, action, state):
    if not tracked(action):
        return False
    rows = records(nav, g.id)
    if action.startswith("cancel_challenge:"):
        cid = action.partition(":")[2]
        for row in rows.values():
            if row.get("challenge") == cid:
                row.update(cancelling=True, kind="pending", text="@feedback.cancelling", age=0,
                           before=state.get("message"))
        return True
    old = rows.get(action)
    if old and old["kind"] in ("pending", "waiting"):
        return None
    target = action.partition(":")[2]
    person = next((p for p in state.get("players") or [] if str(p.get("id")) == target), {})
    name = person.get("name") or target
    rows[action] = dict(kind="pending", text="@feedback.sending", age=0, name=str(name),
                        before=state.get("message"), action=action, challenge="", observed=False)
    return True


def finish(nav, row, kind, text):
    row.update(kind=kind, text=text, left=5.0)
    toast = i18n.message("feedback.result_for", name=i18n.literal(row["name"]), result=text) \
        if row.get("action", "").startswith("challenge:") else text
    nav.say(toast, 3)


def fail(nav, g, action):
    row = records(nav, g.id).get(action)
    if row is None and action.startswith("cancel_challenge:"):
        row = next((receipt for receipt in records(nav, g.id).values()
                    if receipt.get("challenge") == action.partition(":")[2]), None)
    if row:
        finish(nav, row, "error", "@online.failure")


def observe(nav, g, state):
    rows = records(nav, g.id)
    offers = list(state.get("open_challenges") or [])
    if state.get("outgoing_challenge"):
        offers.append(state["outgoing_challenge"])
    updates = {str(row.get("id")): row.get("state") for row in state.get("challenge_updates") or []}
    message = state.get("message")
    for action, row in list(rows.items()):
        if row["kind"] not in ("pending", "waiting"):
            continue
        if action.startswith("challenge:"):
            terminal = updates.get(row.get("challenge"))
            if terminal in TERMINAL:
                finish(nav, row, terminal if terminal in ("declined", "expired") else "success", TERMINAL[terminal])
                continue
            offer = next((o for o in offers if str(o.get("player")) == action.partition(":")[2]
                          or row.get("challenge") and o.get("id") == row["challenge"]
                          or o.get("name") == row["name"]), None)
            if offer:
                if row.get("cancelling"):
                    if not state.get("busy") and message and message != row.get("before"):
                        finish(nav, row, "error", message)
                    continue
                if row["kind"] != "waiting":
                    row.update(kind="waiting", age=0, challenge=str(offer.get("id") or ""), observed=True)
                    if type(offer.get("seconds")) in (int, float) and 0 <= offer["seconds"] <= 3600:
                        row["seconds"] = max(0, float(offer["seconds"]))
                    nav.say(i18n.message("feedback.challenge_to", name=i18n.literal(row["name"])), 3)
                continue
            if row.get("cancelling") and message == "@online.challenge_cancelled":
                finish(nav, row, "success", "@feedback.cancelled")
                continue
            if row.get("observed"):
                if state.get("phase") in ("matched", "starting", "playing"):
                    accepted = (state.get("match") or {}).get("opponent") == row["name"]
                    finish(nav, row, "success", "@feedback.accepted" if accepted else "@feedback.ended")
                elif not state.get("busy"):
                    # A legacy server may omit its reason; never invent a decline or expiry.
                    finish(nav, row, "success", "@feedback.ended")
                continue
        if state.get("busy"):
            row["saw_busy"] = True
            continue
        if action.startswith("search_") and state.get("phase") == "searching":
            if row["kind"] != "waiting":
                row.update(kind="waiting", text="@online.searching_ranked" if action == "search_ranked" else "@online.searching_casual")
                nav.say(row["text"], 3)
            continue
        if action.startswith("search_") and row["kind"] == "waiting":
            finish(nav, row, "success", message or "@feedback.ended")
            continue
        if isinstance(message, str) and message in SUCCESS and (message != row.get("before") or row.get("saw_busy")):
            text = "@feedback.room_created" if action.startswith("create_") or action == "community_create" else message
            finish(nav, row, "success", text)
        elif message and message != row.get("before") and message not in ("@online.connecting", "@online.logged_in"):
            finish(nav, row, "error", message)


def tick(nav, dt):
    changed = False
    for rows in nav.__dict__.get("_action_receipts", {}).values():
        for action, row in list(rows.items()):
            if row["kind"] in ("pending", "waiting"):
                old = int(row["age"])
                row["age"] += dt
                if "seconds" in row:
                    row["seconds"] = max(0, row["seconds"] - dt)
                changed = changed or int(row["age"]) != old
            else:
                row["left"] -= dt
                if row["left"] <= 0:
                    rows.pop(action)
                    changed = True
    return changed


def view(nav, game, action):
    row = records(nav, game).get(action)
    if not row:
        return {}
    text = row["text"]
    if action.startswith("challenge:") and row["kind"] == "waiting":
        seconds = math.ceil(row["seconds"]) if "seconds" in row else int(row["age"])
        clock = f"{seconds // 60}:{seconds % 60:02}"
        if "seconds" in row:
            text = i18n.message("feedback.waiting_countdown", time=clock)
        else:
            text = i18n.message("feedback.waiting_elapsed", time=clock)
    return dict(kind=row["kind"], text=text)
