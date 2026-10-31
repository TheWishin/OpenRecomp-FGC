"""The installed game's build identity, independent of either launcher's version."""
import json
import os


def _code_id(data):
    value = data.get("code_id") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def rebuild_needed(release, out_dir):
    """True for different code, False for the same code, None when not known.

    This follows the T5DR updater's rule: compare the release Code ID with the
    actual build stamp. A launcher version or a shipped runtime is not a stamp.
    """
    expected = _code_id(release)
    if expected is None or not out_dir:
        return None
    try:
        with open(os.path.join(out_dir, "build", "t5dr_build.json"), encoding="utf-8") as stream:
            stamp = json.load(stream)
    except (OSError, ValueError):
        return None
    actual = _code_id(stamp)
    return expected != actual if actual is not None else None


def build_compatibility(release, out_dir):
    """Return same, different or unknown without changing the installed game."""
    needed = rebuild_needed(release, out_dir)
    return "unknown" if needed is None else "different" if needed else "same"
