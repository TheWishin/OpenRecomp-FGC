"""Private and community room controls through the selected install's lobby client."""


PREFIX = "feature_community:"
OPTIONS = dict(size=tuple(range(2, 17)), rotation=("winner", "queue"), mode=("line", "tables"),
               access=("none", "password", "code"), hidden=(False, True), training=(False, True),
               first_to=(1, 2, 3, 5, 10), rematch_policy=("both_confirm", "auto_unless_declined"),
               auto_skip_after_round=(False, True))


def init(owner):
    if not hasattr(owner, "_online_community_prefs"):
        owner._online_community_prefs = {key: values[0] for key, values in OPTIONS.items()}
        owner._online_community_pair = dict(table="", p1="", p2="")


def _cap(client, name):
    check = getattr(client, name, None)
    try:
        return bool(callable(check) and check())
    except Exception:  # an older installed client must leave unsupported actions hidden
        return False


def _text(value, limit=80):
    return str(value if value is not None else "")[:limit]


def _number(value, default=0, maximum=99999):
    return min(maximum, max(0, value)) if isinstance(value, int) and not isinstance(value, bool) else default


def _members(room):
    return [dict(id=_text(p.get("id")), name=_text(p.get("name"), 64),
                 state=p.get("state") if p.get("state") in ("away", "playing", "ready") else "")
            for p in (room.get("players") or [])[:200] if isinstance(p, dict)]


def _room(owner):
    room = getattr(owner._online_client, "my_room", None)
    if not isinstance(room, dict) or not room:
        return {}
    room = dict(room)
    for key in ("players", "line", "tables"):
        if not isinstance(room.get(key), list):
            room[key] = []
    room["line"] = [_text(pid) for pid in room["line"][:200] if isinstance(pid, (str, int))]
    room["tables"] = [dict(table) for table in room["tables"][:16] if isinstance(table, dict)]
    for table in room["tables"]:
        players = table.get("players")
        table["players"] = [_text(pid) for pid in players if isinstance(pid, (str, int))] if isinstance(players, list) else []
        info = table.get("set")
        table["set"] = dict(info) if isinstance(info, dict) else {}
        if not isinstance(table["set"].get("wins"), list):
            table["set"]["wins"] = []
    if not isinstance(room.get("guesses"), dict):
        room["guesses"] = {}
    return room


def _host(owner, room):
    me = getattr(owner._online_client, "me", None)
    return bool(isinstance(me, dict) and me.get("id") and me["id"] == room.get("owner_id"))


def _available(room):
    busy = {pid for table in room.get("tables") or [] if isinstance(table, dict)
            and (table.get("match") or (table.get("set") or {}).get("state") == "active")
            for pid in table.get("players") or []}
    line = room.get("line") or []
    return [p for p in _members(room) if p["id"] in line and p["id"] not in busy and p["state"] != "away"]


def state(owner):
    init(owner)
    client = owner._online_client
    room = _room(owner)
    private = _cap(client, "private_rooms_ok")
    welcome = getattr(client, "welcome", None)
    limits = welcome.get("room_limits") if isinstance(welcome, dict) else None
    maximum = limits.get("max_size") if isinstance(limits, dict) else None
    maximum = max(2, _number(maximum, 8, 16))
    tables = [dict(id=_text(t.get("id")), players=[_text(p) for p in (t.get("players") or [])[:2]],
                   playing=bool(t.get("match") or (t.get("set") or {}).get("state") == "active"),
                   wins=[_number(n) for n in ((t.get("set") or {}).get("wins") or [])[:2]])
              for t in (room.get("tables") or [])[:16] if isinstance(t, dict)]
    current = dict(id=_text(room.get("id")), name=_text(room.get("name"), 64),
                   size=_number(room.get("size"), 2, 16), mode="tables" if room.get("mode") == "tables" else "line",
                   rotation="queue" if room.get("rotation") == "queue" else "winner",
                   first_to=_number(room.get("first_to"), 1, 10), hidden=room.get("hidden") is True,
                   training=room.get("training") is True,
                   lock=room.get("lock") if room.get("lock") in ("password", "code") else "none",
                   host=_host(owner, room), members=_members(room), tables=tables,
                   line=[_text(p) for p in (room.get("line") or [])[:200]], available=_available(room),
                   rematch_policy=room.get("rematch_policy") if room.get("rematch_policy") in
                       OPTIONS["rematch_policy"] else "both_confirm",
                   auto_skip_after_round=room.get("auto_skip_after_round") is True,
                   wrong_passwords=_number((room.get("guesses") or {}).get("wrong")) if _host(owner, room) else 0)
    me = getattr(client, "me", None) or {}
    current["in_line"] = isinstance(me, dict) and me.get("id") in current["line"]
    current["me_id"] = _text(me.get("id")) if isinstance(me, dict) else ""
    current["status"] = _text(room.get("status"), 40)
    badges = _cap(client, "badges_ok")
    roster = getattr(client, "players", None)
    roster = {_text(p.get("id")): p for p in roster if isinstance(p, dict)} if isinstance(roster, list) else {}
    players = []
    for player in owner._online_players:
        row = dict(player)
        row["badge"] = "dev" if badges and roster.get(row.get("id"), {}).get("badge") == "dev" else ""
        players.append(row)
    return dict(capabilities=dict(community=private, room_tables=private and _cap(client, "room_tables_ok"),
                                  badges=badges, mentions=_cap(client, "mentions_ok")),
                players=players, community=dict(preferences=dict(owner._online_community_prefs),
                    maximum=maximum, room=current if room else {}, pair=dict(owner._online_community_pair),
                    first_to=_cap(client, "casual_sets_ok"), training=_cap(client, "training_ok"),
                    rematch_rules=_cap(client, "ingame_rematch_ok"), auto_skip=_cap(client, "auto_skip_ok")))


def _rules(client, prefs, size, mode, training=False):
    if size != 2 or mode != "line" or training or not _cap(client, "ingame_rematch_ok"):
        return {}
    result = dict(rematch_policy=prefs["rematch_policy"])
    if _cap(client, "auto_skip_ok"):
        result["auto_skip_after_round"] = prefs["auto_skip_after_round"]
    return result


def _password(owner):
    password = owner._online_fields.get("online_room_password", "")
    if not isinstance(password, str) or not 4 <= len(password) <= 64 or password != password.strip():
        owner._online_message = "@online.community_password_rule"
        return None
    return password


def action(owner, requested, client):
    if not requested.startswith(("community_", "mention:")):
        return False
    init(owner)
    if owner._online_busy or owner._online_phase != "logged_in" or client is not owner._online_client:
        return True
    if requested.startswith("mention:"):
        target = requested.partition(":")[2]
        player = next((p for p in getattr(client, "players", None) or []
                       if isinstance(p, dict) and str(p.get("id")) == target), None)
        if _cap(client, "mentions_ok") and player and isinstance(player.get("name"), str):
            text = owner._online_fields.get("online_chat", "")
            addition = (" " if text and not text[-1].isspace() else "") + "@" + player["name"] + " "
            if len(text + addition) <= 300:
                owner._online_fields["online_chat"] = text + addition
        return True
    if not _cap(client, "private_rooms_ok"):
        owner._online_message = "@online.social_unavailable"
        return True
    prefs = owner._online_community_prefs
    if requested.startswith("community_option:"):
        parts = requested.split(":", 2)
        if len(parts) != 3:
            return True
        _, key, raw = parts
        value = next((v for v in OPTIONS.get(key, ()) if str(v) == raw), None)
        if value is not None:
            if key == "size" and value > state(owner)["community"]["maximum"]:
                return True
            if key == "mode" and value == "tables" and not _cap(client, "room_tables_ok"):
                return True
            prefs[key] = value
        return True
    room = _room(owner)
    if requested.startswith("community_pair_option:"):
        parts = requested.split(":", 2)
        if len(parts) != 3:
            return True
        _, key, raw = parts
        if key in owner._online_community_pair:
            allowed = ([str(t.get("id")) for t in room.get("tables") or [] if isinstance(t, dict)]
                       if key == "table" else [p["id"] for p in _available(room)])
            if raw in allowed:
                owner._online_community_pair[key] = raw
        return True
    generation = owner._online_generation
    work = None
    if requested == "community_create":
        size, mode = prefs["size"], prefs["mode"]
        if size > state(owner)["community"]["maximum"] or (mode == "tables" and not _cap(client, "room_tables_ok")):
            return True
        training = prefs["training"] and _cap(client, "training_ok")
        if training and mode == "tables":
            return True
        lock = prefs["access"]
        password = _password(owner) if lock == "password" else None
        if lock == "password" and password is None:
            return True
        owner._online_fields["online_room_password"] = ""
        kwargs = dict(name=owner._online_fields.get("online_room_name", "").strip()[:64] or None,
                      ranked=False, size=size, rotation=prefs["rotation"], hidden=prefs["hidden"])
        if lock != "none":
            kwargs["private"] = lock
        if password is not None:
            kwargs["password"] = password
        if training:
            kwargs["training"] = True
        if _cap(client, "casual_sets_ok") and not training:
            kwargs["first_to"] = prefs["first_to"]
        if mode == "tables":
            kwargs["mode"] = mode
        kwargs.update(_rules(client, prefs, size, mode, training))
        work = lambda: client.create_room(**kwargs)
    elif requested in ("community_sit_out", "community_back_in_line") and room:
        work = lambda: client.room_line(back=requested == "community_back_in_line")
    elif requested == "community_copy_code" and room:
        code = getattr(client, "room_code", None)
        if isinstance(code, str):
            owner._online_fields["online_room_code"] = code[:40]
        return True
    elif _host(owner, room):
        if requested.startswith("community_kick:"):
            target = requested.partition(":")[2]
            if any(p["id"] == target for p in _members(room)) and target != str((client.me or {}).get("id")):
                work = lambda: client.room_kick(target)
        elif requested == "community_bar" and room.get("lock") == "password":
            work = client.room_bar
        elif requested == "community_pair" and room.get("mode") == "tables" and _cap(client, "room_tables_ok"):
            pair = dict(owner._online_community_pair)
            available = {p["id"] for p in _available(room)}
            table = next((t for t in room.get("tables") or [] if isinstance(t, dict)
                          and str(t.get("id")) == pair["table"] and not t.get("match")
                          and (t.get("set") or {}).get("state") != "active"), None)
            if table is not None and pair["p1"] != pair["p2"] and {pair["p1"], pair["p2"]} <= available:
                work = lambda: client.room_pair(table["id"], [pair["p1"], pair["p2"]])
        elif requested in ("community_apply", "community_new_code"):
            lock = "code" if requested == "community_new_code" else prefs["access"]
            password = _password(owner) if lock == "password" else None
            if lock == "password" and password is None:
                return True
            owner._online_fields["online_room_password"] = ""
            rules = (_rules(client, prefs, room.get("size", 2), room.get("mode", "line"), room.get("training"))
                     if room.get("status") != "playing" and not room.get("ranked") else {})
            def work():
                result = client.room_lock(lock=lock, password=password, hidden=prefs["hidden"])
                if rules:
                    owner._online_check_request(generation, client)
                    result = client.room_rules(**rules)
                return result
    if work is not None:
        def checked():
            owner._online_check_request(generation, client)
            if owner._online_phase != "logged_in":
                raise RuntimeError("@online.cancelled")
            problem = owner._online_game_check() if requested in (
                "community_create", "community_pair", "community_back_in_line") else ""
            if problem:
                raise RuntimeError(problem)
            owner._online_check_request(generation, client)
            if owner._online_phase != "logged_in":
                raise RuntimeError("@online.cancelled")
            return work()
        owner._online_submit(PREFIX + requested, checked)
    return True


def completion(owner, operation, value, error):
    if not operation.startswith(PREFIX):
        return False
    if error:
        message = owner._online_error(error)
        local_refusal = str(error) in ("@online.game_running", "@online.process_unknown", "@online.cancelled")
        if (not local_refusal and operation.removeprefix(PREFIX) in
                ("community_create", "community_pair", "community_back_in_line", "community_sit_out")):
            # A missing acknowledgement can leave a room or next turn reserved on the server.
            owner.online_close()
        owner._online_message = message
        return True
    room = value[0] if isinstance(value, tuple) and value else value
    if isinstance(room, dict) and room.get("id"):
        owner._online_own_room(room)
    owner._online_message = "@online.community_updated"
    return True


def event(owner, incoming):
    if incoming.get("t") != "chat":
        return False
    client = owner._online_client
    sender = incoming.get("from") or {}
    sender = sender if isinstance(sender, dict) else {}
    me = getattr(client, "me", None) or {}
    mentions = incoming.get("mentions")
    mentioned = bool(_cap(client, "mentions_ok") and isinstance(me, dict) and me.get("id")
                     and sender.get("id") != me["id"] and isinstance(mentions, list) and me["id"] in mentions)
    owner._online_chat.append(dict(name=_text(sender.get("name"), 64), text=_text(incoming.get("text"), 300),
        badge="dev" if _cap(client, "badges_ok") and sender.get("badge") == "dev" else "", mentioned=mentioned))
    owner._online_chat = owner._online_chat[-50:]
    return True


def close(owner):
    if hasattr(owner, "_online_community_pair"):
        owner._online_community_pair = dict(table="", p1="", p2="")
