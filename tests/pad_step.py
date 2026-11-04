"""One controller step towards a row: left/right inside a line of buttons (the online lobby page's groups),
up/down between lines."""


def pad_step(nav, target):
    items = nav.items()
    focus = nav.focus_index(items)
    if nav.section() == "online" and any(it.get("id") == "arcade_options" for it in items):
        from openrecomp import nav_arcade
        region = items[target].get("region")
        if region in ("lobby", "rooms", "friends", "leaderboard", "stats", "profile", "tournaments", "spectating", "account") \
                and nav._chapter_of_focus(items, focus) != region:
            chapters = [c["id"] for c in nav.view()["online"]["chapters"]]
            current = nav._chapter_of_focus(items, focus)
            forward = (chapters.index(region) - chapters.index(current)) % len(chapters)
            backward = (chapters.index(current) - chapters.index(region)) % len(chapters)
            nav.act("chapterNext" if forward <= backward else "chapterPrev", device="xbox")
            return
        if nav_arcade.active(nav, items, focus):
            rows, floor = nav_arcade.routes(nav, items, focus)
            if floor["helpOpen"] and target != floor["controls"]["help"]["index"]:
                nav.act("back", device="xbox")
                return
            visible = {n for row in rows for n in row}
            destination = target
            target_card = next((p for p in floor["players"]
                                if target != p["index"] and any(b["index"] == target for b in p["buttons"] + p["more"])), None)
            if target_card and focus == target_card["index"] and not floor["moreOpen"]:
                nav.act("play", device="xbox")
                return
            if target not in visible:
                if nav_arcade.option(items[target]):
                    destination = floor["controls"]["options"]["index"]
                else:
                    card = next((p for p in floor["players"]
                                 if any(b["index"] == target for b in p["buttons"] + p["more"])), None)
                    if card and not card["focused"] and not floor["moreOpen"]:
                        destination = card["index"]
                    elif card and card["focused"] and not floor["moreOpen"]:
                        nav.act("play", device="xbox")
                        return
                    elif region == "chat":
                        nav.act("x", device="xbox")
                        return
                    else:
                        destination = floor["controls"]["more"]["index"]
                if destination == focus:
                    nav.act("confirm", device="xbox")
                    return
            source = next(((r, row.index(focus)) for r, row in enumerate(rows) if focus in row), None)
            goal = next(((r, row.index(destination)) for r, row in enumerate(rows) if destination in row), None)
            if source and goal:
                if source[0] != goal[0]:
                    nav.act("down" if source[0] < goal[0] else "up", device="xbox")
                elif source[1] != goal[1]:
                    nav.act("right" if source[1] < goal[1] else "left", device="xbox")
                return
    group = items[focus].get("group") if 0 <= focus < len(items) else None
    if group and 0 <= target < len(items) and items[target].get("group") == group:
        nav.act("right" if focus < target else "left", device="xbox")
    else:
        nav.act("down" if focus < target else "up", device="xbox")
