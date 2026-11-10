"""Test safety net: under unittest/pytest (or OPENRECOMP_TESTING=1) no code may see or remove real folders.

Importing the package (openrecomp/__init__.py) calls `enter_sandbox()`: when a test run is detected, LOCALAPPDATA,
APPDATA, USERPROFILE, HOME and OPENRECOMP_HOME point into a throwaway folder, and `launcher_parent()` (where
known_installs looks for game folders beside the launcher) is a folder inside it, never the real install.
`require_removable(path)` stands before everything that removes, moves or exchanges a game/data/program folder
(uninstall, game install/update/restore; the launcher's own updater repeats the rule): under a test run it raises
for any path outside the sandbox, the system temp folder and the folders the run itself made with tempfile."""
import atexit
import os
import shutil
import sys
import tempfile

_SANDBOX = None
_CREATED = []
DIRS_ENV = "OPENRECOMP_TEST_DIRS"


def _runner_loaded():
    return "unittest" in sys.modules or "pytest" in sys.modules


# Decided once, when the package is imported: a test runner is loaded before the code it tests. A launcher that runs
# for a player must not turn into a "test run" later because some module it loads imports unittest on the way
# (it would stop finding the games beside it and refuse to uninstall).
_RUNNER_AT_IMPORT = _runner_loaded()


def testing():
    return os.environ.get("OPENRECOMP_TESTING") == "1" or _RUNNER_AT_IMPORT


def _real(path):
    return os.path.normcase(os.path.realpath(path))


def _inside(path, base):
    path, base = _real(path), _real(base)
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def sandbox():
    return _SANDBOX


def _track_temp_folders():
    """Remember every folder this run makes with tempfile (TemporaryDirectory, mkdtemp), wherever it is: those are
    the folders a test created, so the only ones outside the system temp folder a test may change or remove.
    The ones outside it are also named in OPENRECOMP_TEST_DIRS for child processes (the update helper)."""
    original = tempfile.mkdtemp
    if getattr(original, "openrecomp_tracked", False):
        return

    def mkdtemp(*args, **kwargs):
        path = original(*args, **kwargs)
        real = _real(path)
        _CREATED.append(real)
        if not _inside(real, tempfile.gettempdir()):
            listed = [p for p in os.environ.get(DIRS_ENV, "").split(os.pathsep) if p and os.path.isdir(p)]
            os.environ[DIRS_ENV] = os.pathsep.join(listed[-80:] + [real])
        return path
    mkdtemp.openrecomp_tracked = True
    tempfile.mkdtemp = mkdtemp


def enter_sandbox():
    """Redirect every per-user location to a temp folder for the whole run (idempotent, test runs only)."""
    global _SANDBOX
    if _SANDBOX or not testing():
        return _SANDBOX
    _track_temp_folders()
    inherited = os.environ.get("OPENRECOMP_TEST_ROOT")
    if inherited and os.path.isdir(inherited) and _inside(inherited, tempfile.gettempdir()):
        _SANDBOX = os.path.realpath(inherited)       # a child of a test run lives in its parent's sandbox
    else:
        _SANDBOX = os.path.realpath(tempfile.mkdtemp(prefix="openrecomp-test-"))
        atexit.register(shutil.rmtree, _SANDBOX, True)
    os.environ["OPENRECOMP_TESTING"] = "1"
    os.environ["OPENRECOMP_TEST_ROOT"] = _SANDBOX
    for name, sub in (("LOCALAPPDATA", "local"), ("APPDATA", "roaming"), ("USERPROFILE", "home"), ("HOME", "home")):
        folder = os.path.join(_SANDBOX, sub)
        os.makedirs(folder, exist_ok=True)
        os.environ[name] = folder
    os.environ.setdefault("OPENRECOMP_HOME", os.path.join(_SANDBOX, "openrecomp-home"))
    return _SANDBOX


def launcher_parent(real_parent):
    """Where game folders beside the launcher are looked for: the real parent, except in a test run."""
    if testing():
        return os.path.join(enter_sandbox(), "launcher-parent")
    return real_parent


def _allowed_bases():
    bases = [tempfile.gettempdir()] + list(_CREATED)
    bases += [p for p in os.environ.get(DIRS_ENV, "").split(os.pathsep) if p]      # a parent test process made these
    if os.environ.get("OPENRECOMP_TEST_ROOT"):
        bases.append(os.environ["OPENRECOMP_TEST_ROOT"])
    return bases


def require_removable(path):
    """Raise ValueError when a test run is about to remove something outside the temp folders."""
    if testing() and not any(_inside(path, base) for base in _allowed_bases()):
        raise ValueError("refusing to remove outside the test temp folders: " + str(path))
