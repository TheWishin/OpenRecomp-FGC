"""T4 direct-IP beta checks and the dormant future lobby process flow."""
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
from .t5_online import Online, SearchRefused, game_process_running
from ..manifest import user_dir
from ..ranks import t4_rank_name


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
                    capabilities=dict(direct_ip=True, ranked=False, lobby=False, match_flow=False))

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
                    env.update(TEKKEN4_NET_COALESCE="1", TEKKEN4_NET_DIAG="1",
                               TEKKEN4_RB_AUDIO_TIMELINE="0", TEKKEN4_NET_REFRESH_RC="0",
                               TEKKEN4_NET_AUTO_VS="0", TEKKEN4_NET_TIMESYNC="1",
                               TEKKEN4_NET_MAXPRED="8", TEKKEN4_NET_EARLY="1",
                               TEKKEN4_NET_LAZY="1", TEKKEN4_NET_LOCALPAD="1")
                    diagnostics = self.config.get("t4_diagnostics")
                    if isinstance(diagnostics, dict) and diagnostics.get("net_diagnostics") is False:
                        env["TEKKEN4_NET_DIAG"] = "0"
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


def ticket_env(ticket):
    """Only the ticket fields documented by the T4 lobby handoff; no T5 game driver."""
    if ticket.role not in ("host", "join") or ticket.ranked:
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
    online_ranked = False
    online_lobby = False
    online_match_flow = True
    online_legacy_config = False

    def online_cfg_path(self):
        # Endpoints, TLS pins and session tokens remain scoped to the T4 service.
        return os.path.join(user_dir(), "online-t4.json")

    def _online_build(self, api):
        if not self.ready():
            raise RuntimeError("@online.build_required")
        exe, _why = self.core.find_runtime(self.s)
        if not exe:
            raise RuntimeError("@online.build_required")
        try:
            return api["build"].from_out_dir(os.path.dirname(exe), "dev")
        except (OSError, ValueError):
            raise RuntimeError("@online.build_required") from None

    def _online_player_rank(self, rating):
        return t4_rank_name(rating)

    def online_state(self):
        if self.online_direct_ip:
            return self._direct_state()
        state = super().online_state()
        if state["phase"] == "offline" and state["message"] == "@online.offline":
            state["message"] = "@t4.online_setup_hint"
        state["rank"] = t4_rank_name(getattr(self, "_online_rating", None)) if state["name"] else ""
        return state

    def _online_client_options(self):
        options = super()._online_client_options()
        options.update(relays=False, friends=False, private_rooms=False, tournaments=False,
                       spectate=False, sets=False, match_rules=False)
        return options

    def _online_game_env(self, ticket):
        if ticket.role not in ("host", "join") or ticket.ranked:
            raise RuntimeError("@online.refused")
        api = self._online_modules()
        if "game_env" not in api:
            module = importlib.import_module(self.online_package + ".t4game")
            package = os.path.normcase(os.path.realpath(os.path.join(self.root, "lobby", self.online_package)))
            origin = getattr(module, "__file__", None)
            try:
                local = isinstance(origin, str) and os.path.commonpath(
                    (package, os.path.normcase(os.path.realpath(origin)))) == package
            except ValueError:
                local = False
            if not local or not callable(getattr(module, "game_env", None)):
                raise RuntimeError("@online.client_missing")
            api["game_env"] = module.game_env
        return api["game_env"](ticket)

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
        if (self._online_phase not in ("logged_in", "searching")
                or getattr(self, "_online_owned_run", None) is not None):
            # An unsolicited second offer must never discard an owned game or its result.
            self.online_close()
            self._online_message = "@online.cancelled"
            return True
        self._online_ticket = None
        self._online_match_id = event.get("match")
        self._online_authorized = False
        self._online_ready_check = event.get("ready_check", True) is not False
        self._online_early_start = None
        self._online_owned_run = None
        self._online_pending_start = None
        self._online_result_message = "@online.result_sent"
        self._online_match = self._online_match_view(event)
        self._online_phase, self._online_queue = "matched", ""
        self._online_message = "@online.t4_matched"
        return True

    def _online_event(self, event):
        kind = event.get("t")
        if kind == "notice" and event.get("code") in ("nat_error", "version_mismatch"):
            if self._online_phase in ("matched", "starting", "playing"):
                message = ("@online.game_build_mismatch" if event["code"] == "version_mismatch"
                           else "@online.connection_failed")
                self.online_close()
                self._online_message = message
            return True
        if kind in ("match_reveal", "match_cancel", "match_result", "nat_status", "nat_upgrade", "nat_fallback"):
            if self._online_phase not in ("matched", "starting", "playing", "result", "result_sent"):
                return True
            current = getattr(self, "_online_match_id", None)
            if current and event.get("match") not in (None, current):
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
            # A quick-match cancellation may requeue automatically; disconnect to stop it.
            reason = event.get("reason")
            self.online_close()
            self._online_message = {
                "peer_quit": "@online.peer_quit", "opponent_left": "@online.peer_quit",
                "peer_timeout": "@online.peer_timeout", "ready_timeout": "@online.ready_expired",
                "declined": "@online.peer_declined", "relay_full": "@online.relay_full",
                "nat_failed": "@online.connection_failed", "udp_unreachable": "@online.connection_failed",
                "no_connection": "@online.connection_failed"}.get(reason, "@online.cancelled")
            return True
        if kind == "match_result":
            if self._online_phase == "starting":
                # The lobby can void a match while the launch worker is still pending.
                self.online_close()
                self._online_message = "@online.result_void"
                return True
            if self._online_phase in ("playing", "result", "result_sent"):
                self._online_stop_owned()
                self._online_phase = "result_sent"
                status = event.get("status")
                self._online_result_message = {
                    "confirmed": "@online.result_confirmed", "disputed": "@online.result_disputed",
                    "void": "@online.result_void"}.get(status, "@online.result_sent")
                self._online_message = self._online_result_message
                me = event.get("you") or {}
                self._online_rating = me.get("rating") if isinstance(me, dict) else None
            return True
        return False

    def online_action(self, action):
        if self.online_direct_ip:
            return self._direct_action(action)
        self._online_init()
        if (action in ("login_guest", "login_account", "login_saved")
                and self._online_client is None and not self._online_busy):
            if not self.ready():
                self._online_phase, self._online_message = "error", "@online.build_required"
                return
            if action != "login_saved" and not self.online_text_value("online_name").strip():
                self._online_phase, self._online_message = "error", "@t4.online_name_required"
                return
        if action == "search_ranked":
            self._online_message = "@online.ranked_unavailable"
            return
        client = self._online_client
        phase = self._online_phase
        if action == "start_match" and phase == "matched" and client and not self._online_busy:
            self._online_authorized = True
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
        elif action == "cancel_match" and phase in ("matched", "starting") and client:
            self._online_authorized = False
            self._online_stop_owned()
            # Closing also cancels an in-flight ready request and the client's NAT/bridge.
            self.online_close()
            self._online_message = "@online.cancelled"
        elif action == "stop_match" and phase == "playing":
            self._online_stop_owned()
        elif action in ("result_win", "result_loss", "result_none") and phase == "result" and client and not self._online_busy:
            ticket = self._online_ticket
            winner = None if action == "result_none" else (ticket.slot if action == "result_win" else 1 - ticket.slot)
            evidence = dict(getattr(self, "_online_evidence", {}))
            self._online_submit(action, lambda: client.report_result(
                winner=winner, match_id=ticket.match_id, source="manual", **evidence))
        elif action == "return_lobby" and phase == "result_sent":
            self._online_ticket = None
            self._online_match_id = None
            self._online_authorized = False
            self._online_early_start = None
            self._online_match = {}
            self._online_phase, self._online_message = "logged_in", "@online.logged_in"
        else:
            super().online_action(action)

    def _online_completion(self, action, value, error):
        if action.startswith("login_") and not error:
            self._online_rating = value["me"].get("rating")
        if action not in ("start_match", "start_game", "game_started", "game_playing", "nat_fallback",
                          "result_win", "result_loss", "result_none"):
            return False
        if error:
            self._online_stop_owned()
            message = self._online_error(error)
            self.online_close()
            self._online_message = message
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
                    for key, pattern in (("frames", r"(?:frames|frame)\s*[=: ]\s*(\d+)"),
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

    def online_close(self):
        if self.online_direct_ip:
            return self._direct_close()
        self._online_init()
        with self._online_lock:
            self._online_authorized = False
            self._online_early_start = None
            self._online_pending_start = None
            self._online_stop_owned()
            super().online_close()
