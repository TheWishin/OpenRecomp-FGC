"""The launcher's menu sounds: which sound a press made, and the small player that sends it to Windows. No Qt here.

The WAVs in ui/sounds are made by tools/make_ui_sounds.py (synthesized there, nothing taken from a game or a sound
pack). Nav compares its state before and after a press (nav_sound.py) and classify() names the sound; the app plays
it, only while the launcher's window is in front and no game runs. A pad, the keyboard and the mouse make the same
sound for the same change.

    move        the focus moved (a row, a tile, a key of the on-screen keyboard, a dialog's answer)
    confirm     a choice was taken (Confirm / Start / a click), a hold finished
    back        Back
    tab         another section, game or online chapter (LB/RB, PgUp/PgDn, Q/E, a tab clicked)
    toggle_on   a setting switched on / to its next value
    toggle_off  a setting switched off / to its previous value
    open        an overlay opened (Quick access, a dialog, the keyboard, the file list, ...)
    close       an overlay closed without a choice
    error       refused: the launcher said it is busy, failed, or the row is disabled
    notify      a match was found, an update is offered

Playback: PlaySoundW from winmm with SND_MEMORY | SND_ASYNC, on one worker thread, so the GUI thread never waits for
the audio system. A new sound cuts the one still playing (Windows plays one PlaySound per process), so holding a
direction never piles sounds up; a move also waits MOVE_GAP_S after the last one. PlaySound opens the default output
device for every sound, so a changed default device (headset plugged in, Windows settings) is used from the next
sound on; without any output device nothing plays (no Windows default sound either) and nothing is said. The volume is applied to the samples here
(PlaySound has no volume of its own). Anything else than Windows (or Wine) stays silent.

OPENRECOMP_UI_SOUND=0 in the environment turns the real output off (tests, recordings).
"""
import array
import io
import os
import threading
import time
import wave

SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "sounds")
MOVE, CONFIRM, BACK, TAB, ERROR, NOTIFY = "move", "confirm", "back", "tab", "error", "notify"
TOGGLE_ON, TOGGLE_OFF, OPEN, CLOSE = "toggle_on", "toggle_off", "open", "close"
NAMES = (MOVE, CONFIRM, BACK, TAB, ERROR, NOTIFY, TOGGLE_ON, TOGGLE_OFF, OPEN, CLOSE)
# When two sounds come from one press or one tick, the one that says the most wins.
PRIORITY = {ERROR: 9, NOTIFY: 8, OPEN: 7, CLOSE: 6, CONFIRM: 5, BACK: 5, TAB: 4, TOGGLE_ON: 3, TOGGLE_OFF: 3, MOVE: 1}
# Nav's actions (nav.py) as classify() reads them; CLICK_TAB = a tab clicked with the mouse.
CLICK_TAB = "tab"
MOVES = ("up", "down", "left", "right")
TABS = ("prev", "next", "chapterPrev", "chapterNext", "switchGame", CLICK_TAB)
CHOICES = ("confirm", "play")
# A message whose catalog key holds one of these is a refusal: the error sound instead of the press's own.
REFUSED_WORDS = ("busy", "fail", "blocked", "not_", "wrong", "unavailable", "already", "error", "denied", "refused",
                 "required", "invalid", "disconnected")
VOLUMES = (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)
DEFAULT_VOLUME = 50           # percent: soft next to a video call or music
DEFAULT_ON = True
MOVE_GAP_S = 0.045            # a held direction repeats ~30x/s: at most one tick per 45 ms
SAME_GAP_S = 0.025            # any other sound: the same one twice within 25 ms is one sound


def louder(first, second):
    """-> the sound with the higher priority (the first when equal or one is None)."""
    if not second:
        return first
    if not first:
        return second
    return second if PRIORITY.get(second, 0) > PRIORITY.get(first, 0) else first


def message_key(message):
    """"@library.busy" / i18n.message(...) -> the catalog key ("" for a game's own text)."""
    if isinstance(message, str):
        return message[1:] if message.startswith("@") else ""
    if isinstance(message, dict):
        return str(message.get("_text") or "")
    return ""


def refused(message):
    key = message_key(message)
    return bool(key) and any(word in key for word in REFUSED_WORDS)


def toggle(value, step=1):
    """A setting got value: on for True / the next option, off for False / the previous one."""
    if isinstance(value, bool):
        return TOGGLE_ON if value else TOGGLE_OFF
    return TOGGLE_ON if step > 0 else TOGGLE_OFF


def classify(action, before, after, hint=None):
    """-> a sound name or None for one press. before/after = Nav's state (nav_sound.Sound._sound_state); hint = what
    the press said itself (ERROR for a refused row or a failure, TOGGLE_ON / TOGGLE_OFF for a changed setting)."""
    if hint == ERROR:
        return ERROR
    if not before or not after:
        return None
    told = after["toast"] and (after["toast"] != before["toast"] or after["toast_left"] > before["toast_left"])
    if told and refused(after["toast"]):
        return ERROR
    if before["overlay"] != after["overlay"]:
        if not before["overlay"]:
            return OPEN
        if not after["overlay"]:
            return CONFIRM if action in CHOICES else BACK if action == "back" else CLOSE
        return OPEN
    if after["overlay"] == "dialog" and before["kind"] != after["kind"]:
        return OPEN                                   # one question led to the next
    if hint in (TOGGLE_ON, TOGGLE_OFF, OPEN, CLOSE, BACK):
        return hint
    if after["holding"] and not before["holding"]:
        return None                                   # the hold bar fills; its end confirms
    changed = ({k: v for k, v in after.items() if k != "toast_left"}
               != {k: v for k, v in before.items() if k != "toast_left"})
    if after["overlay"] == "osk":
        if action in CHOICES or action == "x":
            if before["osk"] == after["osk"]:
                return None
            return MOVE if action in CHOICES else BACK     # a key typed / a letter deleted
        if action == "social":
            return TAB if changed else None                # the keyboard's next page
    if before["screen"] != after["screen"]:
        return BACK if action == "back" else CONFIRM
    section_moved = (before["game"] != after["game"]
                     or before["section"] is not None and before["section"] != after["section"])
    if section_moved or action in TABS:
        return TAB if changed else None
    if action in CHOICES:
        return CONFIRM
    if action == "back":
        return BACK if changed else None
    if action in MOVES:
        return MOVE if changed else None
    return CONFIRM if changed else None


def gain(volume):
    """Percent -> sample factor; loudness follows the square, so 50 % sounds about half as loud."""
    v = max(0, min(100, int(volume))) / 100.0
    return v * v


def clean_volume(value):
    """A saved volume -> one of VOLUMES (the nearest), DEFAULT_VOLUME for anything that is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_VOLUME
    return min(VOLUMES, key=lambda v: abs(v - value))


def load(folder=SOUND_DIR):
    """-> {name: (rate, channels, int16 samples)} of the WAVs that are there and readable."""
    out = {}
    for name in NAMES:
        try:
            with wave.open(os.path.join(folder, name + ".wav"), "rb") as w:
                if w.getsampwidth() != 2:
                    continue
                samples = array.array("h")
                samples.frombytes(w.readframes(w.getnframes()))
                out[name] = (w.getframerate(), w.getnchannels(), samples)
        except (OSError, EOFError, wave.Error):
            continue
    return out


def scaled_wav(rate, channels, samples, volume):
    """-> a WAV file image of the samples at volume (percent)."""
    factor = gain(volume)
    scaled = array.array("h", (int(s * factor) for s in samples))
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(scaled.tobytes())
    return out.getvalue()


class NullOutput:
    """No sound at all: not Windows, OPENRECOMP_UI_SOUND=0, or winmm missing."""
    available = False

    def play(self, name):
        pass

    def set_volume(self, volume):
        pass

    def close(self):
        pass


class WinMMOutput:
    """PlaySoundW(SND_MEMORY | SND_ASYNC) on a worker thread; the newest request wins."""
    available = True
    SND_ASYNC, SND_NODEFAULT, SND_MEMORY = 0x0001, 0x0002, 0x0004

    def __init__(self, sounds, volume, winmm=None):
        if winmm is None:
            import ctypes
            winmm = ctypes.WinDLL("winmm")
            winmm.PlaySoundW.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)
            winmm.PlaySoundW.restype = ctypes.c_int
        self._winmm = winmm
        self._sounds = sounds
        self._volume = volume
        self._buffers = {}            # name -> ctypes buffer; alive as long as Windows may read it
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._want = None             # the newest sound asked for (older ones are dropped)
        self._volume_want = None      # a new volume (percent) the buffers are made again for
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="ui-sound", daemon=True)
        self._thread.start()

    def play(self, name):
        with self._lock:
            self._want = name
        self._wake.set()

    def set_volume(self, volume):
        with self._lock:
            self._volume_want = volume
        self._wake.set()

    def close(self):
        with self._lock:
            self._closed = True
        self._wake.set()

    def _run(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                name, self._want = self._want, None
                volume, self._volume_want = self._volume_want, None
                closed = self._closed
            try:
                if closed:
                    self._winmm.PlaySoundW(None, None, 0)
                    return
                if volume is not None and volume != self._volume:
                    self._winmm.PlaySoundW(None, None, 0)   # nothing reads the old buffers any more
                    self._buffers.clear()
                    self._volume = volume
                if name:
                    self._play_now(name)
            except Exception:  # noqa: BLE001 -- a broken audio stack must never take the launcher down
                pass

    def _play_now(self, name):
        buf = self._buffers.get(name)
        if buf is None:
            sound = self._sounds.get(name)
            if sound is None:
                return
            import ctypes
            data = scaled_wav(*sound, self._volume)
            buf = ctypes.create_string_buffer(data, len(data))
            self._buffers[name] = buf
        # A sound still playing stops here; its buffer stays in _buffers, so it is never freed while read. Without an
        # output device (none plugged in, audio service stopped) PlaySound only returns FALSE: SND_NODEFAULT keeps
        # Windows from ringing its own default sound instead. (waveOutGetNumDevs is no test: it can say 0 while the
        # default device plays.)
        self._winmm.PlaySoundW(buf, None, self.SND_MEMORY | self.SND_ASYNC | self.SND_NODEFAULT)


def make_output(sounds, volume):
    if os.name != "nt" or os.environ.get("OPENRECOMP_UI_SOUND") == "0" or not sounds:
        return NullOutput()
    try:
        return WinMMOutput(sounds, volume)
    except (OSError, AttributeError, RuntimeError):
        return NullOutput()


class UiSounds:
    """The launcher's sound setting and its gate: on/off, volume, rate limits. output = NullOutput, WinMMOutput or a
    test's recorder (anything with play(name), set_volume(percent), close())."""

    def __init__(self, enabled=DEFAULT_ON, volume=DEFAULT_VOLUME, output=None, clock=time.monotonic):
        self.enabled = bool(enabled)
        self.volume = clean_volume(volume)
        self.output = output if output is not None else make_output(load(), self.volume)
        self.clock = clock
        self._last = {}
        self.played = []              # the last sounds sent (tests and the log read it; never grows past 32)

    def configure(self, enabled, volume):
        self.enabled = bool(enabled)
        volume = clean_volume(volume)
        if volume != self.volume:
            self.volume = volume
            self.output.set_volume(volume)

    def play(self, name, active=True):
        """-> True when name went to the output. active = the window is in front and no game runs."""
        if not name or name not in PRIORITY or not self.enabled or not active:
            return False
        now = self.clock()
        gap = MOVE_GAP_S if name == "move" else SAME_GAP_S
        last = self._last.get(name)
        if last is not None and now - last < gap:
            return False
        self._last[name] = now
        self.played = (self.played + [name])[-32:]
        self.output.play(name)
        return True

    def close(self):
        self.output.close()
