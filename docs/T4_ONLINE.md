# T4 Online in OpenRecomp

T4 uses the shared login and lobby screens through the player's installed
`t4lobby` package. Game handover delegates ticket conversion to that install's
`t4lobby.t4game.game_env`; a missing or foreign helper is refused. No lobby
implementation or game code is shipped here. The clean T4 source supplied for
this task documents this private package but does not contain it, so the actual
helper and client API remain unverified against an installation.

The runtime package must implement the protocol described by T4's `docs/LOBBY.md`
and `SERVER_HANDOFF_T4.md`: protocol 1, game `t4`, default port 7791, and T4 build
identity from `t4net_build.txt`. A T5DR server, build identity, or certificate pin
must not be used for T4.

## Day-one flow

The controller can log in, start casual quick match, challenge a player from the
lobby list, accept or decline challenges, create/join/leave open rooms, and read
or send lobby chat. Accounts are optional when the server supports them. Ranked,
leaderboards, private/password/code rooms, friends and invitations, tournaments,
spectating, regional relay selection, Discord presence, and extra match-rule
controls stay hidden, as required by the day-one handoff.

A found match requires explicit ready acceptance. While waiting, the launcher
shows that it is waiting for the peer and whether a direct connection or the main
server's relay is being prepared. Each match starts a new T4 process; characters
and stage are chosen in the game's VS BATTLE menus, with the host as P1. The
installed client owns NAT traversal, port handover, and the relay bridge and stays
alive through the match. A direct-to-relay fallback stops the old owned process
before a replacement ticket starts another one. Duplicate start delivery must
not start a second run.

The launcher follows only the new run's connection and frame evidence. When the
game exits, it asks for win, loss, or no result and shows the server's confirmation,
dispute, or void response. T4 has no game result file: these remain manual reports.
Peer quit, lost connection, incompatible build, ready timeout, and relay/UDP
failures have catalog messages. Return to the lobby is available after the result.
T4 rematch inside a running game remains outside day-one scope.

Searching, ready acceptance, and launching refuse while another launcher has a
live T4 game. The installed core's run lock and process inspection are retained;
OpenRecomp also reserves launch ownership until its child exits. Unknown process
state is a refusal. An external game is never taken over or stopped.

The client's public API replaces its bridge at the next match's NAT setup or
releases it when the client closes. OpenRecomp does not invoke private bridge
methods after reporting a result.

## Accounts and deployment

Use the existing T5DR account name and password. There is no separate T4
registration flow in this launcher. Passwords are cleared after submission and
never saved. Saved sessions are scoped to their game and server; a T5DR session
or certificate fingerprint must not be sent to T4. A later login can displace an
earlier connection; a `kicked` state requires deliberate login and never triggers
automatic login.

The handoff describes separate game servers and databases, without a shared
authentication service. The operator must arrange for the existing account
identity to be accepted by T4; OpenRecomp cannot make independent databases share
accounts or invent a cross-server sign-on exchange. T4 needs its own server
configuration and certificate trust. Public password/session authentication
requires TLS under the installed client's existing security rules.

`openrecomp/data/t4_ranks.json` is a display-only table. The maintainer must check
its rating boundaries and rank names before enabling them. The shipped names
are blank, so no rank text appears; the table does not enable ranked matches.

## Manual release checks

Regression tests use fake clients, tickets, processes, logs, and pad actions.
They could not run because the workspace's existing virtual environment cannot
start its Python interpreter; the required unittest suite remains unverified.
Even passing fake tests cannot establish the installed client's signatures,
event order, timing, or real relay lifecycle. No launcher,
real server, search, game, or build was started for this change. `Nav.dry` must
suppress online actions, polling, saved-setting writes, and game launch.

Against an isolated local T4 lobby:

1. Check same-install imports, the `t4game.game_env` helper, T4 build identity,
   default port 7791, and refusal of a T5DR server or incompatible build. Missing
   client/build/helper must give a localized error and leave no game running.
2. Use only a controller for guest, account, saved login, cancellation, logout,
   ready acceptance/decline, result answers, and return to the lobby. Check all
   seven languages, readable messages, focus changes, masking, and long chat.
3. Check the player list, challenge acceptance/decline, open room creation,
   joining/leaving, and chat. Check stale targets and server refusal. Verify all
   features excluded from the day-one scope remain hidden.
4. Exercise quick match through found, accept, peer-ready wait, connection
   preparation, launch, process exit, manual report, and server confirmation.
   Try host and join, each result answer, disputed results, ready timeouts, peer
   quit, and disconnection at every stage.
5. Check cancellation during launch, duplicate start events, an already running
   game in either launcher, two OpenRecomp instances, unknown process inspection,
   and ownership after process exit. Repeat matches to expose stale tickets or
   log evidence; old lines must not describe the new game as connected/playing.
6. Force relay and a silent direct path followed by relay fallback. Check the
   punched port or loopback bridge, old-process exit before replacement launch,
   and resource release on logout/disconnect. After a result, check the next
   match replaces the old bridge without leaving an old game process alive.
7. Check the existing account is accepted on both services, saved tokens stay
   scoped to their server, and alternating logins do not cause an automatic-login
   loop after a kick.

Two physical PCs are still required for real NAT/WAN/relay behavior, human play,
rollback synchronization, sustained game speed, and the relay bandwidth limits
in the handoff. The handoff also leaves direct fight, persistent game mode,
in-session rematch, game-side results, ranked, release server provisioning, and
steady 60 fps as separate work. Offscreen QML and fake inputs cannot prove
physical-controller behavior or visual readability on a real display.
