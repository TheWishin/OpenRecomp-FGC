"""An operating-system reservation held from the final launch check until game exit."""
import errno
import os
import re
import tempfile
import threading


def _lock_file(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class LaunchGuard:
    """A per-game lock shared by launcher processes; no saved PID or stale-lock guesses.

    Acquire before the final native process check and game start. Keep the reservation
    until the child exits, including while an asynchronous stop is still pending.
    """

    def __init__(self, game_id, directory=None):
        if not re.fullmatch(r"[a-z0-9_-]+", game_id):
            raise ValueError("invalid game id")
        self.directory = directory or os.path.join(tempfile.gettempdir(), "OpenRecomp-FGC-launches")
        self.path = os.path.join(self.directory, game_id + ".lock")
        self._stream = None
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("@online.game_running")
            stream = None
            try:
                os.makedirs(self.directory, exist_ok=True)
                stream = open(self.path, "a+b")
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b"\0")
                    stream.flush()
            except OSError as error:
                if stream is not None:
                    stream.close()
                raise RuntimeError("@online.process_unknown") from error
            try:
                _lock_file(stream)
            except OSError as error:
                stream.close()
                message = ("@online.game_running" if error.errno in (errno.EACCES, errno.EAGAIN)
                           else "@online.process_unknown")
                raise RuntimeError(message) from error
            self._stream = stream
        return self

    def release(self, expected=None):
        with self._lock:
            stream = self._stream
            if stream is None or (expected is not None and stream is not expected):
                return
            self._stream = None
            try:
                _unlock_file(stream)
            finally:
                stream.close()

    def watch(self, running):
        """Release after confirmed exit. A failed process check keeps the reservation."""
        with self._lock:
            stream = self._stream
            if stream is None:
                raise RuntimeError("@online.process_unknown")

        def wait():
            pause = threading.Event()
            try:
                while running():
                    pause.wait(0.1)
            except Exception:  # noqa: BLE001 -- unknown child state must not permit a duplicate
                return
            self.release(expected=stream)

        worker = threading.Thread(target=wait, name="openrecomp-game-reservation", daemon=True)
        worker.start()
        return worker
