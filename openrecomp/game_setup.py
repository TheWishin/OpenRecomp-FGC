"""Background work for installing and updating T5DR / T4 (game_releases does the work, this keeps the state).

Only the UI thread reads `state` and calls the methods; one worker thread per job puts its result on a queue.
The view (`view(gid)`) carries no paths of the player's PC except the folder the player chose.
"""
import json
import os
import queue
import threading
import time

from . import game_releases as gr
from .manifest import user_dir

CACHE = "game-releases.json"
CACHE_SECONDS = 3600


def default_parent():
    """Beside OpenRecomp-FGC's own folder (where Setup put it, and where the launcher looks for T5DR-Online-*)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(here)


class GameSetup:
    def __init__(self, config, *, worker=None, latest=None, install=None, update=None, now=None):
        self.config = config                         # the launcher's config dict (read only here)
        self.worker = worker
        self.jobs = []                               # install/update threads: the launcher waits for them at exit
        self.latest = latest or gr.latest
        self.install_fn = install or gr.install_fresh
        self.update_fn = update or gr.update_in_place
        self.now = now or time.time
        self.results = queue.Queue()
        self.state = {}
        self.offers = {}
        self.github = {}                             # gid -> GitHub's newest offer of the channel (or None)
        self.lobby = {}                              # gid -> the lobby's announced release (offer), when seen
        self.cancels = {}

    def _thread(self, fn, keep=False):
        """A check may die with the launcher; an install or update never does (not a daemon: Python waits for it
        at exit, so an exchange of files always finishes or rolls back)."""
        t = threading.Thread(target=fn, daemon=not keep, name="openrecomp-game-setup")
        if keep:
            self.jobs = [j for j in self.jobs if j.is_alive()] + [t]
        t.start()

    def shutdown(self, timeout=None):
        """At the launcher's exit: ask every running install/update to stop, then wait for it (a cancel stops a
        download or unpack at once; an exchange of files already started runs to its end or its rollback)."""
        for event in list(self.cancels.values()):
            event.set()
        for t in list(self.jobs):
            t.join(timeout)
        return not any(t.is_alive() for t in self.jobs)

    def _st(self, gid):
        return self.state.setdefault(gid, dict(phase="idle", installed="", latest="", required=False,
                                               available=False, error="", detail="", step="", done=0, total=0,
                                               result="", rebuild=None, restart=False, parent="", source=""))

    def busy(self, gid=None):
        ids = [gid] if gid else list(self.state)
        return any(self.state.get(i, {}).get("phase") in ("checking", "installing", "updating") for i in ids)

    def _run(self, gid, kind, fn):
        def work():
            try:
                self.results.put((gid, kind, fn(), None))
            except gr.ReleaseError as e:
                self.results.put((gid, kind, None, (e.key, str(e))))
            except Exception as e:  # noqa: BLE001 -- never a dead worker: the player sees a plain failure
                self.results.put((gid, kind, None, ("@setup.err_unknown", repr(e))))
        if self.worker is None:
            self._thread(work, keep=kind in ("install", "update"))
        else:
            self.worker(work)

    # ------------------------------------------------------------------------------------------ checks
    def _cache(self):
        try:
            with open(os.path.join(user_dir(), CACHE), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _store(self, gid, entry):
        data = self._cache()
        data[gid] = entry
        try:
            os.makedirs(user_dir(), exist_ok=True)
            tmp = os.path.join(user_dir(), CACHE + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
            os.replace(tmp, os.path.join(user_dir(), CACHE))
        except OSError:
            pass

    def check(self, gid, root=None, *, force=False):
        """Look for the newest release on GitHub. root None = the game is not installed."""
        if gid not in gr.SOURCES or self.busy(gid):
            return False
        st = self._st(gid)
        channel = gr.channel(self.config, gid, root)
        installed = gr.installed_version(gid, root) if root else ""
        st.update(installed=installed, error="", detail="", root=root or "")
        cached = self._cache().get(gid)
        leftover = bool(root) and gr.interrupted_update(root)      # an update stopped midway: finish its rollback
        if (not leftover and not force and isinstance(cached, dict) and cached.get("channel") == channel
                and 0 <= self.now() - cached.get("checked", 0) < CACHE_SECONDS):
            self.github[gid] = cached.get("offer")
            self._apply(gid)
            return True
        st["phase"] = "checking"
        src = gr.SOURCES[gid]

        def work():
            out = dict(channel=channel)
            if leftover and gr.recover_update(gid, root):
                out["installed"] = gr.installed_version(gid, root)    # the old files are back
            out["offer"] = self.latest(src, channel)
            return out
        self._run(gid, "check", work)
        return True

    def note_lobby(self, gid, data, root=None):
        """The lobby's latest_release as the game's own online client saw it (its welcome, or the refusal of an
        old build). No connection of our own: the lobby is asked only when the player goes online."""
        if gid not in gr.SOURCES:
            return False
        offer = gr.offer_from_lobby(gr.SOURCES[gid], data)
        if offer is None or offer == self.lobby.get(gid):
            return False
        self.lobby[gid] = offer
        if root and not self._st(gid).get("installed"):
            self._st(gid)["installed"] = gr.installed_version(gid, root)
        if self._st(gid).get("phase") in ("ready", "idle", "error"):
            self._apply(gid)
        return True

    def _apply(self, gid):
        st = self._st(gid)
        installed = st.get("installed", "")
        offer, lobby = self.github.get(gid), self.lobby.get(gid)
        newest = offer
        if lobby and (not newest or gr.is_newer(lobby["version"], newest["version"])):
            newest = lobby
        self.offers[gid] = newest
        required_from = lobby or offer
        st.update(phase="ready", latest=newest["version"] if newest else "",
                  required=bool(installed and required_from and gr.is_newer(required_from["version"], installed)),
                  available=bool(installed and newest and gr.is_newer(newest["version"], installed)),
                  source="lobby" if lobby else "github",
                  size=newest["zip"]["size"] if newest else 0, prerelease=bool(newest and newest.get("prerelease")))

    # ------------------------------------------------------------------------------------------ install / update
    def space(self, gid, parent):
        offer = self.offers.get(gid)
        if not offer:
            return dict(problem="@setup.err_release", need=0, free=0, target="")
        src = gr.SOURCES[gid]
        return dict(problem=gr.check_target(src, offer, parent), need=gr.space_needed(src, offer),
                    free=gr.free_space(parent), target=gr.target_folder(src, offer, parent))

    def _progress(self, gid):
        def report(step, done, total):
            st = self._st(gid)
            st.update(step=step, done=int(done or 0), total=int(total or 0))
        return report

    def install(self, gid, parent):
        offer = self.offers.get(gid)
        if offer is None or self.busy():
            return False
        st = self._st(gid)
        cancel = threading.Event()
        self.cancels[gid] = cancel
        st.update(phase="installing", error="", detail="", step="download", done=0, total=offer["zip"]["size"],
                  parent=os.path.abspath(parent), result="")
        self._run(gid, "install", lambda: self.install_fn(gid, offer, parent, progress=self._progress(gid), cancel=cancel))
        return True

    def update(self, gid, root):
        offer = self.offers.get(gid)
        if offer is None or self.busy() or not root:
            return False
        st = self._st(gid)
        cancel = threading.Event()
        self.cancels[gid] = cancel
        st.update(phase="updating", error="", detail="", step="download", done=0, total=offer["zip"]["size"], result="")
        self._run(gid, "update", lambda: self.update_fn(gid, offer, root, progress=self._progress(gid), cancel=cancel))
        return True

    def cancel(self, gid):
        event = self.cancels.get(gid)
        if event is not None:
            event.set()

    def poll(self):
        """[(gid, kind, result, error)] finished since the last poll; the state is already updated."""
        out = []
        while True:
            try:
                gid, kind, result, error = self.results.get_nowait()
            except queue.Empty:
                return out
            st = self._st(gid)
            self.cancels.pop(gid, None)
            if error:
                key, detail = error
                st.update(phase="error" if key != "@setup.cancelled" else "ready", error=key, detail=detail)
            elif kind == "check":
                self._store(gid, dict(checked=self.now(), channel=result["channel"], offer=result["offer"]))
                self.github[gid] = result["offer"]
                if "installed" in result:
                    st["installed"] = result["installed"]
                self._apply(gid)
            elif kind == "install":
                st.update(phase="installed", result=result, installed=self.offers[gid]["version"],
                          required=False, available=False)
            elif kind == "update":
                st.update(phase="updated", installed=result["version"], rebuild=result.get("rebuild"),
                          restart=bool(result.get("restart")), required=False, available=False)
            out.append((gid, kind, result, error))

    def view(self, gid):
        st = dict(self._st(gid))
        offer = self.offers.get(gid)
        st["offer"] = dict(version=offer["version"], size=offer["zip"]["size"], name=offer["name"],
                           prerelease=offer["prerelease"], notes=offer["notes"]) if offer else None
        return st

