"""One build at a time in a T5DR folder, whichever launcher starts it.

A folder set up by T5DR's own launcher can be built from OpenRecomp, and both launchers keep using it afterwards. Two
builds at once would write the same files, so OpenRecomp takes a lock file in the folder while its build runs and refuses
to start when it finds one. T5DR's own launcher writes no lock, but its build leaves a `build.log` in the output folder
that is written to every few seconds and ends with an exit-code line: a log changed in the last minutes without that
line is a build still running. Nothing here writes anywhere else, and the lock file is removed again.
"""
import atexit
import json
import os
import time

LOCK_NAME = "openrecomp-build.lock"
RUNNING_SECONDS = 600           # the quietest build step prints at least this often (T5DR's QUIET_S compile = 600)
_HELD = set()


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
    return int(info.get("pid") or 0) != os.getpid() and _alive(info.get("pid"))


def t5dr_build_running(out_dir, now=None):
    """True when T5DR's own launcher is building into `out_dir`: build.log changed lately and has no exit line yet."""
    log = os.path.join(out_dir, "build.log")
    try:
        age = (time.time() if now is None else now) - os.path.getmtime(log)
        if age > RUNNING_SECONDS:
            return False
        with open(log, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 400))
            tail = stream.read().decode("utf-8", "replace")
    except OSError:
        return False
    last = [line for line in tail.splitlines() if line.strip()][-1:]
    return not (last and last[0].startswith("# exit code"))


def blocker(root, out_dir):
    """"" when a build may start, else the catalog key of the reason."""
    if held_by_other(root):
        return "@t5.build_locked_openrecomp"
    if t5dr_build_running(out_dir):
        return "@t5.build_locked_t5dr"
    return ""


def acquire(root, out_dir):
    """Take the lock; RuntimeError("@key") when a build of either launcher is running. Our own stale lock is replaced."""
    reason = blocker(root, out_dir)
    if reason:
        raise RuntimeError(reason)
    path = lock_path(root)
    try:
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(dict(pid=os.getpid(), started=time.strftime("%Y-%m-%dT%H:%M:%S"), by="OpenRecomp-FGC"), stream)
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
