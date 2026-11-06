"""Background update work; the UI thread alone swaps state and requests a restart."""
import errno
import http.client
import queue
import threading
import time
import urllib.error
from pathlib import Path

from . import updater
from .progress_meter import Meter

BUSY_PHASES = ("checking", "installing", "waiting")


def failure_reason(error):
    """A short word for what went wrong, for a plain sentence (no addresses, no paths): network, verify (the
    download was refused by the security checks), space, or unknown."""
    if isinstance(error, OSError) and getattr(error, "errno", None) in (errno.ENOSPC, getattr(errno, "EDQUOT", -1)):
        return "space"
    if isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException)):
        return "network"
    if isinstance(error, updater.UpdateError):
        return "verify"
    return "unknown"


class UpdateService:
    def __init__(self, root=None, *, api=updater, busy=None, quit=None, worker=None, prereleases=None, now=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
        self.api = api
        self.busy = busy or (lambda: False)
        self.quit = quit or (lambda: None)
        self.worker = worker or self._thread
        self.prereleases = prereleases or (lambda: False)     # the player's Quick access -> Test versions switch
        self.quiet = False                                     # an automatic check: no "up to date" message
        self.now = now or time.time
        self.state = dict(phase="idle", version="", notes="", size=0, test_version="", target="", step="", done=0,
                          total=0, speed=0, left=0, can_cancel=True, cancelling=False, reason="")
        self.cancel_event = threading.Event()
        self.staged = None
        self._stale_checks = 0        # cancelled checks whose answer is still on its way: dropped when it comes
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
            except updater.UpdateCancelled:
                self.results.put((operation, None, "cancelled"))
            except Exception as error:  # no network addresses or machine paths in the UI
                phase = "unconfigured" if getattr(error, "key", "") == "updates_unconfigured" else "error"
                if phase == "error":
                    self.state["reason"] = failure_reason(error)
                self.results.put((operation, None, phase))
        self.worker(work)

    def _begin(self, phase, step, total=0):
        """A new run: a fresh cancel flag and progress meter. The same flag is what the worker's download watches."""
        self.cancel_event = threading.Event()
        self.staged = None
        self.state.update(phase=phase, step=step, done=0, total=total, speed=0, left=0, can_cancel=True,
                          cancelling=False, reason="")

    def _progress(self):
        meter, event = Meter(lambda: self.now()), self.cancel_event

        def report(step, done, total):
            fields = meter.update(step, done, total)
            if fields is not None and not event.is_set():
                self.state.update(fields)
        return report

    def cancel(self):
        """The player cancelled (Back / Esc / B / the Cancel button). While checking, downloading, verifying or
        unpacking, and while the staged update waits for games to close, nothing of the launcher is changed: the
        download stops, partial files go. Once the helper is started (restart) there is nothing to cancel."""
        phase = self.state["phase"]
        if self.applying or phase not in BUSY_PHASES or not self.state.get("can_cancel", True):
            return False
        if phase == "checking":
            self._stale_checks += 1
            self.state.update(phase="cancelled", step="", reason="")
            return True
        if phase == "waiting":
            self._discard()
            self.state.update(phase="cancelled", step="", reason="")
            return True
        if self.state.get("cancelling"):
            return True
        self.cancel_event.set()
        self.state["cancelling"] = True       # the worker answers within a second; poll() then says "cancelled"
        return True

    def _discard(self):
        staged, self.staged, self.prepared = self.staged, None, None
        discard = getattr(self.api, "discard_stage", None)
        if staged is not None and callable(discard):
            try:
                discard(staged)
            except OSError:
                pass

    def check(self, quiet=False):
        if self.state["phase"] in BUSY_PHASES or self.prepared is not None:
            return
        self.release = None
        self.test_release = None
        self.quiet = bool(quiet)
        test = bool(self.prereleases())
        self.state.update(phase="checking", version="", notes="", size=0, test_version="", target="", step="lookup",
                          done=0, total=0, speed=0, left=0, can_cancel=True, cancelling=False, reason="")

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
        if self.state["phase"] in BUSY_PHASES or self.prepared is not None or self.busy():
            return False
        self.quiet = False                 # the player asked for this: a failure is said, even after a quiet check
        self._begin("installing", "lookup")
        self.state.update(target=str(minimum))

        def prepare():
            release = self.api.release_for(self.root, minimum)
            if release is None:
                raise LookupError("no launcher release at or above " + str(minimum))
            self.state.update(version=release["version"], size=release.get("size", 0), total=release.get("size", 0))
            return self._stage(release)
        self._run("stage", prepare)
        return True

    def install(self):
        """Called only after the player confirms the offered release."""
        if self.state["phase"] != "available" or self.release is None or self.busy():
            return False
        self.quiet = False
        release = dict(self.release)
        self._begin("installing", "download", release.get("size", 0))
        self._run("stage", lambda: self._stage(release))
        return True

    def _stage(self, release):
        """Worker thread: download + verify + unpack, then the helper's copy. A cancel at any point removes the
        staged folder and ends in UpdateCancelled."""
        event = self.cancel_event
        staged = self.api.stage_update(self.root, release, progress=self._progress(), cancel=event)
        self.staged = staged
        if event.is_set():
            self._discard()
            raise updater.UpdateCancelled()
        self.state.update(step="prepare", done=0, total=0, speed=0, left=0)
        plan = self.api.prepare_update(self.root, staged)
        if event.is_set():
            self._discard()
            raise updater.UpdateCancelled()
        return plan

    def poll(self):
        changed = False
        while True:
            try:
                operation, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            changed = True
            if operation == "check" and self._stale_checks:
                self._stale_checks -= 1          # the player cancelled this check: its answer is not wanted
                continue
            if error == "cancelled":
                self._discard()
                self.state.update(phase="cancelled", step="", cancelling=False, can_cancel=True)
            elif error:
                self._discard()
                self.state.update(phase=error, step="", cancelling=False, can_cancel=True)
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
                self.state.update(step="", done=0, total=0, speed=0, left=0)
        if self.prepared is not None and not self.applying and self.busy():
            if self.state["phase"] != "waiting":
                self.state["phase"] = "waiting"
                changed = True
        elif self.prepared is not None and not self.applying:
            # Launch only on this thread, after a fresh busy check. The helper waits for our exit.
            self.applying = True
            self.state.update(step="restart", can_cancel=False, cancelling=False)     # the point of no return
            try:
                self.api.launch_update(self.root, self.prepared)
            except Exception as error:
                self.state.update(phase="error", step="", can_cancel=True, reason=failure_reason(error))
                self._discard()
                self.applying = False
            else:
                self.quit()
            changed = True
        return changed
