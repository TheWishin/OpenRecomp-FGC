r"""The launcher's own preferences (not a game's): start with Windows, the data folder, the program version.

Start with Windows is one per-user value in HKCU\Software\Microsoft\Windows\CurrentVersion\Run -- no admin, no
service, no scheduled task. The registry is reached through a small layer (`WinRegistry`) so tests use a fake one and
never touch the real registry. Nothing here writes anywhere else; config.json keeps the other choices."""
import os
import subprocess
import sys

from .manifest import user_dir

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "OpenRecomp"
PROMPT_STYLES = ("auto", "xbox", "ps", "kb")        # Auto = whatever you pressed last
CHANNELS = (False, True)                           # stable / test versions (the same flag the games use)


class WinRegistry:
    """HKCU Run key: get / set / delete one string value. Raises OSError on any failure."""

    def get(self, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
                value, kind = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        return value if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) else None

    def set(self, name, value):
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def available():
    """Start with Windows only exists on Windows."""
    return sys.platform == "win32"


def program_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def startup_command(program=None):
    """The command Windows runs at sign-in: the launcher's own private pythonw (Setup's shortcut does the same), else
    the interpreter running now. Quoted; the launcher starts in its window mode as usual."""
    program = program or program_dir()
    runner = os.path.join(program, "portable", "pythonw.exe")
    if not os.path.isfile(runner):
        runner = sys.executable
        beside = os.path.join(os.path.dirname(runner), "pythonw.exe")
        if os.path.isfile(beside):
            runner = beside
    return f'"{runner}" -B -m openrecomp'


def startup_enabled(registry=None):
    """True when our Run value exists. Any registry trouble reads as off."""
    try:
        return bool((registry or WinRegistry()).get(RUN_NAME))
    except (OSError, ImportError):
        return False


def set_startup(on, registry=None, command=None):
    """-> True when the registry now says what was asked. Never raises; False = it did not work."""
    registry = registry or WinRegistry()
    try:
        if on:
            registry.set(RUN_NAME, command or startup_command())
        else:
            registry.delete(RUN_NAME)
        return startup_enabled(registry) == bool(on)
    except (OSError, ImportError):
        return False


def open_folder(path, opener=None):
    """Open a folder in the file manager (creating it first when it does not exist yet). -> True when it was asked."""
    try:
        os.makedirs(path, exist_ok=True)
        if opener is not None:
            opener(path)
        elif sys.platform == "win32":
            os.startfile(path)                                 # noqa: S606 -- a folder, in Explorer
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except OSError:
        return False


def data_dir():
    return user_dir()
