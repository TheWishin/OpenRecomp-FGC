"""Local-only play time. No game files, account identifiers or network operations.

Each successful launch saves its session immediately, checkpoints at most every
60 seconds and saves again on exit. After a launcher crash, only time up to its
last checkpoint is retained: time while the launcher was absent is never guessed.
"""
import json
import math
import os
import re
import tempfile
import threading
import time
from datetime import datetime

EVERY = 60.0
POLL = 1.0
_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")


def empty():
    return dict(offline_seconds=0.0, online_seconds=0.0, last_played="", sessions=0)


def online_environment(env):
    """Only game-network switches determine mode; graphics/diagnostics do not."""
    env = env or {}
    return any(str(env.get(key, "")).strip() not in ("", "0", "off", "false")
               for key in ("TEKKEN4_NET", "T5_NET_MATCH", "T5_NET", "T5_NET_MODE"))


class Store:
    def __init__(self, directory, clock=None, wall=None, background=True):
        self.path = os.path.join(directory, "playtime.json")
        self.clock = clock or time.monotonic
        self.wall = wall or time.time
        self.background = background
        self.games = {}
        self.active = {}
        self.native = []
        self._lock = threading.RLock()
        self._thread = None
        self._wake = threading.Event()
        self._dirty = False
        self._last_saved = self.clock()
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as stream:
                data = json.load(stream)
            if data.get("version") != 1 or not isinstance(data.get("games"), dict):
                return
            for game, row in data["games"].items():
                if not isinstance(game, str) or not _ID.fullmatch(game) or not isinstance(row, dict):
                    continue
                clean = empty()
                for key in ("offline_seconds", "online_seconds"):
                    value = row.get(key, 0)
                    try:
                        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
                            clean[key] = float(value)
                    except OverflowError:
                        pass
                count = row.get("sessions", 0)
                if type(count) is int and count >= 0:
                    clean["sessions"] = count
                date = row.get("last_played", "")
                if isinstance(date, str):
                    try:
                        clean["last_played"] = datetime.strptime(date, "%Y-%m-%d").date().isoformat()
                    except ValueError:
                        pass
                self.games[game] = clean
        except (OSError, ValueError, TypeError, AttributeError, RecursionError):
            pass

    def _save(self):
        folder = os.path.dirname(self.path)
        os.makedirs(folder, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                             prefix=".playtime-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(dict(version=1, games=self.games), stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self._dirty = False
            self._last_saved = self.clock()
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def _try_save(self):
        try:
            self._save()
        except OSError:
            # Play remains available on read-only/full disks; the next tick retries.
            self._dirty = True

    def _elapsed(self, session):
        elapsed = session.get("elapsed")
        try:
            value = elapsed() if elapsed else self.clock() - session["start"]
            if isinstance(value, (int, float)) and math.isfinite(value):
                return max(session["saved"], float(value))
        except (OSError, ValueError, TypeError, OverflowError):
            pass
        return session["saved"]

    def watch(self, game, running, online=False, process=None, elapsed=None):
        """Watch one owned game process. The opaque token deduplicates repeated hooks."""
        if not isinstance(game, str) or not _ID.fullmatch(game):
            return None
        identity = process if process is not None else running
        token = (game, id(identity))
        with self._lock:
            if token in self.active:
                return token
            handle = None
            if elapsed is None and process is not None and type(getattr(process, "pid", None)) is int:
                handle = Process.open(process.pid)
                if handle is not None:
                    elapsed = handle.elapsed
            now = self.clock()
            row = self.games.setdefault(game, empty())
            row["sessions"] += 1
            row["last_played"] = datetime.fromtimestamp(self.wall()).date().isoformat()
            self.active[token] = dict(game=game, running=running, start=now, saved=0.0,
                                      mode="online_seconds" if online else "offline_seconds",
                                      elapsed=elapsed, handle=handle, identity=identity)
            self._dirty = True
            self.checkpoint()
            self._ensure_thread()
        return token

    def snapshot(self, game):
        with self._lock:
            row = dict(self.games.get(game, empty()))
            for session in self.active.values():
                if session["game"] == game:
                    row[session["mode"]] += self._elapsed(session) - session["saved"]
            return row

    def checkpoint(self):
        """Save current elapsed time without ending sessions that are still alive."""
        with self._lock:
            for session in self.active.values():
                elapsed = self._elapsed(session)
                self.games[session["game"]][session["mode"]] += elapsed - session["saved"]
                session["saved"] = elapsed
            if self.active or self._dirty:
                self._try_save()

    def tick(self):
        with self._lock:
            for watcher in list(self.native):
                watcher.tick()
            ended = False
            for token, session in list(self.active.items()):
                try:
                    running = session["running"]()
                except Exception:  # unknown state never invents an exit
                    continue
                if running is False:
                    elapsed = self._elapsed(session)
                    self.games[session["game"]][session["mode"]] += elapsed - session["saved"]
                    handle = session["handle"]
                    if handle is not None:
                        handle.close()
                    del self.active[token]
                    ended = self._dirty = True
            for watcher in list(self.native):
                if watcher.done:
                    watcher.close()
                    self.native.remove(watcher)
            if ended or self.clock() - self._last_saved >= EVERY or self._dirty:
                self.checkpoint()

    def watch_native(self, game, process, images, scan=None, open_process=None):
        """Only descendants of a native launcher explicitly started here qualify."""
        with self._lock:
            watcher = Native(self, game, process, images, scan, open_process)
            self.native.append(watcher)
            self._ensure_thread()
            return watcher

    def _ensure_thread(self):
        if self.background and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, name="openrecomp-playtime", daemon=True)
            self._thread.start()

    def _run(self):
        while True:
            self._wake.wait(POLL)
            with self._lock:
                self.tick()
                if not self.active and not self.native and not self._dirty:
                    self._thread = None
                    return


class Native:
    def __init__(self, store, game, launcher, images, scan=None, open_process=None):
        self.store, self.game, self.launcher = store, game, launcher
        self.images = {name.casefold() for name in images}
        self.scan = scan or processes
        self.open_process = open_process or Process.open
        self.nodes = {launcher.pid: self.open_process(launcher.pid)}
        self.retired = []
        self.seen = set()
        self.done = False

    @staticmethod
    def _running(process):
        try:
            return process is not None and process.running()
        except OSError:
            return False

    def _belongs(self, child, parent):
        if parent is None:
            return self.launcher.poll() is None
        try:
            born, _end = child.interval()
            parent_born, parent_end = parent.interval()
            return born >= parent_born and (parent_end is None or born <= parent_end)
        except (OSError, AttributeError):
            return self._running(parent)

    def tick(self):
        rows = self.scan()
        if rows is None:
            return
        # Creation/exit identities prevent a recycled parent PID claiming strangers.
        changed = True
        while changed:
            changed = False
            for pid, parent, image in rows:
                if pid == self.launcher.pid or parent not in self.nodes:
                    continue
                previous = self.nodes.get(pid)
                if previous is not None and self._running(previous):
                    continue
                process = self.open_process(pid)
                if process is None:
                    continue
                if not self._belongs(process, self.nodes[parent]):
                    process.close()
                    continue
                try:
                    born = process.interval()[0]
                except (OSError, AttributeError):
                    born = pid
                identity = (pid, born)
                if identity in self.seen:
                    process.close()
                    continue
                if previous is not None:
                    self.retired.append(previous)
                self.nodes[pid] = process
                self.seen.add(identity)
                changed = True
                if image.casefold() in self.images:
                    self.store.watch(self.game, process.running, online=process.online(),
                                     process=process, elapsed=process.elapsed)
        try:
            closed = self.launcher.poll() is not None
        except OSError:
            closed = False
        if closed and not any(self._running(process) for pid, process in self.nodes.items()
                              if pid != self.launcher.pid):
            self.done = True

    def close(self):
        for process in list(self.nodes.values()) + self.retired:
            if process is not None:
                process.close()


class Process:
    """An owned Windows process handle: PID reuse cannot extend a session."""
    def __init__(self, pid, handle, kernel):
        self.pid, self.handle, self.kernel = pid, handle, kernel
        self._clock_start = None

    @classmethod
    def open(cls, pid):
        if os.name != "nt":
            return None
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        handle = kernel.OpenProcess(0x1000 | 0x10, False, pid)  # query and VM_READ for mode switches
        if not handle:
            handle = kernel.OpenProcess(0x1000, False, pid)
        return cls(pid, handle, kernel) if handle else None

    def running(self):
        import ctypes
        from ctypes import wintypes
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise OSError("process state unavailable")
        return code.value == 259

    def interval(self):
        import ctypes
        from ctypes import wintypes
        values = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(self.handle, *[ctypes.byref(value) for value in values]):
            raise OSError("process times unavailable")
        stamps = [(value.dwHighDateTime << 32) | value.dwLowDateTime for value in values]
        return (stamps[0] / 10000000 - 11644473600,
                stamps[1] / 10000000 - 11644473600 if stamps[1] else None)

    def elapsed(self):
        start, end = self.interval()
        if end is not None:
            return max(0.0, end - start)
        if self._clock_start is None:
            self._clock_start = time.monotonic(), max(0.0, time.time() - start)
        clock, elapsed = self._clock_start
        return elapsed + max(0.0, time.monotonic() - clock)

    def online(self):
        """Read only the boolean networking switches; never expose/store environment values."""
        import ctypes
        from ctypes import wintypes
        try:
            kernel = self.kernel
            kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                                 ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
            ntdll = ctypes.WinDLL("ntdll")
            ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                       wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
            pointer = ctypes.sizeof(ctypes.c_void_p)
            # 32-bit games on 64-bit Windows use a 32-bit PEB.
            peb32 = ctypes.c_size_t()
            result = ntdll.NtQueryInformationProcess(self.handle, 26, ctypes.byref(peb32), pointer, None)
            if result >= 0 and peb32.value:
                peb, pointer = peb32.value, 4
            else:
                info = (ctypes.c_void_p * 6)()
                if ntdll.NtQueryInformationProcess(self.handle, 0, info, ctypes.sizeof(info), None) < 0:
                    return False
                peb = info[1]

            def read(address, size):
                buffer = ctypes.create_string_buffer(size)
                count = ctypes.c_size_t()
                if not kernel.ReadProcessMemory(self.handle, address, buffer, size, ctypes.byref(count)):
                    raise OSError("process mode unavailable")
                return buffer.raw[:count.value]

            parameters = int.from_bytes(read(peb + (0x20 if pointer == 8 else 0x10), pointer), "little")
            environment = int.from_bytes(read(parameters + (0x80 if pointer == 8 else 0x48), pointer), "little")
            block = bytearray()
            for offset in range(0, 65536, 256):
                block.extend(read(environment + offset, 256))
                text = block.decode("utf-16-le", errors="replace")
                if "\0\0" in text:
                    switches = {}
                    for entry in text.split("\0\0", 1)[0].split("\0"):
                        key, _, value = entry.partition("=")
                        if key in ("TEKKEN4_NET", "T5_NET_MATCH", "T5_NET", "T5_NET_MODE"):
                            switches[key] = value
                    return online_environment(switches)
        except (OSError, AttributeError, ValueError, TypeError):
            pass
        return False

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def processes():
    """PID, parent PID, executable basename only; no paths or command lines."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("parent", wintypes.DWORD), ("priority", ctypes.c_long), ("flags", wintypes.DWORD),
                    ("image", ctypes.c_wchar * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return None
    rows = []
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(Entry)
        ok = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            rows.append((entry.pid, entry.parent, entry.image))
            ok = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return rows


_stores = {}
_stores_lock = threading.Lock()


def shared_store():
    from .manifest import user_dir
    directory = user_dir()
    with _stores_lock:
        if directory not in _stores:
            _stores[directory] = Store(directory)
        return _stores[directory]
