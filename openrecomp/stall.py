"""A stall detector for the launcher's GUI thread. No Qt in here: the app beats the heart from its own timer.

OPENRECOMP_STALL_LOG=<file> turns it on (OPENRECOMP_STALL_MS: the gap that counts, default 100). A watcher thread
looks every 10 ms whether the GUI thread's heartbeat is late; once it is, it takes the GUI thread's Python stack, so
the log says where most of the time went (a file read, a network call, building the view). One line per stall:

    stall 182 ms  tag=lobby  at openrecomp/adapters/t5dr.py:212 release <- ...

A gap with no Python on the stack is time spent in Qt (QML bindings, layout, drawing).
"""
import os
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))


def _short(path):
    path = os.path.abspath(path)
    parent = os.path.dirname(HERE)
    return os.path.relpath(path, parent).replace("\\", "/") if path.startswith(parent) else os.path.basename(path)


class StallWatch:
    def __init__(self, threshold_ms=100, log_path=None, clock=time.perf_counter):
        self.threshold = threshold_ms / 1000.0
        self.log_path = log_path
        self.clock = clock
        self.main = threading.get_ident()
        self.last = clock()
        self.tag = ""
        self.stalls = []                 # (ms, tag, where)
        self._samples = []               # the GUI thread's stack, every 10 ms while its beat is late
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.last = self.clock()
        self._thread = threading.Thread(target=self._watch, name="openrecomp-stallwatch", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def beat(self):
        """Called by the GUI thread's timer. A late beat ends a stall."""
        now = self.clock()
        gap = now - self.last
        self.last = now
        if gap >= self.threshold:
            with self._lock:
                samples, self._samples = self._samples, []
            where = max(set(samples), key=samples.count) if samples else ""
            where = where or "(Qt: no Python running)"
            self.stalls.append((round(gap * 1000), self.tag, where))
            if self.log_path:
                try:
                    with open(self.log_path, "a", encoding="utf-8") as out:
                        out.write("stall %d ms  tag=%s  at %s\n" % (gap * 1000, self.tag or "-", where))
                except OSError:
                    pass

    def _watch(self):
        while not self._stop.wait(0.01):
            if self.clock() - self.last < 0.03:
                with self._lock:
                    self._samples = []
                continue
            frame = sys._current_frames().get(self.main)  # noqa: SLF001 -- the one way to see another thread's stack
            where = self.describe(frame)
            with self._lock:
                self._samples.append(where)

    @staticmethod
    def describe(frame, depth=6):
        if frame is None:
            return ""
        parts = []
        for entry in traceback.extract_stack(frame)[::-1]:
            if "PySide6" in entry.filename or entry.filename.endswith("stall.py"):
                continue
            parts.append("%s:%d %s" % (_short(entry.filename), entry.lineno, entry.name))
            if len(parts) == depth:
                break
        return " <- ".join(parts)

    def summary(self, tag=None):
        gaps = [ms for ms, t, _ in self.stalls if tag is None or t == tag]
        return dict(count=len(gaps), worst=max(gaps, default=0), total=sum(gaps))


def from_env(environ=None):
    environ = os.environ if environ is None else environ
    path = environ.get("OPENRECOMP_STALL_LOG")
    if not path:
        return None
    try:
        threshold = max(20, int(environ.get("OPENRECOMP_STALL_MS") or 100))
    except ValueError:
        threshold = 100
    return StallWatch(threshold, path).start()
