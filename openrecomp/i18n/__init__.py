"""Small JSON catalog loader used by the launcher and its controller."""
import json
import locale
from functools import cache
from pathlib import Path

_HERE = Path(__file__).parent
LANGUAGES = ("en", "de", "es", "fr", "ja", "ko", "pt-BR")


def system_language():
    """One of our catalog codes, based on the current locale."""
    name = "en"
    for get_locale in (locale.getlocale, locale.getdefaultlocale):
        try:
            detected = get_locale()[0]
        except (ValueError, OSError):
            continue
        if detected:
            name = detected
            break
    name = name.replace("_", "-")
    if name.lower().startswith("pt-br"):
        return "pt-BR"
    code = name.split("-", 1)[0].lower()
    return code if code in LANGUAGES else "en"


def normalize(code):
    return code if code in LANGUAGES else system_language()


def catalog(code):
    return _catalog(normalize(code))


@cache
def _catalog(code):
    try:
        with (_HERE / (code + ".json")).open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def text(code, key, **values):
    """Return a catalog message, always falling back to English then its key."""
    english = catalog("en").get(key, key)
    message = catalog(code).get(key, english)
    return message.format(**values)


def message(key, **values):
    """A deferred message: keep values separate until the view chooses a language."""
    return dict(_text=key, _values=values)


def literal(value):
    """Keep player-entered and server-supplied text distinct from catalog references."""
    return dict(_literal=str(value))


def error_message(error):
    """Keep our deferred messages; leave a game's own error text as supplied."""
    value = error.args[0] if error.args else None
    if isinstance(value, dict) and value.get("_text") in catalog("en") and isinstance(value.get("_values"), dict):
        return value
    return str(error)


def localize(value, code):
    """Replace catalog keys in a plain view dictionary without touching game titles."""
    if isinstance(value, dict):
        if set(value) == {"_literal"}:
            return value["_literal"]
        if value.get("_text") in catalog("en"):
            return text(code, value["_text"], **localize(value["_values"], code))
        return {k: localize(v, code) for k, v in value.items()}
    if isinstance(value, list):
        return [localize(v, code) for v in value]
    if isinstance(value, str) and value.startswith("@") and value[1:] in catalog("en"):
        return text(code, value[1:])
    return value
