"""Checks for the source test bundle's build tools, and the winget installs the player confirms in the launcher."""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from .base import NO_WINDOW


VS_COMMAND = ('winget install --id Microsoft.VisualStudio.2022.BuildTools --exact '
              '--override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"')
COMMANDS = dict(python="winget install --id Python.Python.3.12 --exact",
                git="winget install --id Git.Git --exact",
                cmake="winget install --id Kitware.CMake --exact",
                ninja="winget install --id Ninja-build.Ninja --exact",
                vs2022=VS_COMMAND, msvc=VS_COMMAND)


def _output(command):
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                timeout=8, creationflags=NO_WINDOW, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _version(text):
    match = re.search(r"(?<![\d.])(\d+\.\d+(?:\.\d+)*)(?!\d)", text)
    return match.group(1) if match else ""


def _at_least(version, minimum):
    if not version:
        return False
    parts = tuple(int(part) for part in version.split("."))
    return parts + (0,) * max(0, len(minimum) - len(parts)) >= minimum


def _row(sid, version="", ok=False, value=None):
    return dict(id=sid, label="@t4.tools." + sid, value=value or version or "@t4.tools.missing",
                ok=bool(ok), command=COMMANDS[sid])


def _visual_studio():
    """Use the same VS 2022 C++ setup discovery as the installed build scripts."""
    program_files = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    vswhere = program_files / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None, ""
    command = [str(vswhere), "-latest", "-products", "*", "-version", "[17.0,18.0)",
               "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64"]
    install = _output(command + ["-property", "installationPath"])
    version = _version(_output(command + ["-property", "installationVersion"]))
    if not install or "\n" in install or not version.startswith("17."):
        return None, ""
    return Path(install), version


def _msvc_version(install):
    if install is None:
        return "", False
    try:
        version = (install / "VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt").read_text(
            encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return "", False
    if not re.fullmatch(r"14\.\d+\.\d+", version):
        return "", False
    compiler = install / "VC/Tools/MSVC" / version / "bin/Hostx64/x64/cl.exe"
    # The v143 family is 14.3x or newer; keep the exact toolset version visible.
    return version, _at_least(version, (14, 30)) and compiler.is_file()


def _has_sdk():
    kits = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Windows Kits/10"
    try:
        for include in (kits / "Include").iterdir():
            if ((include / "um/Windows.h").is_file()
                    and (kits / "Lib" / include.name / "um/x64/kernel32.lib").is_file()):
                return True
    except OSError:
        pass
    return False


def _tool(name, extras):
    """Version-check PATH candidates too: a stub or old CMake is not ready."""
    candidate = shutil.which(name)
    if candidate:
        return _version(_output([candidate, "--version"]))
    for folder in extras:
        candidate = folder / (name + ".exe")
        if candidate.is_file():
            return _version(_output([str(candidate), "--version"]))
    return ""


def check_prerequisites():
    """Return version/availability rows and copyable commands; never install anything.

    Call on a worker and refresh after installing tools. Full paths and command
    output stay out of the rows; only parsed versions reach the screen.
    """
    python = ".".join(str(value) for value in sys.version_info[:3])
    rows = [_row("python", python, sys.version_info[:2] >= (3, 12))]
    install, vs_version = _visual_studio()
    extras = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "CMake/bin"]
    if os.environ.get("LOCALAPPDATA"):
        extras.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft/WinGet/Links")
    if install is not None:
        extras += [install / "Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin",
                   install / "Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja"]
    for name, minimum in (("git", (1,)), ("cmake", (3, 20)), ("ninja", (1,))):
        version = _tool(name, extras if name != "git" else [])
        rows.append(_row(name, version, _at_least(version, minimum)))
    msvc, compiler_ok = _msvc_version(install)
    complete = (install is not None and compiler_ok and _has_sdk()
                and (install / "VC/Auxiliary/Build/vcvars64.bat").is_file())
    rows.append(_row("vs2022", vs_version, complete,
                     "@t4.tools.vs_incomplete" if install is not None and not complete else None))
    rows.append(_row("msvc", msvc, compiler_ok))
    return rows


# winget would otherwise stop and ask on a console nobody sees; the player agreed by pressing Build (the Build card
# says first that missing tools are installed and their licence terms apply). --silent where the installer has it.
WINGET_FLAGS = ["--silent", "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]
WINGET_ALREADY = (0x8A15002B, 0x8A150061)       # no newer version / package already installed: not a failure
# Installed, but Windows must restart first (winget's REBOOT_REQUIRED_TO_FINISH / _TO_INSTALL, an installer's 3010
# or 1641 passed through): the build continues after the restart (T4.build_resume_pending).
WINGET_REBOOT = (0x8A150109, 0x8A15010A, 3010, 1641)


def install_plan(rows):
    """The missing rows -> [(label, command)], one per installer (VS and MSVC share one)."""
    plan, seen = [], set()
    for row in rows:
        command = row.get("command") or COMMANDS.get(row.get("id"), "")
        if row.get("ok") is False and not row.get("busy") and command and command not in seen:
            seen.add(command)
            plan.append((row["label"], command))
    return plan


def winget_args(command):
    """A command of COMMANDS -> argv for subprocess (no shell); only winget installs are ever run."""
    args = shlex.split(command, posix=True)
    if len(args) < 3 or args[:2] != ["winget", "install"]:
        raise ValueError("not a winget install")
    winget = shutil.which("winget")
    if not winget:
        raise FileNotFoundError("winget")
    return [winget] + args[1:] + WINGET_FLAGS


def install_status(command, run=subprocess.run):
    """One winget install, hidden, no timeout (Visual Studio takes long). -> "ok" (installed or already there),
    "reboot" (installed, Windows must restart first) or "failed"."""
    result = run(winget_args(command), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, creationflags=NO_WINDOW, check=False)
    code = result.returncode & 0xFFFFFFFF
    if code == 0 or code in WINGET_ALREADY:
        return "ok"
    return "reboot" if code in WINGET_REBOOT else "failed"


def run_install(command, run=subprocess.run):
    """-> True when installed or already there (a restart still pending counts as installed)."""
    return install_status(command, run) != "failed"


def refresh_path(environ=None, read=None):
    """Installers change the user's and the machine's PATH; this process still has the old one. Add the new parts
    (the build started from this launcher inherits them) so the re-check finds the new tools without a restart."""
    environ = os.environ if environ is None else environ
    if read is None:
        read = _registry_paths
    current = environ.get("PATH", "")
    known = {_path_key(part) for part in current.split(os.pathsep) if part}
    added = []
    for value in read():
        for part in os.path.expandvars(value).split(os.pathsep):
            key = _path_key(part)
            if part and key not in known:
                known.add(key)
                added.append(part)
    if added:
        environ["PATH"] = os.pathsep.join([current] + added if current else added)
    return added


def _path_key(part):
    return os.path.normcase(part.rstrip("/" + os.sep))


def _registry_paths():
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(hive, key) as handle:
                out.append(str(winreg.QueryValueEx(handle, "Path")[0]))
        except OSError:
            pass
    return out
