"""One support line per Tekken 5 DR game start, like T5DR's own launcher writes into launcher.log:

    game started: process N, log <file>, settings give K=V, ..., asked for by the launcher: NAME, ...

The settings are what the install's settings object gives the game as environment (env_overrides); what the
launcher adds for a match (online fight lines, names, saves) is listed by name only. Private values are masked the way
the install's problem report masks them (its Scrubber: Windows user name in paths and anywhere else, the PC name,
lobby player names, addresses, tokens), and the line goes where that report reads it (launcher.log in the install).
"""
import getpass
import os
import re

_USER_PATH = re.compile(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/,;\"']+")


def _fallback_mask(text, names):
    text = _USER_PATH.sub(lambda m: m.group(1) + "<user>", text)
    for name in names:
        if len(name) >= 3:
            text = re.sub(r"(?i)(?<![A-Za-z0-9_<])" + re.escape(name) + r"(?![A-Za-z0-9_>])", "<player>", text)
    return text


def line(adapter, pid, extra_env=None):
    """The unmasked line."""
    settings = adapter.s.env_overrides() if hasattr(adapter.s, "env_overrides") else {}
    given = ", ".join(f"{k}={v}" for k, v in sorted(settings.items())) or "nothing"
    asked = ", ".join(sorted(extra_env or {})) or "nothing"
    log = os.path.basename(getattr(getattr(adapter, "game", None), "log_path", "") or "") or "-"
    return f"game started: process {pid}, log {log}, settings give {given}, asked for by the launcher: {asked}"


def mask(adapter, text):
    names = {str(adapter.s.get("nickname") or "").strip()} if hasattr(adapter.s, "get") else set()
    names.discard("")
    try:
        names.add(getpass.getuser())
    except Exception:  # noqa: BLE001
        pass
    try:
        report = adapter._support_import("problem_report")       # noqa: SLF001 -- the install's own scrubber
        return report.Scrubber(player_names=names, replay_paths=[adapter.s.out_dir]).text(text)
    except Exception:  # noqa: BLE001 -- no scrubber: the plain rules, never the raw line
        return _fallback_mask(text, names)


def write(adapter, pid, extra_env=None):
    """Mask and log; never raises (a log must not stop a game start)."""
    try:
        text = mask(adapter, line(adapter, pid, extra_env))
        log = getattr(adapter.core, "log", None)
        if callable(log):
            log(text)
        return text
    except Exception:  # noqa: BLE001
        return ""
