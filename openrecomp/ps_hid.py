"""DualShock 4 / DualSense / DualSense Edge read as HID devices, the way the games and T5DR Online's launcher read them.

Why: over Bluetooth a PlayStation pad switches from the short report 0x01 to an extended report (DualSense 0x31,
DualShock 4 0x11..0x19) once Steam, DS4Windows or another program asked for more, until it is turned off; the HID
descriptor calls that report vendor-defined, so DirectInput / WinMM see nothing ("only works through Steam"). This reads
every mode (USB 0x01, Bluetooth simple 0x01, Bluetooth 0x11..0x19 / 0x31 with the CRC-32 over 0xA1 + report).

Rules: ctypes only (setupapi, hid.dll, kernel32); enumerating opens a device with no access; reading opens it
GENERIC_READ, shared read/write, overlapped, and never calls anything that writes to the pad (no output report, no
feature report -- reading the calibration report is what switches a Bluetooth pad to the extended mode). A pad that
Steam Input hands on as a virtual Xbox pad (SDL's ignore list or SteamVirtualGamepadInfo names it) is left to that pad
while one is there. Only read while the launcher asks (pause() closes everything).

The sources are DirectInput-style names like T5DR's padnav: B1..B19 (PlayStation order: square cross circle triangle
L1 R1 L2 R2 share options L3 R3), HAT_UP.., X Y Z RZ stick ends (X+ X- ...), RX+ / RY+ = L2 / R2 travel past half.
`xinput_names()` turns them into the names Tekken 4's controls.ini uses (A B X Y LB RB LT RT BACK START LS RS DUP ...,
LUP.. RUP..), which is what the game's own HID reader does when it makes the pad XInput slot 4..7."""
import ctypes
import os
import zlib
from collections import namedtuple

PS_VID = 0x054C
PS_MODELS = {0x05C4: "ds4", 0x09CC: "ds4", 0x0CE6: "dualsense", 0x0DF2: "edge"}
PS_MODEL_NAMES = {"ds4": "DualShock 4", "dualsense": "DualSense", "edge": "DualSense Edge"}
PS_FAKE_PIDS = {"ds4": 0x09CC, "dualsense": 0x0CE6, "edge": 0x0DF2}
BT_HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"      # the Bluetooth HID profile, in a Bluetooth pad's path
CRC_RUN_NEVER_GOOD, CRC_RUN_WAS_GOOD = 25, 200            # when bad CRCs are used anyway (as T5DR's reader)
MAX_PADS = 4
_HAT_DIRS = (("UP",), ("UP", "RIGHT"), ("RIGHT",), ("RIGHT", "DOWN"), ("DOWN",), ("DOWN", "LEFT"), ("LEFT",),
             ("LEFT", "UP"))

HidInfo = namedtuple("HidInfo", "path vid pid model bt in_len")
PsPad = namedtuple("PsPad", "key name vid pid model pressed")

# DirectInput-style source -> Tekken 4 / XInput source name
XINPUT_NAMES = {"B1": "X", "B2": "A", "B3": "B", "B4": "Y", "B5": "LB", "B6": "RB", "B7": "LT", "B8": "RT",
                "B9": "BACK", "B10": "START", "B11": "LS", "B12": "RS",
                "HAT_UP": "DUP", "HAT_DOWN": "DDOWN", "HAT_LEFT": "DLEFT", "HAT_RIGHT": "DRIGHT",
                "X+": "LRIGHT", "X-": "LLEFT", "Y-": "LUP", "Y+": "LDOWN",
                "Z+": "RRIGHT", "Z-": "RLEFT", "RZ-": "RUP", "RZ+": "RDOWN", "RX+": "LT", "RY+": "RT"}


def xinput_names(sources):
    return {XINPUT_NAMES[s] for s in sources if s in XINPUT_NAMES}


def ps_model(vid, pid):
    """'ds4' / 'dualsense' / 'edge' for a PlayStation pad read directly, else None."""
    return PS_MODELS.get(pid) if vid == PS_VID else None


def ps_crc_len(model, rid):
    """Length of a Bluetooth extended report (its last 4 bytes are the CRC); 0 = a report without one."""
    if model == "ds4" and 0x11 <= rid <= 0x19:
        return 547 if rid == 0x19 else 78 + 64 * (rid - 0x11)
    if model in ("dualsense", "edge") and rid == 0x31:
        return 78
    return 0


def ps_crc_ok(model, data):
    """True / False: the report's CRC is right / wrong; None: nothing to check."""
    n = ps_crc_len(model, data[0]) if data else 0
    if not n or len(data) < n:
        return None
    return zlib.crc32(bytes(data[:n - 4]), zlib.crc32(b"\xA1")) & 0xFFFFFFFF == int.from_bytes(data[n - 4:n], "little")


class CrcGate:
    """Reports with a wrong CRC are dropped once the pad has sent a good one (a damaged report is input nobody gave),
    unless 200 come in a row; they are used when 25 came and never a good one (pads that do not fill it in)."""

    def __init__(self):
        self.good = self.bad = self.run = 0
        self.lenient = False

    def passes(self, ok):
        if ok is None:
            return True
        if ok:
            self.good += 1
            self.run = 0
            self.lenient = False
            return True
        self.bad += 1
        self.run += 1
        if self.run >= (CRC_RUN_WAS_GOOD if self.good else CRC_RUN_NEVER_GOOD):
            self.lenient = True
        return self.lenient


def _half(name, value):
    return {name + "+"} if value > 127 else set()


def _sources(st, b, b2mask, l2, r2):
    held = set()
    h = b[0] & 0x0F
    if h < 8:
        held |= {"HAT_" + d for d in _HAT_DIRS[h]}
    x = b[2] & b2mask
    bits = (b[0] >> 4) | (b[1] << 4) | ((x & 7) << 12) | ((x >> 4) << 15)
    held |= {f"B{i + 1}" for i in range(19) if bits >> i & 1}
    for name, v in (("X", st[0]), ("Y", st[1]), ("Z", st[2]), ("RZ", st[3])):
        a = v * 257 - 32768
        if a > 16384:
            held.add(name + "+")
        elif a < -16384:
            held.add(name + "-")
    return held | _half("RX", l2) | _half("RY", r2)


def ps_parse(model, bt, data):
    """One input report (as ReadFile hands it over, padded to the device's longest report) -> (mode, held sources);
    mode 'usb' / 'bt-simple' / 'bt-ext'; (None, None) for a report without input. bt: True Bluetooth, False USB,
    None unknown (then a 64-byte report is a USB one)."""
    p = bytes(data)
    n = len(p)
    if n < 10:
        return None, None
    rid = p[0]
    simple = bt is True or (bt is None and n != 64)
    if model == "ds4":
        if rid == 0x01:
            return ("bt-simple" if simple else "usb"), _sources(p[1:5], p[5:8], 0x03, p[8], p[9])
        if 0x11 <= rid <= 0x19 and n >= 12 and p[1] & 0x80:
            return "bt-ext", _sources(p[3:7], p[7:10], 0x03, p[10], p[11])
        return None, None
    if model in ("dualsense", "edge"):
        full = 0xF7 if model == "edge" else 0x07
        if rid == 0x01:
            if simple:
                return "bt-simple", _sources(p[1:5], p[5:8], 0x03, p[8], p[9])
            return "usb", _sources(p[1:5], p[8:11], full, p[5], p[6])
        if rid == 0x31 and n >= 12:
            return "bt-ext", _sources(p[2:6], p[9:12], full, p[6], p[7])
    return None, None


# ---------------------------------------------------------------------- Steam Input

def _vidpid_list(value):
    """SDL's "0xAAAA/0xBBBB,..." ("@file" = read from that file) -> {(vid, pid)}, or None if unset."""
    if not value:
        return None
    text = value
    if value.startswith("@"):
        try:
            with open(value[1:], encoding="latin-1") as stream:
                text = stream.read(4096)
        except OSError:
            text = ""
    out = set()
    for token in text.replace(",", " ").split():
        a, _, b = token.partition("/")
        try:
            vid, pid = int(a, 16), int(b, 16)
        except ValueError:
            continue
        if 0 <= vid <= 0xFFFF and 0 <= pid <= 0xFFFF:
            out.add((vid, pid))
    return out


def steam_virtual_ids(path):
    """{(vid, pid)} of the real pads behind Steam's virtual pads (the SteamVirtualGamepadInfo file)."""
    out, vid, pid = set(), None, None
    if not path:
        return out
    try:
        with open(path, encoding="latin-1") as stream:
            for raw in stream:
                s = raw.strip()
                if s.startswith("["):
                    vid = pid = None
                    continue
                key, _, value = s.partition("=")
                try:
                    if key.strip().upper() == "VID":
                        vid = int(value.strip(), 0)
                    elif key.strip().upper() == "PID":
                        pid = int(value.strip(), 0)
                    else:
                        continue
                except ValueError:
                    continue
                if vid is not None and pid is not None:
                    out.add((vid, pid))
    except OSError:
        pass
    return out


def steam_lists(vid, pid, env=None):
    """Does Steam hand programs a virtual pad for this one and ask them to leave it alone?"""
    env = os.environ if env is None else env
    ignore = _vidpid_list(env.get("SDL_GAMECONTROLLER_IGNORE_DEVICES"))
    if ignore and (vid, pid) in ignore:
        return True
    keep = _vidpid_list(env.get("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT"))
    if keep and (vid, pid) not in keep:
        return True
    return (vid, pid) in steam_virtual_ids(env.get("SteamVirtualGamepadInfo"))


# ---------------------------------------------------------------------- Windows

class _Win32Hid:
    """The few Windows calls the reader needs (setupapi, hid.dll, kernel32), ctypes only."""

    GENERIC_READ = 0x80000000
    FILE_SHARE_RW = 0x1 | 0x2
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    INVALID = ctypes.c_void_p(-1).value
    ERROR_IO_PENDING, ERROR_IO_INCOMPLETE = 997, 996

    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.hid = ctypes.WinDLL("hid")
        self.sa = ctypes.WinDLL("setupapi", use_last_error=True)

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                        ("Data4", ctypes.c_uint8 * 8)]

        class IfData(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint32), ("InterfaceClassGuid", GUID), ("Flags", ctypes.c_uint32),
                        ("Reserved", ctypes.c_size_t)]

        class Attrs(ctypes.Structure):
            _fields_ = [("Size", ctypes.c_uint32), ("VendorID", ctypes.c_uint16), ("ProductID", ctypes.c_uint16),
                        ("VersionNumber", ctypes.c_uint16)]

        class Caps(ctypes.Structure):
            _fields_ = [("Usage", ctypes.c_uint16), ("UsagePage", ctypes.c_uint16),
                        ("InputReportByteLength", ctypes.c_uint16), ("OutputReportByteLength", ctypes.c_uint16),
                        ("FeatureReportByteLength", ctypes.c_uint16), ("Reserved", ctypes.c_uint16 * 17),
                        ("Rest", ctypes.c_uint16 * 10)]

        class Overlapped(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", ctypes.c_uint32),
                        ("OffsetHigh", ctypes.c_uint32), ("hEvent", ctypes.c_void_p)]

        self.GUID, self.IfData, self.Attrs, self.Caps, self.Overlapped = GUID, IfData, Attrs, Caps, Overlapped
        k, h, s = self.k32, self.hid, self.sa
        k.CreateFileW.restype = ctypes.c_void_p
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.CreateEventW.restype = ctypes.c_void_p
        k.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
        k.ResetEvent.argtypes = [ctypes.c_void_p]
        k.ReadFile.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_void_p, ctypes.c_void_p]
        k.GetOverlappedResult.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(w.DWORD), w.BOOL]
        k.CancelIoEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        h.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
        h.HidD_GetAttributes.argtypes = [ctypes.c_void_p, ctypes.POINTER(Attrs)]
        h.HidD_GetAttributes.restype = ctypes.c_ubyte
        h.HidD_GetPreparsedData.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        h.HidD_GetPreparsedData.restype = ctypes.c_ubyte
        h.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        h.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(Caps)]
        h.HidP_GetCaps.restype = ctypes.c_long
        h.HidD_SetNumInputBuffers.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        s.SetupDiGetClassDevsW.restype = ctypes.c_void_p
        s.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR, ctypes.c_void_p, w.DWORD]
        s.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(GUID), w.DWORD,
                                                  ctypes.POINTER(IfData)]
        s.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.POINTER(IfData), ctypes.c_void_p,
                                                       w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
        s.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

    def enumerate(self):
        return [info for info in (self._probe(p) for p in self.paths()) if info is not None]

    def paths(self):
        out = []
        guid = self.GUID()
        self.hid.HidD_GetHidGuid(ctypes.byref(guid))
        devs = self.sa.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x2 | 0x10)   # PRESENT | DEVICEINTERFACE
        if not devs or devs == self.INVALID:
            return out
        try:
            for i in range(256):
                ifd = self.IfData()
                ifd.cbSize = ctypes.sizeof(ifd)
                if not self.sa.SetupDiEnumDeviceInterfaces(devs, None, ctypes.byref(guid), i, ctypes.byref(ifd)):
                    break
                need = self.w.DWORD(0)
                self.sa.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
                if not need.value or need.value > 4096:
                    continue
                buf = ctypes.create_string_buffer(need.value + 4)
                ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                if not self.sa.SetupDiGetDeviceInterfaceDetailW(devs, ctypes.byref(ifd), buf, need.value, None, None):
                    continue
                out.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
        finally:
            self.sa.SetupDiDestroyDeviceInfoList(devs)
        return out

    def _probe(self, path):
        f = self.k32.CreateFileW(path, 0, self.FILE_SHARE_RW, None, self.OPEN_EXISTING, 0, None)   # no access asked
        if not f or f == self.INVALID:
            return None
        try:
            attrs = self.Attrs()
            attrs.Size = ctypes.sizeof(attrs)
            if not self.hid.HidD_GetAttributes(f, ctypes.byref(attrs)):
                return None
            model = ps_model(attrs.VendorID, attrs.ProductID)
            if not model:
                return None
            pp = ctypes.c_void_p()
            if not self.hid.HidD_GetPreparsedData(f, ctypes.byref(pp)):
                return None
            caps = self.Caps()
            try:
                ok = self.hid.HidP_GetCaps(pp, ctypes.byref(caps)) == 0x00110000
            finally:
                self.hid.HidD_FreePreparsedData(pp)
            if not ok or caps.UsagePage != 0x01 or caps.Usage not in (0x04, 0x05):       # the game pad collection
                return None
            low = path.lower()
            bt = True if BT_HID_UUID in low else False if "hid#vid_" in low else None
            return HidInfo(path, attrs.VendorID, attrs.ProductID, model, bt, caps.InputReportByteLength or 64)
        finally:
            self.k32.CloseHandle(f)

    def open(self, info):
        """A reader of the pad's input reports, or None when it cannot be opened (an exclusive owner)."""
        h = self.k32.CreateFileW(info.path, self.GENERIC_READ, self.FILE_SHARE_RW, None, self.OPEN_EXISTING,
                                 self.FILE_FLAG_OVERLAPPED, None)
        if not h or h == self.INVALID:
            return None
        self.hid.HidD_SetNumInputBuffers(h, 64)
        return _Win32Reader(self, h, max(int(info.in_len), 10))


class _Win32Reader:
    """One open pad: reads() hands over every report that came since the last call, never waits."""

    def __init__(self, api, handle, in_len):
        self.api, self.h, self.n = api, handle, in_len
        self.buf = ctypes.create_string_buffer(in_len)
        self.ov = api.Overlapped()
        self.ov.hEvent = api.k32.CreateEventW(None, True, False, None)
        self.pending = False
        self.failed = False

    def reads(self, limit=128):
        k, out = self.api.k32, []
        got = self.api.w.DWORD(0)
        for _ in range(limit):
            if not self.pending:
                k.ResetEvent(self.ov.hEvent)
                if not k.ReadFile(self.h, self.buf, self.n, None, ctypes.byref(self.ov)):
                    if ctypes.get_last_error() != self.api.ERROR_IO_PENDING:
                        self.failed = True
                        break
                self.pending = True
            if not k.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(got), False):
                if ctypes.get_last_error() != self.api.ERROR_IO_INCOMPLETE:
                    self.pending = False
                    self.failed = True
                break
            self.pending = False
            out.append(self.buf.raw[:got.value])
        return out

    def close(self):
        k = self.api.k32
        if self.pending:
            k.CancelIoEx(self.h, ctypes.byref(self.ov))
            got = self.api.w.DWORD(0)
            k.GetOverlappedResult(self.h, ctypes.byref(self.ov), ctypes.byref(got), True)
            self.pending = False
        k.CloseHandle(self.h)
        k.CloseHandle(self.ov.hEvent)


class FakeHid:
    """PS3_PAD_HID_FAKE=<ds4|dualsense|edge>,<usb|bt>,<file> -- the games' test pad: input reports in hex, one per line,
    appended to the file ('#' starts a comment); every line added since the last read is a report. The file gone =
    unplugged. With it no real pad is touched."""

    def __init__(self, spec):
        parts = spec.split(",", 2)
        self.ok = len(parts) == 3 and parts[0].lower() in PS_FAKE_PIDS and parts[1].lower() in ("usb", "bt")
        if not self.ok:
            return
        self.model, self.bt, self.path = parts[0].lower(), parts[1].lower() == "bt", parts[2]
        self.in_len = (547 if self.model == "ds4" else 78) if self.bt else 64

    def enumerate(self):
        if not self.ok or not os.path.isfile(self.path):
            return []
        return [HidInfo("fake:" + self.path, PS_VID, PS_FAKE_PIDS[self.model], self.model, self.bt, self.in_len)]

    def open(self, info):
        return _FakeReader(self.path, self.in_len)


class _FakeReader:
    def __init__(self, path, in_len):
        self.path, self.n, self.off, self.failed = path, in_len, 0, False
        try:
            self.off = os.path.getsize(path)         # opened now: older reports are history, as with a real pad
        except OSError:
            self.failed = True

    def reads(self, limit=4096):
        try:
            with open(self.path, "rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                if size < self.off:
                    self.off = 0
                stream.seek(self.off)
                data = stream.read()
        except OSError:
            self.failed = True
            return []
        end = data.rfind(b"\n") + 1                  # complete lines only
        self.off += end
        out = []
        for line in data[:end].splitlines()[:limit]:
            text = line.split(b"#", 1)[0].decode("latin-1")
            try:
                report = bytes.fromhex("".join(text.split()))
            except ValueError:
                continue
            if report:
                out.append(report[:self.n] + bytes(max(0, self.n - len(report))))
        return out

    def close(self):
        pass


class HidPads:
    """The PlayStation pads that can be read. scan() about once a second, read() on every poll. A pad's pressed set is
    the newest report's plus everything that was down in any report since the last read (a tap between two polls
    counts). `api` is replaceable (tests); by default the Windows one, or the fake named by PS3_PAD_HID_FAKE. Without
    Windows there is nothing to read and everything is empty."""

    def __init__(self, api=None, env=None, xinput_present=None):
        self.env = os.environ if env is None else env
        if api is None:
            fake = self.env.get("PS3_PAD_HID_FAKE")
            try:
                api = FakeHid(fake) if fake else (_Win32Hid() if os.name == "nt" and self.env.get("OPENRECOMP_PAD_HID") != "0" else None)
            except (OSError, AttributeError):         # no hid.dll / setupapi.dll
                api = None
        self.api = api
        self.xinput_present = xinput_present or (lambda: False)
        self.pads = {}                  # path -> dict(info, reader, gate, held, taps, mode)
        self.skipped = set()            # left to Steam Input / could not be opened, until unplugged
        self.notes = []

    def covers(self, vid, pid):
        return any(p["info"].vid == vid and p["info"].pid == pid for p in self.pads.values())

    def scan(self):
        if self.api is None:
            return
        try:
            found = {i.path: i for i in self.api.enumerate()}
        except OSError:
            return
        for path in list(self.pads):
            if path not in found:
                self._drop(path, "unplugged")
        self.skipped &= set(found)
        for path, info in sorted(found.items()):
            if path in self.pads or path in self.skipped:
                continue
            if len(self.pads) >= MAX_PADS:
                break
            if steam_lists(info.vid, info.pid, self.env) and self.xinput_present():
                self.skipped.add(path)
                self.notes.append(("steam", path))
                continue
            reader = self.api.open(info)
            if reader is None:
                self.skipped.add(path)
                self.notes.append(("open_failed", path))
                continue
            self.pads[path] = dict(info=info, reader=reader, gate=CrcGate(), held=frozenset(), taps=set(), mode=None)
            self.notes.append(("open", path))

    def _drop(self, path, why):
        pad = self.pads.pop(path, None)
        if pad is not None:
            try:
                pad["reader"].close()
            except OSError:
                pass
            self.notes.append((why, path))

    def pause(self):
        """Not read for a while (the launcher left the front): close every pad; scan() opens them again."""
        for path in list(self.pads):
            self._drop(path, "closed")
        self.skipped.clear()

    def read(self):
        out = []
        for path in list(self.pads):
            pad = self.pads[path]
            info = pad["info"]
            reports = pad["reader"].reads()
            if pad["reader"].failed:
                self._drop(path, "gone")
                continue
            for report in reports:
                if not pad["gate"].passes(ps_crc_ok(info.model, report)):
                    continue
                mode, held = ps_parse(info.model, info.bt, report)
                if mode is None:
                    continue
                pad["mode"] = mode
                pad["held"] = frozenset(held)
                pad["taps"] |= held
            pressed = pad["held"] | frozenset(pad["taps"])
            pad["taps"] = set()
            link = "Bluetooth" if info.bt else "USB" if info.bt is False else ("Bluetooth" if info.in_len > 64 else "USB")
            out.append(PsPad("hid:" + path, f"{PS_MODEL_NAMES[info.model]} ({link})", info.vid, info.pid, info.model,
                             pressed))
        return out
