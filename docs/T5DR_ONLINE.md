# T5DR online in OpenRecomp

The Online section uses the player's installed T5DR lobby client at run time.
Login, casual and ranked search, lobby players, challenges, rooms, chat, and
friends are controller actions. New fields use the controller keyboard, including
case-sensitive passwords, room passwords, invite codes, and friend names.
Optional friends and private-room controls stay hidden when the installed client
and server do not advertise those capabilities; friends also require an account.

A found match has an explicit ready check. The installed client's match driver
owns game handover, game status, result-file handling, relay fallback, and rematch
handover. OpenRecomp provides the launcher screen and localized status messages.
Manual result answers are available when the driver asks for them. The launcher
does not implement a second game protocol or ship a copy of the game's code.

Regression tests use fake clients, drivers, tickets, and game handles. They could
not run in this workspace because the existing virtual environment's Python
interpreter is unavailable. The required unittest suite therefore remains
unverified. These paths have not been exercised against an installed client and
a local lobby by this change. Even passing fake tests cannot prove the installed
client's timing or a real game's behavior.

## Runtime integration and coexistence

The adapter imports the installed launcher's `t5lobby` client, server resolver,
build identity helpers, and match driver, alongside its existing `core.py` game
runner. The lobby protocol remains version 1. The native launcher remains
available through **Open T5DR launcher**.

One account can be logged in once. A later login wins and the other connection
receives `kicked`. OpenRecomp displays the removal and requires a deliberate
login; it never automatically logs in again. The native source examined for
this task also suppresses automatic login after a kick. The installed version
still needs the coexistence check below.

Saved login uses the native launcher's `online.json`, including its existing
settings-directory override. Session entries are scoped to the lowercased server
field. Account login remembers a session; saved login reuses it without rotating
it. Passwords are not saved. Atomic settings writes preserve unrelated fields,
but concurrent writes by a native launcher holding an older settings copy can
still overwrite newer fields. Resolving that requires native-side coordination.

Searching, accepting a match, and starting a game must refuse when another
launcher already owns a live game. Process inspection includes a native launcher
game and a persistent game waiting between matches. An inspection failure is a
refusal, not permission to launch. Launch ownership also prevents two OpenRecomp
instances from starting the same game concurrently. A stale status file alone
does not prove a live game. An existing game owned by another launcher is never
stopped or taken over.

## Checks against an isolated local lobby

Use local test accounts and compatible builds. None of these checks was performed
by the automated tests for this change.

1. Drive login, search, ready acceptance/decline, result, rematch, and back to the
   lobby using only a controller. Check all seven languages, long names, focus
   changes after asynchronous updates, password masking, and keyboard symbols.
2. Reuse a native saved login in OpenRecomp and the reverse. Check server names,
   typed endpoints, TLS trust, expired sessions, and preserved settings. Log the
   same account into each launcher in turn; the second login must win, with no
   automatic-login loop after either receives `kicked`.
3. Pair local peers through quick match, ranked, challenges, and rooms. Check
   ready timeouts, opponent decline, cancellation, stale offers, and a lost
   request acknowledgement. Check host and join, accepted and disputed results,
   manual-result fallback, rematch acceptance/decline, and return to the lobby.
4. Create and join open, password, and invite-code rooms. Check wrong passwords,
   expired/stale codes, code display, room departure, chat, friend requests,
   online/offline friend status, match/room invitations, and invitation expiry.
   Verify older servers hide unsupported controls.
5. Check game handover in each supported native driver mode, result-file
   freshness, same-process rematches, process exit, peer quit, and connection
   failure at each stage. Duplicate delivery of a start event must not start a
   second run. Check a direct path, forced relay, and direct-to-relay fallback.
6. Check refusal while a game from either launcher is alive, including persistent
   idle. Try two OpenRecomp instances at the same time. Check process-inspection
   failure, cancellation during launch, application exit, and launch ownership
   after a crashed launcher. Do not use a real account for these checks.

Two physical PCs are still required to check real NAT/router behavior, WAN
latency, relay lifetime, game synchronization, and human play. Offscreen QML and
fake pad actions do not establish physical-controller behavior or readability
on a real display. `Nav.dry` must suppress online requests, game launch, polling,
and saved-setting writes. No real server, search, game, build, or launcher was
started while implementing this change.

## Remaining native-launcher features

This is not full native-launcher UI parity. It does not add tournament or
spectating screens; profile, history, leaderboard, and statistics screens;
account registration, password changes, or recovery management; blocking and
moderation controls; room rotation/host administration, training, or handicap
controls; side/stage/rules selection; Discord presence; or native notification
and detailed network preferences. The installed driver may support additional
match behavior internally; that does not imply a controller screen for it here.

The oldest supported native install and its required runtime APIs remain a
release decision. Missing APIs must give a localized error; use the native
launcher for capabilities that OpenRecomp does not expose.
