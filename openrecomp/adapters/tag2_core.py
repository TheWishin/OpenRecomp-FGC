"""The installed TAG2 PC launcher Core (Tag2.Launcher.Core.dll), used through a small host process.

TAG2 PC's account service, game session, launch settings and Ranked requests stay TAG2's own code: the Core that
its launcher uses. This module starts Windows PowerShell with `tag2_bridge/host.ps1`, which loads that Core and
compiles `tag2_bridge/Tag2Bridge.cs` against it; requests and answers are one JSON object per line on the pipes.

- Only a Core whose SHA-256 is in TRUSTED_CORES is loaded (a published TAG2 PC release). It is loaded from a
  private copy, so the install's file is never held open (TAG2's updater replaces it).
- A password goes to the Core in one request line on the pipe. It is never an argument, an environment variable,
  a file or a log line; answers and errors carry no token, key or request body.
- Nothing is retried here. A request the service refused is reported once (`kind` "sign_in" = sign in again).
"""
import hashlib
import json
import os
import shutil
import subprocess
import threading

from .. import __version__
from ..manifest import user_dir
from .base import NO_WINDOW

PRODUCT = "tag2-pc"
CORE_FILE = "Tag2.Launcher.Core.dll"
# Published TAG2 PC launcher Cores this adapter was written for (SHA-256 of the file -> its launcher version).
TRUSTED_CORES = {
    "4effa1893c92389a9bfd5f61204469cd1d59e61e3af4ed7806fd8b541db0dbce": "0.16.33",
}
MAX_CORE_BYTES = 8 * 1024 * 1024
MAX_LINE = 1024 * 1024
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag2_bridge")


def user_agent():
    return f"OpenRecomp-FGC/{__version__} ({PRODUCT})"


def powershell():
    return os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0",
                        "powershell.exe")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        data = stream.read(MAX_CORE_BYTES + 1)
    if len(data) > MAX_CORE_BYTES:
        raise OSError("too large")
    digest.update(data)
    return digest.hexdigest(), data


class CoreError(RuntimeError):
    """A refused request. kind: sign_in, build, profile, input, cancelled, bridge or error."""

    def __init__(self, kind, message=""):
        super().__init__(message or kind)
        self.kind = kind
        self.message = message


class Call:
    """One request: done, then result or error; status = the Core's last progress line."""

    def __init__(self, op):
        self.op = op
        self.done = threading.Event()
        self.result = None
        self.error = None
        self.status = ""

    def finish(self, result=None, error=None):
        self.result, self.error = result, error
        self.done.set()

    def wait(self, timeout):
        if not self.done.wait(timeout):
            raise CoreError("bridge", "timeout")
        if self.error is not None:
            raise self.error
        return self.result


class Core:
    def __init__(self, root, trusted=None, popen=None, cache=None, on_event=None):
        self.root = root
        self.trusted = TRUSTED_CORES if trusted is None else trusted
        self.popen = popen or subprocess.Popen
        self.cache = cache
        self.on_event = on_event or (lambda _event: None)
        self.lock = threading.RLock()
        self.proc = None
        self.calls = {}
        self.next_id = 0
        self.ready = threading.Event()
        self.failure = ""
        self.stderr = ""

    # ---------------------------------------------------------------- can it be used
    def core_path(self):
        return os.path.join(self.root, CORE_FILE)

    def problem(self):
        """"" when this install's Core can be used, else why not (a catalog key)."""
        if os.name != "nt" or not os.path.isfile(powershell()):
            return "@tag2.windows_only"
        try:
            digest, _data = sha256_file(self.core_path())
        except OSError:
            return "@tag2.core_missing"
        return "" if digest in self.trusted else "@tag2.core_unknown"

    def core_version(self):
        try:
            return self.trusted.get(sha256_file(self.core_path())[0], "")
        except OSError:
            return ""

    def _private_copy(self):
        digest, data = sha256_file(self.core_path())
        if digest not in self.trusted:
            raise CoreError("bridge", "@tag2.core_unknown")
        folder = os.path.join(self.cache or os.path.join(user_dir(), "tag2", "core"), digest)
        target = os.path.join(folder, CORE_FILE)
        try:
            same = sha256_file(target)[0] == digest
        except OSError:
            same = False
        if not same:
            os.makedirs(folder, exist_ok=True)
            temporary = target + ".new"
            with open(temporary, "wb") as stream:
                stream.write(data)
            os.replace(temporary, target)
        return target, digest

    # ---------------------------------------------------------------- the host process
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        with self.lock:
            if self.running():
                return
            why = self.problem()
            if why:
                raise CoreError("bridge", why)
            core, digest = self._private_copy()
            command = [powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                       "-File", os.path.join(HERE, "host.ps1"), "-Core", core, "-CoreSha256", digest,
                       "-Root", self.root, "-Agent", user_agent(), "-Bridge", os.path.join(HERE, "Tag2Bridge.cs")]
            self.ready.clear()
            self.failure = ""
            self.stderr = ""
            self.proc = self.popen(command, cwd=self.root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=NO_WINDOW)
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
            threading.Thread(target=self._read_errors, args=(self.proc,), daemon=True).start()

    def _read_errors(self, proc):
        for raw in proc.stderr:
            if len(self.stderr) < 2000:
                self.stderr += raw.decode("utf-8", "replace")

    def _read(self, proc):
        try:
            for raw in proc.stdout:
                if len(raw) > MAX_LINE or not raw.lstrip().startswith(b"{"):
                    continue
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(message, dict):
                    self._handle(message)
        finally:
            proc.wait()
            with self.lock:
                pending, self.calls = list(self.calls.values()), {}
            if not self.ready.is_set():
                self.failure = self.failure or "@tag2.core_failed"
                self.ready.set()
            for call in pending:
                call.finish(error=CoreError("bridge", "@tag2.core_failed"))
            self.on_event(dict(event="closed"))

    def _handle(self, message):
        event = message.get("event")
        if event == "ready":
            self.ready.set()
        elif event == "fatal":
            error = message.get("error") or {}
            self.failure = str(error.get("message") or "@tag2.core_failed")
            self.ready.set()
        elif event == "status":
            call = self.calls.get(message.get("id"))
            if call is not None:
                call.status = str(message.get("text") or "")
            self.on_event(message)
        elif event:
            self.on_event(message)
        elif "id" in message:
            with self.lock:
                call = self.calls.pop(message["id"], None)
            if call is None:
                return
            if message.get("ok"):
                call.finish(result=message.get("result"))
            else:
                error = message.get("error") or {}
                call.finish(error=CoreError(str(error.get("kind") or "error"), str(error.get("message") or "")))

    def request(self, op, **fields):
        """Send one request; -> its Call. The host is started when needed (the player asked for something)."""
        call = Call(op)
        try:
            self.start()
            if not self.ready.wait(60):
                raise CoreError("bridge", "@tag2.core_failed")
            if self.failure:
                raise CoreError("bridge", self.failure)
            with self.lock:
                self.next_id += 1
                number = self.next_id
                self.calls[number] = call
                line = json.dumps(dict(fields, id=number, op=op), ensure_ascii=True, allow_nan=False) + "\n"
                self.proc.stdin.write(line.encode("ascii"))
                self.proc.stdin.flush()
        except CoreError as e:
            call.finish(error=e)
        except (OSError, ValueError):
            call.finish(error=CoreError("bridge", "@tag2.core_failed"))
        return call

    def call(self, op, timeout=30, **fields):
        return self.request(op, **fields).wait(timeout)

    def close(self):
        with self.lock:
            proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write(b'{"op": "quit"}\n')
            proc.stdin.flush()
            proc.stdin.close()
            proc.wait(5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                proc.kill()
            except OSError:
                pass


def clear_cache(cache=None):
    """Remove the private Core copies (they are made again when needed)."""
    shutil.rmtree(cache or os.path.join(user_dir(), "tag2", "core"), ignore_errors=True)
