# T4 Online: lobby and direct IP / VPN beta

The beta plays T4 online in two ways (ranked on a T4 server that opens it, see "Ranked" below):

- **T4 lobby:** through a T4 lobby server. Guest or account login, the player list,
  lobby chat, quick match and challenges (accept or decline), then the same explicit
  Start game, a result report and back to the lobby. The server pairs only players
  with the same T4 build and finds the connection (direct, or through its relay).
- **Direct IP / VPN:** Host and Join by address, as described below. No server.

Both players need compatible locally built T4 runtimes and their own supported
USA SLUS-20328 ISO. T5DR Online uses its installed lobby client; the old T5DR Online
launcher remains available. Its separate checks are in [T5DR_ONLINE.md](T5DR_ONLINE.md).

## T4 lobby

The launcher ships one server entry, **T4 Online** (`openrecomp\vendor\servers.json`):
the beta lobby on the central server (TLS, certificate pinned, UDP 7791 + NAT probe 7792,
casual only, T5DR Online's accounts). As a placeholder (no host, no fingerprint) the
launcher has no T4 server. The maintainer sets or clears it with the address and the
certificate fingerprint the server install printed:

    python tools\set_t4_server.py --host <server address> --fingerprint <SHA-256>
    python tools\set_t4_server.py --clear      (back to the placeholder)

The entry is TLS with the certificate pinned, `"shared_login": true` (the T4 server
shares T5DR Online's accounts) and the default. The launcher uses the first of:

1. the environment variable `OPENRECOMP_T4_SERVER` (for example `host:7791`,
   `host:7791#<certificate SHA-256>` or `tls://host:7791`);
2. `t4_lobby_server` in the launcher's `config.json`;
3. the default entry of the player's own server list `servers.json` (format
   `t5dr-servers/1`) in `%LOCALAPPDATA%\OpenRecomp\t4-online\`, else the shipped
   **T4 Online** once it is filled in.

Without any of these, Online opens on Direct IP / VPN; **T4 Online lobby** switches to
the lobby screen, which says that no server is set up and lets the player type the
address under Lobby address. The choice between lobby and direct IP is remembered.
Search and chat are always explicit actions. Opening the page connects nowhere, except that a login this
launcher saved itself (account, `online-t4.json`) logs in by itself once per launcher start when the page is
first shown; a shared T5DR login is used only when chosen. See "Staying logged in" in T5DR_ONLINE.md.

The lobby client ships inside the launcher (client modules of T5DR Online's open-source
lobby, renamed for Tekken 4; no server code, certificates or server list). T4's own
saved logins are stored apart from T5DR's (`online-t4.json`). Accounts need a secured
server (TLS); guests also work over plain TCP.

**One account for T5DR and T4.** A T5DR Online account logs into the T4 lobby with the
same name and password once the T4 server shares T5DR's accounts (ranks stay per game).
Register account in T4 makes one account for both games; a password change, new recovery
codes or a ban apply to both. The login and account screens say so.
A player whose T5DR login is saved on this PC gets **Use your T5DR login** on the T4
login screen: one press, no password. The launcher offers a saved T5DR login only to a
T4 server that the local server list marks with `"shared_login": true` (same host as
the T5DR server; a string names the T5DR host instead) and that uses TLS (`"tls": "pin"`
with a fingerprint, or `"ca"`); never to a typed address, `OPENRECOMP_T4_SERVER` or a
server's own claim, and never a plain-TCP T5DR login. It is read from the T5DR install's
settings when used, never copied into T4's file. If the T4 server refuses it, the
launcher says so, keeps it untouched for T5DR, and does not offer it again until restart.

**Same build = same inputs, as Direct IP checks them.** Before it logs in the launcher checks that the
extracted `game/disc/SLUS_203.28` is the one the build stamp names, reads the compiler from
`t4net_build.json` (`CXX_ID` + `CXX_VERSION`) and hashes the chosen ISO (SHA-256, once; remembered in
`t4-online/hashes.json` until the file changes). Compiler and ISO hash go into the `code` field it sends
(`lobby_code`: SHA-1 over code id, compiler and ISO hash), so the server's own id (`BuildInfo.wire_id`, from
elf/code/net, unchanged) pairs only players with the same code, compiler and disc image, and the game compares
that same id in its HELLO. No server change; a launcher from before this rule gets other ids and is never paired
with a new one. A server that pins builds (`T5L_BUILDS`) needs these lobby ids (the welcome's `build`).
A stale ELF or a stamp without a compiler says "rebuild"; a missing ISO says "choose your ISO".

What the client expects from the server: a T4 lobby (welcome `"game": "t4"`, UDP magic
`T4LB`, relayed game packets `T4NP`), TCP and UDP 7791 plus UDP 7792 for the NAT probe
unless the address names other ports, guests on, quick match and challenges (unranked), the
lobby chat, and a short minimum match length or none. A T4 game built from a source with
the match result (T4 `t4-result`, docs/MATCH_RESULT_T4.md there) writes its own result file
(`TEKKEN4_NET_RESULT`, next to the game's net.log): the launcher reports it with source "game"
(winner, round score, fighters, stage, the compared state hash) and closes the game five seconds
later; an older build, or a game that ends without a decided match, leaves the manual answer.
The players' game port is any free UDP port
the launcher picks; nothing needs forwarding.

### Controller walk (lobby)

1. Select T4, then Online with LB/RB. If Direct IP / VPN shows, choose **T4 Online lobby**.
2. Enter Player name with the **on-screen keyboard**, check Lobby address, then choose
   **Guest login** (or enter a password for Account login or Register).
3. The lobby lists the other players and the chat. **Refresh players**, choose a player
   to challenge them, or **Quick match**. An incoming challenge shows Accept and Decline.
   Chat: choose the chat field, type with the keyboard, then **Send chat**.
4. When a match is found, choose **Start match**. T4 starts with the lobby's connection;
   pick characters and stage in T4's own VS menus. View + Menu held two seconds ends the
   game (as for direct IP).
5. When the game decided the match itself, the launcher reports it, closes the game and shows
   the lobby's verdict. Otherwise (an older T4 build, a game closed before the match ended)
   report **I won**, **I lost** or **No result** after the game; the lobby's verdict appears,
   then **Back to lobby**. **Direct IP / VPN** on the login screen goes back.

### What T4 Online has (t4-parity)

With a T4 server from the `t4-parity` branch (T5DR Online 1.2.0's lobby with T4's game rules) the T4 page
shows the same Online chapters as T5DR: Lobby (players, lobby chat, private chat in the chat panel,
challenges with **First to** 1-10 and **P1 / P2**), Rooms (classic, community, password / invite code,
tables), Friends (requests, invites), Leaderboard, Statistics, Profile (history, per-fighter numbers),
Tournaments, Account (password, recovery codes, blocks, mutes). An older T4 server only offers what it has.

Not yet, because the T4 game needs them first: spectating and replays, training rooms and the health
handicap, the in-game rematch question and automatic skips, choosing the stage in the lobby (pick it on
T4's own stage select), direct entry into a fight. The T4 server switches them off
(`T5L_GAME_CAPS_OFF`, `T5L_STAGE_CHOICE`), and the launcher does not offer them for T4.

### Ranked

When the T4 server opens ranked (its welcome says `ranked_queue`), accounts get **Search ranked**;
guests play casual. Ranked is a set, best of 3, rated once (Glicko-2) when it is decided; the next
game starts by itself after the server's countdown (no ready vote), **Leave set** between games
counts as a loss. Only results the two games proved count (the T4 game's own result file on both
PCs); a game that only has the players' answers does not count ("The games did not prove this
result") and is played again. The set's fighters are the ones game 1 was fought with: a later game
fought with another fighter goes to the other player.

T4 uses the same rank names in the same order as T5DR. Ratings and player records remain
separate for each game. When the launcher knows a T5DR install, T4 uses its rank plates through
the same runtime cache as the T5DR pages. These pictures come from the player's own game data
and stay on their PC. If a plate is unavailable, T4 uses our own drawn badge
(`tools/make_rank_badges.py`, one SVG per rank in `openrecomp/ui/assets/ranks`). They show in
the lobby table, the profile card and the found match, which names **P1** and **P2** with name,
rank and badge (P1 = the host).
In the game each player's name and badge sit on their side at character select and under the
life bars (Settings: **Name plates in the game**, on by default; nothing changes in the match).
The game uses the drawn badges. See [T4 ranked assets](T4_RANKED.md) for regeneration and the
coordinator's game-header handoff. The T4 server's ladder update is handled separately.

### End-to-end check on one PC

`tools\t4_lobby_e2e.py` runs a local T4 lobby server (127.0.0.1, in-memory database)
and two launchers offscreen, driven by pad presses: login, player list, chat both ways,
a declined challenge, a quick match and an accepted challenge with results. `--stub`
uses the T4 lobby's stand-in game; `--real` starts the real T4 build twice (a heavy run).
Its docstring names the three one-PC allowances it needs. `--accounts --t5dr-lobby
<T5DR lobby folder>` adds T5DR's own lobby server and a T4 lobby that shares its
accounts (TLS, pinned): both players are registered in T5DR first, Alice logs into T4
with her T5DR name and password, Bob with one press on **Use your T5DR login**.

## Internet vorbereiten: auf beiden PCs

Fuer das Quelltext-Testbundle zuerst den [Startweg](T4_FIRST_RUN.md) abschliessen:
Python 3.12, Werkzeugpruefung, eigene USA SLUS-20328 v1.00, erfolgreicher Build.
Vor **Check connection** die angezeigte Build-ID und genaue Compiler/MSVC-Version
mit dem Kollegen vergleichen. Bei Abweichung stoppen, dasselbe Testbundle und
dieselbe MSVC-Version verwenden und neu bauen. Die Pruefung vergleicht zusaetzlich
die ISO-Hashes; Build-ID und Compiler allein sind keine Freigabe.

Ein Spieler ist Host (P1), der andere Join (P2). Beide richten einen der folgenden
Wege ein. Der Launcher zeigt diese Hinweise, aendert aber weder Firewall noch
Router oder VPN. Fuer Build, Checks, Spielstart und Logs braucht ihr keine
PowerShell-Befehle einzugeben.

- **Portfreigabe:** Beim Host im Router UDP extern **7400** auf die feste
  Heimnetz-IPv4 des Host-PCs, intern **7400**, weiterleiten. Nicht TCP waehlen.
  Der Host teilt seine oeffentliche IPv4 privat mit dem Kollegen; der Join-Spieler
  traegt diese IP im Launcher ein. Eine Heimnetz-IP funktioniert ueber das
  Internet nicht. Bei DS-Lite/CGNAT, fehlender oeffentlicher IPv4, zweitem Router
  oder fehlendem Routerzugang den Tailscale-Weg verwenden. Beim Join-Spieler ist
  keine Router-Portfreigabe erforderlich.
- **Tailscale:** Beide Windows-Clients installieren. Der Host laedt den Kollegen
  mit dessen eigenem Konto in dasselbe private Tailnet ein und genehmigt dessen
  PC bei Bedarf. Beide PCs muessen dort verbunden sichtbar sein; die
  Zugriffsregeln muessen UDP 7400 zum Host erlauben. Der Host teilt seine
  Tailscale-IPv4 (`100.x.y.z`) privat mit; Join verwendet diese Adresse. Hier
  ist keine Router-Portfreigabe noetig. Eine Relay-Verbindung kann mehr
  verzoegern und ersetzt den UDP-Test nicht.
- **Firewall:** Beim Host Windows-Sicherheit > Firewall & Netzwerkschutz >
  Erweiterte Einstellungen > Eingehende Regeln > Neue Regel > Port > UDP >
  lokale Ports **7400** > Verbindung zulassen > das aktive Profil waehlen
  (bei VPN gegebenenfalls Oeffentlich). Die UDP-Portregel auf das benoetigte
  Netzwerk beziehungsweise den Kollegen begrenzen. Sie muss sowohl die
  PowerShell-Vorpruefung als auch das Spiel zulassen: Die Vorpruefung oeffnet
  ihren UDP-Socket vor dem Spielstart in PowerShell. Nur `ps2EntryRunner.exe`
  freizugeben reicht deshalb nicht. Alternativ beide Anwendungen im benutzten
  Profil und fuer diesen UDP-Port zulassen. Falls Windows fuer
  `ps2EntryRunner.exe` nachfragt, das benutzte Profil zulassen.
  Beim Join-Spieler muessen ausgehendes UDP zum
  Host auf 7400 und Antworten erlaubt sein. Weitere Sicherheitssoftware
  entsprechend einrichten. Die Firewall nicht abschalten. Nach dem Test die
  Testregel deaktivieren und die temporaere Router-Portfreigabe schliessen.

Danach im Launcher Host/Join waehlen, beim Join die richtige Host-IP mit der
Bildschirmtastatur eingeben und beide **Check connection** ausloesen. Erst wenn
Build, Compiler, ISO und UDP bestanden haben, wird **Start game** angeboten.
Ein Timeout bedeutet zuerst IP, Firewall und Route pruefen; ein TCP-Test
beweist keine UDP-Erreichbarkeit. Nach Spielende **Collect logs** waehlen und
das ZIP am angezeigten Dateipfad im Explorer suchen. Die Sammlung erfolgt lokal;
vor privater Weitergabe den Inhalt pruefen.

## Controller walk

1. Select T4, then Online with LB/RB. One player chooses **Host** (P1); the
   other chooses **Join** (P2).
2. The joining player enters the host's IPv4 address using the **on-screen
   keyboard**. Use the host's VPN address when both PCs use the same VPN.
   The default UDP port is 7400. Arrange the address with the other player
   outside the launcher; direct IP has no player directory (the lobby has one).
3. Both players select **Check connection**. The check waits up to 90 seconds
   for the peer. It compares the build identity, compiler/MSVC version and ISO
   SHA-256 hash, then checks two-way UDP reachability. Each check explains its
   status in the selected language. A missing identity, mismatch, invalid ISO
   or unreachable peer prevents Start game. Back cancels a pending check.
4. After all checks pass, each player selects **Start game**. This is a separate
   action; a successful check never launches T4 by itself. Choose characters
   and stage in T4's normal menus. This beta does not promise direct entry into
   a fight, trusted match results or persistent sessions with new opponents.
   **T4 Online lobby** at the end of the list switches to the lobby screen.
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
For the lobby, both PCs log in to the real T4 server, see each other, chat, play one
quick match and one accepted challenge, and report results; one PC behind a router
without port forwarding.

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

Apart from the one-PC lobby check above, the launcher window, a game, a build and
real networking were not started for this source review. Runtime compatibility and the two-PC result remain release
acceptance work; see [T4_FIRST_RUN.md](T4_FIRST_RUN.md) and
[PACKAGING.md](PACKAGING.md) for the other gates.
