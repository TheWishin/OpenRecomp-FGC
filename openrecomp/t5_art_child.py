"""Pictures read from the player's own Tekken 5 build, in a short-lived child process.

The launcher process also carries the online relay bridge and the UI; decoding a 2048-pixel DXT5 picture in a Python
thread there holds the GIL for long stretches. T5DR.rank_plates/fighter_render start this file with the same Python
(`-I`: no user site, no environment path, no current folder) and wait for it from a thread that only blocks on the
child. The file adds the launcher's package folder and the install's folders itself, writes only into the user
folder / the build's own cache folder as before, and exits 0 when it finished.

    python -I t5_art_child.py <json: {"job": "plates"|"render", "root", "out_dir", ...}>
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
BELOW_NORMAL = 0x00004000 if os.name == "nt" else 0


def plates():
    return {"job": "plates"}


def render(gid, path, mirrored=False):
    return {"job": "render", "gid": gid, "path": path, "mirrored": bool(mirrored)}


def run(root, out_dir, job):
    """Run `job` in a child process of the same Python (-I), below normal priority, with no window, and wait for it:
    (exit code, last error line). The calling thread only blocks on the child, so the launcher's GIL is never held
    by the decoding."""
    python = sys.executable
    if os.name == "nt" and python.lower().endswith("pythonw.exe"):
        candidate = python[:-len("pythonw.exe")] + "python.exe"
        python = candidate if os.path.isfile(candidate) else python
    job = dict(job, root=root, out_dir=out_dir)
    done = subprocess.run([python, "-I", os.path.abspath(__file__), json.dumps(job)], cwd=tempfile.gettempdir(),
                          creationflags=NO_WINDOW | BELOW_NORMAL, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, timeout=600)
    lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
    return done.returncode, (lines[-1] if lines else "")


def _paths(root):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in (os.path.join(root, "launcher"), os.path.join(root, "tools"), os.path.join(root, "lobby"), here):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    sys.dont_write_bytecode = True


def make_plates(out_dir):
    ra = importlib.import_module("t5lobby.rank_art")
    if not ra.is_ready(ra.folder_for(out_dir)):
        ra.extract(out_dir)


def make_render(out_dir, gid, path, mirrored=False):
    from openrecomp.fighter_render import t5_cutout, write_render
    decoder = importlib.import_module("t5lobby.fighter_art")
    sources = decoder.ra.find_sources(out_dir)
    if not sources:
        raise LookupError("no readable game data")
    write_render(path, *t5_cutout(decoder, sources, gid, mirrored=mirrored))


def main(argv):
    job = json.loads(argv[1])
    _paths(job["root"])
    if job["job"] == "plates":
        make_plates(job["out_dir"])
    elif job["job"] == "render":
        make_render(job["out_dir"], int(job["gid"]), job["path"], bool(job.get("mirrored")))
    else:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as error:  # noqa: BLE001 -- the parent only needs the exit code and the last line
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
