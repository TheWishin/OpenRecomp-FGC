"""A short, passive celebration of a confirmed account rank increase. No Qt."""
from . import i18n


def baseline(state):
    me = state.get("me") or {}
    tier = me.get("tier")
    name = me.get("name") or state.get("name")
    identity = me.get("id") or name
    if not state.get("account") or not identity or not name or type(tier) is not int or not 0 <= tier <= 255:
        return None
    return str(identity), str(name), tier


def observe(nav, game, before, state):
    after = baseline(state)
    cues = nav.__dict__.setdefault("_rank_cues", {})
    if after is None or before and before[:2] != after[:2]:
        cues.pop(game.id, None)
    elif before and before[:2] == after[:2] and after[2] > before[2]:
        me = state.get("me") or {}
        cues[game.id] = dict(left=5.0, label="@vibe.rank_up",
                             rank=i18n.literal(str(me.get("rank") or "")))


def tick(nav, dt):
    changed = False
    for game, cue in list(nav.__dict__.get("_rank_cues", {}).items()):
        cue["left"] -= max(0, dt)
        if cue["left"] <= 0:
            nav._rank_cues.pop(game)
            changed = True
    return changed


def view(nav):
    cue = nav.__dict__.get("_rank_cues", {}).get(nav.game.id) if nav.game else None
    return {key: cue[key] for key in ("label", "rank")} if cue else {}
