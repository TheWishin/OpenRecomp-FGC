"""The game opens on the monitor this launcher is on, as T5DR's own launcher starts it (PS3_WINDOW_MONITOR).

T5DR's launcher hands the game the centre of its own window; without it the game opens on Windows' main monitor --
on a PC with two screens that can be another one, with another refresh rate. The install's own code answers
(core.window_center) and its GameRun.start takes the point: an install that has neither starts as before."""
import ctypes
import inspect
import os


def own_window():
    """This program's window (the largest visible one that is not minimized), or None."""
    if os.name != "nt":
        return None
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindow.restype = wintypes.HWND
    user.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
    for fn in (user.IsWindowVisible, user.IsIconic):
        fn.argtypes = (wintypes.HWND,)
    user.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _param):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid() and user.IsWindowVisible(hwnd) and not user.IsIconic(hwnd) \
                and not user.GetWindow(hwnd, 4):          # GW_OWNER: no dialog or tool tip
            rect = wintypes.RECT()
            if user.GetWindowRect(hwnd, ctypes.byref(rect)):
                found.append(((rect.right - rect.left) * (rect.bottom - rect.top), hwnd))
        return True
    user.EnumWindows(each, 0)
    found = [entry for entry in found if entry[0] > 0]
    return max(found)[1] if found else None


def monitor_point(core, window=None):
    """(x, y) as the install's own launcher gives it for this launcher's window, or None."""
    center = getattr(core, "window_center", None)
    if not callable(center):
        return None
    try:
        hwnd = (window or own_window)()
        point = center(hwnd) if hwnd else None
        return (int(point[0]), int(point[1])) if point else None
    except Exception:  # noqa: BLE001 -- the game then opens where Windows puts it, as before
        return None


def start_arguments(core, start, extra_env, window=None):
    """The arguments for the install's GameRun.start: its launcher's own (extra_env, monitor_point)."""
    arguments = dict(extra_env=extra_env)
    try:
        takes_point = "monitor_point" in inspect.signature(start).parameters
    except (TypeError, ValueError):
        takes_point = False
    if takes_point:
        point = monitor_point(core, window)
        if point:
            arguments["monitor_point"] = point
    return arguments
