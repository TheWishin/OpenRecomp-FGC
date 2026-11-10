"""What is pressed right now, for Tekken 4's Pad bindings page: XInput pads and the keyboard, in the names controls.ini uses
(t4_controls_ini.PAD_SOURCES / KEY_NAMES). Windows only (ctypes); anywhere else, or without XInput, it reports nothing.
The launcher reads these only while the page captures a button or runs the input test, never in the background."""
import ctypes
import os
import time

from . import ps_hid
from . import t4_controls_ini as ini

TRIGGER = 30            # the runtime's XINPUT_GAMEPAD_TRIGGER_THRESHOLD
STICK = 0.5 * 32767     # a stick past half way counts as a direction (the runtime's "on" threshold)
PROBE_S = 1.0           # a slot without a pad is asked again at most this often
XINPUT_SLOTS = 4        # XInput's own slots; the game puts PlayStation pads it reads as HID devices at 4..7
HID_FIRST = XINPUT_SLOTS
BUTTONS = ((0x0001, "DUP"), (0x0002, "DDOWN"), (0x0004, "DLEFT"), (0x0008, "DRIGHT"), (0x0010, "START"),
           (0x0020, "BACK"), (0x0040, "LS"), (0x0080, "RS"), (0x0100, "LB"), (0x0200, "RB"), (0x1000, "A"),
           (0x2000, "B"), (0x4000, "X"), (0x8000, "Y"))


def pad_name(slot):
    """The name of an XInput pad on the page (XInput's own numbering, 1-based)."""
    return "XInput %d" % (slot + 1) if slot < HID_FIRST else "PlayStation pad %d" % (slot - HID_FIRST + 1)


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
    """XInput slots, PlayStation pads read as HID devices (slots 4..7, as the game numbers them) and the keyboard.
    `slots()` is cached and refreshed by `step()`; `pad_held` / `keys_held` read now. `hid`: a ps_hid.HidPads (tests);
    TEKKEN4_PAD_HID=0 turns the HID reader off, as in the game."""

    def __init__(self, clock=time.monotonic, hid=None):
        self.clock = clock
        self.hid = hid
        self._hid_slot = {}                  # pad key -> slot 4..7, kept while the pad is there
        self._hid_state = {}                 # slot -> (name, xinput names held)
        self._hid_scan = 0.0
        self.get = None
        self.key_state = None
        self._slots = set()
        self._probe = {i: 0.0 for i in range(4)}
        if self.hid is None and os.name == "nt" and os.environ.get("TEKKEN4_PAD_HID") != "0":
            self.hid = ps_hid.HidPads(xinput_present=lambda: bool(self._slots))
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
        self._hid_poll(now)
        return self.slots()

    def slots(self):
        return set(self._slots) | set(self._hid_state)

    def name(self, slot):
        known = self._hid_state.get(slot)
        return known[0] if known else pad_name(slot)

    def _hid_poll(self, now=None):
        """Scan for PlayStation pads once a second, read the reports that came; slots are kept while a pad stays."""
        if self.hid is None:
            return
        now = self.clock() if now is None else now
        try:
            if now - self._hid_scan >= PROBE_S:
                self._hid_scan = now
                self.hid.scan()
            pads = self.hid.read()
        except Exception:  # noqa: BLE001 -- a pad pulled out must not end the page
            pads = []
        keys = {pad.key for pad in pads}
        for key in [k for k in self._hid_slot if k not in keys]:
            del self._hid_slot[key]
        used = set(self._hid_slot.values())
        state = {}
        for pad in pads:
            slot = self._hid_slot.get(pad.key)
            if slot is None:
                slot = next((n for n in range(HID_FIRST, HID_FIRST + ps_hid.MAX_PADS) if n not in used), None)
                if slot is None:
                    continue
                self._hid_slot[pad.key] = slot
                used.add(slot)
            state[slot] = (pad.name, ps_hid.xinput_names(pad.pressed))
        self._hid_state = state

    def pause(self):
        """The page is not in front: let go of the PlayStation pads (they are opened again by the next step())."""
        if self.hid is not None:
            try:
                self.hid.pause()
            except Exception:  # noqa: BLE001
                pass
        self._hid_state, self._hid_slot, self._hid_scan = {}, {}, 0.0

    def pad_held(self, slot):
        if slot >= HID_FIRST:
            self._hid_poll()
            known = self._hid_state.get(slot)
            return set(known[1]) if known else set()
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
