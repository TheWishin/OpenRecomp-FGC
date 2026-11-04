"""Another launcher of the same game on this PC (owner: "it should say: hey, you are logged in, but you can really
only play in one launcher").

The lobby lets one connection per account: the newer login wins and the older launcher is told "logged in from
another place". So OpenRecomp looks for the other launchers itself and says so before anyone is logged out:

    native     the game's own launcher (T5DR Online's Tk launcher, Tekken 4's Easy Launcher): a Python process whose
               command line runs its script (t5dr_launcher.pyw / t4_launcher.pyw). Neither has a single-instance
               lock of its own; their command lines are the one sign they leave.
    window     another OpenRecomp window: every window holds one of SLOTS window locks while it runs.
    online     another OpenRecomp window is logged in to this game's lobby: it holds one of SLOTS online locks.

The locks are operating-system byte locks (as launch_guard): a closed or crashed window lets go by itself, no PID
files and no stale-lock guesses. The process look runs on a worker thread every EVERY seconds; others() only reads
its last answer, so a redraw never waits for it. Off until enable() (the app's main); unit tests pass their own scan.
"""
import os
import tempfile
import threading

SCRIPTS = {"t5dr": ("t5dr_launcher.pyw",), "t4": ("t4_launcher.pyw",)}
SLOTS = 16
EVERY = 3.0


# ---------------------------------------------------------------- processes and their command lines (Windows)
def _command_lines():
    """[(pid, command line)] of this user's Python processes; [] where that cannot be read (not Windows)."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("ppid", wintypes.DWORD), ("prio", ctypes.c_long), ("flags", wintypes.DWORD),
                    ("exe", ctypes.c_wchar * 260)]

    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("maximum", ctypes.c_ushort), ("buffer", ctypes.c_void_p)]

    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.ULONG,
                                                ctypes.POINTER(wintypes.ULONG)]
    snap = k32.CreateToolhelp32Snapshot(2, 0)                 # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return []
    out = []
    own = os.getpid()
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            name = entry.exe.lower()
            if entry.pid and entry.pid != own and (name.startswith("python") or name in ("py.exe", "pyw.exe")):
                handle = k32.OpenProcess(0x1000, False, entry.pid)   # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    try:
                        size = wintypes.ULONG(0)
                        buffer = ctypes.create_string_buffer(8192)
                        # 60 = ProcessCommandLineInformation (Windows 8.1+): a UNICODE_STRING into the buffer.
                        if ntdll.NtQueryInformationProcess(handle, 60, buffer, len(buffer), ctypes.byref(size)) >= 0:
                            text = UnicodeString.from_buffer(buffer)
                            if text.buffer and text.length:
                                out.append((entry.pid, ctypes.wstring_at(text.buffer, text.length // 2)))
                    finally:
                        k32.CloseHandle(handle)
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def native_running(game, lines):
    """Does one of these command lines run the game's own launcher script?"""
    scripts = SCRIPTS.get(game, ())
    for _pid, line in lines:
        low = str(line).replace("/", "\\").lower()
        if any(script in low for script in scripts):
            return True
    return False


# ---------------------------------------------------------------- lock slots shared by OpenRecomp windows
def _lock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Slots:
    """N lock files of one kind ("window", "online-t5dr"): take() holds a free one, others() counts the ones other
    processes hold."""

    def __init__(self, directory, kind, count=SLOTS):
        self.directory, self.kind, self.count = directory, kind, count
        self._held = None
        self._lock = threading.Lock()

    def _path(self, n):
        return os.path.join(self.directory, "%s-%d.lock" % (self.kind, n))

    def _open(self, n):
        os.makedirs(self.directory, exist_ok=True)
        stream = open(self._path(n), "a+b")
        if os.fstat(stream.fileno()).st_size == 0:
            stream.write(b"\0")
            stream.flush()
        return stream

    @property
    def held(self):
        return self._held is not None

    def take(self):
        with self._lock:
            if self._held is not None:
                return True
            for n in range(self.count):
                try:
                    stream = self._open(n)
                except OSError:
                    continue
                try:
                    _lock(stream)
                except OSError:
                    stream.close()
                    continue
                self._held = (n, stream)
                return True
            return False

    def release(self):
        with self._lock:
            held, self._held = self._held, None
        if held is not None:
            try:
                _unlock(held[1])
            except OSError:
                pass
            held[1].close()

    def others(self):
        own = self._held[0] if self._held is not None else None
        count = 0
        for n in range(self.count):
            if n == own or not os.path.exists(self._path(n)):
                continue
            try:
                stream = self._open(n)
            except OSError:
                continue
            try:
                _lock(stream)
            except OSError:
                count += 1                       # somebody holds it
            else:
                _unlock(stream)
            finally:
                stream.close()
        return count


# ---------------------------------------------------------------- the detector
class Detector:
    def __init__(self, scan=None, directory=None, every=EVERY):
        self.scan = scan or _command_lines
        self.directory = directory or os.path.join(tempfile.gettempdir(), "OpenRecomp-FGC-presence")
        self.every = every
        self.enabled = False
        self.window = Slots(self.directory, "window")
        self._online = {}
        self._known = {}                         # game -> dict(native=, window=, online=)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None

    def enable(self, background=True):
        """The app's start: hold a window slot, look now and then every EVERY seconds."""
        self.enabled = True
        self.window.take()
        self.refresh()
        if background and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="openrecomp-other-launchers", daemon=True)
            self._thread.start()

    def disable(self):
        self.enabled = False
        self._wake.set()
        self.window.release()
        for slots in self._online.values():
            slots.release()

    def _run(self):
        while self.enabled:
            self._wake.wait(self.every)
            self._wake.clear()
            if self.enabled:
                self.refresh()

    def _slots(self, game):
        with self._lock:
            if game not in self._online:
                self._online[game] = Slots(self.directory, "online-" + game)
            return self._online[game]

    def refresh(self):
        try:
            lines = self.scan()
        except Exception:  # noqa: BLE001 -- an unreadable process list says nothing, never "another launcher"
            lines = []
        known = {}
        for game in SCRIPTS:
            try:
                windows, online = self.window.others(), self._slots(game).others()
            except OSError:
                windows, online = 0, 0
            known[game] = dict(native=native_running(game, lines), window=windows > 0, online=online > 0)
        with self._lock:
            self._known = known

    def others(self, game):
        """dict(native, window, online) of the last look; all False when off or for a game without a launcher."""
        if not self.enabled:
            return dict(native=False, window=False, online=False)
        with self._lock:
            return dict(self._known.get(game) or dict(native=False, window=False, online=False))

    def online(self, game, on):
        """This window is logged in to the game's lobby (on) or not any more."""
        if not self.enabled or game not in SCRIPTS:
            return
        slots = self._slots(game)
        if on:
            slots.take()
        else:
            slots.release()


DETECTOR = Detector()


def enable():
    if os.environ.get("OPENRECOMP_OTHER_LAUNCHERS", "1") != "0":
        DETECTOR.enable()


def kind(game, detector=None):
    """The other launcher that matters most: "native" (the game's own), "online" (another OpenRecomp window logged
    in to this game), "window" (another OpenRecomp window), or ""."""
    if not game:
        return ""
    found = (detector or DETECTOR).others(game)
    return next((k for k in ("native", "online", "window") if found.get(k)), "")
