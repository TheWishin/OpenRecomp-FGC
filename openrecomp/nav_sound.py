"""The menu sound of a press: Nav's state before and after it, named by ui_sound.classify(). No Qt, no audio.

Every press goes through Nav.act() or one of Nav's click_*() methods (the mouse); both run inside sounded(), so a pad,
the keyboard and the mouse make the same sound for the same change. The app takes it with take_sound() after every
press and tick and plays it (ui_sound.UiSounds). Things that happen on their own (a match found, an update offer)
note theirs with note_sound().
"""
import math

from . import ui_sound


def _scalars(value):
    if not isinstance(value, dict):
        return None
    return tuple(sorted((k, v) for k, v in value.items() if isinstance(v, (str, int, float, bool))))


class Sound:
    pending_sound = None
    sound_hint = None
    _sound_depth = 0

    def _sound_state(self):
        try:
            g = self.game
            return dict(
                screen=self.screen, overlay=self.overlay or "",
                kind=self.confirm_kind if self.overlay == "dialog" else "",
                game=g.id if g else "", section=self.sec.get(g.id) if g else None,
                focus=tuple(sorted(self.focus.items())), start=self.start_focus, exit=self.exit_focus,
                drawer=self.drawer_focus, grid=self.grid_focus, picker=_scalars(self.picker), osk=_scalars(self.osk),
                results=self.show_results, log=_scalars(getattr(self, "build_log_open", None)),
                toast=self.toast, toast_left=self.toast_left, holding=self.holding is not None,
                language=self.language, fullscreen=self.fullscreen, motion=self.reduced_motion,
                prereleases=self.game_prereleases)
        except Exception:  # noqa: BLE001 -- a sound must never break a press
            return None

    def sounded(self, action, fn, *args, **kwargs):
        """Run one press (fn) and note the sound it made; presses inside it (a click that confirms) count once."""
        outer = not self._sound_depth
        if outer:
            self.sound_hint = None
            before = self._sound_state()
        self._sound_depth += 1
        try:
            return fn(*args, **kwargs)
        finally:
            self._sound_depth -= 1
            if outer:
                try:
                    self.note_sound(ui_sound.classify(action, before, self._sound_state(), self.sound_hint))
                except Exception:  # noqa: BLE001 -- as above
                    pass
                self.sound_hint = None

    def hint_sound(self, name):
        """The press says what it did itself: a refused row (ui_sound.ERROR wins over anything else)."""
        if self._sound_depth:
            self.sound_hint = ui_sound.louder(self.sound_hint, name) if self.sound_hint == ui_sound.ERROR else name

    def hint_toggle(self, value, step=1):
        """A setting got value (ui_sound.toggle: on / off)."""
        self.hint_sound(ui_sound.toggle(value, step))

    def observe_online_sound(self, g, state):
        """Ready/result sounds follow public adapter transitions, once per match and outcome."""
        match = state.get("match") or {}
        phase = state.get("phase")
        result = (state.get("set") or {}).get("result") or match.get("result") or state.get("result")
        if not isinstance(result, str):
            result = ""
        if state.get("message") in ("@online.set_won", "@online.set_lost"):
            result = "win" if state["message"] == "@online.set_won" else "loss"
        snapshot = (str(state.get("netext_session") or ""), str(match.get("id") or ""), phase, result)
        seen = self.__dict__.setdefault("_online_sound_seen", {})
        previous = seen.get(g.id)
        seen[g.id] = snapshot
        if previous == snapshot or any(game.a.running() for game in self.games):
            return
        if phase == "starting" and (previous is None or previous[:3] != snapshot[:3]):
            self.note_sound(ui_sound.READY)
        elif phase in ("result", "result_sent") and result in ("win", "won", "loss", "lost"):
            # result -> result_sent is the same outcome, not a second fanfare.
            if previous is None or previous[:2] != snapshot[:2] or previous[3] != result:
                self.note_sound(ui_sound.WIN if result in ("win", "won") else ui_sound.LOSS)

    def tick_offer_sounds(self):
        """One warning at each of the last three seconds; no timer or work when there are no offers."""
        audible = None
        for row in self.__dict__.get("_global_offer_clock", {}).values():
            seconds = row.get("seconds")
            if type(seconds) not in (int, float) or not math.isfinite(seconds):
                continue
            remaining = max(0, math.ceil(seconds - row["age"]))
            previous = row.get("soundSecond")
            row["soundSecond"] = remaining
            if 1 <= remaining <= 3 and remaining != previous:
                audible = ui_sound.COUNTDOWN
        if audible and not any(game.a.running() for game in self.games):
            self.note_sound(audible)

    def note_sound(self, name):
        if name:
            self.pending_sound = ui_sound.louder(self.pending_sound, name)

    def take_sound(self):
        """-> the sound to play now (None when there is none)."""
        name, self.pending_sound = self.pending_sound, None
        return name
