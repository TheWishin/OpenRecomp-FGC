# T5DR online: login and search

The adapter implements guest and existing-account login, saved login, casual
and ranked search, cancellation, and display of a found match. This is part (a),
tested with fake clients only. Ready checks, game handover, and results belong
to the next part. Use **Open T5DR launcher** for the other online features.

The Online section and its keyboard work with a controller. Passwords retain
their case and spaces and are masked on screen. Ranked search requires an
account. Connecting, searching, cancellation, kicks, and errors have persistent
status text in all seven launcher languages.

## Runtime integration and coexistence

The adapter imports the installed T5DR launcher's own `t5lobby` client, server
resolver, and build identity helpers at run time, as it already imports
`core.py`. No lobby implementation or game code is copied here. Both launchers
use the same lobby and build identity. The lobby protocol stays at version 1;
there is no server change or new protocol field.

One account can be logged in once. A later login wins and the other client
receives `kicked` with the reason “logged in from another place”. OpenRecomp
shows that state and requires a deliberate login; it never logs back in by
itself. The installed native launcher must also suppress automatic login after
that kick to avoid the two launchers repeatedly displacing each other. Its
behavior is outside this repository and has not been verified here; the manual
coexistence check below is a release requirement.

Saved login uses the native launcher's `online.json` in its user settings
directory, including its `T5_ONLINE_DIR` override. Its `sessions` entries are
keyed by the lowercased server field. Account login requests a remembered
session, and saved login reuses that session without rotating it. The
remembered session is distinct from the short-lived reconnect token.
Passwords are never saved. Writes preserve
unrelated settings and use an atomic replacement. Concurrent native launcher
writes can still replace settings from its older in-memory copy; fully
coordinating those writes would require a native launcher change.

Search must refuse while a game is running on this PC, including one started
by the native launcher and a persistent game sitting between matches. The
adapter checks its own child process and uses Windows `tasklist` to look for
any live `t5dr.exe`, including one from another install. If inspection fails,
search is refused. While searching it checks again each second and closes
the lobby connection if a game appears. A leftover game status file is not
proof that the process is alive. It does not stop or take over a game started
elsewhere.

Finding a match stops this part's flow. The safe match information remains on
screen; the adapter does not accept a ready check or start a game. A stopped
connection prevents the server from automatically requeueing this player if
the other player leaves.

## Checks against a local lobby

These are manual checks for the maintainer using an isolated local lobby and
test accounts. They have not been exercised by this change's automated tests.

1. Drive guest login, account login, server entry, and the keyboard using only
   a controller. Check mixed-case passwords, symbols, spaces, masking, and
   cancellation. Check all seven languages for clipping and clear errors.
2. Save an account login in the native launcher, then use it in OpenRecomp
   without entering the password again. Repeat in the other direction. Check
   server names, typed addresses, TLS settings, expired sessions, and preserved
   unrelated settings.
3. Log the same account into each launcher in turn. Confirm the second login
   wins, the first clearly explains the kick, and neither automatically logs
   back in after being kicked. Leave both open long enough to detect a loop.
4. Search casual and ranked with compatible local test peers, then cancel.
   Confirm guest ranked search is refused and failed requests leave a usable
   screen. Check disconnects and server/build/protocol refusal messages.
5. Test search refusal while an OpenRecomp game is running and while a game
   started by the native launcher is running, including its persistent idle
   state. Close the game and confirm search becomes available. Check process
   inspection failure as well.
6. Pair two local test clients. Confirm OpenRecomp displays the found match,
   does not send ready, launch a game, or report a result, and stays stopped
   when the opponent leaves or the ready timer expires.
7. Reopen the native launcher through the existing entry and verify its other
   features still work. Check cancellation and application exit release the
   connection without forgetting the remembered login.

Automated online coverage uses fake clients, servers and process inspection.
Most adapter tests replace the worker submitter with a synchronous helper;
the separate thread cancellation tests cover selected interleavings, not all
thread schedules or the installed client's own threads. UI tests load real QML
offscreen with fake backend state; they do not establish physical pad behavior
or visual readability on a real display. `Nav.dry` must prevent connection, search,
cancellation, polling, and saved-setting writes. No real server, search, game,
or build was exercised during implementation. The required unittest command
could not currently run because the repository virtual environment refers to
an unavailable base interpreter; rerun it after repairing that environment.

## Open questions

- What is the oldest supported native T5DR install? Missing runtime APIs must
  produce an actionable error; the native launcher remains available.
- Should later work coordinate simultaneous settings writes with the native
  launcher? This part keeps its existing file format.
- Ready-check timing, match handover, reconnect during a match, and result
  reporting remain for the next part.
