"""Controller choices and ready-check text for native casual match rules."""
from . import i18n


def detail_rows(state):
    rules = state.get("match_rules") or {}
    out = []
    if rules.get("training"):
        out.append(dict(k="@online.room", v="@online.training_rule"))
    if ("you" in rules and "opponent" in rules
            and (rules["you"], rules["opponent"]) != (100, 100)):
        out.append(dict(k="@online.life", v=i18n.message("online.match_health",
                                                       you=rules["you"], opponent=rules["opponent"])))
    return out


def rows(nav, g, state, action):
    if not (state.get("capabilities") or {}).get("handicap"):
        return []
    rules = state.get("rules") or {}
    maximum = 150 if rules.get("maximum") == 150 else 100
    choices = [(value, str(value) + " %") for value in range(maximum, 29, -10)]
    current = rules.get("life", 100)
    return [dict(kind="cycler", id="rules_life", label="@online.life", value=str(current) + " %",
                 current=current, options=choices, hint="@online.life_hint",
                 detail=dict(kicker="@section.online", title="@online.life", lead="@online.life_hint", rows=[]),
                 set=lambda value: nav._online_action(g, "rules_life:" + str(value)))]
