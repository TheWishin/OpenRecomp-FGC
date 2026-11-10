"""Tekken Tag Tournament 2 (TAG2 PC): account, team and Ranked screens on top of the manifest game.

games/tag2.json finds the install, shows its updates and opens TAG2's own launcher. This adapter adds what data
cannot do, through TAG2's own launcher Core (tag2_core.py): sign in / create account, play offline and online,
the Ranked team with outfits, the Ranked request and the Ranked record. Nothing of TAG2's service or matchmaking
is rebuilt here, and the Core, the game and TAG2's launcher are used unchanged.

Rules kept (TAG2 0.16.33 integration handover):
- account.dat stays where the Core keeps it, protected for this Windows user; it is never read, copied or shown.
- A refused saved sign-in ("sign in again") is shown once; nothing is retried by itself.
- Every request to TAG2's service follows a button the player pressed.
- The rows that talk to TAG2's live service (sign in, play online, Ranked) are off unless switched on
  (OPENRECOMP_TAG2_ONLINE=1 or "tag2": {"online": true} in the config): without the switch the Online section is the
  manifest's (TAG2's own launcher), and no request is sent.
"""
import json
import os
import threading
import types

from .. import i18n
from ..audio_output import default_audio_output
from ..manifest import save_config
from .manifest_game import ManifestGame
from .tag2_core import Core, CoreError

def _fighters():
    """TAG2's character names by id (openrecomp/data/tag2_fighters.json; the index is the game's character id)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tag2_fighters.json")
    try:
        with open(path, encoding="utf-8") as stream:
            names = json.load(stream)["fighters"]
        return tuple(str(name) for name in names)
    except (OSError, ValueError, KeyError, TypeError):
        return ()


FIGHTERS = _fighters()
SETTINGS = (          # id, Core field, label, [(value, label)]
    ("tag2_skip_intros", "SkipStartupIntros", "@tag2.setting.skip_intros", ((False, "@off"), (True, "@on"))),
    ("tag2_backend", "GraphicsBackend", "@tag2.setting.backend",
     (("d3d12", i18n.literal("Direct3D 12")), ("vulkan", i18n.literal("Vulkan")))),
    ("tag2_scale", "RenderScale", "@tag2.setting.scale",
     ((1, i18n.literal("1x")), (2, i18n.literal("2x")), (3, i18n.literal("3x")))),
    ("tag2_vsync", "PresentVSync", "@tag2.setting.vsync", ((False, "@off"), (True, "@on"))),
)
DEFAULTS = dict(SkipStartupIntros=False, GraphicsBackend="d3d12", RenderScale=1, PresentVSync=False)
MAX_SETTINGS_BYTES = 1024 * 1024
LIVE_ROWS = ("tag2_sign_in", "tag2_register", "tag2_other_account", "tag2_play_online", "tag2_ranked",
             "tag2_ranked_cancel", "tag2_progress")


class Tag2(ManifestGame):
    native_label = "@tag2.native_label"
    STOP_WAIT = 5

    def __init__(self, manifest, config=None, *, core=None, **kwargs):
        super().__init__(manifest, config, **kwargs)
        self.core = core if core is not None else Core(self.root, on_event=self._event)
        if core is not None:
            core.on_event = self._event
        self._op = None                 # dict(kind, call): the one request that is running
        self._status = ""               # the Core's progress line of that request
        self._message = ""              # what the last request said
        self._toast = ""
        self._dirty = False
        self._game = None               # dict(pid, kind) of the game the Core started for us
        self._need_sign_in = False
        self._other_account = False
        self._name = ""
        self._password = ""
        self._pick = 0
        self._slots = {}                # character id -> outfit slots the game named in the last Ranked request
        self._progress = None
        self._account = None            # the Core's answer once it was asked
        self._saved = None              # the Core's settings once it was asked
        self.audio_output = default_audio_output     # True / False / None (cannot tell); tests replace it
        self._stop_timer = None

    def live(self):
        """The account, online and Ranked rows: only when the player (or a tester) switched them on."""
        stored = self.config.get("tag2") if isinstance(self.config, dict) else None
        return os.environ.get("OPENRECOMP_TAG2_ONLINE") == "1" or (isinstance(stored, dict) and stored.get("online") is True)

    # ---------------------------------------------------------------- the Core
    def core_problem(self):
        return self.core.problem() if self.root else "@tag2.core_missing"

    def _event(self, event):
        kind = event.get("event")
        if kind in ("game_exit", "closed"):
            if kind == "closed" or (self._game or {}).get("pid") == event.get("pid"):
                self._game = None
        elif kind == "game" and type(event.get("pid")) is int:      # a game the Core started before a request failed
            self._game = dict(pid=event["pid"], kind=str(event.get("kind") or ""))
        self._dirty = True

    def _busy(self):
        return self._op is not None

    def _request(self, kind, op, **fields):
        if self._busy():
            raise RuntimeError("@tag2.busy")
        self._status = ""
        self._op = dict(kind=kind, call=self.core.request(op, **fields))
        self._dirty = True

    def section_poll(self):
        """Called by the launcher's timer: finish a request that answered. -> True when the rows changed."""
        changed, self._dirty = self._dirty, False
        op = self._op
        if op is not None:
            if op["call"].status != self._status:
                self._status = op["call"].status
                changed = True
            if op["call"].done.is_set():
                self._op = None
                self._status = ""
                self._finish(op["kind"], op["call"])
                changed = True
        return changed

    def section_toast(self):
        toast, self._toast = self._toast, ""
        return toast

    def _say(self, message):
        self._message = self._toast = message

    def _finish(self, kind, call):
        if call.error is not None:
            self._failed(call.error)
            return
        result = call.result if isinstance(call.result, dict) else {}
        if kind == "account":
            self._account = dict(has_account=bool(result.get("has_account")), name=str(result.get("name") or ""))
            self._need_sign_in = self._other_account = False
            self._name = self._password = ""
            self._progress = None
            self._say(self.message("tag2.signed_in_as", name=i18n.literal(self._account["name"])))
        elif kind in ("play", "ranked"):
            if type(result.get("pid")) is int:
                self._game = dict(pid=result["pid"], kind=str(result.get("kind") or ""))
                game = self._game
                self._playtime_online_launch = game["kind"] != "offline"
                try:
                    self._track_playtime(lambda: self._game is game, process=types.SimpleNamespace(pid=game["pid"]))
                finally:
                    self._playtime_online_launch = False
            if kind == "ranked":
                for row in result.get("team") or ():
                    if isinstance(row, dict) and type(row.get("id")) is int:
                        self._slots[row["id"]] = [s for s in row.get("slots") or () if type(s) is int and s >= 0]
                outcome = str(result.get("outcome") or "")
                if outcome in ("accepted", "searching"):
                    self._say("@tag2.ranked_searching")
                else:
                    self._say(self.message("tag2.ranked_answer", answer=i18n.literal(result.get("code") or outcome or "?")))
            else:
                self._message = ""
        elif kind == "progress":
            self._progress = result
            self._message = ""

    def _failed(self, error):
        kind = getattr(error, "kind", "error")
        text = getattr(error, "message", "") or ""
        if kind == "sign_in":
            # The service no longer takes the saved sign-in (a newer sign-in elsewhere replaced it): ask once.
            self._need_sign_in = True
            self._say("@tag2.sign_in_again")
        elif kind == "build":
            self._say("@tag2.build_needed")
        elif kind == "cancelled":
            self._say("@tag2.cancelled")
        elif kind == "bridge":
            self._say(text if text.startswith("@tag2.") else "@tag2.core_failed")
        else:
            self._say(i18n.literal(text) if text else "@tag2.core_failed")     # the Core's own sentence

    # ---------------------------------------------------------------- state
    def status(self):
        st = super().status()
        if self.ready() and st["status"] == "@ready":
            why = self.core_problem()
            if why:
                st["detail"] = why
            elif self._busy() and self._status:
                st["detail"] = i18n.literal(self._status)
            elif self._message:
                st["detail"] = self._message
        return st

    def _local(self, name):
        return os.path.join(self.root, "local", name)

    def _has_account(self):
        if self._account is not None:
            return self._account["has_account"]
        return bool(self.root) and os.path.isfile(self._local("account.dat"))     # only whether it exists

    def _settings_file(self):
        try:
            with open(self._local("launcher-settings.json"), "rb") as stream:
                data = stream.read(MAX_SETTINGS_BYTES + 1)
            value = json.loads(data.decode("utf-8")) if len(data) <= MAX_SETTINGS_BYTES else {}
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _player_name(self):
        if self._account is not None and self._account["name"]:
            return self._account["name"]
        name = self._settings_file().get("PlayerName")
        return name if isinstance(name, str) else ""

    # ---------------------------------------------------------------- playing
    def start(self, extra_env=None):
        """Play offline through the Core (its shader preparation, its arguments and environment)."""
        if self.core_problem():
            return super().start(extra_env)             # as the manifest alone: TAG2's own launcher
        if self.running():
            raise RuntimeError("@generic.running")
        self._request("play", "play", mode="offline")
        return 0

    def start_warning(self, what):
        """A warning the player confirms before this start ("" = none). TAG2's public build can end right after
        start when Windows has no playback device; the start is not held back and nothing is worked around."""
        if what not in ("start", "tag2_play_online", "tag2_ranked") or self.core_problem() or self._game is not None:
            return ""
        return "@tag2.no_audio" if self.audio_output() is False else ""

    def open_native(self):
        if self._game is not None or self._busy():
            raise RuntimeError("@generic.running")
        return super().start()

    def running(self):
        return (self._game is not None or (self._op or {}).get("kind") in ("play", "ranked")
                or super().running())

    def stop(self):
        game = self._game
        if game is None:
            super().stop()
            return
        if self._stop_timer is not None:                # Stop again while it closes: end it now
            self.core.request("stop", force=True)
            return
        self.core.request("stop")

        def end():
            self._stop_timer = None
            if self._game is game:
                self.core.request("stop", force=True)
        self._stop_timer = threading.Timer(self.STOP_WAIT, end)
        self._stop_timer.daemon = True
        self._stop_timer.start()

    def section_close(self):
        if self._stop_timer is not None:
            self._stop_timer.cancel()
        self.core.close()

    # ---------------------------------------------------------------- settings (the Core validates and saves)
    def settings(self):
        if not self.root or self.core_problem():
            return []
        values = self._saved if self._saved is not None else self._settings_file()
        out = []
        for sid, field, label, options in SETTINGS:
            value = values.get(field, DEFAULTS[field])
            if not any(type(o) is type(value) and o == value for o, _label in options):
                value = DEFAULTS[field]
            out.append(dict(id=sid, label=label, hint="@tag2.setting.hint", lead="@tag2.setting.hint",
                            options=list(options), value=value))
        return out

    def quick_settings(self):
        return [s[0] for s in SETTINGS]

    def set_setting(self, sid, value):
        if self.running():
            raise RuntimeError("@generic.running")
        entry = next((s for s in SETTINGS if s[0] == sid), None)
        if entry is None or not any(type(o) is type(value) and o == value for o, _label in entry[3]):
            raise RuntimeError("@generic.settings_error")
        try:
            saved = self.core.call("settings_set", values={entry[1]: value})
        except CoreError as e:
            raise RuntimeError(i18n.literal(e.message) if e.message and not e.message.startswith("@") else "@tag2.core_failed") from e
        self._saved = saved if isinstance(saved, dict) else None

    # ---------------------------------------------------------------- Ranked team
    def _prefs(self):
        stored = self.config.get("tag2")
        return stored if isinstance(stored, dict) else {}

    def team(self):
        team = self._prefs().get("team")
        if (isinstance(team, list) and len(team) == 2 and all(type(c) is int and 0 <= c < len(FIGHTERS) for c in team)
                and team[0] != team[1]):
            return list(team)
        return None

    def _remember(self, **values):
        stored = dict(self._prefs(), **values)
        self.config["tag2"] = stored
        try:
            save_config(self.config)
        except (OSError, ValueError):
            pass

    def fighters(self):
        return [dict(key=str(i), name=name, image="") for i, name in enumerate(FIGHTERS)]

    def pick_fighter_slot(self, slot):
        self._pick = 1 if slot == 1 else 0

    def chosen_fighter(self):
        team = self._prefs().get("team")
        if isinstance(team, list) and len(team) == 2 and type(team[self._pick]) is int and 0 <= team[self._pick] < len(FIGHTERS):
            return str(team[self._pick])
        return "random"

    def set_fighter(self, key):
        if not str(key).isdigit() or int(key) >= len(FIGHTERS):
            return                                      # Ranked needs two real fighters: Random keeps the choice
        team = self._prefs().get("team")
        team = list(team) if isinstance(team, list) and len(team) == 2 else [-1, -1]
        team[self._pick] = int(key)
        self._remember(team=team)

    def costumes(self, key):
        slots = self._slots.get(int(key)) if str(key).isdigit() else None
        if not slots:
            return []
        return ([dict(button=1, name="@tag2.costume_default")]
                + [dict(button=slot + 2, name=self.message("tag2.costume_slot", n=slot + 1)) for slot in slots])

    def _costume(self, character):
        value = (self._prefs().get("costumes") or {}).get(str(character), -1)
        return value if type(value) is int and value >= -1 else -1

    def chosen_costume(self, key):
        return self._costume(key) + 2 if str(key).isdigit() else 0

    def set_costume(self, key, button):
        if str(key).isdigit() and type(button) is int and button >= 1:
            costumes = dict(self._prefs().get("costumes") or {})
            costumes[str(key)] = button - 2
            self._remember(costumes=costumes)

    # ---------------------------------------------------------------- online rows
    def text_value(self, tid):
        return {"online_name": self._name, "online_password": self._password}.get(tid, "")

    def set_text_value(self, tid, value):
        if tid == "online_name":
            self._name = str(value)[:64]
        elif tid == "online_password":
            self._password = str(value)[:128]

    def _row(self, iid, label, hint, verb="@confirm", disabled=False, value="", **more):
        return dict(kind="action", id=iid, label=label, verb="" if disabled else verb, hint=hint, value=value,
                    disabled=disabled, detail=dict(kicker="@section.online", title=label, lead=hint, leadLines=6,
                                                   rows=more.pop("rows", [])), **more)

    def online_items(self):
        why = self.core_problem()
        if why:
            return [self._row("tag2_core", "@tag2.account", why, disabled=True)] + super().online_items()
        if not self.live():
            return super().online_items()               # TAG2's own launcher signs in and finds matches
        busy = self._busy()
        line = i18n.literal(self._status) if busy and self._status else ("@tag2.working" if busy else self._message)
        signed = self._has_account() and not self._need_sign_in
        if signed:
            head = self.message("tag2.signed_in_as", name=i18n.literal(self._player_name() or "?"))
        else:
            head = "@tag2.sign_in_again" if self._need_sign_in else "@tag2.not_signed_in"
        out = [self._row("tag2_status", "@tag2.account", line or head, disabled=True, value=head)]
        if not signed or self._other_account:
            out += self._login_rows(busy)
        if signed:
            out += self._play_rows(busy)
        return out

    def _login_rows(self, busy):
        ready = bool(self._name.strip() and self._password) and not busy
        note = "@tag2.sign_in_hint" if ready or busy else "@tag2.need_name_password"
        return [
            dict(self._row("online_name", "@online.name", "@tag2.name_hint", verb="@change", value=i18n.literal(self._name)),
                 opens="text:online_name"),
            dict(self._row("online_password", "@online.password", "@tag2.sign_in_hint", verb="@change",
                           value=i18n.literal("•" * len(self._password))), opens="text:online_password"),
            self._row("tag2_sign_in", "@tag2.sign_in", note, disabled=not ready),
            self._row("tag2_register", "@tag2.create_account", "@tag2.create_account_hint" if ready else note,
                      disabled=not ready),
        ]

    def _play_rows(self, busy):
        game = self._game
        team = self.team()
        out = [self._row("tag2_play_online", "@tag2.play_online", "@tag2.play_online_hint", verb="@start",
                         disabled=busy or self.running()),
               dict(kind="heading", label="@tag2.ranked")]
        for slot, label in ((0, "@tag2.team_first"), (1, "@tag2.team_second")):
            self_team = self._prefs().get("team")
            chosen = self_team[slot] if isinstance(self_team, list) and len(self_team) == 2 else -1
            known = type(chosen) is int and 0 <= chosen < len(FIGHTERS)
            costume = self._costume(chosen) if known else -1
            value = i18n.literal(FIGHTERS[chosen]) if known else "@missing"
            rows = [dict(k="@fighter.costume", v="@tag2.costume_default" if costume < 0
                         else self.message("tag2.costume_slot", n=costume + 1))] if known else []
            out.append(dict(self._row("tag2_team_%d" % slot, label, "@tag2.team_hint", verb="@choose", value=value,
                                      disabled=busy, rows=rows), opens="fighters:%d" % slot))
        if (self._op or {}).get("kind") == "ranked":
            out.append(self._row("tag2_ranked_cancel", "@tag2.ranked_cancel", "@tag2.ranked_cancel_hint", verb="@cancel"))
        else:
            offline = game is not None and game["kind"] == "offline"
            blocked = busy or team is None or offline or super().running()
            hint = "@tag2.choose_team" if team is None else "@tag2.ranked_hint"
            out.append(self._row("tag2_ranked", "@tag2.ranked_search", hint, verb="@start", disabled=blocked))
        out.append(self._row("tag2_progress", "@tag2.progress", "@tag2.progress_hint", disabled=busy,
                             rows=self._progress_rows()))
        if not self._other_account:
            out.append(self._row("tag2_other_account", "@tag2.other_account", "@tag2.other_account_hint",
                                 disabled=busy or self.running()))
        return out

    def _progress_rows(self):
        p = self._progress
        if not isinstance(p, dict):
            return []
        rows = [dict(k="@tag2.record", v=i18n.literal("%s / %s" % (p.get("ranked_wins") or 0, p.get("ranked_losses") or 0))),
                dict(k="@tag2.player_record", v=i18n.literal("%s / %s" % (p.get("player_wins") or 0, p.get("player_losses") or 0)))]
        for rank in (p.get("ranks") or ())[:12]:
            if isinstance(rank, dict) and type(rank.get("character")) is int and 0 <= rank["character"] < len(FIGHTERS):
                rows.append(dict(k=i18n.literal(FIGHTERS[rank["character"]]),
                                 v=self.message("tag2.rank_row", rank=rank.get("rank", 0), points=rank.get("points", 0))))
        return rows

    def run_online(self, item_id):
        """A row the player pressed. Each one is at most one request to the Core; none repeats by itself."""
        if item_id == "own":
            self.open_native()
            return ""
        if item_id in LIVE_ROWS and not self.live():
            return ""
        if item_id in ("tag2_sign_in", "tag2_register"):
            if not (self._name.strip() and self._password):
                return "@tag2.need_name_password"
            password, self._password = self._password, ""
            self._request("account", "sign_in" if item_id == "tag2_sign_in" else "register",
                          name=self._name.strip(), password=password)
        elif item_id == "tag2_other_account":
            self._other_account = True
        elif item_id == "tag2_play_online":
            if self.running():
                raise RuntimeError("@generic.running")
            self._request("play", "play", mode="online")
        elif item_id == "tag2_ranked":
            team = self.team()
            if team is None:
                return "@tag2.choose_team"
            self._request("ranked", "ranked", team=team, costumes=[self._costume(team[0]), self._costume(team[1])])
        elif item_id == "tag2_ranked_cancel":
            self.core.request("ranked_cancel")
        elif item_id == "tag2_progress":
            self._request("progress", "progress")
        return ""
