"""Test safety net: under unittest/pytest (or OPENRECOMP_TESTING=1) no code may see or remove real folders.

Importing the package (openrecomp/__init__.py) calls `enter_sandbox()`: when a test run is detected, LOCALAPPDATA,
APPDATA, USERPROFILE, HOME and OPENRECOMP_HOME point into a throwaway folder, and `launcher_parent()` (where
known_installs looks for game folders beside the launcher) is a folder inside it, never the real install.
`require_removable(path)` is the last line before an rmtree of a game/data/program folder: under a test run it
raises for any path outside the sandbox / the system temp folder."""
import atexit
import os
import shutil
import sys
import tempfile

_SANDBOX = None


def testing():
    return (os.environ.get("OPENRECOMP_TESTING") == "1" or "unittest" in sys.modules or "pytest" in sys.modules)


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def _inside(path, base):
    path, base = _real(path), _real(base)
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def sandbox():
    return _SANDBOX


def enter_sandbox():
    """Redirect every per-user location to a temp folder for the whole run (idempotent, test runs only)."""
    global _SANDBOX
    if _SANDBOX or not testing():
        return _SANDBOX
    _SANDBOX = os.path.realpath(tempfile.mkdtemp(prefix="openrecomp-test-"))
    os.environ["OPENRECOMP_TESTING"] = "1"
    os.environ["OPENRECOMP_TEST_ROOT"] = _SANDBOX
    for name, sub in (("LOCALAPPDATA", "local"), ("APPDATA", "roaming"), ("USERPROFILE", "home"), ("HOME", "home")):
        folder = os.path.join(_SANDBOX, sub)
        os.makedirs(folder, exist_ok=True)
        os.environ[name] = folder
    os.environ.setdefault("OPENRECOMP_HOME", os.path.join(_SANDBOX, "openrecomp-home"))
    atexit.register(shutil.rmtree, _SANDBOX, True)
    return _SANDBOX


def launcher_parent(real_parent):
    """Where game folders beside the launcher are looked for: the real parent, except in a test run."""
    if testing():
        return os.path.join(enter_sandbox(), "launcher-parent")
    return real_parent


def _allowed_bases():
    bases = [tempfile.gettempdir()]
    if os.environ.get("OPENRECOMP_TEST_ROOT"):
        bases.append(os.environ["OPENRECOMP_TEST_ROOT"])
    return bases


def require_removable(path):
    """Raise ValueError when a test run is about to remove something outside the temp folders."""
    if testing() and not any(_inside(path, base) for base in _allowed_bases()):
        raise ValueError("refusing to remove outside the test temp folders: " + str(path))
