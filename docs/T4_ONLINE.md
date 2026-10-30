# T4 Online in OpenRecomp

T4 uses the shared launcher login and lobby flow through the player's installed
`t4lobby` package. No lobby implementation or game code is shipped here. The
runtime package must implement the protocol described by the T4 project's
`docs/LOBBY.md` and `SERVER_HANDOFF_T4.md`: protocol 1, game `t4`, default port
7791, and the T4 build identity from `t4net_build.txt`.

Day one covers casual quick match, challenges from the player list, open rooms,
and lobby chat. A found match requires an explicit acceptance. Each match starts
a new T4 process; characters and stage are chosen in the game's VS BATTLE menus.
Host is P1. When the game exits, the launcher asks for a win, loss, or no result.
These are manual reports: T4 has no game result file. Ranked and leaderboard
are unavailable.

The installed lobby client owns NAT traversal, port handover, and the relay
bridge. The launcher keeps that client alive through the match. Its public
API releases a bridge on the next match's NAT setup or when the client closes;
the launcher does not call private bridge methods after a result.

## Accounts and deployment

Use the existing T5DR account name and password. There is no separate T4
registration flow in this launcher. Passwords are cleared after submission and
never saved. Saved sessions belong to their game and server; a T5DR session or
certificate fingerprint must not be sent to a T4 endpoint.

The documented lobby protocol authenticates against the selected server. The
handoff describes separate game servers and databases, but does not specify a
shared authentication service. The server operator must arrange for the existing
account identity to be accepted by T4. The launcher cannot make independently
provisioned databases share accounts or provide an undocumented cross-server
single-sign-on exchange. Verify this before release.

T4 needs its own server configuration and certificate trust. Do not reuse T5DR's
shipped server list or certificate pin. Public password/session authentication
requires TLS; local test accounts may use an isolated local lobby under the
runtime client's existing security rules.

## Rank names

`openrecomp/data/t4_ranks.json` is the client display table. The maintainer must
fill and check rating boundaries and Tekken 8 rank names before enabling it.
Its shipped name fields are blank, so the launcher displays no rank. This is
text only and does not change the server's rating or enable ranked matches.

## Manual release checks

These checks require the maintainer's own installation. They are not performed
by automated tests, which use fake clients, tickets, processes, and logs.

Against an isolated local T4 lobby:

1. Check runtime import, T4 build identity, default port 7791, and refusal of a
   T5DR server or incompatible build. Missing client/build must give a localized
   error without starting a game.
2. Use only a controller for guest, account, saved login, cancellation, logout,
   and relogin after a kick. Verify the same existing account is accepted on
   both game services and a server never receives another server's saved token.
3. Check the player list, challenge acceptance/decline, open room creation,
   joining/leaving, and lobby chat. Check stale players/rooms and server refusals.
4. Exercise quick match through found, accept, NAT preparation, launch, game
   exit, manual result, and server confirmation. Try both host and join, each
   result answer, rejected/disputed results, and a disconnect at each stage.
5. Check cancellation and an external running game prevent an unwanted launch.
   Repeat matches to catch stale ticket, process, and log state. Ensure old log
   lines cannot report a new game as connected or playing.
6. Force relay and a silent direct path followed by relay fallback. Verify the
   game uses the punched port or the runtime client's loopback relay bridge,
   restarts with the replacement ticket, and releases owned resources on logout
   or disconnect. After a result, check the runtime client's bridge is replaced
   by the next match and cannot keep an old game process running.
7. Check all seven languages for readable status, controller focus, long player
   names, chat, and password masking. Verify no T4 ranked/leaderboard action or
   rank icon appears, and no rank text appears with the shipped blank table.

With two physical PCs:

1. Use matching T4 builds and drive quick match, challenges, and open rooms.
   Play through boot, menus, character/stage select, fight, process exit, and
   manual result agreement and disagreement.
2. Test direct LAN, real NAT/WAN, forced relay, and direct-to-relay fallback.
   Check host/join ports, bridge lifetime, connection loss, peer quit, and
   reconnecting deliberately after a kick.
3. Check rollback evidence and final synchronization on both PCs, sustained
   speed, and relay bandwidth/drop limits described in the handoff. Human play,
   real router behavior, TLS certificates, and release server provisioning need
   separate verification.
