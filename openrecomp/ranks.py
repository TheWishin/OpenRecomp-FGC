"""T4 rating labels from the same ladder as the lobby and drawn badges."""
import math

from .vendor.t4lobby import ranks


def t4_rank_name(rating, table=None):
    """Return the label for a rating, or nothing for empty or invalid mappings."""
    if (isinstance(rating, bool) or not isinstance(rating, (int, float))
            or (isinstance(rating, float) and not math.isfinite(rating))):
        return ""
    if table is None:
        return ranks.name(ranks.tier_for(rating))
    if not isinstance(table, dict) or not isinstance(table.get("ranks"), list):
        return ""
    selected = ""
    previous = None
    for row in table["ranks"]:
        if not isinstance(row, dict):
            return ""
        boundary = row.get("minimum_rating")
        name = row.get("name")
        if (isinstance(boundary, bool) or not isinstance(boundary, (int, float))
                or (isinstance(boundary, float) and not math.isfinite(boundary)) or not isinstance(name, str)
                or (previous is not None and boundary <= previous)):
            return ""
        if boundary <= rating:
            selected = name.strip()
        previous = boundary
    return selected
