"""Remove OpenRecomp-FGC completely, from inside the launcher (0.1.3): the game folders it installed, its own data
folder (%LOCALAPPDATA%\\OpenRecomp), and -- through Setup's own uninstaller, or for a zip copy a short script after
the launcher closed -- the program folder, shortcuts and the Windows Apps entry.

`plan()` only lists; nothing is touched before the player confirmed the list. Never removed: a game folder this
launcher did not create (no install marker), a developer checkout (.git), disc images / packages / licences
(.iso .pkg .rap .edat: moved out to the kept folder first), and -- unless the player says otherwise -- saves and
replays (moved to `OpenRecomp-kept-<date>` beside the game folder)."""
from datetime import datetime
import os
import shutil
import subprocess

from . import game_releases
from . import safety
from .manifest import user_dir

GAMES = ("t4", "t5dr")
NEVER_DELETE = (".iso", ".pkg", ".rap", ".edat", ".sdat", ".bin.iso", ".cue", ".chd")
# Saves and replays per game, relative to its folder (kept unless the player removes everything).
KEEP = {"t4": ("save", "launcher/save", "logs/netplay-results"),
        "t5dr": ("native/gamedata", "native/gamedata-online", "native/replays", "native/save-backups",
                 "gamedata", "gamedata-online", "replays", "save-backups")}
SETUP_UNINSTALLER = "Uninstall OpenRecomp.exe"
WAIT_SECONDS = 6            # the zip copy's folder goes this long after the launcher quit
SETUP_RECORD = "OpenRecomp-install.txt"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def _unsafe(path):
    """A folder no uninstall may ever remove: a drive root, the user's home or a folder above it, a git checkout."""
    real = _norm(path)
    home = _norm(os.path.expanduser("~"))
    drive_root = os.path.dirname(real) == real
    return (drive_root or real == home or home.startswith(real + os.sep) or
            os.path.exists(os.path.join(path, ".git")))


def program_dir():
    """The launcher's own program folder (OpenRecomp-FGC: Setup's folder or the zip's)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plan(config, program=None):
    """What a complete uninstall would do: dict(games=[{game, root}], skipped=[{game, root, why}], data=<folder|"">,
    program=<folder|"">, setup_uninstaller=<exe|"">). Paths only; nothing is touched."""
    # Without a program folder given, the games beside the running launcher -- in a test run the sandbox's folder
    # (safety.launcher_parent), never a real folder beside the checkout.
    parent = None if program else safety.launcher_parent(os.path.dirname(program_dir()))
    program = program or program_dir()
    parent = parent or os.path.dirname(os.path.abspath(program))
    roots = (config.get("roots") or {}) if isinstance(config, dict) else {}
    games, skipped, seen = [], [], set()
    from .known_installs import candidates
    for game in GAMES:
        chosen = roots.get(game)
        # 0.1.3: every install of the game this launcher knows (the folder in use, the ones used before, the ones it
        # made), not only the one in use; still only those with its own install marker.
        for root in [chosen] + (candidates(config, game, parent=parent) if isinstance(config, dict) else []):
            if not isinstance(root, str) or not root or not os.path.isdir(root) or _norm(root) in seen:
                continue
            seen.add(_norm(root))
            if _unsafe(root):
                skipped.append(dict(game=game, root=root, why="unsafe"))
            elif not game_releases.managed(game, root):
                if root == chosen:
                    skipped.append(dict(game=game, root=root, why="not_ours"))
            else:
                games.append(dict(game=game, root=root))
    data = user_dir()
    data = data if os.path.isdir(data) and not _unsafe(data) else ""
    setup = os.path.join(program, SETUP_UNINSTALLER)
    has_setup = os.path.isfile(setup) and os.path.isfile(os.path.join(program, SETUP_RECORD))
    removable = not _unsafe(program) and os.path.isfile(os.path.join(program, "release.json"))
    return dict(games=games, skipped=skipped, data=data, program=program if (has_setup or removable) else "",
                setup_uninstaller=setup if has_setup else "")


def _kept_folder(root, stamp):
    return os.path.join(os.path.dirname(os.path.abspath(root)), "OpenRecomp-kept-" + stamp)


def _move_out(source, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        base, n = target, 2
        while os.path.exists(target):
            target = f"{base}-{n}"
            n += 1
    shutil.move(source, target)
    return target


def remove_game(game, root, keep_saves=True, stamp=None):
    """Remove one game folder this launcher installed. Disc images/packages/licences and (keep_saves) saves and
    replays are moved to OpenRecomp-kept-<stamp> beside it first. -> dict(kept=[paths], removed=root)."""
    safety.require_removable(root)       # first: saves are moved out before the folder goes
    if _unsafe(root) or not game_releases.managed(game, root):
        raise ValueError("not a folder this launcher installed: " + root)
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    kept_root = os.path.join(_kept_folder(root, stamp), game)
    kept = []
    if keep_saves:
        for relative in KEEP.get(game, ()):
            source = os.path.join(root, *relative.split("/"))
            if os.path.exists(source):
                kept.append(_move_out(source, os.path.join(kept_root, *relative.split("/"))))
    for folder, dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(NEVER_DELETE):
                source = os.path.join(folder, name)
                kept.append(_move_out(source, os.path.join(kept_root, "your-files", name)))
    safety.require_removable(root)
    shutil.rmtree(root)
    return dict(kept=kept, removed=root)


def execute(the_plan, keep_saves=True, start=None):
    """Do what plan() listed. Games and the data folder now; the program folder last, after the launcher quit
    (Setup's uninstaller /S /removesettings, or for a zip copy a short cmd script). -> dict(games, kept, data,
    program_started)."""
    start = start or subprocess.Popen
    # Only what the confirmed plan listed, and (test runs) nothing outside the temp folders.
    for item in the_plan.get("games", []):
        safety.require_removable(item["root"])
    for key in ("data", "program", "setup_uninstaller"):
        if the_plan.get(key):
            safety.require_removable(the_plan[key])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    result = dict(games=[], kept=[], data=False, program_started=False, errors=[])
    for item in the_plan.get("games", []):
        try:
            done = remove_game(item["game"], item["root"], keep_saves, stamp)
            result["games"].append(item["root"])
            result["kept"] += done["kept"]
        except (OSError, ValueError) as error:
            result["errors"].append(f"{item['root']}: {error}")
    data = the_plan.get("data")
    if data and os.path.isdir(data):
        safety.require_removable(data)
        shutil.rmtree(data, ignore_errors=True)
        result["data"] = not os.path.isdir(data)
    if the_plan.get("setup_uninstaller"):
        start([the_plan["setup_uninstaller"], "/S", "/removesettings"], creationflags=DETACHED | NO_WINDOW,
              close_fds=True)
        result["program_started"] = True
    elif the_plan.get("program"):
        folder = the_plan["program"]
        if '"' in folder or "%" in folder:
            result["errors"].append(f"{folder}: remove this folder by hand")     # cmd would read these characters
        else:
            # Waits until this launcher (its Python) has exited, then removes the zip copy's program folder. One
            # ready command line: a list made Python escape the quotes as \" (cmd does not know that), rmdir got a
            # wrong path and the folder stayed (0.1.3 real test); /s keeps the inner quotes as they are.
            cmd = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "cmd.exe")
            line = f'"{cmd}" /d /s /c "ping -n {WAIT_SECONDS} 127.0.0.1 >nul & rmdir /s /q "{folder}""'
            start(line, creationflags=DETACHED | NO_WINDOW, close_fds=True, cwd=os.path.dirname(folder))
            result["program_started"] = True
    return result
