"""Wine / Proton (Linux, Steam Deck): what the launcher must know there. docs/LINUX_STEAM_DECK.md.

Tekken 4's build (tools/build_game.ps1) and its online check and log collection are PowerShell scripts. Windows
always has PowerShell; Wine and Proton ship only a stand-in powershell.exe that does not run scripts. Under Wine the
launcher asks PowerShell once whether it answers and otherwise says so (@t4.no_powershell) instead of starting a
script that cannot run. On Windows nothing here starts a process: powershell_works() is True at once.
"""
import ctypes
import os
import subprocess

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
PROBE = "Write-Output ('or' + 'ps' + 'ok')"      # the answer is not in the command line itself
_cache = {}


def wine_version(ntdll=None):
    """'10.0' when this process runs under Wine or Proton (ntdll exports wine_get_version only there), else None.
    `ntdll`: a stand-in (tests)."""
    if ntdll is None:
        if "wine" in _cache:
            return _cache["wine"]
        if os.name != "nt":
            _cache["wine"] = None
            return None
    try:
        get = (ntdll or ctypes.WinDLL("ntdll")).wine_get_version
        get.restype = ctypes.c_char_p
        found = (get() or b"?").decode("ascii", "replace")
    except (AttributeError, OSError, ValueError):
        found = None
    if ntdll is None:
        _cache["wine"] = found
    return found


def powershell_works(run=None, wine=None):
    """True when PowerShell can run scripts here. Asked only under Wine (once, 20 s at most); `run`/`wine`: tests."""
    if not (wine if wine is not None else wine_version()):
        return True
    if run is None and "powershell" in _cache:
        return _cache["powershell"]
    try:
        result = (run or subprocess.run)(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROBE],
                                         stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                                         timeout=20, creationflags=NO_WINDOW)
        works = "orpsok" in (result.stdout or "")
    except (OSError, subprocess.SubprocessError):
        works = False
    if run is None:
        _cache["powershell"] = works
    return works
