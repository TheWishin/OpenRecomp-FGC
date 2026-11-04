"""Small JSON catalog loader used by the launcher and its controller."""
import json
import locale
import os
from functools import cache
from pathlib import Path

_HERE = Path(__file__).parent
LANGUAGES = ("en", "de", "es", "fr", "ja", "ko", "pt-BR")


# Windows' locale.getlocale() gives English names ("German_Switzerland"), not codes: every player started in English.
_NAMES = {"english": "en", "german": "de", "spanish": "es", "french": "fr", "japanese": "ja", "korean": "ko"}


def _ui_locale():
    """Windows' display language as a locale name ("de_DE"), the language Setup speaks too; None elsewhere."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        return locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except (AttributeError, OSError, ValueError):
        return None


def _code(name):
    """A catalog code for a locale name ("de_DE", "pt-BR", "German_Switzerland"), else None."""
    low = str(name or "").strip().replace("-", "_").lower()
    if not low:
        return None
    if low.startswith(("pt_br", "portuguese_brazil")):
        return "pt-BR"
    first = low.split("_", 1)[0]
    if first in _NAMES:
        return _NAMES[first]
    return first if first in LANGUAGES else None


def system_language():
    """One of our catalog codes: Windows' display language first, then the current locale; English otherwise."""
    detectors = (_ui_locale, lambda: locale.getlocale()[0], lambda: locale.getdefaultlocale()[0])
    for detect in detectors:
        try:
            code = _code(detect())
        except (ValueError, OSError):
            continue
        if code:
            return code
    return "en"


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


def template(code, key):
    """Return an unformatted catalog message for a consumer that supplies values later."""
    english = catalog("en").get(key, key)
    return catalog(code).get(key, english)


def text(code, key, /, **values):
    """Return a catalog message, always falling back to English then its key."""
    return template(code, key).format(**values)


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
