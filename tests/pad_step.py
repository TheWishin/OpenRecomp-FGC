"""One controller step towards a row: left/right inside a line of buttons (the online lobby page's groups),
up/down between lines."""


def pad_step(nav, target):
    items = nav.items()
    focus = nav.focus_index(items)
    group = items[focus].get("group") if 0 <= focus < len(items) else None
    if group and 0 <= target < len(items) and items[target].get("group") == group:
        nav.act("right" if focus < target else "left", device="xbox")
    else:
        nav.act("down" if focus < target else "up", device="xbox")
