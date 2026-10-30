"""Controllers -> semantic actions. XInput and Windows joystick input need no game install; an installed T5DR Online
can also supply its HID reader (t5lobby.padnav). The launcher reads pads only while it is in front.
"""
import ctypes
import importlib
from importlib.machinery import PathFinder
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
        return set().union(*self._devices().values())

    def _devices(self):
        if self.get is None:
            return {}
        held = {}
        st = _XInputState()
        for i in range(4):
            if self.get(i, ctypes.byref(st)) == 0:
                held[i] = xinput_held(st.pad.buttons, st.pad.lx, st.pad.ly)
        return held

    def return_devices(self):
        return {index for index, held in self._devices().items() if {"BACK", "START"} <= held}


class _JoyCaps(ctypes.Structure):
    _fields_ = [("mid", ctypes.c_ushort), ("pid", ctypes.c_ushort), ("name", ctypes.c_wchar * 32),
                ("xmin", ctypes.c_uint), ("xmax", ctypes.c_uint), ("ymin", ctypes.c_uint), ("ymax", ctypes.c_uint),
                ("zmin", ctypes.c_uint), ("zmax", ctypes.c_uint), ("buttons", ctypes.c_uint),
                ("period_min", ctypes.c_uint), ("period_max", ctypes.c_uint),
                ("rmin", ctypes.c_uint), ("rmax", ctypes.c_uint), ("umin", ctypes.c_uint), ("umax", ctypes.c_uint),
                ("vmin", ctypes.c_uint), ("vmax", ctypes.c_uint), ("caps", ctypes.c_uint),
                ("max_axes", ctypes.c_uint), ("axes", ctypes.c_uint), ("max_buttons", ctypes.c_uint),
                ("regkey", ctypes.c_wchar * 32), ("oem", ctypes.c_wchar * 260)]


class _JoyState(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint) for name in
                ("size", "flags", "x", "y", "z", "r", "u", "v", "buttons", "button_number", "pov", "reserved1", "reserved2")]


def joystick_ps_held(state, caps):
    """Sony's Windows joystick button order, POV in hundredths of a degree, and calibrated left-stick range."""
    held = {PS_NAMES["B" + str(index + 1)] for index in range(10)
            if state.buttons & (1 << index) and "B" + str(index + 1) in PS_NAMES}
    if caps.caps & 0x10 and state.pov != 0xFFFF:
        if state.pov >= 31500 or state.pov <= 4500:
            held.add("DUP")
        if 4500 <= state.pov <= 13500:
            held.add("DRIGHT")
        if 13500 <= state.pov <= 22500:
            held.add("DDOWN")
        if 22500 <= state.pov <= 31500:
            held.add("DLEFT")
    for value, low, high, negative, positive in (
            (state.x, caps.xmin, caps.xmax, "DLEFT", "DRIGHT"),
            (state.y, caps.ymin, caps.ymax, "DUP", "DDOWN")):
        if high > low:
            position = (value - low) / (high - low)
            if position < 0.25:
                held.add(negative)
            elif position > 0.75:
                held.add(positive)
    return held


class WinMMPlayStationReader:
    """Sony pads exposed by Windows' joystick API, including on an empty game shelf."""
    kind = "ps"

    def __init__(self):
        self.api = None
        self.devices = []
        self.next_scan = 0.0
        try:
            self.api = ctypes.windll.winmm
            self.api.joyGetNumDevs.restype = ctypes.c_uint
            self.api.joyGetDevCapsW.argtypes = [ctypes.c_size_t, ctypes.POINTER(_JoyCaps), ctypes.c_uint]
            self.api.joyGetPosEx.argtypes = [ctypes.c_uint, ctypes.POINTER(_JoyState)]
        except (OSError, AttributeError):
            self.api = None

    def read(self):
        return set().union(*self._devices().values())

    def _devices(self):
        if self.api is None:
            return {}
        now = time.monotonic()
        if now >= self.next_scan:
            self.next_scan = now + 1.0
            self.devices = []
            for index in range(min(self.api.joyGetNumDevs(), 16)):
                caps = _JoyCaps()
                if self.api.joyGetDevCapsW(index, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                    name = caps.name.casefold()
                    if any(known in name for known in ("wireless controller", "dualsense", "dualshock", "sony")):
                        self.devices.append((index, caps))
        held = {}
        for index, caps in self.devices:
            state = _JoyState()
            state.size, state.flags, state.pov = ctypes.sizeof(state), 0xFF, 0xFFFF
            if self.api.joyGetPosEx(index, ctypes.byref(state)) == 0:
                held[index] = joystick_ps_held(state, caps)
        return held

    def return_devices(self):
        return {index for index, held in self._devices().items() if {"BACK", "START"} <= held}

    def pause(self):
        pass


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
        package_root = os.path.normcase(os.path.realpath(os.path.join(lobby, "t5lobby")))

        def local_origin(origin):
            try:
                return isinstance(origin, str) and os.path.commonpath(
                    (package_root, os.path.normcase(os.path.realpath(origin)))) == package_root
            except ValueError:
                return False

        try:
            spec = PathFinder.find_spec("t5lobby", [lobby])
            if spec is None or not local_origin(spec.origin):
                return
            for name, module in tuple(sys.modules.items()):
                if name == "t5lobby" or name.startswith("t5lobby."):
                    if not local_origin(getattr(module, "__file__", None)):
                        return
            if lobby in sys.path:
                sys.path.remove(lobby)
            sys.path.insert(0, lobby)
            module = importlib.import_module("t5lobby.padnav")
            if local_origin(getattr(module, "__file__", None)):
                self.source = module.HidSource()
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
            try:
                self.source.pause()
            except Exception:  # a disconnected reader must still let the launcher yield input
                pass
        self.next_scan = 0.0


class Pads:
    """poll() -> [(action, "down"|"up")]: edges, plus the repeat of held directions. One pad's press wins the prompts."""

    def __init__(self, readers=None, clock=time.monotonic):
        self.readers = readers if readers is not None else []
        self.clock = clock
        self.down = {}
        self.pressed = set()
        self.kind = "xbox"
        self.reset_return()

    def reset_return(self):
        self.return_holds = {}
        self.return_sent = set()

    def return_requested(self, dt):
        """An explicit game-exit chord, read only by native readers while T4 owns the foreground."""
        held = {(id(reader), index) for reader in self.readers
                if isinstance(reader, (XInputReader, WinMMPlayStationReader)) for index in reader.return_devices()}
        self.return_holds = {key: self.return_holds.get(key, 0.0) + max(0.0, dt) for key in held}
        self.return_sent.intersection_update(held)
        ready = {key for key, duration in self.return_holds.items() if duration >= 2.0} - self.return_sent
        if ready:
            self.return_sent.update(ready)
            self.suppress()
            return True
        return False

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
            if name in held:
                self.pressed.add(action)
            if name in held and action not in self.down:
                self.down[action] = now + REPEAT_DELAY
                self.kind = kinds.get(name, self.kind)
                out.append((action, "down"))
            elif name in held and action in DIRECTIONS and now >= self.down[action]:
                self.down[action] = now + REPEAT_RATE
                out.append((action, "down"))
            elif name not in held and action in self.down:
                del self.down[action]
                if action in self.pressed:
                    self.pressed.remove(action)
                    out.append((action, "up"))
        return out

    def forget(self):
        """The launcher left the front: nothing is held any more, and a press held across the switch is not a new one."""
        self.suppress()
        for r in self.readers:
            if hasattr(r, "pause"):
                r.pause()

    def suppress(self):
        """Require release after capture, retaining HID queues until navigation resumes."""
        self.down = {action: float("inf") for _name, action in SOURCES}
