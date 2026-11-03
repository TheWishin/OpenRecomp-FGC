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
    def __init__(self, config, *, worker=None, latest=None, lobby=None, install=None, update=None, now=None):
        self.config = config                         # the launcher's config dict (read only here)
        self.worker = worker or self._thread
        self.latest = latest or gr.latest
        self.lobby = lobby or lobby_release
        self.install_fn = install or gr.install_fresh
        self.update_fn = update or gr.update_in_place
        self.now = now or time.time
        self.results = queue.Queue()
        self.state = {}
        self.offers = {}
        self.cancels = {}

    @staticmethod
    def _thread(fn):
        threading.Thread(target=fn, daemon=True, name="openrecomp-game-setup").start()

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

    def check(self, gid, root=None, *, force=False, online_hint=None):
        """Look for the newest release (and the lobby's required one). root None = the game is not installed."""
        if gid not in gr.SOURCES or self.busy(gid):
            return False
        st = self._st(gid)
        channel = gr.channel(self.config)
        installed = gr.installed_version(gid, root) if root else ""
        st.update(installed=installed, error="", detail="", root=root or "")
        cached = self._cache().get(gid)
        if (not force and isinstance(cached, dict) and cached.get("channel") == channel
                and 0 <= self.now() - cached.get("checked", 0) < CACHE_SECONDS):
            self._apply(gid, cached.get("offer"), cached.get("lobby"))
            return True
        st["phase"] = "checking"
        src = gr.SOURCES[gid]

        def work():
            lobby = None
            if root:
                try:
                    lobby = gr.offer_from_lobby(src, (online_hint or self.lobby)(gid, root))
                except Exception:  # noqa: BLE001 -- the lobby is optional; GitHub answers anyway
                    lobby = None
            offer = self.latest(src, channel)
            return dict(offer=offer, lobby=lobby, channel=channel)
        self._run(gid, "check", work)
        return True

    def _apply(self, gid, offer, lobby):
        st = self._st(gid)
        installed = st.get("installed", "")
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
                self._store(gid, dict(checked=self.now(), channel=result["channel"], offer=result["offer"],
                                      lobby=result["lobby"]))
                self._apply(gid, result["offer"], result["lobby"])
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


def lobby_release(gid, root):
    """The lobby's latest_release for an installed game, through that install's own updater (T5DR: lobby first,
    the same server list and certificate checks as online play). None for games without one."""
    if gid != "t5dr" or os.environ.get(gr.NO_CHECK_ENV) == "1":
        return None
    from .adapters.t5dr import load_runtime
    updater = load_runtime(root, "updater")
    fetch = getattr(updater, "fetch_lobby_release", None)
    return fetch(root) if callable(fetch) else None
