"""One controller step towards a row: left/right inside a line of buttons (the online lobby page's groups),
up/down between lines."""


def pad_step(nav, target):
    items = nav.items()
    focus = nav.focus_index(items)
    if nav.section() == "online" and any(it.get("region") == "chat" for it in items) \
            and not any(it.get("id") == "arcade_options" for it in items):
        region, source = items[target].get("region"), items[focus].get("region")
        if (region == "chat") != (source == "chat"):
            nav.act("x", device="xbox")
            return
        if region == "chat":
            visible = nav._visible_chat_rows(items, focus)
            if target in visible and focus in visible and target != focus:
                nav.act("down" if visible.index(focus) < visible.index(target) else "up", device="xbox")
            return
    if nav.section() == "online" and any(it.get("id") == "arcade_options" for it in items):
        from openrecomp import nav_arcade
        region = items[target].get("region")
        if nav_arcade.active(nav, items, focus) and region in ("lobby", "rooms", "friends", "leaderboard", "stats", "profile", "tournaments", "spectating", "account") and region != nav._chapter_of_focus(items, focus):
            _, current_floor = nav_arcade.routes(nav, items, focus)
            if any(current_floor[name] for name in ("optionsOpen", "moreOpen", "helpOpen")):
                nav.act("back", device="xbox")
                return
        if region in ("lobby", "rooms", "friends", "leaderboard", "stats", "profile", "tournaments", "spectating", "account") \
                and nav._chapter_of_focus(items, focus) != region:
            chapters = [c["id"] for c in nav.view()["online"]["chapters"]]
            current = nav._chapter_of_focus(items, focus)
            forward = (chapters.index(region) - chapters.index(current)) % len(chapters)
            backward = (chapters.index(current) - chapters.index(region)) % len(chapters)
            nav.act("chapterNext" if forward <= backward else "chapterPrev", device="xbox")
            return
        if not nav_arcade.active(nav, items, focus):
            source_region = items[focus].get("region")
            if region == "chat":
                if source_region != "chat":
                    nav.act("x", device="xbox")
                    return
                visible = nav._visible_chat_rows(items, focus)
                if target not in visible:
                    toggle = next((n for n in visible if items[n].get("id") == "chat_toggle"), None)
                    if toggle == focus:
                        nav.act("confirm", device="xbox")
                    return
                source = visible.index(focus) if focus in visible else 0
                goal = visible.index(target)
                if source != goal:
                    nav.act("down" if source < goal else "up", device="xbox")
                return
            if source_region == "chat":
                nav.act("x" if nav.__dict__.get("chat_back", {}).get(nav.game.id) else "chapterNext", device="xbox")
                return
        if nav_arcade.active(nav, items, focus):
            rows, floor = nav_arcade.routes(nav, items, focus)
            if floor["helpOpen"] and target != floor["controls"]["help"]["index"]:
                nav.act("back", device="xbox")
                return
            source_region = items[focus].get("region")
            if region == "chat" and source_region != "chat":
                if floor["optionsOpen"] or floor["moreOpen"]:
                    nav.act("back", device="xbox")
                elif any(player["index"] == focus for player in floor["players"]):
                    nav.act("right", device="xbox")
                elif any(player["focused"] for player in floor["players"]):
                    nav.act("up", device="xbox")
                else:
                    nav.act("x", device="xbox")
                return
            if source_region == "chat" and region != "chat":
                nav.act("left", device="xbox")
                return
            visible = {n for row in rows for n in row}
            if target not in visible and (floor["optionsOpen"] or floor["moreOpen"]):
                nav.act("back", device="xbox")
                return
            destination = target
            target_card = next((p for p in floor["players"]
                                if target != p["index"] and any(b["index"] == target for b in p["buttons"] + p["more"])), None)
            if target_card and focus == target_card["index"] and not floor["moreOpen"] and target in visible \
                    and target in {b["index"] for b in target_card["buttons"]}:
                nav.act("left", device="xbox")
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
