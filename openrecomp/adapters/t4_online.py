"""T4 online: direct-IP / VPN checks, and the lobby (accounts, players, chat, matches) through the vendored client."""
import hashlib
import importlib
import ipaddress
import json
import os
import queue
import re
import subprocess
import threading
import time
import uuid
import zipfile

from .base import NO_WINDOW
from .t5_match import T5Match
from .t5_online import Online, SearchRefused, entry_tls, game_process_running
from ..manifest import save_config, user_dir
from .. import wine
from ..vendor.t4lobby import ranks as t4_ranks


# The T4 lobby client ships with the launcher (openrecomp/vendor/t4lobby); T4 installs have none.
VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor")
SERVER_ENV = "OPENRECOMP_T4_SERVER"
# The server the launcher ships with ("T4 Online"; a placeholder until tools/set_t4_server.py fills it in).
SHIPPED_SERVERS = os.path.join(VENDOR, "servers.json")
SERVERS_FORMAT = "t5dr-servers/1"
# Our own fallback rank badges (tools/make_rank_badges.py: T5DR's rank names), one SVG per T4 rank tier.
RANK_BADGES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "assets", "ranks")
# T5DR's lobby features that work for Tekken 4 as they are (docs/T4_ONLINE.md "What T4 Online has"): the server is
# T5DR's lobby (1.2.0, t4-parity). Left out: spectating (the T4 game has no replay recorder yet) and the health
# handicap / training rooms (t5_rules: the T4 game has no life rules yet); the T4 server never takes those caps.
T4_FEATURE_MODULES = (".t5_tournaments", ".t5_profiles", ".t5_community", ".t5_accounts", ".t5_challenges",
                      ".t5_moderation", ".t5_private_chat")


def source_net_profile(config):
    """The netplay switches a source-test build runs online with, the same for direct IP and lobby matches."""
    env = dict(TEKKEN4_NET_COALESCE="1", TEKKEN4_NET_DIAG="1",
               TEKKEN4_RB_AUDIO_TIMELINE="0", TEKKEN4_NET_REFRESH_RC="0",
               TEKKEN4_NET_AUTO_VS="0", TEKKEN4_NET_TIMESYNC="1",
               TEKKEN4_NET_MAXPRED="8", TEKKEN4_NET_EARLY="1",
               TEKKEN4_NET_LAZY="1", TEKKEN4_NET_LOCALPAD="1")
    diagnostics = config.get("t4_diagnostics")
    if isinstance(diagnostics, dict) and diagnostics.get("net_diagnostics") is False:
        env["TEKKEN4_NET_DIAG"] = "0"
    return env


DIRECT_CHECKS = ("build", "compiler", "iso", "udp")
DIRECT_LABELS = dict(build="@t4.direct_check_build", compiler="@t4.direct_check_compiler",
                     iso="@t4.direct_check_iso", udp="@t4.direct_check_udp")
DIRECT_FAILURES = dict(build="@t4.direct_build_mismatch", compiler="@t4.direct_compiler_mismatch",
                       iso="@t4.direct_iso_mismatch", udp="@t4.direct_unreachable")
IDENTITY_RULES = dict(build_id=r"[0-9a-f]{16}", compiler=r"[A-Za-z0-9_.+ -]{1,100}",
                      iso_sha256=r"[0-9a-f]{64}", elf_sha1=r"[0-9a-f]{40}",
                      net=r"[0-9]{1,3}", strict_hello=r"[01]", delay_match=r"[01]")
# Call the installed tools, never copy their implementation or start net_play.ps1 during checks.
PREFLIGHT_SCRIPT = r'''
param([string]$Tool, [string]$BuildStamp, [string]$Iso, [string]$Elf,
      [string]$Output, [string]$Peer, [int]$Port, [switch]$AsHost)
$ErrorActionPreference = 'Stop'
. $Tool
@{side = $(if ($AsHost) {'host'} else {'join'}); port = $Port; delay = 'auto'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $Output) 'run_info.json') -Encoding UTF8
$identity = New-T4NetIdentity -BuildStampJson $BuildStamp -IsoPath $Iso
if ((Get-FileHash -LiteralPath $Elf -Algorithm SHA1).Hash.ToLowerInvariant() -cne $identity.elf_sha1) {
    throw 'stale_elf'
}
$identity | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path (Split-Path -Parent $Output) 'build_identity.json') -Encoding UTF8
Invoke-T4NetPreflight -AsHost ([bool]$AsHost) -Peer $Peer -Port $Port -Identity $identity -TimeoutSeconds 90 -OutputPath $Output
'''


LOBBY_CODE_PREFIX = b"t4-lobby-code-v1:"
HEX_DIGEST = re.compile(r"[0-9a-f]{40,64}")
_hash_cache = {}


def lobby_code(code_id, compiler, iso_sha):
    """The code field a lobby launcher sends: SHA-1 over the build's code id, the compiler and the ISO (40 hex digits
    like a code id). Equal only for the same code, the same compiler and the same disc image."""
    fields = (str(code_id).lower(), str(compiler), str(iso_sha).lower())
    return hashlib.sha1(LOBBY_CODE_PREFIX + b":".join(field.encode() for field in fields)).hexdigest()


def stamp_compiler(path):
    """'<CXX_ID> <CXX_VERSION>' from t4net_build.json's toolchain lines, the same string Direct IP compares.
    Raises ValueError when the stamp has none (a build from before the toolchain record: rebuild)."""
    with open(path, "rb") as stream:
        data = stream.read(32769)
    if len(data) > 32768:
        raise ValueError          # (callers say "rebuild"; no text of its own)
    stamp = json.loads(data.decode("utf-8-sig"))
    toolchain = stamp.get("toolchain") if isinstance(stamp, dict) else None
    if not isinstance(toolchain, list) or not all(isinstance(line, str) for line in toolchain):
        raise ValueError
    ids = [line[7:] for line in toolchain if line.startswith("CXX_ID=")]
    versions = [line[12:] for line in toolchain if line.startswith("CXX_VERSION=")]
    if len(ids) != 1 or len(versions) != 1:
        raise ValueError
    compiler = ids[0] + " " + versions[0]
    if not re.fullmatch(IDENTITY_RULES["compiler"], compiler):
        raise ValueError
    return compiler


def _file_hash(path, algorithm):          # algorithm: a hashlib constructor
    """hashlib digest of a file, remembered for its size and time (an ISO is hashed once per launcher run and
    once more only when it changes; the cache file keeps it across runs)."""
    info = os.stat(path)
    key = f"{algorithm().name}|{os.path.normcase(os.path.realpath(path))}|{info.st_size}|{info.st_mtime_ns}"
    if key in _hash_cache:
        return _hash_cache[key]
    cache_path = os.path.join(user_dir(), "t4-online", "hashes.json")
    try:
        with open(cache_path, encoding="utf-8") as stream:
            saved = json.load(stream)
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    digest = saved.get(key)
    if not (isinstance(digest, str) and HEX_DIGEST.fullmatch(digest)):
        h = algorithm()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                h.update(block)
        digest = h.hexdigest()
        same_file = key.rsplit("|", 2)[0] + "|"                   # an older hash of this file is out of date
        saved = {k: v for k, v in saved.items() if not k.startswith(same_file)}
        saved[key] = digest
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            temporary = cache_path + "." + uuid.uuid4().hex + ".tmp"
            with open(temporary, "w", encoding="utf-8") as stream:
                json.dump(dict(list(saved.items())[-16:]), stream)
            os.replace(temporary, cache_path)
        except OSError:
            pass
    _hash_cache[key] = digest
    return digest


def iso_sha256(path):
    return _file_hash(path, hashlib.sha256)


def t4_elf_sha1(path):
    return _file_hash(path, hashlib.sha1)


class DirectCheckError(RuntimeError):
    def __init__(self, message, checks=None, run_dir=None):
        super().__init__(message)
        self.checks = checks or {}
        self.run_dir = run_dir


class T4Direct:
    online_direct_ip = True
    direct_port = 7400

    def _direct_init(self):
        if hasattr(self, "_direct_results"):
            return
        self._direct_results = queue.Queue()
        self._direct_generation = 0
        self._direct_cancel = threading.Event()
        self._direct_role, self._direct_address = "host", ""
        self._direct_phase, self._direct_message = "offline", "@t4.direct_hint"
        self._direct_checks, self._direct_verified = {}, None
        self._direct_last_run = None
        self._direct_log_path = ""
        self._direct_log_baseline = {}
        self._direct_busy = False
        self._direct_stopping = False
        self._direct_worker = None
        self._online_lock = threading.RLock()
        self._online_phase = "offline"

    def _direct_status(self, phase, message):
        self._direct_phase = self._online_phase = phase
        self._direct_message = message

    def _direct_state(self):
        self._direct_init()
        identity = self._direct_local_identity()
        checks = [dict(id=key, label=DIRECT_LABELS[key], ok=self._direct_checks.get(key),
                       value=("@t4.direct_match" if key != "udp" else "@t4.direct_passed")
                       if self._direct_checks.get(key) is True else
                       DIRECT_FAILURES[key] if self._direct_checks.get(key) is False else "@t4.direct_pending")
                  for key in DIRECT_CHECKS]
        return dict(phase=self._direct_phase, message=self._direct_message, checks=checks,
                    role=self._direct_role, busy=self._direct_busy,
                    build_id=identity.get("build_id", ""), compiler=identity.get("compiler", ""),
                    log_path=self._direct_log_path,
                    name="", account=False, queue="", match={}, saved_available=False,
                    capabilities=dict(direct_ip=True, ranked=False, lobby=False, match_flow=False,
                                      lobby_available=True))

    def _direct_local_identity(self):
        """Display the local stamp only; the peer preflight still verifies every input."""
        try:
            exe, _why = self.core.find_runtime(self.s)
            if not exe:
                return {}
            path = os.path.join(os.path.dirname(exe), "t4net_build.json")
            with open(path, "rb") as stream:
                data = stream.read(32769)
            if len(data) > 32768:
                return {}
            stamp = json.loads(data.decode("utf-8-sig"))
            if not isinstance(stamp, dict):
                return {}
            build = stamp.get("id")
            toolchain = stamp.get("toolchain")
            if not isinstance(toolchain, list) or not all(isinstance(line, str) for line in toolchain):
                return {}
            ids = [line[7:] for line in toolchain if line.startswith("CXX_ID=")]
            versions = [line[12:] for line in toolchain if line.startswith("CXX_VERSION=")]
            if len(ids) != 1 or len(versions) != 1:
                return {}
            compiler = ids[0] + " " + versions[0]
            if (not isinstance(build, str) or not re.fullmatch(IDENTITY_RULES["build_id"], build)
                    or not re.fullmatch(IDENTITY_RULES["compiler"], compiler)):
                return {}
            return dict(build_id=build, compiler=compiler)
        except (OSError, TypeError, ValueError):
            return {}

    @staticmethod
    def _direct_stamp(path):
        stat = os.stat(path)
        return os.path.realpath(path), stat.st_size, stat.st_mtime_ns

    @staticmethod
    def _direct_user_folder():
        dest = os.path.realpath(os.path.join(user_dir(), "t4-online"))
        checkout = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        try:
            inside = os.path.commonpath((checkout, dest)) == checkout
        except ValueError:
            inside = False
        if inside:
            raise RuntimeError("@t4.direct_logs_failed")
        os.makedirs(dest, exist_ok=True)
        return dest

    def _direct_process(self, command, cancel, env=None):
        if cancel.is_set():
            raise RuntimeError("@online.cancelled")
        if command[:1] == ["powershell.exe"] and not wine.powershell_works():
            raise DirectCheckError("@t4.no_powershell")     # Wine/Proton only (always works on Windows)
        proc = subprocess.Popen(command, cwd=self.root, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        try:
            while proc.poll() is None:
                if cancel.wait(0.1):
                    proc.terminate()
                    proc.wait(timeout=5)
                    raise RuntimeError("@online.cancelled")
            return proc.returncode
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

    def _direct_preflight(self, role, address, cancel):
        if not self.ready():
            raise DirectCheckError("@online.build_required")
        problem = self._online_game_check()
        if problem:
            raise DirectCheckError(problem)
        exe, _why = self.core.find_runtime(self.s)
        tool = os.path.join(self.root, "tools", "net_preflight.ps1")
        stamp = os.path.join(os.path.dirname(exe), "t4net_build.json")
        iso = self.core.effective_iso(self.s)
        elf = os.path.join(self.root, "game", "disc", "SLUS_203.28")
        paths = (exe, stamp, iso, elf, tool)
        try:
            stamps = tuple(self._direct_stamp(path) for path in paths)
        except (OSError, TypeError):
            raise DirectCheckError("@t4.direct_identity_failed") from None
        run_dir = os.path.join(self._direct_user_folder(), "check-" + uuid.uuid4().hex)
        os.makedirs(run_dir)
        wrapper = os.path.join(run_dir, "check.ps1")
        output = os.path.join(run_dir, "preflight.json")
        with open(wrapper, "w", encoding="utf-8") as stream:
            stream.write(PREFLIGHT_SCRIPT)
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-File", wrapper, "-Tool", tool, "-BuildStamp", stamp, "-Iso", iso,
                   "-Elf", elf, "-Output", output, "-Peer", address or "0.0.0.0",
                   "-Port", str(self.direct_port)]
        if role == "host":
            command.append("-AsHost")
        env = dict(os.environ, TEKKEN4_NET_STRICT_HELLO="0", TEKKEN4_NET_DELAY_MATCH="0",
                   TEKKEN4_NET_PORT="0", TEKKEN4_NET_BIND="")
        try:
            code = self._direct_process(command, cancel, env)
            try:
                with open(output, encoding="utf-8-sig") as stream:
                    report = json.load(stream)
            except (OSError, ValueError):
                raise DirectCheckError("@t4.direct_identity_failed") from None
            mismatch = report.get("mismatch_fields") or []
            checks = dict(build=not any(key in mismatch for key in
                                       ("build_id", "elf_sha1", "net", "strict_hello", "delay_match")),
                          compiler="compiler" not in mismatch, iso="iso_sha256" not in mismatch,
                          udp=True if report.get("status") == "ok" else None) if report.get("peer") else {}
            if code or report.get("status") != "ok":
                reason = report.get("reason")
                if reason == "udp_timeout":
                    checks["udp"] = False
                key = ("compiler" if "compiler" in mismatch else
                       "iso" if "iso_sha256" in mismatch else "build")
                message = (DIRECT_FAILURES[key] if reason == "build_mismatch" else
                           "@t4.direct_unreachable" if reason == "udp_timeout" else "@t4.direct_failed")
                raise DirectCheckError(message, checks, run_dir)
            local, peer = report.get("local"), report.get("peer")
            if (mismatch or not isinstance(local, dict) or not isinstance(peer, dict)
                    or any(not isinstance(local.get(key), str) or not re.fullmatch(pattern, local[key])
                           or local[key] != peer.get(key) for key, pattern in IDENTITY_RULES.items())):
                raise DirectCheckError("@t4.direct_identity_failed")
            if stamps != tuple(self._direct_stamp(path) for path in paths):
                raise DirectCheckError("@t4.direct_identity_failed")
            identity = report.get("local") or {}
            if not re.fullmatch(r"[0-9a-f]{16}", str(identity.get("build_id", ""))):
                raise DirectCheckError("@t4.direct_identity_failed")
            return dict(paths=paths, stamps=stamps, build=identity["build_id"],
                        checks=dict.fromkeys(DIRECT_CHECKS, True), checked_at=time.monotonic(), run_dir=run_dir)
        except DirectCheckError as error:
            error.run_dir = run_dir
            raise
        finally:
            os.remove(wrapper)

    def _direct_submit(self, action, work):
        generation = self._direct_generation
        self._direct_busy = True

        def run():
            try:
                value, error = work(), None
            except Exception as exc:  # noqa: BLE001 -- raw paths and tool errors stay out of the view
                value, error = None, exc
            self._direct_results.put((generation, action, value, error))
        try:
            self._direct_worker = threading.Thread(target=run, name="openrecomp-t4-direct", daemon=True)
            self._direct_worker.start()
        except Exception:
            self._direct_busy = False
            self._direct_status("error", "@t4.direct_failed")

    def _direct_action(self, action):
        self._direct_init()
        if action in ("disconnect", "cancel_match", "stop_match"):
            return self._direct_close()
        if self._direct_busy or self._direct_phase == "playing":
            return
        if action in ("host", "join"):
            self._direct_role = action
            self._direct_verified, self._direct_checks = None, {}
            self._direct_status("offline", "@t4.direct_hint")
        elif action == "check":
            if self._direct_role == "join":
                try:
                    address = ipaddress.IPv4Address(self._direct_address.strip())
                    if address.is_unspecified or address.is_multicast or int(address) == 0xffffffff:
                        raise ValueError("peer")
                except ValueError:
                    self._direct_verified, self._direct_checks = None, {}
                    self._direct_status("error", "@t4.direct_invalid_address")
                    return
            self._direct_verified, self._direct_checks = None, {}
            self._direct_cancel = threading.Event()
            cancel, role, address = self._direct_cancel, self._direct_role, self._direct_address.strip()
            self._direct_status("checking", "@t4.direct_checking")
            self._direct_submit(action, lambda: self._direct_preflight(role, address, cancel))
        elif action == "start_match":
            verified = self._direct_verified
            if (self._direct_phase != "checked" or not verified
                    or time.monotonic() - verified["checked_at"] > 60):
                self._direct_verified = None
                self._direct_status("error", "@t4.direct_check_required")
                return
            self._direct_status("starting", "@online.starting")
            generation, role, address = self._direct_generation, self._direct_role, self._direct_address.strip()

            def start():
                if verified["stamps"] != tuple(self._direct_stamp(path) for path in verified["paths"]):
                    raise DirectCheckError("@t4.direct_identity_failed")
                problem = self._online_game_check()
                if problem:
                    raise DirectCheckError(problem)
                env = dict(TEKKEN4_NET=("host:" + str(self.direct_port) if role == "host" else
                                       "join:" + address + ":" + str(self.direct_port)),
                           TEKKEN4_NET_BUILD=verified["build"], TEKKEN4_NET_DELAY="auto",
                           TEKKEN4_NET_STRICT_HELLO="0", TEKKEN4_NET_DELAY_MATCH="0", TEKKEN4_NET_PORT="0",
                           TEKKEN4_NET_BIND="", TEKKEN4_NET_PEER="", TEKKEN4_NET_KEY="", TEKKEN4_NET_SEED="",
                           TEKKEN4_NET_TIMEOUT="90")
                if getattr(self.core, "source_only", False):
                    env.update(source_net_profile(self.config))
                with self._online_lock:
                    if generation != self._direct_generation:
                        raise RuntimeError("@online.cancelled")
                    self._direct_log_baseline = self._direct_log_stamps()
                    previous = getattr(self, "run", None)
                    try:
                        self.start(extra_env=env)
                    finally:
                        # Keep a post-start failure reachable by Disconnect/Stop.
                        if getattr(self, "run", None) is not previous:
                            self._online_owned_run = self.run
            self._direct_submit(action, start)
        elif action == "collect_logs":
            self._direct_log_path = ""
            cancel = self._direct_cancel = threading.Event()
            self._direct_submit(action, lambda: self._direct_collect_logs(cancel))

    def _direct_collect_logs(self, cancel):
        tool = os.path.join(self.root, "tools", "collect_test_logs.ps1")
        dest = os.path.join(self._direct_user_folder(), "report-" + uuid.uuid4().hex)
        owned = self._direct_last_run
        if not owned:
            raise DirectCheckError("@t4.direct_logs_failed")
        os.mkdir(dest)
        source = owned["run_dir"]
        command = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-File", tool, "-RunDir", source, "-OutputDirectory", dest]
        if self._direct_process(command, cancel):
            raise DirectCheckError("@t4.direct_logs_failed")
        outputs = os.listdir(dest)
        if len(outputs) != 1:
            raise DirectCheckError("@t4.direct_logs_failed")
        archive = os.path.join(dest, outputs[0])
        info = os.lstat(archive)
        if (not outputs[0].startswith("T4-test-logs-") or not outputs[0].endswith(".zip")
                or os.path.islink(archive) or getattr(info, "st_file_attributes", 0) & 0x400
                or not os.path.isfile(archive) or not zipfile.is_zipfile(archive)):
            raise DirectCheckError("@t4.direct_logs_failed")
        return archive

    def _direct_log_stamps(self):
        out = {}
        folder = os.path.realpath(getattr(self.core, "SAVE_DIR", ""))
        checkout = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        try:
            if os.path.commonpath((checkout, folder)) == checkout:
                return out
        except ValueError:
            pass
        # Fixed diagnostic names only. No cards, screenshots, replay data or arbitrary paths.
        for name in ("net.log", "rb_frames.log", "stdout.txt", "stderr.txt"):
            path = os.path.join(folder, name)
            try:
                info = os.lstat(path)
                if (os.path.realpath(path) != path or os.path.islink(path)
                        or getattr(info, "st_file_attributes", 0) & 0x400):
                    continue
                with open(path, "rb") as stream:
                    prefix = stream.read(4096)
                out[name] = (path, info.st_size, info.st_mtime_ns, prefix)
            except OSError:
                continue
        return out

    def _direct_snapshot_logs(self):
        owned = self._direct_last_run
        if not owned:
            return
        for name, (path, size, stamp, prefix) in self._direct_log_stamps().items():
            previous = self._direct_log_baseline.get(name)
            if previous and (size, stamp) == previous[1:3]:
                continue
            # A runtime may append or replace its log at launch. Include only this run's suffix.
            offset = previous[1] if previous and size >= previous[1] and prefix.startswith(previous[3]) else 0
            if size - offset > 64 * 1024 * 1024:
                continue
            try:
                with open(path, "rb") as stream:
                    stream.seek(offset)
                    data = stream.read(64 * 1024 * 1024 + 1)
                if self._direct_stamp(path)[1:] != (size, stamp) or len(data) > 64 * 1024 * 1024:
                    continue
                with open(os.path.join(owned["run_dir"], name), "wb") as stream:
                    stream.write(data)
            except OSError:
                continue

    def _direct_poll(self):
        self._direct_init()
        self._online_reap_owned()
        changed = False
        worker = self._direct_worker
        if (self._direct_stopping and getattr(self, "_online_owned_run", None) is None
                and (worker is None or not worker.is_alive())):
            self._direct_stopping = self._direct_busy = False
            self._direct_status("offline", "@t4.direct_hint")
            changed = True
        while True:
            try:
                generation, action, value, error = self._direct_results.get_nowait()
            except queue.Empty:
                break
            if generation != self._direct_generation:
                continue
            self._direct_busy = False
            changed = True
            if error:
                self._direct_verified = None
                self._direct_checks = error.checks if isinstance(error, DirectCheckError) else {}
                if isinstance(error, DirectCheckError) and error.run_dir:
                    self._direct_last_run = dict(run_dir=error.run_dir)
                self._direct_status("error", str(error) if isinstance(error, DirectCheckError)
                                    else "@t4.direct_failed")
            elif action == "check":
                self._direct_verified, self._direct_checks = value, value["checks"]
                self._direct_last_run = value
                self._direct_status("checked", "@t4.direct_checked")
            elif action == "start_match":
                self._direct_status("playing", "@online.playing")
            elif action == "collect_logs":
                self._direct_log_path = value or ""
                self._direct_message = "@t4.direct_logs_saved"
        if self._direct_phase == "playing":
            run = getattr(self, "_online_owned_run", None)
            if run is None or run.proc.poll() is not None:
                self._direct_verified = None
                if run is not None:
                    self._direct_stopping = self._direct_busy = True
                self._direct_status("stopping" if run is not None else "offline", "@t4.direct_finished")
                changed = True
        return changed

    def _direct_close(self):
        self._direct_init()
        with self._online_lock:
            self._direct_generation += 1
            self._direct_cancel.set()
            self._direct_verified = None
            self._direct_stopping = self._direct_busy = True
            self._online_stop_owned()
            worker = self._direct_worker
            if (getattr(self, "_online_owned_run", None) is None
                    and (worker is None or not worker.is_alive())):
                self._direct_stopping = self._direct_busy = False
            self._direct_status("stopping" if self._direct_stopping else "offline",
                                "@t4.returning" if self._direct_stopping else "@t4.direct_hint")


def _is_set(info):
    """A ranked set (best of 3, rated once) or a casual first-to-N set (t4-parity): every game a new T4 game."""
    return isinstance(info, dict) and bool(info.get("rated") or info.get("casual")) and bool(info.get("id"))


def ticket_env(ticket):
    """Only the ticket fields documented by the T4 lobby handoff; no T5 game driver. Ranked tickets too (T4 ranked:
    the game writes its own proven result, docs/T4_ONLINE.md "Ranked")."""
    if ticket.role not in ("host", "join"):
        raise RuntimeError("@online.refused")
    peer = f"{ticket.peer[0]}:{int(ticket.peer[1])}"
    port = str(int(ticket.local_port))
    delay = ticket.input_delay if ticket.input_delay is not None else "auto"
    env = dict(TEKKEN4_NET_BUILD=str(ticket.build), TEKKEN4_NET_KEY=str(ticket.key),
               TEKKEN4_NET_SEED=str(ticket.seed), TEKKEN4_NET_DELAY=str(delay),
               TEKKEN4_NET_TIMEOUT=str(ticket.timeout))
    if ticket.role == "host":
        env.update(TEKKEN4_NET="host:" + port, TEKKEN4_NET_PEER=peer)
    else:
        env.update(TEKKEN4_NET="join:" + peer, TEKKEN4_NET_PORT=port)
    return env


class T4Online(T4Direct, Online):
    online_package = "t4lobby"
    online_game = "t4"
    online_port = 7791
    online_lobby = True
    online_match_flow = True
    online_legacy_config = False
    online_registration = True
    online_feature_modules = T4_FEATURE_MODULES

    @property
    def online_ranked(self):
        """Ranked when the T4 server opens it (welcome ranked_queue: a T4 server with proven game results); the
        beta server before that answered false."""
        client = self.__dict__.get("_online_client")
        welcome = getattr(client, "welcome", None) if client is not None else None
        return bool(isinstance(welcome, dict) and welcome.get("ranked_queue"))

    @property
    def online_direct_ip(self):
        return self._t4_online_mode() == "direct"

    def _t4_online_mode(self):
        """The player's last choice; without one the lobby once a T4 server is known, else direct IP."""
        mode = self.config.get("t4_online_mode")
        if mode in ("direct", "lobby"):
            return mode
        return "lobby" if self._online_default_server() else "direct"

    def _t4_set_mode(self, mode):
        if mode == self._t4_online_mode():
            return
        if self.online_direct_ip:
            self._direct_init()
            if (self._direct_busy or self._direct_phase in ("checking", "starting", "playing", "stopping")
                    or getattr(self, "_online_owned_run", None) is not None):
                self._direct_message = "@t4.mode_busy"
                return
        else:
            self._online_init()
            if (self._online_client is not None or self._online_busy
                    or getattr(self, "_online_owned_run", None) is not None):
                self._online_message = "@t4.mode_busy"
                return
        self.config["t4_online_mode"] = mode
        # Both screens share _online_phase: each starts from its own idle state.
        if mode == "lobby":
            self._online_init()
            self._online_phase, self._online_message = "offline", "@online.offline"
        else:
            self._direct_init()
            self._direct_status("offline", "@t4.direct_hint")
        try:
            save_config(self.config)
        except (OSError, ValueError, TypeError):
            pass  # the choice still holds for this session

    def online_cfg_path(self):
        # Endpoints, TLS pins and session tokens remain scoped to the T4 service.
        return os.path.join(user_dir(), "online-t4.json")

    def _online_lobby_dir(self):
        return VENDOR

    def _online_servers_dir(self):
        # Never T5DR's servers.json in the launcher's home folder.
        return os.path.join(user_dir(), "t4-online")

    def _t4_listed_entries(self):
        """Entries of the local T4 server lists (the launcher's shipped one, then the player's), by name."""
        entries = {}
        for path in (SHIPPED_SERVERS, os.path.join(self._online_servers_dir(), "servers.json")):
            try:
                with open(path, encoding="utf-8") as stream:
                    doc = json.load(stream)
            except (OSError, ValueError):
                continue
            servers = doc.get("servers") if isinstance(doc, dict) and doc.get("format") == SERVERS_FORMAT else None
            for entry in servers if isinstance(servers, list) else []:
                if isinstance(entry, dict) and str(entry.get("host") or "").strip():
                    name = str(entry.get("name") or entry.get("host")).strip()[:64]
                    entries.pop(name, None)
                    entries[name] = entry
        return entries

    def _t4_explicit_server(self):
        """OPENRECOMP_T4_SERVER, else the launcher config's t4_lobby_server, else "" (docs/T4_ONLINE.md 1 and 2)."""
        configured = os.environ.get(SERVER_ENV, "").strip() or str(self.config.get("t4_lobby_server") or "").strip()
        return configured[:256]

    def _online_explicit_server(self):
        return self._t4_explicit_server()          # never OPENRECOMP_T5_SERVER / t5_lobby_server

    def _online_default_server(self):
        """OPENRECOMP_T4_SERVER, the launcher config's t4_lobby_server, or a T4 servers.json entry; never built in."""
        configured = self._t4_explicit_server()
        if configured:
            return configured
        if not hasattr(self, "_t4_listed_server"):
            listed = self._t4_listed_entries()
            # A listed name resolves through the same servers.json files when the client connects. The player's
            # own list comes last, so its default wins over the shipped "T4 Online".
            self._t4_listed_server = next((name for name, entry in reversed(listed.items())
                                           if entry.get("default") is True), next(iter(listed), ""))
        return self._t4_listed_server

    def _t4_shared_host(self):
        """The host whose T5DR remembered login may log in here, or "".

        Only a locally listed T4 server marked "shared_login" (the operator's approval, never the server's own
        claim), selected by its name, with TLS (a pinned certificate or a CA): a typed address never qualifies.
        "shared_login": true shares with T5DR logins of the same host; a string names that host."""
        entry = self._t4_listed_entries().get(self._online_fields["online_server"].strip())
        if not entry or not entry.get("shared_login"):
            return ""
        tls = entry_tls(entry)                       # what the connection will really use (omitted = off)
        if tls not in ("ca", "pin") or (tls == "pin" and not str(entry.get("fingerprint") or "").strip()):
            return ""
        host = entry["shared_login"] if isinstance(entry["shared_login"], str) else entry.get("host")
        return str(host or "").strip().lower()

    def _t4_shared_session(self, fresh=False):
        """The newest T5DR remembered login for the approved host, from the T5DR install this launcher knows."""
        key = (self._online_fields["online_server"].strip(), len(getattr(self, "_t4_shared_rejected", ())))
        cached = getattr(self, "_t4_shared_cache", None)
        if not fresh and cached and cached[0] == key and time.monotonic() - cached[1] < 2.0:
            return cached[2]
        found = self._t4_shared_lookup()
        self._t4_shared_cache = (key, time.monotonic(), found)
        return found

    def _t4_shared_lookup(self):
        host = self._t4_shared_host()
        if not host:
            return None
        rejected = getattr(self, "_t4_shared_rejected", set())
        found = []
        for peer in getattr(self, "account_peers", ()) or ():
            try:
                sessions = peer.online_account_sessions()
            except Exception:  # noqa: BLE001 -- another game's unreadable settings never block this login
                continue
            for session in sessions if isinstance(sessions, list) else []:
                if (isinstance(session, dict) and session.get("host") == host and session.get("token")
                        and session["token"] not in rejected):
                    found.append(session)
        if not found:
            return None
        best = max(found, key=lambda session: session.get("saved") or 0)
        return dict(name=str(best.get("name") or "")[:64], token=best["token"], shared=True)

    def _online_saved(self):
        self._online_init()
        own = super()._online_saved()
        if own is not None:
            return own
        return self._t4_shared_session()

    def _online_init(self):
        if hasattr(self, "_online_fields"):
            return
        # The direct-IP screen mirrors its phase into _online_phase and owns _online_lock;
        # neither means the lobby state exists yet.
        lock = getattr(self, "_online_lock", None)
        phase = self.__dict__.pop("_online_phase", None)
        try:
            super()._online_init()
        except BaseException:
            if phase is not None:
                self._online_phase = phase
            raise
        if lock is not None:
            self._online_lock = lock
        explicit = self._t4_explicit_server()
        if explicit:
            # The documented order: an override beats the address saved by the last login (online-t4.json).
            self._online_fields["online_server"] = explicit
        elif not self._online_fields["online_server"].strip():
            self._online_fields["online_server"] = self._online_default_server()

    def _online_build(self, api):
        if not self.ready():
            raise RuntimeError("@online.build_required")
        exe, _why = self.core.find_runtime(self.s)
        if not exe:
            raise RuntimeError("@online.build_required")
        try:
            info = api["build"].from_out_dir(os.path.dirname(exe), self._t4_release())
        except (OSError, ValueError):
            raise RuntimeError("@online.build_required") from None
        return self._t4_identity_build(api, info, os.path.dirname(exe))

    def _t4_identity_build(self, api, info, out):
        """The lobby identity holds what Direct IP's check compares (net_preflight.ps1 New-T4NetIdentity): the
        build id's fields (ELF, code, netplay version) AND the compiler and the ISO. The ELF on disk must be the
        stamp's (a stale extraction is another game). Compiler and ISO go into the code field the server hashes
        (lobby_code): the server recomputes the id from elf/code/net as before, so it needs no change, and
        only builds with the same compiler and ISO are paired; the game gets that id as TEKKEN4_NET_BUILD and
        compares it in its HELLO, the same on both PCs."""
        elf = os.path.join(self.root, "game", "disc", "SLUS_203.28")
        try:
            if t4_elf_sha1(elf) != str(info.elf_sha1).lower():
                raise RuntimeError("@t4.direct_identity_failed")
            compiler = stamp_compiler(os.path.join(out, "t4net_build.json"))
        except (OSError, ValueError):
            raise RuntimeError("@t4.direct_identity_failed") from None
        iso = self.core.effective_iso(self.s) if callable(getattr(self.core, "effective_iso", None)) else ""
        if not iso:
            raise RuntimeError("@iso.choose_first")
        try:
            iso_sha = iso_sha256(iso)
        except OSError:
            raise RuntimeError("@iso.choose_first") from None
        return api["build"](info.elf_sha1, lobby_code(info.code_id, compiler, iso_sha), info.release, info.net)

    def _t4_release(self):
        """The T4 release's version (release.json), for the server's update notice; "dev" for a source build."""
        try:
            with open(os.path.join(self.root, "release.json"), encoding="utf-8") as stream:
                version = json.load(stream).get("version")
        except (OSError, ValueError, AttributeError, TypeError):
            return "dev"
        return version[:40] if isinstance(version, str) and re.fullmatch(r"[0-9A-Za-z.+-]{1,40}", version) else "dev"

    def _online_player_rank(self, rating):
        return ""                       # the T4 server's tier comes with the player; never infer it from rating

    def rank_plate(self, tier):
        """The known T5DR install's cached plate, or our drawn badge for the same tier."""
        if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier < len(t4_ranks.NAMES):
            return ""
        for peer in getattr(self, "account_peers", ()):
            if peer.m.get("id") == "t5dr" and peer.found():
                path = peer.rank_plate(tier)
                if path:
                    return path
        path = os.path.join(RANK_BADGES, "t4_rank_%02d.svg" % tier)
        return path if os.path.isfile(path) else ""

    def rank_progress(self, rating):
        """The ranked card's bar from the vendored client's rank table (t4lobby/ranks.py, the server's)."""
        if isinstance(rating, bool) or not isinstance(rating, (int, float)):
            return None
        try:
            ranks = importlib.import_module(self.online_package + ".ranks")
            tier = ranks.tier_for(rating)
            low, high = ranks.threshold(tier), ranks.threshold(tier + 1)
            following = str(ranks.name(tier + 1))
        except Exception:  # noqa: BLE001 -- an older client without the table, or the top rank
            return None
        if high != high or high in (float("inf"), float("-inf")):
            return None
        low = low if low not in (float("inf"), float("-inf")) else high - 50
        return float(low), float(high), following

    def _online_player(self, player):
        out = super()._online_player(player)
        if out:
            out["rank"] = "" if out.get("guest") else t4_ranks.display_name(out)
        # The server sends the developer badge only for a marked account; a client cannot set it.
        if out and player.get("badge") == "dev":
            out["badge"] = "dev"
        return out

    def online_state(self):
        if self.online_direct_ip:
            state = self._direct_state()
            other = self._other_state()
            if other:
                state["other_launcher"] = other
            return state
        state = super().online_state()
        server = bool(self._online_fields["online_server"].strip())
        if state["phase"] == "offline" and state["message"] == "@online.offline":
            state["message"] = "@t4.online_setup_hint" if server else "@t4.lobby_no_server"
        state["capabilities"].update(t4_lobby=True, direct_available=True, server_set=server)
        state["capabilities"]["rematch"] = bool(getattr(self, "_online_rematch", False)
                                                   and callable(getattr(self._online_client, "rematch", None)))
        saved = self._online_saved() if state.get("saved_available") else None
        # One account for T5DR and T4: a T5DR remembered login offered here is named as such.
        state["saved_shared"] = bool(saved and saved.get("shared"))
        me = state.get("me") or {}
        if me:
            me["rank"] = "" if me.get("guest") else t4_ranks.display_name(me)
        state["rank"] = str(me.get("rank") or "")[:40] if state["name"] and not me.get("guest") else ""
        info = getattr(self, "_online_set", {})
        state["set"] = dict(info, wins=list(info.get("wins", []))) if info else {}
        state["capabilities"]["leave_set"] = bool(
            info.get("state") == "active" and info.get("rated") and self._online_phase in ("result", "result_sent")
            and callable(getattr(self._online_client, "leave_set", None)))
        return state

    def _online_client_options(self):
        options = super()._online_client_options()
        # Ranked sets (best of 3, rated once): every game is a new connection and a new T4 game, started by itself
        # after the server's countdown (_online_match_found, origin "set").
        # Friends, rooms (private, community, tables), tournaments, private chat, mentions and casual sets as in
        # T5DR. Off until the T4 game has them: spectate, the life rules, the in-game rematch, the auto skips; the
        # challenge delay stays 0..2 (T4's netplay takes 0..4, T5DR 1.2.0's picker offers 0..8).
        options.update(relays=False, friends=True, private_rooms=True, tournaments=True, spectate=False, sets=True,
                       match_rules=False, private_chat=True, badges=True, mentions=True, casual_sets=True,
                       room_tables=True, input_delay8=False, ingame_rematch=False, auto_skip_after_round=False,
                       auto_skip_intro=False)
        return options

    def _online_game_env(self, ticket):
        if ticket.role not in ("host", "join"):
            raise RuntimeError("@online.refused")
        api = self._online_modules()
        if "game_env" not in api:
            module = importlib.import_module(self.online_package + ".t4game")
            package = os.path.normcase(os.path.realpath(os.path.join(self._online_lobby_dir(), self.online_package)))
            origin = getattr(module, "__file__", None)
            try:
                local = isinstance(origin, str) and os.path.commonpath(
                    (package, os.path.normcase(os.path.realpath(origin)))) == package
            except ValueError:
                local = False
            if not local or not callable(getattr(module, "game_env", None)):
                raise RuntimeError("@online.client_missing")
            api["game_env"] = module.game_env
            # The game's own result file (T4 game >= t4-result): absent in an older client = manual result only.
            reader, report = getattr(module, "read_game_result", None), getattr(module, "game_result_report", None)
            api["game_result"] = (reader, report) if callable(reader) and callable(report) else None
            hud = getattr(module, "hud_env", None)
            api["hud_env"] = hud if callable(hud) else None
        if ticket.ranked and not api.get("game_result"):
            raise RuntimeError("@online.refused")      # ranked needs the game's own result (an older client: none)
        env = dict(TEKKEN4_NET_STRICT_HELLO="0", TEKKEN4_NET_DELAY_MATCH="0")
        if getattr(self.core, "source_only", False):
            env.update(source_net_profile(self.config))
        # The lobby's endpoint, key, seed and build always win over the local profile.
        env.update(api["game_env"](ticket))
        # The game's name plates: both players' names and rank badges on their sides (the same on both PCs).
        if api.get("hud_env"):
            you = getattr(self, "_t4_you", None) or dict(self._online_me or {}, name=self._online_name)
            plates = self.config.get("t4_name_plates", True) is not False
            env.update(api["hud_env"](ticket.slot, you, ticket.opponent, plates))
        # Where the game writes its result (TEKKEN4_NET_RESULT, next to its net.log): one file per match, a stale
        # one removed first; a file naming another match is never read (read_game_result checks the match id).
        self._t4_result_path, self._t4_result_sent, self._t4_result_stop_at = None, False, None
        if api.get("game_result"):
            safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(ticket.match_id))[:64] or "match"
            path = os.path.join(self.core.SAVE_DIR, "t4_result-" + safe + ".json")
            for stale in (path, path + ".tmp"):
                try:
                    os.remove(stale)
                except OSError:
                    pass
            env["TEKKEN4_NET_RESULT"] = path
            self._t4_result_path = path
        return env

    def _t4_game_result_poll(self):
        """The T4 game's own result (TEKKEN4_NET_RESULT): decided by the game on frames both games had confirmed.
        Reported once with source "game" (the manual buttons stay for games that end without one); the game is
        closed a few seconds later (the opponent's game may still need ours to confirm its last frames)."""
        stop_at = getattr(self, "_t4_result_stop_at", None)
        if stop_at is not None and time.monotonic() >= stop_at:
            self._t4_result_stop_at = None
            if getattr(self, "_online_owned_run", None) is not None:
                self._online_stop_owned()
            return True
        path = getattr(self, "_t4_result_path", None)
        if (not path or getattr(self, "_t4_result_sent", False) or self._online_phase != "playing"
                or self._online_busy):
            return False
        client, ticket = self._online_client, self._online_ticket
        api = self._online_modules()
        if client is None or ticket is None or not api.get("game_result"):
            return False
        read, report = api["game_result"]
        res = read(path, ticket.match_id)
        if res is None:
            return False
        self._t4_result_sent = True
        kw = dict(report(res), match_id=ticket.match_id)
        kw["desync"] = max(kw.get("desync", 0), int(getattr(self, "_online_evidence", {}).get("desync", 0)))
        winner, score = res["winner"], res["score"]
        self._online_result_message = "@online.result_sent"
        self._online_submit("result_game", lambda: client.report_result(winner=winner, score=score, **kw))
        self._t4_result_stop_at = time.monotonic() + 5.0
        return True

    def _online_match_message(self):
        reason = getattr(self, "_online_evidence", {}).get("reason")
        return {"peer_quit": "@online.peer_quit", "peer_timeout": "@online.peer_timeout",
                "no_peer": "@online.connection_failed", "build_mismatch": "@online.game_build_mismatch"}.get(reason)

    def _online_game_check(self):
        self._online_reap_owned()
        if (getattr(self, "_online_owned_run", None) is not None
                or self.running() or self.core.run_lock_holder()):
            return "@online.game_running"
        exe, _why = self.core.find_runtime(self.s)
        if not exe:
            return "@online.build_required"
        running = game_process_running(os.path.basename(exe))
        return "@online.process_unknown" if running is None else ("@online.game_running" if running else "")

    def text_value(self, tid):
        if self.online_direct_ip:
            self._direct_init()
            return self._direct_address if tid == "online_address" else ""
        return self.online_text_value(tid) if tid.startswith("online_") else ""

    def set_text_value(self, tid, value):
        if self.online_direct_ip:
            self._direct_init()
            if tid == "online_address" and not self._direct_busy and self._direct_phase != "playing":
                self._direct_address = str(value).strip()[:256]
                self._direct_verified, self._direct_checks = None, {}
                self._direct_status("offline", "@t4.direct_hint")
            return
        if tid.startswith("online_"):
            self.set_online_text_value(tid, value)

    def _online_match_found(self, event):
        self._online_reap_owned()
        if (event.get("origin") == "rematch" and event.get("ready_check") is False
                and self._online_phase == "result_sent" and getattr(self, "_online_next_authorized", False)
                and event.get("rematch_of") == getattr(self, "_online_match_id", None)
                and event.get("match") and event["match"] != getattr(self, "_online_match_id", None)):
            # T4 rematches use a fresh connection and game. Only this player's vote authorizes the next ticket;
            # the launch worker waits for the previous owned process to stop before starting it.
            self._online_ticket = None
            self._online_match_id = event["match"]
            self._online_authorized = True
            self._online_next_authorized = self._online_rematch = False
            self._online_ready_check = False
            self._online_early_start = self._online_pending_start = None
            self._online_result_message = "@online.result_sent"
            self._online_match = dict(self._online_match_view(event), my_ready=True, peer_ready=False)
            self._t4_set_info(event)
            self._online_phase, self._online_queue = "starting", ""
            self._online_message = "@online.starting"
            return True
        info = event.get("set") if isinstance(event.get("set"), dict) else None
        if (event.get("origin") == "set" and _is_set(info)
                and self._online_phase in ("result", "result_sent")
                and info.get("id") == getattr(self, "_online_set", {}).get("id")):
            # The next game of this set (ranked, or a casual first-to-N set): no vote, it starts by itself (the
            # previous game is stopped first).
            self._online_ticket = None
            self._online_match_id = event.get("match")
            self._online_authorized = True
            self._online_next_authorized = self._online_rematch = False
            self._online_ready_check = False
            self._online_early_start = None
            self._online_pending_start = None
            self._online_result_message = "@online.result_sent"
            self._online_match = dict(self._online_match_view(event), my_ready=True, peer_ready=False)
            self._t4_set_info(event)
            self._online_phase, self._online_queue = "starting", ""
            self._online_message = "@online.starting"
            return True
        if (self._online_phase not in ("logged_in", "searching")
                or getattr(self, "_online_owned_run", None) is not None):
            # An unsolicited second offer must never discard an owned game or its result: say no to that offer
            # only (closing the connection here logged the player out and stopped the game it protected).
            mid, client = event.get("match"), self._online_client
            if mid and client is not None and mid != getattr(self, "_online_match_id", None):
                def decline():
                    try:
                        client.ready(False, match_id=mid)
                    except Exception:  # noqa: BLE001 -- the offer may be gone already
                        pass
                threading.Thread(target=decline, name="openrecomp-lobby", daemon=True).start()
            return True
        self._online_ticket = None
        self._online_match_id = event.get("match")
        self._online_authorized = False
        self._online_next_authorized = self._online_rematch = False
        self._online_ready_check = event.get("ready_check", True) is not False
        self._online_early_start = None
        self._online_owned_run = None
        self._online_pending_start = None
        self._online_result_message = "@online.result_sent"
        self._online_match = dict(self._online_match_view(event), my_ready=False, peer_ready=False)
        self._t4_set_info(event)
        self._online_phase, self._online_queue = "matched", ""
        self._online_message = "@online.t4_matched"
        return True

    def _t4_set_info(self, event):
        """Remember this player's own lobby entry and side; a ranked set's score and game number for the rows."""
        self._t4_you = event.get("you") if isinstance(event.get("you"), dict) else None
        info = event.get("set")
        slot = event.get("slot") if event.get("slot") in (0, 1) else 0
        self._t4_slot = slot
        self._online_set = T5Match._online_set_view(self, info, slot) if _is_set(info) else {}

    def _online_match_view(self, event):
        """The found match: the ping, and who plays which side with name and rank (and badge) -- P1 = the host."""
        out = super()._online_match_view(event)
        if event.get("ranked") is True:
            out["ranked"] = True
        slot, opponent = event.get("slot"), event.get("opponent")
        if slot not in (0, 1) or not isinstance(opponent, dict):
            return out                                  # a blind ready check: names after both accepted
        you = event.get("you") if isinstance(event.get("you"), dict) else dict(self._online_me or {})
        you = dict(you, name=you.get("name") or self._online_name)

        def side(p, mine):
            p = self._online_player(p) if p else {}
            guest = bool(p.get("guest"))
            return dict(name=str(p.get("name") or "")[:64], rank="" if guest else str(p.get("rank") or "")[:40],
                        tier=None if guest else p.get("tier"), you=mine)
        out["slot"] = slot
        mine, theirs = side(you, True), side(opponent, False)
        out["sides"] = [mine, theirs] if slot == 0 else [theirs, mine]
        return out

    def _online_event(self, event):
        kind = event.get("t")
        if kind == "opponent_ready":
            current = getattr(self, "_online_match_id", None)
            if (self._online_phase in ("matched", "starting")
                    and (not current or event.get("match") in (None, current))):
                self._online_match["peer_ready"] = True
            return True
        if kind == "notice" and event.get("code") in ("nat_error", "version_mismatch"):
            if self._online_phase in ("matched", "starting", "playing"):
                message = ("@online.game_build_mismatch" if event["code"] == "version_mismatch"
                           else "@online.connection_failed")
                # This match cannot be played: leave it, stay in the lobby (closing here was a logout).
                self._online_to_lobby(message, leave=getattr(self, "_online_match_id", None) or None)
            return True
        if kind in ("match_reveal", "match_cancel", "match_result", "rematch", "nat_status", "nat_upgrade", "nat_fallback"):
            if self._online_phase not in ("matched", "starting", "playing", "result", "result_sent"):
                return True
            current = getattr(self, "_online_match_id", None)
            if current and event.get("match") not in (None, current):
                return True
        if kind == "rematch":
            if self._online_phase != "result_sent":
                return True
            if event.get("state") == "offered" and not getattr(self, "_online_next_authorized", False):
                self._online_rematch = True
                self._online_message = "@online.rematch_offer"
            elif event.get("state") in ("declined", "expired"):
                self._online_rematch = self._online_next_authorized = self._online_authorized = False
                self._online_message = "@online.rematch_declined"
            return True
        if kind in ("nat_status", "nat_upgrade", "nat_fallback"):
            if self._online_phase not in ("matched", "starting", "playing"):
                return True
            if kind == "nat_fallback":
                self._online_message = "@online.connection_fallback" if event.get("ok") else "@online.connection_failed"
            else:
                path = event.get("path") if kind == "nat_upgrade" else event.get("phase")
                self._online_message = "@online.connection_relay" if path == "relay" else "@online.connection_direct"
            return True
        if kind == "match_reveal":
            opponent = event.get("opponent") or {}
            opponent = opponent if isinstance(opponent, dict) else {}
            self._online_match["opponent"] = str(opponent.get("name") or "")
            if event.get("slot") in (0, 1):
                view = self._online_match_view(dict(event, you=getattr(self, "_t4_you", None) or event.get("you")))
                self._online_match.update({k: view[k] for k in ("slot", "sides") if k in view})
                self._t4_slot = event["slot"]
            return True
        if kind == "match_start":
            ticket = event.get("ticket")
            if ticket is None:
                return True
            if getattr(self, "_online_match_id", None) and ticket.match_id != self._online_match_id:
                return True
            if not getattr(self, "_online_authorized", False):
                # Accepted challenges can already be past the server's ready step.
                # Keep their ticket private until the player confirms the game start.
                if self._online_phase == "matched" and not getattr(self, "_online_ready_check", True):
                    self._online_early_start = (self._online_generation, event)
                return True
            if self._online_phase not in ("starting", "playing"):
                return True
            if getattr(self, "_online_ticket", None) is ticket:
                return True
            previous = getattr(self, "_online_ticket", None)
            if previous is not None and not (previous.path in ("direct", "lan")
                                              and ticket.path == "relay"):
                return True
            if self._online_busy:
                self._online_pending_start = event
                return True
            self._online_ticket = ticket
            self._online_match_id = ticket.match_id
            self._online_phase, self._online_message = "starting", "@online.starting"
            client = self._online_client
            generation = self._online_generation
            old_run = getattr(self, "_online_owned_run", None)

            def launch():
                self._online_check_request(generation, client)
                if old_run is not None:
                    self._online_stop_owned(wait=True, expected=old_run)
                else:
                    problem = self._online_game_check()
                    if problem:
                        raise SearchRefused(problem)
                offsets, prefixes = {}, {}
                for name in ("net.log", "rb_frames.log"):
                    path = os.path.join(self.core.SAVE_DIR, name)
                    try:
                        stat = os.stat(path)
                        offsets[path] = (stat.st_size, stat.st_mtime_ns)
                        with open(path, "rb") as stream:
                            prefixes[path] = stream.read(4096)
                    except OSError:
                        offsets[path] = (0, 0)
                env = self._online_game_env(ticket)
                with self._online_lock:
                    if generation != self._online_generation or not self._online_authorized:
                        raise RuntimeError("@online.cancelled")
                    self._online_log_offsets, self._online_log_prefixes = offsets, prefixes
                    self.start(extra_env=env)
                    self._online_owned_run = self.run
                    self._online_started_at = time.monotonic()
                    self._online_connected = self._online_playing = self._online_fallback = False
                    self._online_started_sent = self._online_playing_sent = False
                    self._online_evidence = dict(frames=0, desync=0)
                    self._online_log_pending = {}
                return client
            self._online_submit("start_game", launch)
            return True
        if kind == "match_cancel":
            # A quick-match cancellation may requeue automatically: leave the queue, stay logged in.
            reason = event.get("reason")
            self._online_to_lobby({
                "peer_quit": "@online.peer_quit", "opponent_left": "@online.peer_quit",
                "peer_timeout": "@online.peer_timeout", "ready_timeout": "@online.ready_expired",
                "declined": "@online.peer_declined", "relay_full": "@online.relay_full",
                "nat_failed": "@online.connection_failed", "udp_unreachable": "@online.connection_failed",
                "no_connection": "@online.connection_failed"}.get(reason, "@online.cancelled"))
            return True
        if kind == "match_result":
            if self._online_phase == "starting":
                # The lobby can void a match while the launch worker is still pending: back to the lobby (the match
                # reset stops a game the worker started).
                self._online_to_lobby("@online.result_void")
                return True
            if self._online_phase in ("playing", "result", "result_sent"):
                self._online_stop_owned()
                self._online_phase = "result_sent"
                self._online_rematch = bool(event.get("rematch_window"))
                self._online_next_authorized = False
                status = event.get("status")
                self._online_result_message = {
                    "confirmed": "@online.result_confirmed", "disputed": "@online.result_disputed",
                    "void": "@online.result_void"}.get(status, "@online.result_sent")
                if status == "void" and event.get("reason") == "unproven":
                    self._online_result_message = "@t4.result_unproven"
                elif event.get("reason") == "char_lock":
                    self._online_result_message = "@t4.result_char_lock"
                self._online_message = self._online_result_message
                me = event.get("you") or {}
                self._online_rating = me.get("rating") if isinstance(me, dict) else None
                info = event.get("set")
                if _is_set(info):
                    self._online_set = T5Match._online_set_view(self, info, getattr(self, "_t4_slot", 0))
            return True
        if kind == "set_end":
            info = getattr(self, "_online_set", {})
            if info and (not event.get("set") or event.get("set") == info.get("id")):
                self._online_set = T5Match._online_set_view(self, dict(event, id=info.get("id")), ended=True)
            return True
        return False

    def online_action(self, action):
        if action in ("mode_lobby", "mode_direct"):
            return self._t4_set_mode("lobby" if action == "mode_lobby" else "direct")
        if self._other_action(action):
            return
        if self.online_direct_ip:
            return self._direct_action(action)
        self._online_init()
        if (action in ("login_guest", "login_account", "login_saved", "login_register")
                and self._online_client is None and not self._online_busy):
            if not self.ready():
                self._online_phase, self._online_message = "error", "@online.build_required"
                return
            if action != "login_saved" and not self.online_text_value("online_name").strip():
                self._online_phase, self._online_message = "error", "@t4.online_name_required"
                return
            if not self.online_text_value("online_server").strip():
                self._online_phase, self._online_message = "error", "@t4.lobby_no_server"
                return
        if action == "login_saved" and self._online_client is None and not self._online_busy:
            saved = self._online_saved()
            self._t4_shared_attempt = saved["token"] if saved and saved.get("shared") else None
        client = self._online_client
        phase = self._online_phase
        if action == "start_match" and phase == "matched" and client and not self._online_busy:
            self._online_authorized = True
            self._online_match["my_ready"] = True
            self._online_phase, self._online_message = "starting", "@online.starting"
            generation = self._online_generation
            ready_check = getattr(self, "_online_ready_check", True)

            def ready():
                problem = self._online_game_check()
                if problem:
                    raise SearchRefused(problem)
                self._online_check_request(generation, client)
                return client.ready(True) if ready_check else None
            self._online_submit(action, ready)
        elif action == "cancel_match" and phase == "matched" and client and getattr(self, "_online_owned_run", None) is None:
            # Declined at the ready check: say no and stay in the lobby.
            self._online_to_lobby("@online.cancelled", decline=getattr(self, "_online_match_id", None) or "")
        elif action == "cancel_match" and phase in ("matched", "starting") and client:
            # Cancelled after Start: leave the match (the server cancels it for both players, and the client drops
            # its game socket on that cancel) and stay in the lobby; the match reset stops a game already started.
            self._online_authorized = False
            self._online_to_lobby("@online.cancelled", leave=getattr(self, "_online_match_id", None) or None)
        elif action == "stop_match" and phase == "playing":
            self._online_stop_owned()
        elif action in ("result_win", "result_loss", "result_none") and phase == "result" and client and not self._online_busy:
            ticket = self._online_ticket
            winner = None if action == "result_none" else (ticket.slot if action == "result_win" else 1 - ticket.slot)
            evidence = dict(getattr(self, "_online_evidence", {}))
            self._online_submit(action, lambda: client.report_result(
                winner=winner, match_id=ticket.match_id, source="manual", **evidence))
        elif (action == "leave_set" and phase in ("result", "result_sent") and client and not self._online_busy
              and self.online_state()["capabilities"].get("leave_set")):
            self._online_submit("leave_set", lambda: client.leave_set())
            self._online_set = {}
            self._online_ticket = None
            self._online_match_id = None
            self._online_authorized = False
            self._online_match = {}
            self._online_phase, self._online_message = "logged_in", "@online.logged_in"
        elif (action == "rematch" and phase == "result_sent" and client and not self._online_busy
              and self.online_state()["capabilities"].get("rematch")):
            mid, generation = self._online_match_id, self._online_generation
            self._t4_rematch_from = mid
            self._online_authorized = self._online_next_authorized = True
            self._online_rematch = False
            self._online_message = "@online.rematch_wait"

            def rematch():
                self._online_check_request(generation, client)
                return client.rematch(mid, True, keep=False)
            self._online_submit("t4_rematch", rematch)
        elif action == "return_lobby" and phase == "result_sent" and not self._online_busy:
            mid = self._online_match_id
            decline = bool(getattr(self, "_online_rematch", False) or getattr(self, "_online_next_authorized", False))
            self._online_rematch = self._online_next_authorized = False
            self._online_ticket = None
            self._online_match_id = None
            self._online_authorized = False
            self._online_early_start = None
            self._online_match = {}
            self._online_phase, self._online_message = "logged_in", "@online.logged_in"
            if decline and client and callable(getattr(client, "rematch", None)):
                self._online_submit("t4_rematch_decline", lambda: client.rematch(mid, False, keep=False))
        else:
            super().online_action(action)

    def _online_error(self, error, saved=False):
        attempt = getattr(self, "_t4_shared_attempt", None)
        if saved and attempt and getattr(error, "code", "") == "auth_failed":
            # Never deleted from T5DR's settings; only not offered again in this session.
            self._t4_shared_rejected = getattr(self, "_t4_shared_rejected", set()) | {attempt}
            self._t4_shared_attempt = None
            return "@t4.saved_shared_refused"
        if isinstance(error, RuntimeError) and str(error) in ("@t4.direct_identity_failed", "@iso.choose_first"):
            return str(error)                         # the lobby identity's own refusals (_t4_identity_build)
        return super()._online_error(error, saved)

    def _online_completion(self, action, value, error):
        if action == "t4_rematch_decline":
            # The old window may already have expired; its reply cannot undo the return to the lobby.
            return True
        if action == "t4_rematch":
            previous = self.__dict__.pop("_t4_rematch_from", None)
            if error and self._online_match_id == previous and self._online_phase == "result_sent":
                # A correlated match_found can arrive before a lost request reply. Its new ticket keeps the vote.
                self._online_next_authorized = self._online_authorized = False
                self._online_message = self._online_error(error)
            return True
        if action.startswith("login_") and not error:
            self._online_rating = value["me"].get("rating")
        if action not in ("start_match", "start_game", "game_started", "game_playing", "nat_fallback",
                          "result_win", "result_loss", "result_none", "result_game"):
            return False
        if error and action == "result_game":
            # The game's report did not go through: the player answers instead (the manual buttons).
            self._online_phase, self._online_message = "result", "@online.result_prompt"
            return True
        if error:
            # The match could not go on: back to the lobby, logged in (closing here was a logout). A match that has
            # not started is left; the match reset stops the owned game.
            if action in ("game_started", "game_playing", "nat_fallback") and self._online_transport_error(error):
                return True                     # the game plays on; the client resumes the lobby and tells it
            message = self._online_error(error)
            mid = getattr(self, "_online_match_id", None) or None
            phase = self._online_phase
            self._online_to_lobby(message, decline=mid if phase == "matched" else None,
                                  leave=mid if phase in ("starting", "playing") else None)
        elif action == "start_game":
            self._online_phase, self._online_message = "playing", "@online.playing"
        elif (action == "start_match" and self._online_phase == "starting"
              and self._online_message == "@online.starting" and getattr(self, "_online_ready_check", True)):
            self._online_message = "@online.waiting_peer_ready"
        elif action.startswith("result_"):
            self._online_phase = "result_sent"
            self._online_message = getattr(self, "_online_result_message", "@online.result_sent")
        elif action == "nat_fallback" and not value:
            self._online_fallback = True
        return True

    def _online_match_started(self):
        return (getattr(self, "_online_ticket", None) is not None
                or getattr(self, "_online_owned_run", None) is not None)

    def _online_stop_submit(self, work):
        worker = threading.Thread(target=work, name="openrecomp-t4-stop", daemon=False)
        worker.start()
        return worker

    def _online_reap_owned(self):
        run = getattr(self, "_online_owned_run", None)
        waiter = getattr(self, "_run_waiter", None)
        if run is not None and run.proc.poll() is not None and (waiter is None or not waiter.is_alive()):
            if self.online_direct_ip:
                stopping = getattr(self, "_online_stopper", None)
                if stopping and stopping[0] is run and stopping[1] is not None and stopping[1].is_alive():
                    return
                self._direct_verified = None
                self._direct_stopping = self._direct_busy = True
                self._direct_status("stopping", "@t4.direct_finished")

                def capture():
                    try:
                        self._direct_snapshot_logs()
                    finally:
                        with self._online_lock:
                            if self._online_owned_run is run:
                                self._online_owned_run = None
                self._online_stopper = (run, self._online_stop_submit(capture))
                return
            with self._online_lock:
                if self._online_owned_run is run:
                    self._online_owned_run = None
                    self._online_stopper = None

    def _online_stop_owned(self, wait=False, expected=None):
        run = getattr(self, "_online_owned_run", None)
        if expected is not None and run is not expected:
            raise RuntimeError("@online.cancelled")
        if run is None:
            return
        stopping = getattr(self, "_online_stopper", None)
        if stopping is not None and stopping[0] is run:
            if wait and stopping[1] is not None:
                stopping[1].join()
            self._online_reap_owned()
            if getattr(self, "_online_owned_run", None) is None:
                return
            if stopping[1] is not None and stopping[1].is_alive():
                return
            self._online_stopper = None

        def stop():
            try:
                run.stop()
                waiter = getattr(self, "_run_waiter", None)
                if waiter:
                    waiter.join(timeout=5)
                if run.proc.poll() is not None and (waiter is None or not waiter.is_alive()):
                    with self._online_lock:
                        if self._online_owned_run is run:
                            if self.online_direct_ip:
                                self._direct_snapshot_logs()
                            self._online_owned_run = None
            except Exception:  # noqa: BLE001 -- closing the lobby must still close its sockets
                pass
        if wait:
            stop()
            if getattr(self, "_online_owned_run", None) is run:
                raise RuntimeError("@online.game_running")
        else:
            self._online_stopper = (run, self._online_stop_submit(stop))

    def _online_read_evidence(self):
        for path, (offset, stamp) in list(self._online_log_offsets.items()):
            try:
                stat = os.stat(path)
                # The core/runtime may truncate a log on each start.
                baseline = self._online_log_prefixes.get(path)
                with open(path, "rb") as stream:
                    prefix = stream.read(len(baseline)) if baseline is not None else None
                if (stat.st_size < offset or (stat.st_mtime_ns != stamp and stat.st_size == offset)
                        or (baseline is not None and prefix != baseline)):
                    offset = 0
                if stat.st_mtime_ns != stamp:
                    self._online_log_prefixes.pop(path, None)
                with open(path, "r", encoding="utf-8", errors="replace") as stream:
                    stream.seek(offset)
                    chunk = stream.read(256 * 1024)
                    position = stream.tell()
                self._online_log_offsets[path] = (position, stat.st_mtime_ns)
            except OSError:
                continue
            text = self._online_log_pending.get(path, "") + chunk
            lines = text.split("\n")
            self._online_log_pending[path] = lines.pop()[-4096:]
            for line in lines:
                if re.search(r"\bconnected\b", line) and "disconnected" not in line:
                    self._online_connected = True
                if "NETSUMMARY" in line:
                    self._online_playing = True
                    # The T4 game writes "NETSUMMARY [final] live <frames> logical ...; rollbacks N resim frames N".
                    for key, pattern in (("frames", r"\blive\s+(\d+)"),
                                         ("frames", r"(?<!resim )\b(?:frames|frame)\s*[=: ]\s*(\d+)"),
                                         ("desync", r"mismatches\s*[=: ]\s*(\d+)")):
                        found = re.search(pattern, line)
                        if found:
                            self._online_evidence[key] = max(self._online_evidence[key], int(found.group(1)))
                for reason in ("peer_timeout", "peer_quit", "no_peer", "build_mismatch"):
                    if reason in line:
                        self._online_evidence["reason"] = reason

    def online_poll(self):
        if self.online_direct_ip:
            return self._direct_poll()
        if hasattr(self, "_online_lock"):
            self._online_reap_owned()
        changed = super().online_poll()
        early = getattr(self, "_online_early_start", None)
        if (early is not None and not self._online_busy and getattr(self, "_online_authorized", False)
                and self._online_phase == "starting"):
            self._online_early_start = None
            if early[0] == self._online_generation:
                self._online_event(early[1])
                return True
        pending = getattr(self, "_online_pending_start", None)
        if pending is not None and not self._online_busy:
            self._online_pending_start = None
            self._online_event(pending)
            return True
        if self._t4_game_result_poll():
            return True
        if self._online_phase != "playing" or self._online_busy:
            return changed
        run = getattr(self, "_online_owned_run", None)
        self._online_read_evidence()
        if run is None:
            self._online_phase, self._online_message = "result", self._online_match_message() or "@online.result_prompt"
            return True
        if run.proc.poll() is not None:
            self._online_phase, self._online_message = "result", self._online_match_message() or "@online.result_prompt"
            return True
        problem = self._online_match_message()
        if problem and self._online_message != problem:
            self._online_message = problem
            changed = True
        client, ticket = self._online_client, self._online_ticket
        if self._online_connected and not getattr(self, "_online_started_sent", False):
            self._online_started_sent = True
            self._online_submit("game_started", lambda: client.game_started(ticket.match_id))
            return True
        if self._online_playing and not getattr(self, "_online_playing_sent", False):
            self._online_playing_sent = True
            self._online_submit("game_playing", lambda: client.game_playing(ticket.match_id))
            return True
        if (not self._online_connected and not self._online_fallback and ticket.path in ("direct", "lan")
                and time.monotonic() - self._online_started_at >= 20):
            self._online_fallback = True
            self._online_message = "@online.connection_fallback"
            self._online_submit("nat_fallback", lambda: client.nat_fallback(ticket.match_id))
            return True
        return changed

    def _online_match_reset(self):
        self._online_authorized = False
        self._online_next_authorized = self._online_rematch = False
        self._online_early_start = None
        self._online_pending_start = None
        self._online_ticket = None
        self._online_match_id = None
        self._online_stop_owned()

    def online_close(self):
        if self.online_direct_ip:
            return self._direct_close()
        self._online_init()
        with self._online_lock:
            self._online_authorized = False
            self._online_next_authorized = self._online_rematch = False
            self._online_early_start = None
            self._online_pending_start = None
            self._online_stop_owned()
            super().online_close()
