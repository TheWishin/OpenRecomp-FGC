"""Local ordering of received community rows. No requests or adapter mutations."""


OPTIONS = {
    "rooms": (("recommended", "@community_ui.recommended"), ("name", "@community_ui.name"),
              ("players", "@community_ui.players"), ("ping", "@community_ui.ping")),
    "friends": (("status", "@community_ui.status"), ("name", "@community_ui.name")),
    "tournaments": (("status", "@community_ui.status"), ("name", "@community_ui.name")),
    "spectating": (("rank", "@community_ui.live_rank"), ("name", "@community_ui.name"),
                   ("ping", "@community_ui.ping")),
}


def number(value, missing=float("inf")):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else missing


def room_count(room):
    count = room.get("players", room.get("members"))
    return len(count) if isinstance(count, (list, tuple)) else number(count, 0)


def key(region, mode, row):
    name = str(row.get("name") or "").casefold()
    ping = number(row.get("ping"))
    if mode == "name":
        return (name,)
    if mode == "ping":
        return ping, name
    if region == "rooms":
        count = room_count(row)
        if mode == "players":
            return -count, ping, name
        maximum = number(row.get("size", row.get("maximum")), 0)
        open_seat = row.get("status") == "open" and maximum > count
        return not open_seat, ping, name
    if region == "friends":
        return {"online": 0, "in_match": 1}.get(row.get("status"), 2), name
    if region == "tournaments":
        return {"signup": 0, "checkin": 1, "running": 2, "finished": 3, "cancelled": 4}.get(row.get("state"), 5), name
    # Missing rank/ping stay unknown, after known values. Never manufacture a ranking.
    return -number(row.get("tier"), -float("inf")), ping, name


def apply(nav, game, state, by_region):
    memory = nav.__dict__.setdefault("community_sort", {}).setdefault(game.id, {})
    sources = dict(rooms=state.get("rooms") or [], friends=state.get("friends") or [],
                   tournaments=(state.get("tournaments") or {}).get("rows") or [],
                   spectating=(state.get("spectating") or {}).get("targets") or [])
    prefixes = dict(rooms=("join_room:", "room_watch:"),
                    friends=("invite_friend:", "invite_room:", "remove_friend:"),
                    tournaments=("tour_select:",), spectating=("spec_watch_",))
    for region, options in OPTIONS.items():
        rows = by_region[region]
        if not rows:
            continue
        mode = memory.get(region, options[0][0])
        if mode not in dict(options):
            mode = options[0][0]
        source = sources[region]
        ordered = sorted(source, key=lambda row: key(region, mode, row))
        order = {str(row.get("name") if region == "friends" else row.get("id")): n
                 for n, row in enumerate(ordered)}

        def row_key(item):
            iid = item.get("id") or ""
            identity = iid if region == "spectating" else iid.partition(":")[2]
            return order.get(identity, len(order))

        positions = [n for n, item in enumerate(rows) if str(item.get("id") or "").startswith(prefixes[region])]
        sorted_rows = sorted((rows[n] for n in positions), key=row_key)
        for position, item in zip(positions, sorted_rows):
            rows[position] = item
        def choose(value, region=region, options=options):
            if value in dict(options):
                memory[region] = value

        control = dict(kind="cycler", id="community_sort:" + region, region=region,
                       label="@community_ui.sort", options=list(options), current=mode,
                       value=next(label for value, label in options if value == mode),
                       set=choose,
                       hint="", detail=dict(kicker="@community_ui.sort", title="@community_ui.sort", rows=[]))
        insert_at = next((n + 1 for n, row in enumerate(rows) if row.get("id") in
                          ("refresh_rooms", "refresh_friends", "tour_refresh")), 0)
        rows.insert(insert_at, control)
