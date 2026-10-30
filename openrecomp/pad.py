"""Controllers -> semantic actions. Qt 6 has no gamepad module: XInput directly, PlayStation pads through the HID reader
of an installed T5DR Online (t5lobby.padnav) when there is one. The launcher reads pads only while it is in front.
"""
import ctypes
import importlib
import os
import sys
import time

# (source name of a pressed thing, action); the names are padnav's, so both readers end in one table
SOURCES = (("A", "confirm"), ("B", "back"), ("X", "x"), ("Y", "social"), ("LB", "prev"), ("RB", "next"), ("START", "play"), ("BACK", "switchGame"),
           ("DUP", "up"), ("DDOWN", "down"), ("DLEFT", "left"), ("DRIGHT", "right"))
# padnav's names for a PlayStation pad: buttons in the pad's own order, the hat, the left stick (Y- is up)
PS_NAMES = {"B1": "X", "B2": "A", "B3": "B", "B4": "Y", "B5": "LB", "B6": "RB", "B9": "BACK", "B10": "START",
            "HAT_UP": "DUP", "HAT_DOWN": "DDOWN", "HAT_LEFT": "DLEFT", "HAT_RIGHT": "DRIGHT",
            "X-": "DLEFT", "X+": "DRIGHT", "Y-": "DUP", "Y+": "DDOWN"}
DIRECTIONS = {"up", "down", "left", "right"}
REPEAT_DELAY, REPEAT_RATE = 0.36, 0.12
STICK = 16000
XI_BITS = ((0x0001, "DUP"), (0x0002, "DDOWN"), (0x0004, "DLEFT"), (0x0008, "DRIGHT"), (0x0010, "START"), (0x0020, "BACK"),
           (0x0100, "LB"), (0x0200, "RB"), (0x1000, "A"), (0x2000, "B"), (0x4000, "X"), (0x8000, "Y"))


class _XInputGamepad(ctypes.Structure):
    _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte), ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]


class _XInputState(ctypes.Structure):
    _fields_ = [("packet", ctypes.c_ulong), ("pad", _XInputGamepad)]


def xinput_held(buttons, lx, ly):
    """The source names held on one XInput pad: its buttons, the left stick as a D-pad."""
    held = {name for bit, name in XI_BITS if buttons & bit}
    if ly > STICK:
        held.add("DUP")
    elif ly < -STICK:
        held.add("DDOWN")
    if lx > STICK:
        held.add("DRIGHT")
    elif lx < -STICK:
        held.add("DLEFT")
    return held


class XInputReader:
    kind = "xbox"

    def __init__(self):
        self.get = None
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                self.get = getattr(ctypes.windll, name).XInputGetState
                break
            except (OSError, AttributeError):
                continue

    def read(self):
        if self.get is None:
            return set()
        held = set()
        st = _XInputState()
        for i in range(4):
            if self.get(i, ctypes.byref(st)) == 0:
                held |= xinput_held(st.pad.buttons, st.pad.lx, st.pad.ly)
        return held


def ps_held(devices):
    """Source names of padnav's devices, in the XInput names SOURCES uses. Other inputs (triggers, right stick) drop out."""
    return {PS_NAMES[name] for dev in devices for name in dev.pressed if name in PS_NAMES}


class PlayStationReader:
    """Only with an installed T5DR Online: its reader knows USB, Bluetooth and Steam's extended reports."""
    kind = "ps"

    def __init__(self, t5dr_root=None):
        self.source = None
        self.next_scan = 0.0
        if not t5dr_root:
            return
        lobby = os.path.join(t5dr_root, "lobby")
        if lobby not in sys.path:
            sys.path.insert(0, lobby)
        try:
            self.source = importlib.import_module("t5lobby.padnav").HidSource()
        except Exception:  # noqa: BLE001 -- no PlayStation pads then, XInput still works
            self.source = None

    def read(self):
        if self.source is None:
            return set()
        now = time.monotonic()
        try:
            if now >= self.next_scan:
                self.next_scan = now + 1.0
                self.source.scan()
            return ps_held(self.source.read())
        except Exception:  # noqa: BLE001 -- a pad pulled out must not end the launcher
            return set()

    def pause(self):
        if self.source is not None:
            self.source.pause()
        self.next_scan = 0.0


class Pads:
    """poll() -> [(action, "down"|"up")]: edges, plus the repeat of held directions. One pad's press wins the prompts."""

    def __init__(self, readers=None, clock=time.monotonic):
        self.readers = readers if readers is not None else []
        self.clock = clock
        self.down = {}
        self.kind = "xbox"

    def poll(self):
        held, kinds = set(), {}
        for r in self.readers:
            names = r.read()
            held |= names
            for name in names:
                kinds.setdefault(name, r.kind)
        out = []
        now = self.clock()
        for name, action in SOURCES:
            if name in held and action not in self.down:
                self.down[action] = now + REPEAT_DELAY
                self.kind = kinds.get(name, self.kind)
                out.append((action, "down"))
            elif name in held and action in DIRECTIONS and now >= self.down[action]:
                self.down[action] = now + REPEAT_RATE
                out.append((action, "down"))
            elif name not in held and action in self.down:
                del self.down[action]
                out.append((action, "up"))
        return out

    def forget(self):
        """The launcher left the front: nothing is held any more, and a press held across the switch is not a new one."""
        self.down = {action: float("inf") for _n, action in SOURCES if action in self.down}
        for r in self.readers:
            if hasattr(r, "pause"):
                r.pause()

    def suppress(self):
        """Require release after capture, retaining HID queues until navigation resumes."""
        self.down = {action: float("inf") for _name, action in SOURCES}
