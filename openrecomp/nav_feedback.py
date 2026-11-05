"""Transient action receipts at the adapter boundary. No timers, Qt or network here."""
import math

from . import i18n, ui_sound


TERMINAL = {"accepted": "@feedback.accepted", "declined": "@feedback.declined",
            "expired": "@feedback.expired", "cancelled": "@feedback.cancelled"}
SUCCESS = {"@online.room_joined", "@online.friend_requested", "@online.invite_sent",
           "@online.challenge_sent", "@online.challenge_cancelled", "@online.searching_ranked",
           "@online.searching_casual", "@online.community_updated"}
OFFER_ACTION = "offers"


def records(nav, game):
    return nav.__dict__.setdefault("_action_receipts", {}).setdefault(game, {})


def tracked(action):
    return (action in ("create_room", "create_password_room", "create_code_room", "community_create",
                       "join_room_code", "add_friend", "search_ranked", "search_casual",
                       "accept_challenge", "decline_challenge", "start_match", "cancel_match")
            or action.startswith(("challenge:", "cancel_challenge:", "join_room:", "invite_friend:", "invite_room:", "accept_invite:", "decline_invite:")))


def begin(nav, g, action, state):
    if not tracked(action):
        return False
    rows = records(nav, g.id)
    _answer_session(nav, g, state)
    identity = _answer_identity(g, action, state)
    if identity:
        if identity in nav.__dict__.get("_global_offer_answers", {}):
            return None
        _mark_answer(nav, g.id, identity)
    if action in ("accept_challenge", "decline_challenge"):
        challenge = state.get("challenge") or {}
        cid = str(challenge.get("id") or "")
        if not cid or any(row.get("incoming") == cid and row.get("kind") in ("pending", "waiting")
                          for row in rows.values()):
            return None
        rows[action] = dict(kind="pending", text="@feedback.sending", age=0, incoming=cid,
                            name=str(challenge.get("name") or ""), before=state.get("message"),
                            action=action, challenge="", observed=False, offerIdentity=identity)
        return True
    if action in ("start_match", "cancel_match") or action.startswith(("accept_invite:", "decline_invite:")):
        if not identity:
            # Direct-IP adapters also use start/cancel; keep their existing gates.
            return False
        rows[action] = dict(kind="pending", text="@feedback.sending", age=0,
                            name=str((state.get("match") or {}).get("opponent") or ""),
                            before=state.get("message"), action=action, challenge="", observed=False,
                            offerIdentity=identity)
        return True
    if action.startswith("cancel_challenge:"):
        cid = action.partition(":")[2]
        if any(row.get("challenge") == cid and row.get("cancelling") and row.get("kind") in ("pending", "waiting")
               for row in rows.values()):
            return None
        matched = False
        for row in rows.values():
            if row.get("challenge") == cid:
                matched = True
                row.update(cancelling=True, kind="pending", text="@feedback.cancelling", age=0,
                           before=state.get("message"))
        if not matched:
            offer = next((offer for offer in state.get("open_challenges") or [] if str(offer.get("id")) == cid), {})
            rows[action] = dict(cancelling=True, kind="pending", text="@feedback.cancelling", age=0,
                                before=state.get("message"), name=str(offer.get("name") or cid),
                                action=action, challenge=cid, observed=False)
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
    owner = next((game for game, rows in nav.__dict__.get("_action_receipts", {}).items()
                  if any(receipt is row for receipt in rows.values())), nav.game.id)
    nav.__dict__.setdefault("last_action_result", {})[owner] = dict(text=toast, error=kind in ("error", "declined", "expired"), buttons=[])
    nav.say(toast, 3)


def fail(nav, g, action):
    row = records(nav, g.id).get(action)
    if row is None and action.startswith("cancel_challenge:"):
        row = next((receipt for receipt in records(nav, g.id).values()
                    if receipt.get("challenge") == action.partition(":")[2]), None)
    if row:
        nav.__dict__.get("_global_offer_answers", {}).pop(row.get("offerIdentity"), None)
        finish(nav, row, "error", "@online.failure")


def observe(nav, g, state):
    observe_offers(nav, g, state)
    rows = records(nav, g.id)
    offers = list(state.get("open_challenges") or [])
    if state.get("outgoing_challenge"):
        offers.append(state["outgoing_challenge"])
    updates = {str(row.get("id")): row.get("state") for row in state.get("challenge_updates") or []}
    message = state.get("message")
    for action, row in list(rows.items()):
        if row["kind"] not in ("pending", "waiting"):
            continue
        if action in ("start_match", "cancel_match") or action.startswith(("accept_invite:", "decline_invite:")):
            if state.get("phase") in ("error", "kicked") or message == "@online.failure" and not state.get("busy"):
                nav.__dict__.get("_global_offer_answers", {}).pop(row.get("offerIdentity"), None)
                finish(nav, row, "error", message or "@online.failure")
            elif state.get("busy"):
                row["saw_busy"] = True
            elif action == "start_match" and state.get("phase") in ("starting", "playing"):
                finish(nav, row, "success", "@feedback.accepted")
            elif action == "cancel_match" and state.get("phase") not in ("matched", "starting"):
                finish(nav, row, "success", "@feedback.cancelled")
            elif action.startswith(("accept_invite:", "decline_invite:")) and not any(str(invite.get("id")) == action.partition(":")[2] for invite in state.get("invites") or []):
                finish(nav, row, "success", "@feedback.ended")
            continue
        if row.get("incoming"):
            current = str((state.get("challenge") or {}).get("id") or "")
            phase = state.get("phase")
            if current and current != row["incoming"]:
                finish(nav, row, "success", "@feedback.ended")
            elif phase in ("matched", "starting", "playing"):
                finish(nav, row, "success", "@feedback.accepted" if action == "accept_challenge" else "@feedback.ended")
            elif phase in ("offline", "error", "kicked"):
                finish(nav, row, "error", message or "@online.failure")
            elif state.get("busy"):
                row["saw_busy"] = True
            elif message == "@online.challenge_answered" and (message != row.get("before") or row.get("saw_busy")):
                finish(nav, row, "success", message)
            elif message and message != row.get("before") and message not in ("@online.connecting", "@online.logged_in"):
                finish(nav, row, "error", message)
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
        if action.startswith("search_") and state.get("phase") in ("searching", "cancelling", "matched", "starting", "playing", "result", "result_sent"):
            phase = state["phase"]
            status = {"searching": "@online.searching_ranked" if action == "search_ranked" else "@online.searching_casual",
                      "cancelling": "@feedback.cancelling", "matched": "@online.match_found",
                      "starting": "@online.starting", "playing": "@online.playing", "result": "@online.result",
                      "result_sent": "@online.result_sent"}[phase]
            if row.get("phase") != phase:
                row.update(kind="waiting", phase=phase, text=status)
                nav.say(status, 3)
            continue
        if state.get("busy"):
            row["saw_busy"] = True
            continue
        if action.startswith("search_") and row["kind"] == "waiting":
            failed = state.get("phase") in ("error", "kicked")
            finish(nav, row, "error" if failed else "success", message or "@feedback.ended")
            continue
        if isinstance(message, str) and message in SUCCESS and (message != row.get("before") or row.get("saw_busy")):
            text = "@feedback.room_created" if action.startswith("create_") or action == "community_create" else message
            finish(nav, row, "success", text)
        elif message and message != row.get("before") and message not in ("@online.connecting", "@online.logged_in"):
            finish(nav, row, "error", message)


def tick(nav, dt):
    from . import nav_rank_cue
    changed = nav_rank_cue.tick(nav, dt)
    for row in nav.__dict__.get("_global_offer_clock", {}).values():
        old = int(row["age"])
        row["age"] += max(0, dt)
        changed = changed or old != int(row["age"])
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
    result = dict(kind=row["kind"], text=text)
    if action.startswith("search_"):
        elapsed = int(row["age"])
        result.update(phase=row.get("phase", "pending"), elapsed=elapsed, clock=f"{elapsed // 60}:{elapsed % 60:02}")
    return result


def _offers(g, state):
    """Use only offers and actions already exposed by the common adapter."""
    challenge = state.get("challenge") or {}
    if challenge.get("id"):
        yield "challenge:" + str(challenge["id"]), _peer_info(state, challenge), "accept_challenge", "decline_challenge"
    for invite in state.get("invites") or []:
        if invite.get("id"):
            yield "invite:" + str(invite["id"]), invite, "accept_invite:" + str(invite["id"]), "decline_invite:" + str(invite["id"])
    if state.get("phase") == "matched" and (state.get("capabilities") or {}).get("match_flow"):
        match = state.get("match") or {}
        opponent = match.get("opponent")
        name = opponent.get("name") if isinstance(opponent, dict) else opponent
        key = str(match.get("id") or match.get("match") or name or "ready")
        yield "match:" + key, _peer_info(state, match), "start_match", "cancel_match"


def _answer_identity(g, action, state):
    for key, info, accept, decline in _offers(g, state):
        if action in (accept, decline):
            return g.id + "/" + key
    if action == "cancel_match" and state.get("phase") == "starting":
        match = state.get("match") or {}
        opponent = match.get("opponent")
        name = opponent.get("name") if isinstance(opponent, dict) else opponent
        return g.id + "/match:" + str(match.get("id") or match.get("match") or name or "ready") + "/cancel"
    return ""


def _mark_answer(nav, game, identity):
    answers = nav.__dict__.setdefault("_global_offer_answers", {})
    answers[identity] = game
    while len(answers) > 256:
        answers.pop(next(iter(answers)))


def _answer_session(nav, g, state):
    session = state.get("netext_session")
    if session is None:
        return
    sessions = nav.__dict__.setdefault("_global_offer_session", {})
    if g.id in sessions and sessions[g.id] != session:
        answers = nav.__dict__.setdefault("_global_offer_answers", {})
        for identity, game in list(answers.items()):
            if game == g.id:
                answers.pop(identity)
        for action, row in list(records(nav, g.id).items()):
            if row.get("offerIdentity"):
                records(nav, g.id).pop(action)
        clocks = nav.__dict__.get("_global_offer_clock", {})
        for identity, row in list(clocks.items()):
            if row["game"] == g.id:
                clocks.pop(identity)
    sessions[g.id] = session


def _peer_info(state, info):
    opponent = info.get("opponent")
    public = info.get("opponent_info")
    peer = dict(public) if isinstance(public, dict) else dict(opponent) if isinstance(opponent, dict) else {}
    name = info.get("name") or peer.get("name") or (opponent if isinstance(opponent, str) else "")
    player_id = info.get("player") or peer.get("id")
    roster = [person for person in state.get("players") or []
              if str(person.get("id")) == str(player_id)] if player_id else [person for person in state.get("players") or [] if person.get("name") == name]
    if len(roster) == 1:
        peer = dict(roster[0], **peer)
    peer.update(info)
    peer["name"] = name
    return peer


def observe_offers(nav, g, state):
    _answer_session(nav, g, state)
    clocks = nav.__dict__.setdefault("_global_offer_clock", {})
    live = set()
    for key, info, accept, decline in _offers(g, state):
        identity = g.id + "/" + key
        live.add(identity)
        if identity not in clocks:
            serial = nav.__dict__.get("_global_offer_serial", 0) + 1
            nav._global_offer_serial = serial
            row = dict(age=0.0, serial=serial, game=g.id)
            seconds = info.get("seconds")
            if type(seconds) in (int, float) and math.isfinite(seconds) and 0 <= seconds <= 3600:
                row["seconds"] = seconds
            clocks[identity] = row
            if not any(getattr(game.a, "running", lambda: False)() for game in nav.games):
                nav.note_sound(ui_sound.NOTIFY)
                nav.pending_attention = True
    for identity, row in list(clocks.items()):
        if row["game"] == g.id and identity not in live:
            clocks.pop(identity)
            if nav.__dict__.get("_global_offer_focus") == identity:
                nav._global_offer_focus = ""
    if state.get("message") == "@online.failure" and not state.get("busy"):
        for identity in live:
            if any(receipt.get("offerIdentity") == identity and receipt.get("kind") in ("pending", "waiting")
                   and (receipt.get("before") != state["message"] or receipt.get("saw_busy"))
                   for receipt in records(nav, g.id).values()):
                nav.__dict__.setdefault("_global_offer_answers", {}).pop(identity, None)


def global_view(nav):
    """A passive stack. Arrival never changes a page, selection, draft or OS focus."""
    from .nav_online_layout import connection
    from .nav_challenges import _details
    rows = []
    # The game owns its in-game panel while running; launcher notifications must not compete with it.
    if any(getattr(g.a, "running", lambda: False)() for g in nav.games):
        return []
    for g in nav.games:
        state = getattr(g.a, "online_state", lambda: {})()
        for key, info, accept, decline in _offers(g, state):
            identity = g.id + "/" + key
            clock = nav.__dict__.get("_global_offer_clock", {}).get(identity, {})
            terms = (state.get("challenge_preferences") or {}).get("incoming") or {}
            details = _details(terms if terms.get("id") == info.get("id") else info)
            if key.startswith("match:"):
                for field, label in (("mode", "@feedback.mode"), ("rounds", "@feedback.rounds"), ("delay", "@online.challenge_delay")):
                    value = info.get(field)
                    if isinstance(value, (str, int)):
                        details.append(dict(k=label, v=i18n.literal(str(value))))
            seconds = max(0, math.ceil(clock["seconds"] - clock.get("age", 0))) if "seconds" in clock else None
            pending = bool(state.get("busy")) or identity in nav.__dict__.get("_global_offer_answers", {})
            from .nav_common import uri
            rows.append(dict(identity=identity, game=g.id, gameShort=i18n.literal(g.short), serial=clock.get("serial", 0),
                accent="#71CBE5" if g.m.get("adapter") == "t4" else "#D11F3F" if g.m.get("adapter") == "t5dr" else g.accent,
                kind=key.partition(":")[0], title="@online.match_found" if key.startswith("match:") else "@online.accept_invite" if key.startswith("invite:") else "@online.accept_challenge",
                name=i18n.literal(str(info.get("name") or info.get("opponent") or "")),
                rank=i18n.literal(str(info.get("rank") or "")), rating=i18n.literal(str(info.get("rating") or "")),
                plate=uri(g.a.rank_plate(info.get("tier"))) if info.get("tier") is not None else "",
                selfName=i18n.literal(str((state.get("me") or {}).get("name") or state.get("name") or "")),
                selfRank=i18n.literal(str((state.get("me") or {}).get("rank") or state.get("rank") or "")),
                art=uri(g.a.fighter_image(info["main"])) if info.get("main") else "",
                fighter=i18n.literal(g.a.fighter_label(info["main"])) if info.get("main") else "",
                selfArt=uri(g.a.fighter_image(state["me"]["main"])) if (state.get("me") or {}).get("main") else "",
                connection=connection(info), details=details, seconds=seconds,
                countdown=f"{seconds // 60}:{seconds % 60:02}" if seconds is not None else "",
                disabled=pending, focused=nav.__dict__.get("_global_offer_focus") == identity,
                acceptLabel="@feedback.ready" if key.startswith("match:") else "@online.accept_invite" if key.startswith("invite:") else "@online.accept_challenge",
                declineLabel="@online.cancel_match" if key.startswith("match:") else "@online.decline_invite" if key.startswith("invite:") else "@online.decline_challenge",
                reviewLabel="@feedback.review_offer", hint="@feedback.offer_hint", versus="@feedback.vs",
                status=state.get("message") if pending else "", accept=accept, decline=decline))
    return sorted(rows, key=lambda row: row["serial"], reverse=True)


def click_global(nav, identity, accept):
    if nav.overlay == "binding" or getattr(nav, "native_edit", "") or nav.overlay == "osk":
        return False
    row = next((row for row in global_view(nav) if row["identity"] == identity), None)
    if not row or row["disabled"]:
        return False
    game = next(g for g in nav.games if g.id == row["game"])
    nav._global_offer_focus = ""
    if accept:
        nav._cancel_hold()
        nav.overlay = None
        nav._select_game(game)
        nav.screen = "hub"
        nav.main_menu_game = ""
        nav.sec[game.id] = "online"
    origin_focus = dict(nav.focus)
    success = nav._online_action(game, row["accept"] if accept else row["decline"])
    if not accept:
        nav.focus = origin_focus
    if not success:
        nav._global_offer_answers.pop(identity, None)
    return success


def global_action(nav, action):
    if nav.overlay == "binding" or getattr(nav, "native_edit", "") or nav.overlay == "osk":
        return False
    rows = global_view(nav)
    if action == "offers" and rows:
        nav._global_offer_focus = rows[0]["identity"]
        nav._cancel_hold()
        return True
    focused = next((row for row in rows if row["focused"]), None)
    if not focused:
        return False
    if action in ("confirm", "back"):
        click_global(nav, focused["identity"], action == "confirm")
    elif action in ("up", "down", "prev", "next"):
        index = rows.index(focused)
        nav._global_offer_focus = rows[(index + (-1 if action in ("up", "prev") else 1)) % len(rows)]["identity"]
    elif action == "offers":
        nav._global_offer_focus = ""
    return True


def activity_view(nav):
    for g in nav.games:
        state = getattr(g.a, "online_state", lambda: {})()
        phase = state.get("phase")
        if phase in ("searching", "cancelling", "matched", "starting", "playing", "result", "result_sent"):
            return dict(game=g.id, current=g is nav.game, phase=phase, label="@feedback.return_activity", name=i18n.literal(g.short),
                        status=state.get("message") or "@online.status")
    return {}


def return_activity(nav):
    activity = activity_view(nav)
    if not activity or nav.overlay == "binding":
        return False
    game = next(g for g in nav.games if g.id == activity["game"])
    nav._select_game(game)
    nav.screen = "hub"
    nav.main_menu_game = ""
    nav.overlay = None
    nav.sec[game.id] = "online"
    if activity["phase"] in ("searching", "cancelling"):
        nav._go_chapter(nav.items(), "lobby")
        rows = nav.items()
        nav.focus[nav.key()] = next((n for n, row in enumerate(rows) if row.get("id") == "cancel"), nav.focus_index(rows))
    return True


def match_view(nav, g):
    """The VS presentation contains only public adapter data, never inferred match terms."""
    from .nav_online_layout import connection
    from .nav_common import uri
    from .nav_challenges import _details
    state = getattr(g.a, "online_state", lambda: {})()
    if state.get("phase") not in ("matched", "starting", "playing", "result", "result_sent"):
        return {}
    match = state.get("match") or {}
    me = state.get("me") or {}
    you_char, opp_char = match.get("you_char"), match.get("opp_char")
    picked = state.get("phase") in ("matched", "starting") and all(
        isinstance(key, str) and key and key != "random" for key in (you_char, opp_char))

    def player(info, name, pick, mirrored=False):
        main = info.get("main") or ""
        fighter = pick if picked else main
        return dict(name=i18n.literal(str(name)), rank=i18n.literal(str(info.get("rank") or "")),
                    rating=str(info["rating"]) if info.get("rating") is not None else "",
                    region=i18n.literal(str(info.get("region") or info.get("country") or "")),
                    fighter=i18n.literal(str(g.a.fighter_label(fighter))) if fighter else "",
                    main=i18n.literal(str(g.a.fighter_label(main))) if main else "", mainLabel="@online_ui.col.main", picked=bool(picked),
                    art=uri(g.a.fighter_image(fighter)) if fighter else "",
                    render=uri(g.a.fighter_render(fighter, mirrored=mirrored)) if fighter else "",
                    plate=uri(g.a.rank_plate(info.get("tier"))) if info.get("tier") is not None else "")
    opponent = match.get("opponent")
    opponent_info = match.get("opponent_info") if isinstance(match.get("opponent_info"), dict) else match
    if isinstance(opponent, dict):
        opponent_info, opponent = opponent, opponent.get("name", "")
    else:
        roster = [person for person in state.get("players") or [] if person.get("name") == opponent]
        if len(roster) == 1:
            opponent_info = dict(roster[0], **opponent_info)
    details = _details(match)
    for detail in details:
        if detail.get("k") == "@online.challenge_delay":
            detail["k"] = "@input_delay"
    feel = match.get("online_feel") or (state.get("netext") or {}).get("online_feel")
    if feel in ("responsive", "balanced", "smooth"):
        details.append(dict(k="@netext.online_feel", v="@netext." + feel))
    if "delay" not in match:
        details.append(dict(k="@online.challenge_delay", v="@unknown"))
    if type(match.get("ranked")) is bool and "mode" not in match:
        details.append(dict(k="@feedback.mode", v="@online.ranked_mode" if match["ranked"] else "@online.casual_mode"))
    for field, label in (("mode", "@feedback.mode"), ("rounds", "@feedback.rounds")):
        if type(match.get(field)) in (str, int):
            value = {"ranked": "@online.ranked_mode", "casual": "@online.casual_mode", "challenge": "@online.challenge"}.get(match[field]) if field == "mode" else None
            details.append(dict(k=label, v=value or i18n.literal(str(match[field]))))
    row = next((row for row in global_view(nav) if row["game"] == g.id and row["kind"] == "match"), {})
    ready = match.get("opponent_ready")
    starting = state.get("phase") == "starting" and ready is True
    waiting = state.get("phase") == "starting" and not starting
    delay = next((detail["v"] for detail in details if detail["k"] in ("@input_delay", "@online.challenge_delay")), "@unknown")
    compact = [i18n.localize("@feedback.delay_short", nav.language) + " " + i18n.localize(delay, nav.language)]
    compact += [detail["v"] for detail in details if detail["k"] == "@feedback.mode"]
    compact += [str(match["rounds"]) + " " + i18n.localize("@feedback.rounds", nav.language)] if "rounds" in match else []
    conn = connection(match)
    compact += [conn["text"], conn["path"]]
    info_line = i18n.literal(" \u00b7 ".join(i18n.localize(part, nav.language) for part in compact if part))
    return dict(gameId=g.id, left=player(me, me.get("name") or state.get("name") or "", you_char),
                right=player(opponent_info, opponent or "", opp_char, mirrored=True), connection=connection(match), details=details,
                game=i18n.literal(g.short), versus="@feedback.vs", countdown=row.get("countdown", ""),
                seconds=row.get("seconds"), readyLabel="@online.waiting_peer_ready" if waiting else "@feedback.ready",
                disabled=bool(state.get("busy")) or state.get("phase") == "starting",
                phase=state.get("phase"), starting=starting, waiting=waiting,
                startingLabel="@online.starting", declineLabel="@online.cancel_match", infoLine=info_line,
                status="@online.starting" if starting else "@online.waiting_peer_ready" if waiting else "",
                opponentStatus="@feedback.opponent_ready" if ready is True else "@feedback.opponent_waiting" if ready is False else "")
