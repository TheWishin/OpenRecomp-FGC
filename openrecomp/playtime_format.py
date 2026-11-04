"""Localized display of the player's local play-time records. No Qt or network."""
from datetime import date, datetime, timedelta
import math

from . import i18n


def _seconds(value):
    try:
        value = float(value)
        return max(0, value) if math.isfinite(value) else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def duration(seconds, language):
    minutes = int(_seconds(seconds) // 60)
    hours, minutes = divmod(minutes, 60)
    key = "hours_minutes" if hours and minutes else "hours" if hours else "minutes"
    return i18n.text(language, "playtime." + key, hours=hours, minutes=minutes)


def last_played(value, language, today=None):
    today = today or date.today()
    if isinstance(today, datetime):
        today = today.date()
    try:
        played = date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return i18n.text(language, "playtime.last_never")
    if played == today:
        return i18n.text(language, "playtime.last_today")
    if played == today - timedelta(days=1):
        return i18n.text(language, "playtime.last_yesterday")
    natural = language in ("ja", "ko")
    stamp = i18n.text(language, "playtime.date", year=f"{played.year:04d}",
                      month=str(played.month) if natural else f"{played.month:02d}",
                      day=str(played.day) if natural else f"{played.day:02d}")
    return i18n.text(language, "playtime.last_date", date=stamp)


def total(stats):
    return _seconds(stats.get("offline_seconds")) + _seconds(stats.get("online_seconds"))


def summary(stats, language, today=None):
    return i18n.text(language, "playtime.summary", duration=duration(total(stats), language),
                     last=last_played(stats.get("last_played"), language, today))


def profile(games, language):
    entries = []
    for game in games:
        stats = game if isinstance(game, dict) else getattr(game.a, "playtime", lambda: {})()
        short = game.get("short", "") if isinstance(game, dict) else game.short
        entries.append(i18n.text(language, "playtime.entry", game=short,
                                 duration=duration(total(stats), language)))
    return i18n.text(language, "playtime.profile", games=i18n.text(language, "playtime.separator").join(entries))
