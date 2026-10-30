r"""Starts the real games through the launcher's own code path, checks that they run, stops them. Only what this script started.

    python tools\launch_check.py <scratch folder> [t5dr] [replay] [t4]

Tekken 5 DR runs muted, without taking the foreground and with a save folder of its own. Tekken 4 runs silent in a normal
window. Tekken 4's settings file is put back afterwards (a run writes its last_run record there).
"""
import ctypes
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openrecomp import adapters, manifest as mf  # noqa: E402
from openrecomp.nav import Game, Nav  # noqa: E402


def tail(path, n=6):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [line.rstrip() for line in f.readlines()[-n:]]
    except OSError as e:
        return [str(e)]


def games():
    manifests, problems = mf.load_all([mf.BUILTIN_DIR])
    print("manifest problems:", problems)
    return {m["id"]: Game(m, adapters.make(m, {})) for m in manifests}


def check_t5(scratch, replay=False):
    g = games()["t5dr"]
    print("t5dr root:", g.a.root, "| ready:", g.a.ready(), "|", g.a.status())
    env = {"PS3_WINDOW_BACKGROUND": "1", "PS3_AUDIO_MUTE": "1", "PS3_SAVEDATA_DIR": os.path.join(scratch, "t5save")}
    nav = Nav([g], launch_env=env)
    if replay:
        rows = g.a.replays()
        print("replays:", len(rows), rows[0]["label"], rows[0]["date"])
        nav.act("confirm")
        nav.sec["t5dr"] = "replays"
        nav.act("confirm")
    else:
        nav.act("play")
    print("toast:", nav.toast, "| running:", g.a.running(), "| pid:", g.a.game.proc.pid if g.a.game else None)
    time.sleep(22)
    alive = g.a.running()
    print("still running after 22 s:", alive, "| fps line:", g.a.game.fps, "| log:", g.a.game.log_path)
    for line in tail(g.a.game.log_path, 5):
        print("   ", line[:150])
    g.a.stop()
    deadline = time.time() + 10
    while g.a.running() and time.time() < deadline:
        time.sleep(0.2)
    print("stopped:", not g.a.running())
    return alive


def find_window(title):
    return ctypes.windll.user32.FindWindowW(None, title)


def check_t4(scratch):
    g = games()["t4"]
    print("t4 root:", g.a.root, "| ready:", g.a.ready(), "|", g.a.status())
    settings = g.a.core.SETTINGS_PATH
    backup = os.path.join(scratch, "t4_settings_backup.json")
    shutil.copyfile(settings, backup)
    nav = Nav([g], launch_env={"TEKKEN4_SOUND": "0"})
    try:
        nav.act("play")
        print("toast:", nav.toast, "| running:", g.a.running(), "| exe:", g.a.run.exe if g.a.run else None)
        time.sleep(25)
        alive = g.a.running()
        print("still running after 25 s:", alive)
        hwnd = find_window("TEKKEN 4")
        print("window:", hwnd)
        if hwnd and hasattr(g.a.core, "capture_window"):
            path = os.path.join(scratch, "t4_shot.png")
            print("capture:", g.a.core.capture_window(hwnd, path), os.path.exists(path))
        for line in tail(g.a.core.LAST_RUN_LOG, 5):
            print("   ", line[:150])
        g.a.stop()
        deadline = time.time() + 10
        while g.a.running() and time.time() < deadline:
            time.sleep(0.2)
        print("stopped:", not g.a.running())
        time.sleep(1)
    finally:
        shutil.copyfile(backup, settings)
    print("run lock after:", repr(g.a.core.run_lock_holder()))
    return alive


def main():
    lock = os.environ.get("OPENRECOMP_HEAVY_LOCK")
    if not lock:
        print("OPENRECOMP_HEAVY_LOCK is not set: not checking for heavy work on this PC.")
    elif os.path.exists(lock):
        print("Heavy work is running on this PC (HEAVY.lock): no game starts now.")
        return 2
    scratch = sys.argv[1]
    os.makedirs(scratch, exist_ok=True)
    wanted = sys.argv[2:] or ["t5dr", "replay", "t4"]
    ok = True
    if "t5dr" in wanted:
        ok &= check_t5(scratch)
    if "replay" in wanted:
        ok &= check_t5(scratch, replay=True)
    if "t4" in wanted:
        ok &= check_t4(scratch)
    print("RESULT:", "OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
