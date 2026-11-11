# Tekken Tag Tournament 2 (TAG2 PC) adapter

Status: **first step, released in 0.1.7.** Offline Play and the four quick settings for TAG2 PC 0.16.33; the rows that
talk to TAG2's live service (sign in, play online, Ranked) are off by default. The checks under "Before a release"
that need a real TAG2 install are still open.

TAG2 PC is frameperfectlab.com's PC port. `games/tag2.json` (manifest v2) already finds an installed TAG2 PC,
shows its updates and opens TAG2's own launcher. The adapter `openrecomp/adapters/tag2.py` adds account, team and
Ranked screens. It does this through TAG2's own launcher Core (`Tag2.Launcher.Core.dll` of the install), as
TAG2's integration notes ask: OpenRecomp-FGC keeps its screens, TAG2 keeps its account service, its game session
and its matchmaking. No TAG2 code, font, picture or binary is part of this repository.

## Where the contract comes from

The adapter was written against the *TAG2 Launcher 0.16.33 / engine package b49 integration handover* of TAG2's
developer (`README-INTEGRATION`, `LAUNCHER-API`, `BUILD-AND-VERIFY`, `tests/LaunchContract.cs`). The launcher
source in that handover is a **reconstruction from the published binaries**, not the original source text; it was
read as documentation of the Core's public methods only. Nothing from it was run, compiled or copied into this
repository, except the two notices under `licences/tag2-launcher/` (Oxanium font, Natural Earth map), which
belong to TAG2's own launcher and are kept here with their own texts for reference. OpenRecomp-FGC ships
neither that font nor that map.

## How it is built

| Part | What it does |
| --- | --- |
| `adapters/tag2.py` | `Tag2(ManifestGame)`: the rows of the Online section, offline start, settings, Ranked team. |
| `adapters/tag2_core.py` | Starts and talks to the host process; checks the Core's SHA-256 first. |
| `adapters/tag2_bridge/host.ps1` | Windows PowerShell 5.1: checks the hash again, loads the Core, compiles the bridge. |
| `adapters/tag2_bridge/Tag2Bridge.cs` | One JSON line in, one out; every step is a public method of the Core. |

- **Which Core**: only a Core whose SHA-256 is listed in `tag2_core.TRUSTED_CORES` (today: the published 0.16.33
  Core). Any other version shows "not known to this launcher yet" and everything works as with the manifest alone
  (TAG2's own launcher). The Core is loaded from a private copy under the launcher's data folder, so the install's
  file is never held open and TAG2's updater can replace it.
- **Live rows are off by default**: sign in / create account, *Play online*, the Ranked team, *Search Ranked* and
  the Ranked record appear only with `OPENRECOMP_TAG2_ONLINE=1` or `"tag2": {"online": true}` in the launcher's
  config. Without the switch the Online section is the manifest's (TAG2's own launcher) and the adapter sends no
  request to TAG2's service; Play offline, the quick settings and the no-audio warning work either way.
- **No extra tools**: Windows PowerShell and the .NET Framework compiler are part of Windows; TAG2's Core itself
  starts its update scripts the same way. Without Windows PowerShell (Linux, Steam Deck) the adapter falls back
  to the manifest behaviour.
- **Requests**: `User-Agent: OpenRecomp-FGC/<version> (tag2-pc)` on every request the Core sends (a message
  handler given to the Core's constructor); `product`, build and protocol are the Core's own values.

## What the player sees

- **Play offline** (Play section): the Core's `PlayOfflineAsync` -- its shader preparation, its arguments and
  environment. The Core's progress lines are shown as they are (English).
- **Quick settings**: skip startup intros, graphics backend, internal resolution, VSync. Read from TAG2's
  `local/launcher-settings.json`, changed through the Core (`SaveSettings` validates).
- **Online section**: sign in / create account (name and password; the password goes to the Core once over a
  pipe and is never stored, logged or put on a command line), *Play online* (`PlayAsync`), the Ranked team (two
  fighters from the fighter grid, outfits the game offered), *Search Ranked* (`PlayRankedAsync` with the team
  selector: `PreviewRankedTeamAsync` -> `RankedTeamSelection`), *Cancel Ranked request*, *Ranked record*
  (`LoadRankedProgressAsync`, only when pressed), *Use another account*.
- **TAG2 launcher**: still opens TAG2's own launcher (build, patch, update, controllers, keyboard, repair).

## Rules the adapter keeps

- **One account per player.** A new sign-in from another installation makes the service refuse the older saved
  sign-in (HTTP 401 on `session` / `profile` / `leaderboard`). The adapter then shows "sign in again" and the
  sign-in form, and sends nothing by itself: there is no retry, no timer and no background request anywhere.
- **`account.dat` stays TAG2's.** It is written and read only by the Core (Windows-user DPAPI). The adapter
  checks only whether the file exists; it never opens, copies, exports or shows it, a token or a session key.
- **The Core, the game and TAG2's launcher are unchanged.** No file of the install is modified by our code; the
  Core writes what it always writes (`local/`).
- **No second game, no interrupted match**: one request at a time; Ranked again uses the game the Core owns.
- **Nothing is invented**: no command-line switch, no setting and no Ranked state beyond the Core's.

## Tests

Run from the repository root with the repository's own `.venv` (never an installed launcher's Python):

    .venv\Scripts\python.exe -m unittest discover -s tests -p "test_tag2_*.py"

- `tests/test_tag2_adapter.py`: the adapter with a recording Core (no process, no network).
- `tests/test_tag2_bridge.py`: the real host with a **stand-in Core** (`tests/fixtures/tag2_stand_in_core.cs`, our
  own file with the Core's public names), a "service" on 127.0.0.1 in the test process and a sleeping Python as
  the "game": User-Agent, password handling, sign-in-again, offline start and stop, Ranked team hand-over,
  cancelling.
- **Launch contract**: the 96 argument / environment cases and the 540p guards of the handover's
  `tests/LaunchContract.cs`, on the bridge's `start_info` (the Core's `CreateGameStartInfo` with settings applied
  the way the adapter applies them). With the stand-in they always run. To run them against the **published
  Core**, set `OPENRECOMP_TAG2_CORE` to the `Tag2.Launcher.Core.dll` of a TAG2 PC install: an empty temporary
  root, start settings are only constructed, nothing is started.

Result on 2026-11-10 with the published 0.16.33 Core (SHA-256 `4effa189...0dbce`, copied from an updated TAG2 PC
folder into an empty temporary root): the bridge compiles against it and all 96 cases plus the 540p guards pass.

No test signs in to TAG2's service, searches a match or submits a result.

## Open

- **Start without an audio output**: TAG2's public build can end with an access violation right after start
  when Windows has no playback device. TAG2's developer is investigating; the adapter neither hides nor works
  around it. Before Play offline, Play online and Search Ranked the launcher asks Windows for the default
  playback device (`openrecomp/audio_output.py`, MMDevice API) and, only on a clear "none", shows a warning the
  player confirms ("Start anyway?"); the start then goes ahead unchanged. When Windows cannot tell, nothing is
  asked.
- **Not tried with a real TAG2 install yet**: the published Core, the real service, a real Ranked request, the
  screens with a controller. See "Before a release".
- **Outfits** are offered only after the game named them (the first Ranked request of a session); before that
  the default outfit is used. There is no team preview before the game runs.
- **The Core's own messages are English**; the launcher's rows are in seven languages.
- **A new TAG2 version** needs its Core hash added (after checking the bridge still compiles against it).
- **Build / patch / update / controllers / keyboard / leaderboard / player name change** are not in the adapter:
  TAG2's own launcher does them. Two launchers must not update or build one TAG2 folder at the same time.
- **Linux / Steam Deck**: manifest behaviour only (no Windows PowerShell under Proton).
- **Extra environment for one start** (the launcher's fullscreen-once) is not applied: the Core owns the game's
  environment.

## Before a release

1. Run the launch contract against the published Core (`OPENRECOMP_TAG2_CORE`) again for the TAG2 version of the
   release and keep the 96/96 result.
2. Live checks with the two dedicated test accounts (passwords from outside the repository, one account per
   side): sign in, sign-in-again after a second sign-in, play online, one Ranked request, the Ranked record.
3. Hand check of every row with a controller and in all seven languages; antivirus check of the PowerShell host.
4. Decide whether the bridge should be precompiled and signed instead of compiled on the player's PC (the files
   are already in `tools/package_release.py`).
5. TAG2's developer confirms the integration once more for the public release and the TAG2 version it is for.
