r"""Makes the launcher's menu sounds in openrecomp\ui\sounds from nothing: sine, FM and noise with short envelopes.

    python tools\make_ui_sounds.py [folder]          (default: openrecomp\ui\sounds)

Pure Python, no packages: every sample is computed here, so the WAVs are ours (no sound pack, nothing from a game).
48 kHz, 16-bit, mono, 40-150 ms each. One family: bright FM "glass" notes over a small low punch, so it feels a little
like a fighting game's select screen without being loud. The same script always writes the same samples (the noise
comes from a fixed seed); tests/test_ui_sound.py checks the committed files against it.
"""
import math
import os
import struct
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "openrecomp", "ui", "sounds")
RATE = 48000
FADE_IN_S, FADE_OUT_S = 0.0015, 0.006    # no click at either end


class Voice:
    """A buffer the parts below are added into."""

    def __init__(self, seconds):
        self.n = int(round(RATE * seconds))
        self.buf = [0.0] * self.n

    def note(self, at, seconds, f0, f1=None, level=1.0, attack=0.002, tau=0.03, ratio=0.0, index=0.0, index_tau=0.02,
             partial=0.0):
        """A sine from f0 to f1 (exponential glide) with an FM modulator at ratio x the carrier, whose depth decays."""
        f1 = f0 if f1 is None else f1
        first, count = int(round(RATE * at)), int(round(RATE * seconds))
        phase = mod = 0.0
        for i in range(count):
            t = i / RATE
            f = f0 * (f1 / f0) ** (t / seconds)
            mod += 2 * math.pi * f * ratio / RATE
            phase += 2 * math.pi * f / RATE
            env = min(1.0, t / attack) * math.exp(-t / tau)
            depth = index * math.exp(-t / index_tau)
            w = math.sin(phase + depth * math.sin(mod))
            if partial:
                w += partial * math.sin(2 * phase)
            if first + i < self.n:
                self.buf[first + i] += level * env * w

    def thump(self, at, seconds, f0=170.0, f1=70.0, level=0.6, tau=0.02):
        """The low punch under a press: a fast pitch drop, like a soft hit."""
        self.note(at, seconds, f0, f1, level=level, attack=0.001, tau=tau)

    def noise(self, at, seconds, level=0.3, attack=0.002, tau=0.02, cutoff0=6000.0, cutoff1=None, highpass=300.0,
              seed=1):
        """White noise from a fixed seed through a low-pass that may sweep (a swoosh) and a gentle high-pass."""
        cutoff1 = cutoff0 if cutoff1 is None else cutoff1
        first, count = int(round(RATE * at)), int(round(RATE * seconds))
        state = seed * 2654435761 % 2 ** 32 or 1
        low = high_in = high = 0.0
        hp = math.exp(-2 * math.pi * highpass / RATE)
        for i in range(count):
            t = i / RATE
            state = (1664525 * state + 1013904223) % 2 ** 32
            white = state / 2 ** 31 - 1.0
            cutoff = cutoff0 * (cutoff1 / cutoff0) ** (t / seconds)
            a = 1.0 - math.exp(-2 * math.pi * cutoff / RATE)
            low += a * (white - low)
            high = hp * (high + low - high_in)
            high_in = low
            env = min(1.0, t / attack) * math.exp(-t / tau)
            if first + i < self.n:
                self.buf[first + i] += level * env * high

    def samples(self, peak):
        """-> 16-bit samples, the loudest at peak x full scale, faded in and out."""
        fade_in, fade_out = max(1, int(RATE * FADE_IN_S)), max(1, int(RATE * FADE_OUT_S))
        out = list(self.buf)
        for i in range(min(fade_in, self.n)):
            out[i] *= i / fade_in
        for i in range(min(fade_out, self.n)):
            out[self.n - 1 - i] *= i / fade_out
        top = max(abs(v) for v in out) or 1.0
        scale = peak * 32767 / top
        return [max(-32767, min(32767, int(round(v * scale)))) for v in out]


# Notes (Hz): one key (G major / E minor) for the whole set, so sounds that follow each other never clash.
G5, B5, D6, E6, FS6, G6, B6 = 783.99, 987.77, 1174.66, 1318.51, 1479.98, 1567.98, 1975.53


def move():
    """Cursor / focus moved: a short glass tick."""
    v = Voice(0.045)
    v.note(0, 0.045, E6 * 1.12, level=1.0, attack=0.0008, tau=0.010, ratio=2.0, index=0.9, index_tau=0.006)
    v.noise(0, 0.006, level=0.25, attack=0.0003, tau=0.0015, cutoff0=9000, highpass=2500, seed=3)
    return v, 0.36


def confirm():
    """A choice taken: a low punch and two rising notes."""
    v = Voice(0.13)
    v.thump(0, 0.06, 190, 75, level=0.75, tau=0.018)
    v.note(0, 0.07, B5, level=0.65, attack=0.001, tau=0.028, ratio=3.0, index=1.4, index_tau=0.015)
    v.note(0.035, 0.095, FS6, level=0.8, attack=0.001, tau=0.04, ratio=3.0, index=1.2, index_tau=0.02)
    v.noise(0, 0.01, level=0.25, attack=0.0004, tau=0.003, cutoff0=7000, highpass=1500, seed=5)
    return v, 0.50


def back():
    """Back / cancel: two softer notes going down."""
    v = Voice(0.10)
    v.note(0, 0.05, D6, level=0.8, attack=0.001, tau=0.022, ratio=1.0, index=0.6, index_tau=0.012)
    v.note(0.03, 0.07, G5, level=0.85, attack=0.0015, tau=0.03, ratio=1.0, index=0.5, index_tau=0.015)
    return v, 0.40


def tab():
    """Section / tab switched (LB/RB, PgUp/PgDn): a quick swoosh and a blip."""
    v = Voice(0.075)
    v.noise(0, 0.06, level=0.9, attack=0.012, tau=0.02, cutoff0=1500, cutoff1=9000, highpass=600, seed=7)
    v.note(0.018, 0.057, G6, level=0.55, attack=0.001, tau=0.016, ratio=2.0, index=0.8, index_tau=0.008)
    return v, 0.40


def error():
    """Refused: two low, soft buzzes (odd partials: a muted square)."""
    v = Voice(0.15)
    for at, f in ((0.0, 196.0), (0.075, 185.0)):
        for k, level in ((1, 1.0), (3, 0.33), (5, 0.16), (7, 0.08)):
            v.note(at, 0.07, f * k, level=level, attack=0.003, tau=0.035)
    return v, 0.38


def notify():
    """Something for the player (a match was found): a three-note "ready" chime."""
    v = Voice(0.15)
    v.thump(0, 0.05, 160, 80, level=0.4, tau=0.015)
    for at, f in ((0.0, G5), (0.04, D6), (0.08, G6)):
        v.note(at, 0.15 - at, f, level=0.75, attack=0.001, tau=0.045, ratio=3.5, index=1.1, index_tau=0.02,
               partial=0.15)
    return v, 0.50


def toggle_on():
    """A setting switched on / up: a short rising chirp with a click."""
    v = Voice(0.075)
    v.note(0, 0.075, 700, 1400, level=0.9, attack=0.002, tau=0.03, partial=0.2)
    v.noise(0, 0.005, level=0.25, attack=0.0003, tau=0.0012, cutoff0=9000, highpass=2500, seed=11)
    return v, 0.38


def toggle_off():
    """A setting switched off / down: the same chirp falling."""
    v = Voice(0.075)
    v.note(0, 0.075, 1400, 700, level=0.9, attack=0.002, tau=0.03, partial=0.2)
    v.noise(0, 0.005, level=0.25, attack=0.0003, tau=0.0012, cutoff0=9000, highpass=2500, seed=13)
    return v, 0.38


def open_():
    """A panel opens (Quick access, a dialog, the keyboard): a rising swoosh into a bright note."""
    v = Voice(0.11)
    v.noise(0, 0.08, level=0.7, attack=0.02, tau=0.03, cutoff0=900, cutoff1=7000, highpass=400, seed=17)
    v.note(0, 0.07, 520, 1040, level=0.35, attack=0.01, tau=0.04)
    v.note(0.045, 0.065, B6, level=0.6, attack=0.001, tau=0.02, ratio=2.0, index=0.7, index_tau=0.01)
    return v, 0.40


def close():
    """A panel closes: the swoosh falling, no bright note."""
    v = Voice(0.10)
    v.noise(0, 0.08, level=0.7, attack=0.004, tau=0.03, cutoff0=7000, cutoff1=900, highpass=400, seed=19)
    v.note(0, 0.08, 1040, 520, level=0.35, attack=0.002, tau=0.035)
    return v, 0.40


SOUNDS = {"move": move, "confirm": confirm, "back": back, "tab": tab, "error": error, "notify": notify,
          "toggle_on": toggle_on, "toggle_off": toggle_off, "open": open_, "close": close}


def render(name):
    """-> the 16-bit samples of one sound."""
    voice, peak = SOUNDS[name]()
    return voice.samples(peak)


def wav_bytes(samples):
    import io
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return out.getvalue()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    folder = argv[0] if argv else OUT
    os.makedirs(folder, exist_ok=True)
    for name in SOUNDS:
        samples = render(name)
        with open(os.path.join(folder, name + ".wav"), "wb") as f:
            f.write(wav_bytes(samples))
        print(f"{name}.wav  {len(samples) / RATE * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
