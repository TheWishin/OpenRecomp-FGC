"""Rank tiers on top of Glicko-2: Tekken 7's rank names, in Tekken 7's order (Tekken 4 Online).

The owner's choice (2026-11-04): T4 ranked uses Tekken 7's ranks. The list is Tekken 7's final one (Season 4
on: Tekken God Omega added above Tekken God Prime; source and check in docs/T4_RANKED.md): Beginner, 9th Kyu ..
1st Kyu, 1st Dan .. 3rd Dan, then the named Dan ranks Initiate .. Tekken God Omega -- 47 tiers. Only the NAMES are
Tekken 7's; the badges are our own pictures (tools/make_rank_badges.py in the launcher and the game), never
Namco's emblems. Index = tier: TEKKEN4_HUD_RANKS hands the tier to the game's name plates as is. T4 ratings and
ranks are separate from T5DR's (shared accounts, a profile per game).

Thresholds: like T5DR's (docs/RANKED.md "Ranks"): 8th Kyu at 1150, 50 points per Kyu step, 40 from 2nd Kyu to 3rd
Dan; then 30 points per named rank up to Tekken King (2500) -- Tekken 7 has more ranks than Tekken 5 DR in the same
rating range -- and 50 per god rank above (Tekken God Omega 2700).

How a player moves through the tiers (all numbers in RankRules):

* Placement: the first `placement` ranked matches of an account are placement
  matches. Meanwhile the tier is Beginner (index 0, what the game shows for a new
  profile). After the last one the tier is set straight from the rating, at most
  `placement_cap` (Beginner is never reached again).
* Promotion: as soon as the rating reaches a higher tier's threshold, the player
  is promoted (several tiers at once if the rating jumped).
* Demotion, with hysteresis: only when the rating falls `hysteresis` points
  below the current tier's threshold, and not during the `shield` matches after
  a promotion. The new tier is the highest one whose threshold is within
  `hysteresis` points of the rating, so it is not lost again right away.
  Kyu ranks are never lost (as in the arcade): a player drops at most to 1st
  Dan once they have reached it, and never below their placement tier while
  they are in the Kyu ranks.
* Provisional: while the rating deviation (RD) is above `provisional_rd` the
  rating is still a rough guess; the UI shows the tier with a "?" (also during
  placement).
"""
from dataclasses import dataclass

from .i18n import t

# (name, rating threshold). Index 0 = Beginner (unplaced), index 1 has no threshold (the floor).
RANKS = [
    ("Beginner", None),
    ("9th Kyu", None), ("8th Kyu", 1150), ("7th Kyu", 1200), ("6th Kyu", 1250), ("5th Kyu", 1300),
    ("4th Kyu", 1350), ("3rd Kyu", 1400), ("2nd Kyu", 1440), ("1st Kyu", 1480),
    ("1st Dan", 1520), ("2nd Dan", 1560), ("3rd Dan", 1600),
    ("Initiate", 1630), ("Mentor", 1660), ("Expert", 1690), ("Grand Master", 1720), ("Brawler", 1750),
    ("Marauder", 1780), ("Fighter", 1810), ("Vanguard", 1840), ("Warrior", 1870), ("Vindicator", 1900),
    ("Juggernaut", 1930), ("Usurper", 1960), ("Vanquisher", 1990), ("Destroyer", 2020), ("Savior", 2050),
    ("Overlord", 2080), ("Genbu", 2110), ("Byakko", 2140), ("Seiryu", 2170), ("Suzaku", 2200),
    ("Mighty Ruler", 2230), ("Revered Ruler", 2260), ("Divine Ruler", 2290), ("Eternal Ruler", 2320), ("Fujin", 2350),
    ("Raijin", 2380), ("Yaksa", 2410), ("Ryujin", 2440), ("Emperor", 2470), ("Tekken King", 2500),
    ("Tekken God", 2550), ("True Tekken God", 2600), ("Tekken God Prime", 2650), ("Tekken God Omega", 2700),
]
BEGINNER = 0
FIRST_DAN = 10
NAMES = [n for n, _ in RANKS]
OLD_NAMES = {}                  # (T5DR's servers before 1.1.4 sent other words for two tiers; T4 never did)


# Tekken 7's colour groups (first tier, last tier, key): the badges' colours and shapes (make_rank_badges.py).
GROUPS = [
    (0, 0, "beginner"), (1, 9, "kyu"), (10, 12, "dan"), (13, 16, "lightblue"), (17, 20, "green"), (21, 24, "yellow"),
    (25, 28, "orange"), (29, 32, "red"), (33, 36, "ruler"), (37, 40, "blue"), (41, 42, "purple"), (43, 46, "gold"),
]


def group(tier):
    """The colour group key of a tier ("kyu", "gold", ...)."""
    for lo, hi, key in GROUPS:
        if lo <= tier <= hi:
            return key
    return "beginner"


def threshold(tier):
    """Rating at which `tier` starts (float('-inf') for the floor tiers)."""
    t = RANKS[tier][1]
    return float("-inf") if t is None else float(t)


def tier_for(rating):
    """Highest tier (>= 1) whose threshold the rating reaches."""
    best = 1
    for i in range(1, len(RANKS)):
        if rating >= threshold(i):
            best = i
    return best


def name(tier):
    return NAMES[max(0, min(len(NAMES) - 1, int(tier)))]


def index(name_or_tier):
    """'2nd Dan' / '2nd dan' / 11 -> 11; None when unknown."""
    if isinstance(name_or_tier, int):
        return name_or_tier if 0 <= name_or_tier < len(RANKS) else None
    low = str(name_or_tier).strip().lower()
    for i, n in enumerate(NAMES):
        if n.lower() == low:
            return i
    return OLD_NAMES.get(low)


def display_name(info):
    """The rank's name for the UI: from the tier when the server sent one (an older server's names map to
    today's), else the name it sent."""
    tier = info.get("tier") if info else None
    if isinstance(tier, int) and 0 <= tier < len(NAMES):
        return NAMES[tier]
    rank = (info or {}).get("rank") or ""
    i = index(rank) if rank else None
    return NAMES[i] if i is not None else rank


@dataclass
class RankRules:
    placement: int = 5          # placement matches before the first real tier
    placement_cap: int = 12     # 3rd Dan: the highest tier placement can give
    hysteresis: float = 30.0    # rating points below a tier's threshold before demotion
    shield: int = 3             # matches after a promotion without demotion
    provisional_rd: float = 110.0


@dataclass
class RankState:
    tier: int = BEGINNER        # current tier (index into RANKS)
    games: int = 0              # ranked matches that counted
    since_change: int = 0       # ranked matches since the last tier change
    peak: int = BEGINNER        # highest tier ever held
    floor: int = BEGINNER       # placement tier (Kyu ranks below it are never given back)

    def as_dict(self):
        return {"tier": self.tier, "games": self.games, "since_change": self.since_change, "peak": self.peak,
                "floor": self.floor}


def after_match(state, rating, rules=None):
    """State after one more counted ranked match that left the rating at `rating`.
    -> (new RankState, event): event is None, 'placed', 'promoted' or 'demoted'."""
    rules = rules or RankRules()
    s = RankState(state.tier, state.games + 1, state.since_change + 1, state.peak, state.floor)
    event = None
    if s.games < rules.placement:
        s.tier = BEGINNER
    elif state.tier == BEGINNER:
        s.tier = max(1, min(rules.placement_cap, tier_for(rating)))
        s.floor = s.tier
        s.since_change = 0
        event = "placed"
    else:
        target = tier_for(rating)
        if target > s.tier:
            s.tier = target
            s.since_change = 0
            event = "promoted"
        elif rating < threshold(s.tier) - rules.hysteresis and s.since_change > rules.shield:
            low = tier_for(rating + rules.hysteresis)
            # Kyu ranks are never lost: not below 1st Dan once reached, not below the placement tier.
            low = max(low, FIRST_DAN if s.peak >= FIRST_DAN else s.floor, 1)
            if low < s.tier:
                s.tier = low
                s.since_change = 0
                event = "demoted"
    s.peak = max(s.peak, s.tier)
    return s, event


def describe(state, rd, rules=None):
    """What the lobby shows: {tier, rank, provisional, placement: [played, needed] or None}."""
    rules = rules or RankRules()
    placing = state.tier == BEGINNER and state.games < rules.placement
    return {"tier": state.tier, "rank": name(state.tier),
            "provisional": bool(placing or rd > rules.provisional_rd),
            "placement": [state.games, rules.placement] if placing else None}


def record_label(rec, draws=False):
    """[wins, losses(, draws)] -> '5W 3L' (and ' 1D' when asked for and not zero)."""
    out = t("{wins}W {losses}L", wins=rec[0], losses=rec[1])
    if draws and len(rec) > 2 and rec[2]:
        out += " " + t("{draws}D", draws=rec[2])
    return out


def label(info):
    """'2nd Dan', '2nd Dan?' (provisional), 'Beginner (placement 2/5)'."""
    if not info:
        return ""
    if info.get("placement"):
        n, k = info["placement"]
        return t("{rank} (placement {done}/{total})", rank=display_name(info), done=n, total=k)
    return display_name(info) + ("?" if info.get("provisional") else "")
