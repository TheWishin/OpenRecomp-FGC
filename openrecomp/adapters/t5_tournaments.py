"""Tournament views and commands delegated to the selected install's lobby client."""
import copy
import time


OPTIONS = dict(format=("single", "double"), set_wins=(2, 3),
               start_minutes=(5, 10, 15, 30, 60, 120, 180, 360, 720, 1440),
               max_players=(8, 16, 32, 64), checkin_minutes=(0, 5, 10, 15, 30, 60),
               seeding=("random", "rating"))
SUMMARY = ("id", "name", "state", "format", "set_wins", "best_of", "players", "max_players",
           "start", "start_time", "checkin_minutes", "checkin_opens", "seeding", "organizer",
           "can_manage", "rated", "champion", "rev")


def init(owner):
    if hasattr(owner, "_online_tours"):
        return
    owner._online_tours = dict(rows=[], detail={}, selected="", selected_set="", call={},
                               can_create=False, create_hint="", stale=False, pending="",
                               options=dict(format="double", set_wins=2, start_minutes=15,
                                            max_players=16, checkin_minutes=10, seeding="random"))
    owner._online_tour_refresh = dict(listed=False, list_dirty=False, detail_dirty=False,
                                      next_list=0.0, next_detail=0.0)
    for key in ("online_tour_name", "online_tour_clock", "online_tour_dq"):
        owner._online_fields.setdefault(key, "")


def close(owner):
    if hasattr(owner, "_online_tours"):
        del owner._online_tours
    init(owner)
    for key in ("online_tour_name", "online_tour_clock", "online_tour_dq"):
        owner._online_fields[key] = ""


def supported(client):
    welcome = getattr(client, "welcome", None)
    if not isinstance(welcome, dict):
        return False
    features, caps = welcome.get("features"), welcome.get("caps")
    collections = (list, tuple, set, frozenset)
    return bool(isinstance(features, collections) and "tournaments" in features
                and isinstance(caps, collections) and "tournaments" in caps
                and getattr(client, "tournaments", False)
                and callable(getattr(client, "tour_list", None))
                and callable(getattr(client, "tour_get", None)))


def _fields(value, keys):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in keys if key in value
            and isinstance(value[key], (str, int, float, bool, type(None)))}


def _summary(value):
    out = _fields(value, SUMMARY)
    if isinstance(value, dict):
        out["you"] = _fields(value.get("you"), ("entrant", "checked_in", "dq", "place", "set", "build_ok"))
    return out


def _detail(value):
    out = _summary(value)
    if not isinstance(value, dict):
        return out
    for field in ("entrants", "standings"):
        rows = value.get(field)
        out[field] = [_fields(row, ("name", "seed", "rating", "dq", "place", "checked_in"))
                      for row in rows[:256] if isinstance(row, dict)] if isinstance(rows, list) else []
    bracket = value.get("bracket")
    if isinstance(bracket, dict):
        out["bracket"] = _fields(bracket, ("format", "rounds", "losers_rounds"))
        sets = bracket.get("sets")
        out["bracket"]["sets"] = []
        for row in sets[:512] if isinstance(sets, list) else []:
            item = _fields(row, ("id", "bracket", "round", "index", "state", "live", "reason", "winner", "watch"))
            if not item:
                continue
            for key in ("p", "score", "wins", "seeds", "known"):
                val = row.get(key)
                if isinstance(val, (list, tuple)):
                    item[key] = [v if isinstance(v, (str, int, float, bool, type(None))) else None for v in val[:2]]
            out["bracket"]["sets"].append(item)
    return out


def state(owner):
    init(owner)
    result = copy.deepcopy(owner._online_tours)
    call = result.get("call") or {}
    if call:
        call["seconds"] = max(0, int(call.pop("expires", 0) - time.monotonic() + 0.99))
    return dict(tournaments=result, capabilities=dict(tournaments=supported(owner._online_client)))


def _clock(text, now):
    if not text.strip():
        return None
    try:
        hour, minute = (int(part) for part in text.strip().replace(".", ":").split(":"))
    except ValueError:
        raise ValueError("@online.tour_invalid") from None
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError("@online.tour_invalid")
    local = time.localtime(now)
    when = time.mktime((local.tm_year, local.tm_mon, local.tm_mday, hour, minute, 0, 0, 0, -1))
    if when <= now + 30:
        when = time.mktime((local.tm_year, local.tm_mon, local.tm_mday + 1, hour, minute, 0, 0, 0, -1))
    return when


def _set(owner, sid):
    return next((row for row in (owner._online_tours["detail"].get("bracket") or {}).get("sets", [])
                 if str(row.get("id")) == sid), None)


def _submit(owner, client, operation, call):
    generation = owner._online_generation

    def work():
        owner._online_check_request(generation, client)
        return call()
    owner._online_submit("feature_tour:" + operation, work)


def poll(owner):
    init(owner)
    client = owner._online_client
    data, refresh = owner._online_tours, owner._online_tour_refresh
    if (not supported(client) or getattr(owner, "_online_busy", False)
            or getattr(owner, "_online_phase", "") != "logged_in"):
        return False
    now = time.monotonic()
    listing = refresh["listed"] and refresh["list_dirty"] and now >= refresh["next_list"]
    tid = data["selected"]
    detail = bool(tid and refresh["detail_dirty"] and now >= refresh["next_detail"])
    if not listing and not detail:
        return False
    if listing:
        refresh.update(list_dirty=False, next_list=now + 4)
    if detail:
        refresh.update(detail_dirty=False, next_detail=now + 1)

    generation = owner._online_generation

    def fetch():
        listing_result = client.tour_list() if listing else None
        owner._online_check_request(generation, client)
        return dict(list=listing_result, detail=client.tour_get(tid) if detail else None, selected=tid)
    _submit(owner, client, "refresh", fetch)
    return True


def action(owner, request, client):
    if not request.startswith("tour_"):
        return False
    init(owner)
    data = owner._online_tours
    if not supported(client):
        owner._online_message = "@online.tour_unavailable"
        return True
    verb, _, target = request.partition(":")
    if verb == "tour_option":
        choices = OPTIONS.get(target)
        if choices:
            current = data["options"][target]
            data["options"][target] = choices[(choices.index(current) + 1) % len(choices)]
        return True
    if verb == "tour_refresh":
        owner._online_tour_refresh.update(next_list=time.monotonic() + 4, list_dirty=False)
        _submit(owner, client, "list", client.tour_list)
        return True
    if verb == "tour_select":
        if any(str(row.get("id")) == target for row in data["rows"]):
            data.update(selected=target, selected_set="", detail={}, pending="")
            owner._online_tour_refresh.update(next_detail=time.monotonic() + 1, detail_dirty=False)
            _submit(owner, client, "detail:" + target, lambda: client.tour_get(target))
        return True
    if verb == "tour_refresh_detail":
        if target and target == data["selected"]:
            owner._online_tour_refresh.update(next_detail=time.monotonic() + 1, detail_dirty=False)
            _submit(owner, client, "detail:" + target, lambda: client.tour_get(target))
        return True
    if verb == "tour_select_set":
        if _set(owner, target):
            data.update(selected_set=target, pending="")
        return True
    if verb == "tour_create":
        if not data["can_create"] or not getattr(owner, "_online_account", False):
            return True
        name = owner._online_fields["online_tour_name"].strip()
        try:
            now = time.time()
            start = _clock(owner._online_fields["online_tour_clock"], now)
            if len(name) < 3 or len(name) > 80:
                raise ValueError
        except ValueError:
            owner._online_message = "@online.tour_invalid"
            return True
        options = dict(data["options"])
        minutes = options.pop("start_minutes")
        start = start or now + 60 * minutes
        fmt = options.pop("format")
        _submit(owner, client, "create", lambda: client.tour_create(name, fmt=fmt, start=start, **options))
        return True
    if verb == "tour_accept":
        call = data["call"]
        expected = str((call.get("tournament") or {}).get("id", "")) + ":" + str((call.get("set") or {}).get("id", ""))
        if not call or target != expected or call.get("expires", 0) <= time.monotonic() or call.get("accepted"):
            return True
        problem = owner._online_game_check()
        if problem:
            owner._online_message = problem
            return True
        tid, _, sid = target.partition(":")
        _submit(owner, client, "accept:" + target, lambda: client.tour_accept(tid, sid))
        return True
    if verb == "tour_confirm":
        if target != data["pending"]:
            return True
        data["pending"] = ""
        return _change(owner, client, target, confirmed=True)
    if verb == "tour_abandon_change":
        data["pending"] = ""
        return True
    return _change(owner, client, request)


def _change(owner, client, request, confirmed=False):
    data = owner._online_tours
    verb, _, target = request.partition(":")
    tid, _, extra = target.partition(":")
    detail = data["detail"]
    if not tid or tid != data["selected"] or str(detail.get("id")) != tid:
        return True
    current = detail.get("state")
    you = detail.get("you") or {}
    if verb in ("tour_join", "tour_leave", "tour_checkin"):
        allowed = {"tour_join": current in ("signup", "checkin") and not you.get("entrant") and you.get("build_ok", True),
                   "tour_leave": current in ("signup", "checkin", "running") and you.get("entrant"),
                   "tour_checkin": current == "checkin" and you.get("entrant") and not you.get("checked_in")}
        if not allowed[verb] or not getattr(owner, "_online_account", False):
            return True
        if verb == "tour_leave" and current == "running" and not confirmed:
            data["pending"] = request
            return True
        method = getattr(client, verb, None)
        if callable(method):
            _submit(owner, client, "detail:" + tid, lambda: method(tid))
        return True
    if not detail.get("can_manage"):
        return True
    operation = verb.removeprefix("tour_")
    kwargs = {}
    if operation in ("start", "cancel"):
        if current not in (("signup", "checkin") if operation == "start" else ("signup", "checkin", "running")):
            return True
    elif operation in ("win0", "win1", "reset"):
        row = _set(owner, extra)
        if current != "running" or row is None or extra != data["selected_set"]:
            return True
        kwargs["set"] = extra
        if operation.startswith("win"):
            kwargs["winner"] = int(operation[-1])
            if not (row.get("p") or [None, None])[kwargs["winner"]]:
                return True
            operation = "override" if row.get("state") == "done" else "report"
    elif operation == "dq":
        player = owner._online_fields["online_tour_dq"].strip()
        if (current != "running" or player != extra
                or not any(row.get("name") == player for row in detail.get("entrants", []))):
            return True
        kwargs["player"] = player
    else:
        return True
    if not confirmed:
        data["pending"] = request
        return True
    if callable(getattr(client, "tour_admin", None)):
        _submit(owner, client, "detail:" + tid, lambda: client.tour_admin(tid, operation, **kwargs))
    return True


def completion(owner, operation, value, error):
    if not operation.startswith("feature_tour:"):
        return False
    init(owner)
    data = owner._online_tours
    if error:
        owner._online_message = owner._online_error(error)
        return True
    verb = operation.removeprefix("feature_tour:")
    if verb == "list" and isinstance(value, dict):
        rows = value.get("rows")
        data["rows"] = [_summary(row) for row in rows[:256] if isinstance(row, dict)] if isinstance(rows, list) else []
        data["can_create"] = bool(value.get("can_create"))
        data["create_hint"] = str(value.get("create_hint") or "")[:200]
        owner._online_tour_refresh["listed"] = True
    elif verb == "refresh" and isinstance(value, dict):
        listing, detail = value.get("list"), value.get("detail")
        if isinstance(listing, dict):
            completion(owner, "feature_tour:list", listing, None)
        if isinstance(detail, dict) and value.get("selected") == data["selected"]:
            data.update(detail=_detail(detail), stale=False)
    elif verb == "create" and isinstance(value, dict):
        data.update(detail=_detail(value), selected=str(value.get("id") or ""), selected_set="", stale=False)
        data["rows"] = [_summary(value)] + [row for row in data["rows"] if row.get("id") != value.get("id")]
    elif verb.startswith("detail:") and isinstance(value, dict):
        if verb.partition(":")[2] == data["selected"]:
            data.update(detail=_detail(value), stale=False)
    elif verb.startswith("accept:") and data["call"]:
        call = data["call"]
        expected = str(call["tournament"].get("id")) + ":" + str(call["set"].get("id"))
        if verb.removeprefix("accept:") == expected:
            call["accepted"] = True
    owner._online_message = "@online.tour_updated"
    return True


def event(owner, value):
    kind = value.get("t")
    if kind == "match_found" and value.get("origin") == "tournament":
        init(owner)
        owner._online_tours["call"] = {}
        return False
    if not isinstance(kind, str) or not kind.startswith("tour_"):
        return False
    init(owner)
    data = owner._online_tours
    if kind == "tour_access":
        data["can_create"] = bool(value.get("can_create"))
        data["create_hint"] = str(value.get("create_hint") or "")[:200]
        data["pending"] = ""
        owner._online_tour_refresh.update(list_dirty=True, detail_dirty=True)
    elif kind == "tour_call":
        accepted = value.get("accepted")
        deadline = value.get("deadline")
        seconds = max(0, deadline) if isinstance(deadline, (int, float)) else 0
        data["call"] = dict(tournament=_fields(value.get("tournament"), ("id", "name")),
                            set=_fields(value.get("set"), ("id", "bracket", "round")),
                            opponent=_fields(value.get("opponent"), ("name",)),
                            best_of=value.get("best_of") if isinstance(value.get("best_of"), int) else 3,
                            accepted=bool(accepted[0]) if isinstance(accepted, (list, tuple)) and accepted else False,
                            expires=time.monotonic() + seconds)
        tid = str((data["call"].get("tournament") or {}).get("id") or "")
        if tid and tid != data["selected"]:
            data.update(selected=tid, selected_set="", detail={}, pending="")
        owner._online_tour_refresh["detail_dirty"] = True
    elif kind == "tour_call_end":
        call = data["call"]
        if call and call["tournament"].get("id") == value.get("tournament") and call["set"].get("id") == value.get("set"):
            data["call"] = {}
            owner._online_tour_refresh["detail_dirty"] = True
    elif kind in ("tour_changed", "tour_notice"):
        tournament = value.get("tournament")
        changed_id = value.get("id") if kind == "tour_changed" else (
            tournament.get("id") if isinstance(tournament, dict) else None)
        owner._online_tour_refresh["list_dirty"] = True
        if str(changed_id or "") == data["selected"]:
            data["stale"] = True
            data["pending"] = ""
            owner._online_tour_refresh["detail_dirty"] = True
        owner._online_message = "@online.tour_waiting"
    return True
