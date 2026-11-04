"""Local play time views use only the adapter's plain snapshot."""
from . import i18n, playtime_format


def stats(game):
    return getattr(game.a, "playtime", lambda: {})()


def summary(game, language):
    return i18n.literal(playtime_format.summary(stats(game), language))


def profile(games, language):
    return i18n.literal(playtime_format.profile(games, language))


def details(game, language):
    value = stats(game)
    return [dict(k="@playtime.offline", v=i18n.literal(playtime_format.duration(value.get("offline_seconds", 0), language))),
            dict(k="@playtime.online", v=i18n.literal(playtime_format.duration(value.get("online_seconds", 0), language))),
            dict(k="@playtime.sessions", v=str(value.get("sessions", 0)))]
