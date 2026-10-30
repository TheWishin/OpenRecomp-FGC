"""Small JSON catalog loader used by the launcher and its controller."""
import json
import locale
import os
from pathlib import Path

_HERE = Path(__file__).parent
LANGUAGES = ("en", "de", "es", "fr", "ja", "ko", "pt-BR")


def system_language():
    """One of our catalog codes, based on Windows' current UI locale."""
    name = (locale.getlocale()[0] or locale.getdefaultlocale()[0] or "en").replace("_", "-")
    if name.lower().startswith("pt-br"):
        return "pt-BR"
    code = name.split("-", 1)[0].lower()
    return code if code in LANGUAGES else "en"


def normalize(code):
    return code if code in LANGUAGES else system_language()


def catalog(code):
    try:
        with (_HERE / (normalize(code) + ".json")).open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def text(code, key, **values):
    """Return a catalog message, always falling back to English then its key."""
    english = catalog("en").get(key, key)
    message = catalog(code).get(key, english)
    return message.format(**values)


def localize(value, code):
    """Replace catalog keys in a plain view dictionary without touching game titles."""
    if isinstance(value, dict):
        return {k: localize(v, code) for k, v in value.items()}
    if isinstance(value, list):
        return [localize(v, code) for v in value]
    if isinstance(value, str) and value.startswith("@"):
        return text(code, value[1:])
    return value
