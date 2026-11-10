"""One build at a time in a T5DR folder, whichever launcher starts it.

A folder set up by T5DR's own launcher can be built from OpenRecomp, and both launchers keep using it afterwards. Two
builds at once would write the same files, so OpenRecomp takes a lock file in the folder while its build runs and refuses
to start when it finds one. T5DR's own launcher writes no lock, but its build leaves a `build.log` in the output folder
that is written to every few seconds and ends with an exit-code line. That log alone proves nothing: a build cut off
mid-way (a launcher closed or crashed) leaves exactly the same log. So "running" needs a real build process (build_game.py
or the compiler it started) for this folder. Only where the process list cannot be read does the log decide, with a short
window. The player can always choose "Build anyway". Nothing here writes anywhere else, and the lock file is removed again.
"""
import atexit
import json
import os
import time

LOCK_NAME = "openrecomp-build.lock"
RUNNING_SECONDS = 600           # the quietest build step prints at least this often (T5DR's QUIET_S compile = 600)
BLIND_SECONDS = 120             # the log's window when the process list cannot be read
SCAN_CACHE_SECONDS = 3.0
SCRIPTS = ("build_game.py", "build_game_dll.py")
COMPILERS = ("clang-cl", "lld-link", "clang.exe", "ninja")
_HELD = set()
_ANYWAY = set()
_SCAN = {"at": -1e9, "value": None}


def lock_path(root):
    return os.path.join(root, LOCK_NAME)


def _alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return True
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)         # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5                 # access denied: it exists
    try:
        code = ctypes.c_ulong()
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        return code.value == 259                            # STILL_ACTIVE
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def _read(path):
    try:
        with open(path, encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return None


def held_by_other(root):
    """True when another OpenRecomp process (not this one) is building in `root`."""
    info = _read(lock_path(root))
    if info is None:
        return False
    try:
        pid = int(info.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    if pid == os.getpid() or not _alive(pid):
        return False
    # The pid lives, but is it the launcher that wrote the lock? After a restart of the PC the number can belong to
    # any program: only the same start time counts (a lock without one, from 0.1.7 and older, is believed).
    started = _started(pid)
    return not (started is not None and info.get("started_at") is not None and started != info.get("started_at"))


def _started(pid):
    from ..updater import pid_started
    return pid_started(pid)


def _norm(path):
    if not path:
        return ""
    return os.path.normcase(os.path.abspath(str(path))).replace("/", "\\").rstrip("\\")


def _wanted(name):
    return name.startswith("python") or name in ("py.exe", "pyw.exe") or any(c in name for c in COMPILERS)


def _scan():
    """[(pid, command line)] of the Python and compiler processes, or None when that cannot be read completely."""
    from . import other_launchers
    return other_launchers._command_lines(_wanted, strict=True)


def _processes():
    now = time.monotonic()
    if now - _SCAN["at"] > SCAN_CACHE_SECONDS:
        _SCAN.update(at=now, value=_scan())
    return _SCAN["value"]


def forget_scan():
    _SCAN.update(at=-1e9, value=None)


def _is_build(line, folders):
    """A build_game script or a compiler of the build, for one of `folders` (its command line names it)."""
    low = str(line).replace("/", "\\").lower()
    if not any(f in low for f in folders):
        return False        # (a relative script path says nothing about which folder it builds: not counted)
    return any(s in low for s in SCRIPTS) or any(c in low for c in COMPILERS)


def t5dr_build_process(out_dir, root=None, lines=None):
    """True / False when a build process for this folder exists / does not; None when the processes cannot be listed."""
    lines = _processes() if lines is None else lines
    if lines is None:
        return None
    folders = [f.lower() for f in {_norm(out_dir), _norm(root) or _norm(os.path.dirname(_norm(out_dir)))} if f]
    own = os.getpid()
    return any(pid != own and _is_build(line, folders) for pid, line in lines)


def t5dr_build_running(out_dir, now=None, root=None):
    """True when T5DR's own launcher is building into `out_dir`: a build process for the folder exists and build.log has
    no exit line. Where the process list cannot be read: the log changed in the last BLIND_SECONDS without that line."""
    log = os.path.join(out_dir, "build.log")
    process = t5dr_build_process(out_dir, root)
    if process is False:
        return False
    try:
        age = (time.time() if now is None else now) - os.path.getmtime(log)
        if process is None and age > BLIND_SECONDS:
            return False
        with open(log, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 400))
            tail = stream.read().decode("utf-8", "replace")
    except OSError:
        return bool(process)
    last = [line for line in tail.splitlines() if line.strip()][-1:]
    return not (last and last[0].startswith("# exit code"))


def build_anyway(out_dir):
    """The player chose to build although T5DR's launcher looks busy: skip that check for the next build here."""
    _ANYWAY.add(_norm(out_dir))


def blocker(root, out_dir):
    """"" when a build may start, else the catalog key of the reason."""
    if held_by_other(root):
        return "@t5.build_locked_openrecomp"
    if _norm(out_dir) not in _ANYWAY and t5dr_build_running(out_dir, root=root):
        return "@t5.build_locked_t5dr"
    return ""


def acquire(root, out_dir):
    """Take the lock; RuntimeError("@key") when a build of either launcher is running. Our own stale lock is replaced."""
    reason = blocker(root, out_dir)
    if reason:
        raise RuntimeError(reason)
    _ANYWAY.discard(_norm(out_dir))
    path = lock_path(root)
    try:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(dict(pid=os.getpid(), started=time.strftime("%Y-%m-%dT%H:%M:%S"), started_at=_started(os.getpid()),
                           by="OpenRecomp-FGC"), stream)
    except OSError as error:
        raise RuntimeError("@t5.build_lock_failed") from error
    _HELD.add(path)
    atexit.register(release, root)


def release(root):
    if not root:
        return
    path = lock_path(root)
    if path not in _HELD:
        return
    _HELD.discard(path)
    try:
        info = _read(path) or {}
        if int(info.get("pid") or 0) == os.getpid():
            os.unlink(path)
    except (OSError, ValueError):
        pass
