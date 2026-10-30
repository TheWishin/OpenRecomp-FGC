"""Background update work; the UI thread alone swaps state and requests a restart."""
import queue
import threading
from pathlib import Path

from . import updater


class UpdateService:
    def __init__(self, root=None, *, api=updater, busy=None, quit=None, worker=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
        self.api = api
        self.busy = busy or (lambda: False)
        self.quit = quit or (lambda: None)
        self.worker = worker or self._thread
        self.state = dict(phase="idle", version="", notes="", size=0)
        self.results = queue.Queue()
        self.release = None
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

    def check(self):
        if self.state["phase"] in ("checking", "installing"):
            return
        self.release = None
        self.state.update(phase="checking", version="", notes="", size=0)
        self._run("check", lambda: self.api.check_release(self.root))

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
                self.release = result
                self.state.update(phase="available" if result else "current",
                                  **{key: result.get(key, default) if result else default
                                     for key, default in (("version", ""), ("notes", ""), ("size", 0))})
            elif operation == "stage":
                self.prepared = result
        if self.prepared is not None and not self.applying and not self.busy():
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
