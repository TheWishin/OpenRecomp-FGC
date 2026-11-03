"""Tekken 4: where the lobby ends and the T4 game begins (docs/LOBBY.md).

T5DR's handover.MatchTicket is kept as it is (the client library makes it); game_env() below turns it into the
T4 port's netplay environment, read by runtime/tekken4_rollback_overrides.cpp npConfigure() and runtime/tekken4_net.cpp
(docs/ROLLBACK_PHASE3.md):

    TEKKEN4_NET          host:<local port>      host = P1 (slot 0): binds the punched port ...
    TEKKEN4_NET_PEER     <ip:port>              ... and calls the peer at once (the opponent's punched endpoint, the
                                                lobby server's relay, or 127.0.0.1:<port> of the launcher's relay
                                                bridge); it follows the peer to the address its HELLO comes from
    TEKKEN4_NET          join:<ip:port>         join = P2 (slot 1): calls the peer (same three kinds) ...
    TEKKEN4_NET_PORT     <local port>           ... from exactly the punched port (relay bridge: the bridge's game port)
    TEKKEN4_NET_BUILD    16 hex digits          the build id the lobby paired on (= t4net_build.txt); another one in
                                                the peer's HELLO -> build_mismatch
    TEKKEN4_NET_KEY      hex secret             the match secret from the server (TCP only): SipHash-2-4 tag on every
                                                packet, so only the opponent's game takes part (and is followed after
                                                a NAT rebinding)
    TEKKEN4_NET_SEED     32-bit                 the host's session seed (mixed into the game's srand)
    TEKKEN4_NET_DELAY    auto | 0..4            rollback input delay: a ranked match's fixed value (match_start
                                                input_delay), else the player's setting; the host's value wins
    TEKKEN4_NET_TIMEOUT  seconds                the peer silent this long = lost
    TEKKEN4_NET_BIND     ip                     only when the lobby tools bind the game socket somewhere special
                                                (T5_NET_BIND=127.0.0.1 in tests)
    TEKKEN4_NET_MATCH / _PATH / _RTT_MS         informational (not read by the game yet; in the run dir's env file)

Not passed (the T4 game has no use for them yet): T5_NET_DELAY (T5DR's lockstep delay), T5_FIGHT / T5_CTL_DIR
(direct fight, persistent game), T5_NET_UNLOCKS, T5_NET_RESULT_FILE (the T4 game writes no result file yet: the
result comes from the player, or "no result" -- open item in docs/LOBBY.md).

The T4 game logs to its run dir (the working directory): net.log (transport: "connected (host, P1), peer ...",
"cannot connect (<reason>): ...", "peer lost (<reason>): ...") and rb_frames.log ("NETSUMMARY ...", "NETDESYNC",
"NETEND f=<frame>"). GameWatch reads both.
"""
import json
import os
import re
import subprocess
import time

from . import proto

GAME_EXE = "ps2EntryRunner.exe"
ELF_NAME = "SLUS_203.28"


def game_env(ticket, delay="auto", bind=None):
    """The TEKKEN4_* environment for one side of a lobby match (ticket: handover.MatchTicket)."""
    peer = f"{ticket.peer[0]}:{int(ticket.peer[1])}"
    env = {}
    if ticket.role == "host":
        env["TEKKEN4_NET"] = f"host:{int(ticket.local_port)}"
        env["TEKKEN4_NET_PEER"] = peer
    else:
        env["TEKKEN4_NET"] = f"join:{peer}"
        env["TEKKEN4_NET_PORT"] = str(int(ticket.local_port))
    if ticket.build:
        env["TEKKEN4_NET_BUILD"] = ticket.build
    if ticket.key:
        env["TEKKEN4_NET_KEY"] = ticket.key
    env["TEKKEN4_NET_SEED"] = str(int(ticket.seed) & 0xFFFFFFFF)
    env["TEKKEN4_NET_TIMEOUT"] = str(int(ticket.timeout))
    d = ticket.input_delay if ticket.input_delay is not None else delay
    env["TEKKEN4_NET_DELAY"] = "auto" if d in (None, "", "auto") else str(max(0, min(4, int(d))))
    if bind is None:
        b = os.environ.get("T5_NET_BIND", "").strip()      # the lobby tools' own bind (tests): the game binds the same
        bind = b or None
    if bind:
        env["TEKKEN4_NET_BIND"] = bind
    env["TEKKEN4_NET_MATCH"] = ticket.match_id
    env["TEKKEN4_NET_PATH"] = ticket.path
    env["TEKKEN4_NET_RTT_MS"] = f"{ticket.rtt_ms:.1f}"
    return env


# ------------------------------------------------------------------------------------------------ the game's logs
RE_CONNECTED = re.compile(r"connected \((host|join), P([12])\)")
RE_FAIL = re.compile(r"cannot connect \((\w+)\)")
RE_LOST = re.compile(r"peer lost \((\w+)\)")
RE_SUMMARY = re.compile(r"^NETSUMMARY( final)? live (\d+) logical (\d+): fps window ([\d.]+) run ([\d.]+);.*?"
                        r"rtt (-?\d+) ms \(\d+\) delay (-?\d+); hashes compared (\d+) mismatches (\d+); "
                        r"packets out (\d+) in (\d+)")
RE_DESYNC = re.compile(r"^NETDESYNC")
RE_END = re.compile(r"^NETEND f=(\d+)")


def parse_summary(line):
    m = RE_SUMMARY.search(line)
    if not m:
        return None
    return {"final": bool(m.group(1)), "live": int(m.group(2)), "logical": int(m.group(3)),
            "fps_window": float(m.group(4)), "fps_run": float(m.group(5)), "rtt_ms": int(m.group(6)),
            "delay": int(m.group(7)), "hashes": int(m.group(8)), "mismatches": int(m.group(9)),
            "packets_out": int(m.group(10)), "packets_in": int(m.group(11))}


class _Tail:
    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.buf = b""

    def lines(self):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
        except OSError:
            return []
        self.pos += len(data)
        data = self.buf + data
        parts = data.split(b"\n")
        self.buf = parts.pop()
        return [p.decode("utf-8", "replace").rstrip("\r") for p in parts]


class GameWatch:
    """What one T4 game's run dir says about its netplay session."""

    def __init__(self, run_dir):
        self.net = _Tail(os.path.join(run_dir, "net.log"))
        self.frames = _Tail(os.path.join(run_dir, "rb_frames.log"))
        self.connected = False
        self.fail = None          # cannot connect (reason)
        self.lost = None          # peer lost (reason)
        self.summary = None       # the latest NETSUMMARY (dict)
        self.summaries = 0
        self.desync_lines = 0
        self.ended = None         # NETEND frame

    def poll(self):
        for ln in self.net.lines():
            if RE_CONNECTED.search(ln):
                self.connected = True
            m = RE_FAIL.search(ln)
            if m and self.fail is None:
                self.fail = m.group(1)
            m = RE_LOST.search(ln)
            if m and self.lost is None:
                self.lost = m.group(1)
        for ln in self.frames.lines():
            if ln.startswith("NETSUMMARY"):
                s = parse_summary(ln)
                if s:
                    self.summary = s
                    self.summaries += 1
            elif RE_DESYNC.match(ln):
                self.desync_lines += 1
            else:
                m = RE_END.match(ln)
                if m:
                    self.ended = int(m.group(1))
        return self

    @property
    def reason(self):
        return self.fail or self.lost


# ------------------------------------------------------------------------------------------------ starting the game
class GameSetup:
    """Where the T4 game is and how to start it.

    exe_dir   the netplay build's folder (<T4 build>\\ps2xRuntime: ps2EntryRunner.exe and
              t4net_build.txt, docs/rollback/net_build.cmd)
    elf       the player's game\\disc\\SLUS_203.28 (from his own disc)
    run_root  one run dir per match below it (its own memory card, net.log, rb_frames.log)
    command   instead of the game: another program started the same way (tests: tools/t4_stub_game.py)"""

    def __init__(self, exe_dir=None, elf=None, run_root=None, delay="auto", sound=True, pad=None, extra_env=None,
                 command=None):
        self.exe_dir = exe_dir
        self.elf = elf
        self.run_root = run_root or os.path.join(os.getcwd(), "t4online")
        self.delay = delay
        self.sound = sound
        self.pad = pad
        self.extra_env = dict(extra_env or {})
        self.command = list(command) if command else None

    def argv(self):
        if self.command:
            return list(self.command)
        return [os.path.join(self.exe_dir, GAME_EXE), self.elf]

    def start(self, ticket, attempt=0):
        """Start the game for `ticket` -> (Popen, run_dir, env)."""
        name = f"{proto.file_safe(ticket.match_id)}_{ticket.role}" + (f"_{attempt}" if attempt else "")
        run_dir = os.path.join(self.run_root, name)
        os.makedirs(run_dir, exist_ok=True)
        env = game_env(ticket, self.delay)
        env.setdefault("TEKKEN4_SOUND", "1" if self.sound else "0")
        if self.pad is not None:
            env["TEKKEN4_NET_PAD"] = str(self.pad)
        env.update(self.extra_env)
        with open(os.path.join(run_dir, "lobby_env.json"), "w", encoding="utf-8") as f:
            json.dump({k: ("(secret)" if k == "TEKKEN4_NET_KEY" else v) for k, v in env.items()}, f, indent=1)
        full = dict(os.environ)
        full.setdefault("PS2X_GS_BACKEND", "gl")
        full.update(env)
        out = open(os.path.join(run_dir, "stdout.txt"), "wb")
        err = open(os.path.join(run_dir, "stderr.txt"), "wb")
        try:
            p = subprocess.Popen(self.argv(), cwd=run_dir, env=full, stdout=out, stderr=err,
                                 stdin=subprocess.DEVNULL)
        finally:
            out.close()
            err.close()
        return p, run_dir, env


def stop(p, wait=10.0):
    if p is None or p.poll() is not None:
        return
    p.terminate()
    try:
        p.wait(wait)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait(5)


# ------------------------------------------------------------------------------------------------ one match
class T4Match:
    """Plays one lobby match with the T4 game: start it from match_start, tell the server when the games hear each
    other, ask for the relay when the direct path stays silent (nat_fallback, a second match_start for the same match
    restarts the game), stop at NETEND or when the game exits, report the result.

    result_of(watch, rc) -> (winner, score) or None: who won (the player's answer, a test's fixed value); None = no
    result (reported as winner null). The T4 game itself writes no result file yet."""

    FALLBACK_AFTER = 20.0       # s without "connected" on the direct path -> ask for the relay (T5DR: 15 s)
    POLL = 0.2

    def __init__(self, client, setup, result_of=None, log=print, stop_at_end=True, max_seconds=None):
        self.c = client
        self.setup = setup
        self.result_of = result_of
        self.log = log
        self.stop_at_end = stop_at_end
        self.max_seconds = max_seconds

    def play(self, ev):
        ticket = ev["ticket"]
        mid = ticket.match_id
        way = {"direct": "direct connection", "lan": "local network", "relay": "through the relay"}.get(ticket.path,
                                                                                                        ticket.path)
        self.log(f"match {mid}: {ticket.opponent.get('name', '?')} -- {way}, ping {ticket.rtt_ms:.0f} ms; "
                 f"you are P{ticket.slot + 1} ({ticket.role})")
        attempt = 0
        p, run_dir, env = self.setup.start(ticket, attempt)
        self.log(f"  game started (run dir {run_dir}): TEKKEN4_NET={env['TEKKEN4_NET']}")
        watch = GameWatch(run_dir)
        t0 = time.monotonic()
        told_started = told_playing = asked_fallback = False
        try:
            while True:
                watch.poll()
                if watch.connected and not told_started:
                    told_started = True
                    self.log("  the two games are connected")
                    self._quiet(self.c.game_started, mid)
                if watch.summaries and not told_playing:
                    told_playing = True                      # 600 live frames: the games hear each other
                    self._quiet(self.c.game_playing, mid)
                if (not watch.connected and not asked_fallback and ticket.path != "relay"
                        and time.monotonic() - t0 > self.FALLBACK_AFTER):
                    asked_fallback = True
                    ok = self._quiet(self.c.nat_fallback, mid)
                    self.log(f"  nothing from the opponent's game; relay fallback {'granted' if ok else 'refused'}")
                    if ok:
                        nxt = self.c.next_event(15, ("match_start",))
                        if nxt and nxt.get("ticket") is not None and nxt["ticket"].match_id == mid:
                            stop(p)
                            ticket = nxt["ticket"]
                            attempt += 1
                            p, run_dir, env = self.setup.start(ticket, attempt)
                            watch = GameWatch(run_dir)
                            self.log(f"  game restarted on the relay: TEKKEN4_NET={env['TEKKEN4_NET']}")
                rc = p.poll()
                if rc is not None:
                    watch.poll()
                    break
                if watch.ended is not None and self.stop_at_end:
                    time.sleep(5.0)          # (the opponent's game may be a few frames behind and still need ours)
                    watch.poll()
                    stop(p)
                    rc = p.poll()
                    break
                if watch.reason in ("build_mismatch", "no_peer", "rejected"):
                    stop(p)
                    rc = p.poll()
                    break
                if self.max_seconds and time.monotonic() - t0 > self.max_seconds:
                    stop(p)
                    rc = p.poll()
                    break
                time.sleep(self.POLL)
        except BaseException:
            stop(p)
            raise
        return self._report(ticket, watch, rc, run_dir)

    def _quiet(self, fn, *args):
        try:
            return fn(*args)
        except proto.LobbyError:
            return None

    def _report(self, ticket, watch, rc, run_dir):
        s = watch.summary or {}
        out = {"match": ticket.match_id, "role": ticket.role, "rc": rc, "run_dir": run_dir,
               "connected": watch.connected, "reason": watch.reason, "summary": s, "ended": watch.ended,
               "desync_lines": watch.desync_lines}
        res = self.result_of(watch, rc) if self.result_of else None
        winner, score = (res if res else (None, None))
        reason = watch.reason or ("" if watch.connected else "no_peer")
        # disconnect: this game lost the opponent; manual: the player's answer, or no result (winner null)
        source = "disconnect" if watch.lost in ("peer_timeout", "peer_quit") and not res else "manual"
        kw = {"match_id": ticket.match_id, "source": source}
        if s:
            kw["desync"] = s.get("mismatches", 0)
            kw["frames"] = s.get("live", 0)
        if reason:
            kw["reason"] = reason
        try:
            self.c.report_result(winner, score, **kw)
            ev = self.c.next_event(30, ("match_result",))
            out["lobby_result"] = ev
        except proto.LobbyError as e:
            out["lobby_error"] = str(e)
        return out
