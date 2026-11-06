"""What is pressed right now, for Tekken 4's Pad bindings page: XInput pads and the keyboard, in the names controls.ini uses
(t4_controls_ini.PAD_SOURCES / KEY_NAMES). Windows only (ctypes); anywhere else, or without XInput, it reports nothing.
The launcher reads these only while the page captures a button or runs the input test, never in the background."""
import ctypes
import os
import time

from . import t4_controls_ini as ini

TRIGGER = 30            # the runtime's XINPUT_GAMEPAD_TRIGGER_THRESHOLD
STICK = 0.5 * 32767     # a stick past half way counts as a direction (the runtime's "on" threshold)
PROBE_S = 1.0           # a slot without a pad is asked again at most this often
BUTTONS = ((0x0001, "DUP"), (0x0002, "DDOWN"), (0x0004, "DLEFT"), (0x0008, "DRIGHT"), (0x0010, "START"),
           (0x0020, "BACK"), (0x0040, "LS"), (0x0080, "RS"), (0x0100, "LB"), (0x0200, "RB"), (0x1000, "A"),
           (0x2000, "B"), (0x4000, "X"), (0x8000, "Y"))


def pad_name(slot):
    """The name of an XInput pad on the page (XInput's own numbering, 1-based)."""
    return "XInput %d" % (slot + 1)


class _Gamepad(ctypes.Structure):
    _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte), ("lx", ctypes.c_short),
                ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_ulong), ("pad", _Gamepad)]


def held_sources(buttons, lt, rt, lx, ly, rx, ry):
    """XInput units (y up) -> the source names held, the runtime's way: buttons, triggers past 30/255, sticks past half."""
    held = {name for bit, name in BUTTONS if buttons & bit}
    if lt > TRIGGER:
        held.add("LT")
    if rt > TRIGGER:
        held.add("RT")
    for (x, y), side in (((lx, ly), "L"), ((rx, ry), "R")):
        if y > STICK:
            held.add(side + "UP")
        elif y < -STICK:
            held.add(side + "DOWN")
        if x > STICK:
            held.add(side + "RIGHT")
        elif x < -STICK:
            held.add(side + "LEFT")
    return held


class Reader:
    """XInput slots and the keyboard. `slots()` is cached and refreshed by `step()`; `pad_held` / `keys_held` read now."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.get = None
        self.key_state = None
        self._slots = set()
        self._probe = {i: 0.0 for i in range(4)}
        if os.name == "nt":
            for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
                try:
                    self.get = getattr(ctypes.windll, name).XInputGetState
                    break
                except (OSError, AttributeError):
                    continue
            try:
                self.key_state = ctypes.windll.user32.GetAsyncKeyState
                self.key_state.restype = ctypes.c_short
            except (OSError, AttributeError):
                self.key_state = None

    def _read(self, slot):
        if self.get is None:
            return None
        state = _State()
        if self.get(slot, ctypes.byref(state)) != 0:
            return None
        g = state.pad
        return held_sources(g.buttons, g.lt, g.rt, g.lx, g.ly, g.rx, g.ry)

    def step(self):
        """Refreshes the connected slots: a present pad is checked every time, an empty slot once a second."""
        now = self.clock()
        for slot in range(4):
            if slot in self._slots:
                if self._read(slot) is None:
                    self._slots.discard(slot)
                    self._probe[slot] = now
            elif now - self._probe[slot] >= PROBE_S:
                self._probe[slot] = now
                if self._read(slot) is not None:
                    self._slots.add(slot)
        return set(self._slots)

    def slots(self):
        return set(self._slots)

    def pad_held(self, slot):
        held = self._read(slot)
        if held is None:
            self._slots.discard(slot)
            return set()
        return held

    def keys_held(self):
        if self.key_state is None:
            return set()
        held = set()
        for name, vk in ini.KEY_VK.items():
            if ini.canonical_key(name) != name:
                continue                    # one name per key
            if self.key_state(vk) & 0x8000:
                held.add(name)
        return held
