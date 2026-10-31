# T4 direct IP / VPN beta

The beta supports T4 offline and online by direct IP or VPN, with no lobby and
no ranked. There is no account, matchmaking, room, chat, relay, leaderboard or
server-reported result flow. Lobby-based online stays hidden until its server
exists. T5DR Online uses its installed lobby client; the old T5DR Online launcher
remains available. Its separate checks are in [T5DR_ONLINE.md](T5DR_ONLINE.md).

Both players need compatible locally built T4 runtimes and their own supported
USA SLUS-20328 ISO. The launcher reads the installed T4 build identity and uses
the same build/compiler/ISO and UDP checks as T4's `tools\net_play.ps1`.
It does not build a game or repair an incompatible installation during a check.

## Controller walk

1. Select T4, then Online with LB/RB. One player chooses **Host** (P1); the
   other chooses **Join** (P2).
2. The joining player enters the host's IPv4 address using the **on-screen
   keyboard**. Use the host's VPN address when both PCs use the same VPN.
   The default UDP port is 7400. Arrange the address with the other player
   outside the launcher; this beta has no player directory.
3. Both players select **Check connection**. The check waits up to 90 seconds
   for the peer. It compares the build identity, compiler/MSVC version and ISO
   SHA-256 hash, then checks two-way UDP reachability. Each check explains its
   status in the selected language. A missing identity, mismatch, invalid ISO
   or unreachable peer prevents Start game. Back cancels a pending check.
4. After all checks pass, each player selects **Start game**. This is a separate
   action; a successful check never launches T4 by itself. Choose characters
   and stage in T4's normal menus. This beta does not promise direct entry into
   a fight, trusted match results or persistent sessions with new opponents.
5. To stop the owned T4 process and return, hold View + Menu (Share + Options)
   on one controller for two seconds. An external game is never taken over.
6. After closing T4, **Collect logs** calls the installed T4
   `tools\collect_test_logs.ps1` and writes diagnostic zip files in the launcher's
   local user folder. Collection uses the owned check/run records and includes
   filtered netplay log lines, validated build/preflight metadata and basic
   hardware facts. The installed collector redacts paths and network addresses;
   it excludes raw stdout/stderr, saves, game data and pictures. Its behavior
   must be verified against the shipped T4 release. Review each zip before
   sharing it outside the PC. **Back** returns through the launcher screens.

Direct IP requires a working UDP route. The launcher does not configure a router,
VPN or firewall and supplies no NAT traversal or relay fallback. A blocked route
is a failed reachability check, not proof that either player's build is wrong.
The owner must check both the preflight UDP traffic and the actual game traffic
in the intended network setup.

## Settings

**Connection diagnostics** is an opt-in switch, **off by default**. It sets
`TEKKEN4_NET_DIAG` for online play and may add timing/logging overhead. Enable it
before a test when the maintainer asks, then collect the diagnostic zip files.
The launcher does not expose experimental run-ahead, packet simulation, forced
frame limits or screenshot/desync-dump switches as beta player settings.
Ordinary graphics and sound settings keep their existing defaults.

## Release gate: two physical PCs

Source reading and fake tests cannot approve real online play. Before a Sunday
release, the owner must use two physical PCs and record a successful host/join
test on the intended direct IP or VPN route. Repeat with the PCs' roles reversed.

- Use only a pad for address entry, checks, start, cancel, log collection and Back.
  Check all seven languages at 1080p and Windows 150% scaling, including long
  translated error messages and visible focus.
- Deliberately try a different build, compiler/MSVC version and ISO hash, a
  missing/stale identity, an invalid address and an unreachable peer. Each must
  fail before launch, explain recovery, and permit retry or Back.
- Check timeout, cancellation, peer departure, game failure and repeated sessions.
  Refuse duplicate starts and an already running T4 from another launcher. Old
  check results must not authorize changed settings or a new peer.
- Verify real gameplay synchronization, sustained speed, sound, both local pads,
  disconnect behavior and the return chord. A passing UDP check alone is not
  a passing game test.
- Check diagnostics off/on and the collected zip files on both PCs. Keep player
  logs and reports local; no game data, saves or personal paths belong in this
  public repository.

The launcher window, a game, a build and real networking were not started for
this source review. Runtime compatibility and the two-PC result remain release
acceptance work; see [T4_FIRST_RUN.md](T4_FIRST_RUN.md) and
[PACKAGING.md](PACKAGING.md) for the other gates.
