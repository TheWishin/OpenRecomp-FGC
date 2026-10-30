"""Client-only T4 rank labels, maintained independently of lobby ratings."""
import json
import math
from pathlib import Path


def t4_rank_name(rating, table=None):
    """Return the label for a rating, or nothing for empty or invalid mappings."""
    if (isinstance(rating, bool) or not isinstance(rating, (int, float))
            or (isinstance(rating, float) and not math.isfinite(rating))):
        return ""
    if table is None:
        try:
            table = json.loads((Path(__file__).parent / "data" / "t4_ranks.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
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
