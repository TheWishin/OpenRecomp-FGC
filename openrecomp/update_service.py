"""Background update work; the UI thread alone swaps state and requests a restart."""
import queue
import threading
from pathlib import Path

from . import updater


class UpdateService:
    def __init__(self, root=None, *, api=updater, busy=None, quit=None, worker=None, prereleases=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
        self.api = api
        self.busy = busy or (lambda: False)
        self.quit = quit or (lambda: None)
        self.worker = worker or self._thread
        self.prereleases = prereleases or (lambda: False)     # the player's Quick access -> Test versions switch
        self.quiet = False                                     # an automatic check: no "up to date" message
        self.state = dict(phase="idle", version="", notes="", size=0, test_version="", target="")
        self.results = queue.Queue()
        self.release = None
        self.test_release = None      # a newer test version (pre-release) while the launcher is current on stable
        self.prepared = None
        self.applying = False

    @staticmethod
    def _thread(fn):
        threading.Thread(target=fn, daemon=True, name="openrecomp-update").start()

    def _run(self, operation, fn):
        def work():
            try:
                self.results.put((operation, fn(), ""))
            except Exception as error:  # no network addresses or machine paths in the UI
                phase = "unconfigured" if getattr(error, "key", "") == "updates_unconfigured" else "error"
                self.results.put((operation, None, phase))
        self.worker(work)

    def check(self, quiet=False):
        if self.state["phase"] in ("checking", "installing", "waiting") or self.prepared is not None:
            return
        self.release = None
        self.test_release = None
        self.quiet = bool(quiet)
        test = bool(self.prereleases())
        self.state.update(phase="checking", version="", notes="", size=0, test_version="", target="")

        def work():
            release = self.api.check_release(self.root, prereleases=test)
            newer_test = None
            if release is None and not test and hasattr(self.api, "release_offers"):
                try:
                    newer_test = self.api.release_offers(self.root)[1]
                except Exception:
                    newer_test = None          # only a hint: the stable answer stands
            return dict(release=release, test=newer_test)
        self._run("check", work)

    def take_test(self):
        """The player chose the test version named in "The launcher is up to date": offer it like a stable update."""
        if self.state["phase"] != "current" or self.test_release is None:
            return False
        self.release = self.test_release
        self.state.update(phase="available", version=self.release["version"], notes=self.release.get("notes", ""),
                          size=self.release.get("size", 0))
        return True

    def install_for(self, minimum):
        """Update all (a game release needs OpenRecomp-FGC `minimum`): find a launcher release at or above it -- the
        newest stable one, else a test version -- and install it without another question (the player pressed
        Update all). The game update continues after the restart (app_game_setup: pending game update)."""
        if self.state["phase"] in ("checking", "installing", "waiting") or self.prepared is not None or self.busy():
            return False
        self.state.update(phase="installing", target=str(minimum))

        def prepare():
            release = self.api.release_for(self.root, minimum)
            if release is None:
                raise LookupError("no launcher release at or above " + str(minimum))
            self.state.update(version=release["version"], size=release.get("size", 0))
            staged = self.api.stage_update(self.root, release)
            return self.api.prepare_update(self.root, staged)
        self._run("stage", prepare)
        return True

    def install(self):
        """Called only after the player confirms the offered release."""
        if self.state["phase"] != "available" or self.release is None or self.busy():
            return False
        self.state["phase"] = "installing"
        release = dict(self.release)
        def prepare():
            staged = self.api.stage_update(self.root, release)
            return self.api.prepare_update(self.root, staged)
        self._run("stage", prepare)
        return True

    def poll(self):
        changed = False
        while True:
            try:
                operation, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            changed = True
            if error:
                self.state["phase"] = error
            elif operation == "check":
                if isinstance(result, dict) and "release" in result and "test" in result:
                    result, self.test_release = result["release"], result["test"]
                self.release = result
                self.state.update(phase="available" if result else "current",
                                  test_version=self.test_release["version"] if self.test_release and not result else "",
                                  **{key: result.get(key, default) if result else default
                                     for key, default in (("version", ""), ("notes", ""), ("size", 0))})
            elif operation == "stage":
                self.prepared = result
        if self.prepared is not None and not self.applying and self.busy():
            if self.state["phase"] != "waiting":
                self.state["phase"] = "waiting"
                changed = True
        elif self.prepared is not None and not self.applying:
            # Launch only on this thread, after a fresh busy check. The helper waits for our exit.
            self.applying = True
            try:
                self.api.launch_update(self.root, self.prepared)
            except Exception:
                self.state["phase"] = "error"
                self.prepared = None
                self.applying = False
            else:
                self.quit()
            changed = True
        return changed
