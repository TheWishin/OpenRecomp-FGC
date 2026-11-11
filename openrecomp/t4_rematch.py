"""Tekken 4: the rematch question in the game, the part of adapters/t4_online.py that is files (the T4 port's docs/DIRECTFIGHT_T4.md, "Rematch question in the game").

The two games ask and decide by themselves, from the pad inputs netplay exchanges anyway. The launcher's part is
small and all of it is files next to the game's result file (TEKKEN4_NET_RESULT):

    <stem>.json           match 1 of the session; its field "rematch" says what the question after it did:
                          off (not asked in this session) | pending | rematch | declined | timeout
    <stem>-m<k>.json      match k >= 2 of the session (a rematch in the running game), same fields
    <stem>-next.json      written by the launcher: {"index": k, "match": "<lobby match id>"} -- the lobby's id of
                          the session's k-th match, once the server made the rematch

Capability as T5DR's, but OFF by default while Tekken 4 is a beta (the T4 game's own default is off too): on only with
T4_INGAME_REMATCH=1, and only with a game that has it (its program file names the switch TEKKEN4_INGAME_REMATCH).
Everything else falls back to the launcher's own rematch. Turning the default on is DEFAULT below.
"""
import json
import os
import re

SWITCH = "T4_INGAME_REMATCH"
DEFAULT = "1"              # on: the question is the default (as T5DR's since 1.2.0); the owner decided 2026-11-11
GAME_SWITCH = "TEKKEN4_INGAME_REMATCH"
MARKER = GAME_SWITCH.encode("ascii")
STATES = ("off", "pending", "rematch", "declined", "timeout")
HOLD_SECONDS = 25.0        # the game may stay this long after its result for the question (2 s + 7.5 s + a margin)
CONTINUE_SECONDS = 12.0    # ... and this long after both said yes for the lobby's match_start {continue}
_MATCH_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def wanted(env=None):
    """The question in the game: T4_INGAME_REMATCH=1 turns it on, 0 off, unset = DEFAULT (off: the launcher asks)."""
    value = (os.environ if env is None else env).get(SWITCH, DEFAULT).strip()
    return value == "1"


def game_has_it(exe):
    """Does this game build know the question? Its program file carries the switch's name."""
    try:
        with open(exe, "rb") as stream:
            tail = b""
            while True:
                chunk = stream.read(1 << 20)
                if not chunk:
                    return False
                if MARKER in tail + chunk:
                    return True
                tail = chunk[-len(MARKER):]
    except (OSError, TypeError, ValueError):
        return False


def tagged(base, tag):
    """base with tag before its extension: t4_result-x.json + "-m2" -> t4_result-x-m2.json (as the game does)."""
    stem, ext = os.path.splitext(base)
    return stem + tag + ext


def result_path(base, index):
    return base if index <= 1 else tagged(base, "-m%d" % index)


def next_path(base):
    return tagged(base, "-next")


def clear(base):
    """Before a game starts: nothing of an earlier session next to its result file."""
    folder, name = os.path.split(base)
    stem, ext = os.path.splitext(name)
    stale = [next_path(base), next_path(base) + ".tmp"]
    try:
        for entry in os.listdir(folder or "."):
            if re.fullmatch(re.escape(stem) + r"-m\d+" + re.escape(ext) + r"(\.tmp)?", entry):
                stale.append(os.path.join(folder, entry))
    except OSError:
        pass
    for path in stale:
        try:
            os.remove(path)
        except OSError:
            pass


def state(path):
    """The "rematch" field of a match's result file, or None (no file yet, half written, an older game)."""
    try:
        with open(path, encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return None
    value = data.get("rematch") if isinstance(data, dict) else None
    return value if value in STATES else None


def write_next(base, index, match_id):
    """Name the lobby match of the session's match `index` for the running game. False: not a plain id."""
    match_id = str(match_id)
    if isinstance(index, bool) or not isinstance(index, int) or not 2 <= index <= 64 or not _MATCH_ID.match(match_id):
        return False
    path = next_path(base)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="ascii") as stream:
        json.dump({"index": index, "match": match_id}, stream)
    os.replace(temporary, path)          # the game opens it shared for delete
    return True
