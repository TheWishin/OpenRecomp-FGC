# T5DR 1.1.9: keep both launchers

Install OpenRecomp beside T5DR Online, in a separate folder. Keep the complete
1.1.9 installation where it is. OpenRecomp uses that install's launcher modules
and built game at run time; it does not distribute or migrate them. Choosing an
installation is not permission to copy, move, rebuild or update it.

OpenRecomp looks for `T5DR-Online-*` folders in the player's Downloads and
Desktop folders and for configured locations. An explicitly selected folder,
including `OPENRECOMP_T5DR_ROOT`, takes priority; an invalid explicit selection
does not silently switch to a different install. If a moved installation is not
found, choose its current folder with the controller folder picker. An enclosing
folder containing exactly one installation is also accepted. Do not choose the
`native`, `runtime` or settings subfolder as the installation root. A valid build
stamp is preferred over an unbuilt candidate, then the newer version. Merely
finding `runtime/t5dr.exe` does not prove that the player's game is built.

## What stays where

| Item | During the transition |
| --- | --- |
| T5DR program and built game | Used from the selected installation; no program, game data or build is copied or moved by attachment. Keep the original launcher available. |
| Launcher settings | Existing preferences supply the starting values. OpenRecomp saves its own changes separately; it does not rewrite the old launcher's settings file. Unknown source fields remain intact. |
| Saved login | Reading a saved-login indicator makes no connection. Use saved login explicitly resumes an existing token without asking for a newly remembered login. Only a login OpenRecomp saved in its private file logs in by itself (once, when Online is first shown); the native launcher's token never does (that would push the native launcher out). New password logins save only in OpenRecomp's private file. Bad borrowed tokens are suppressed for this session without deleting the old file. Tokens and passwords never appear in the public view or drill report. Account actions still affect the server account. |
| Replays | Browsing uses the selected replay folder, including a custom folder. No recordings are copied or moved. A server history row cannot restore a missing recording. |
| Controls | Existing bindings supply the starting controls. An accepted edit saves complete controls in OpenRecomp's private file; cancelling an edit does not save. The game receives that file through `PS3_CONTROLS`. The old launcher's bindings stay available. |
| OpenRecomp settings and artwork cache | Belong to `OPENRECOMP_HOME`, normally `%LOCALAPPDATA%\OpenRecomp`. Keep that directory outside both program installations. |

Changes made in one launcher's preferences do not automatically become edits in
the other launcher. Keep both launchers closed while changing an installation or
running an updater. Do not run two game sessions against the same installation.
The old launcher's native utilities remain available from that launcher.

The separate preference files live under
`OPENRECOMP_HOME/t5dr/<installation-id>/`; the installation ID is derived from the
selected root so different installs do not share overrides. OpenRecomp suppresses
the native settings constructor's `save()` and saves private preference edits
through its own persistence path. Unobserved direct writes by a native settings
constructor remain part of the real 1.1.9 verification below. Gameplay itself uses
the native runtime and can write saves, recordings and other runtime output to
its existing output folder. The real runtime's launch-time writes and control
override behavior still need the manual checks below; fake tests cannot prove
that every installed runtime routine leaves every original file unchanged.
Likewise, a lobby server may rotate or invalidate tokens independently of local
file preservation. Verify that returning to the original saved login works
against the real server before recommending the transition to players.

## One build rule for both launchers

Launcher version numbers are not game compatibility identifiers. A newer
launcher can still use the same game build. The T5DR updater compares the offered
release's Code ID with the `code_id` in the actual
`<out_dir>/build/t5dr_build.json` build stamp. OpenRecomp delegates current game
readiness to the selected installation's `core.game_state`.

| Evidence | What the player sees |
| --- | --- |
| Required Code ID and built Code ID match, and the installed core says the game is ready | Ready / Play. A launcher-only update does not require a rebuild. |
| Both Code IDs are known and differ | Build again. The old launcher's Play page says "Build the game once (about 2 minutes)" and offers BUILD GAME. OpenRecomp reports that the game needs rebuilding rather than treating its own launcher version as the game version. |
| A Code ID or build stamp is missing or unreadable | Compatibility is unknown; do not claim that the builds match. OpenRecomp marks an otherwise built game Not ready and blocks Play until compatibility can be established. An absent build still shows the installed core's missing-build state. |

## Building a folder from the T5DR launcher

A folder the T5DR launcher set up (it has no OpenRecomp install marker) can be built from OpenRecomp too, and **both
launchers keep working on it afterwards**. Nothing the T5DR launcher relies on is changed: not its `launcher.json`, not
`release.json`, not its Python, tools or `native` layout. OpenRecomp builds with that folder's own Python and writes
exactly what the T5DR launcher's BUILD GAME writes (the output folder, normally `native`). The package and licence you
choose in OpenRecomp stay in OpenRecomp's own home, like every other setting; the T5DR launcher keeps its own choices.
Saves, replays, settings and `native\logs` are never touched.

* The first time you press Build on such a folder OpenRecomp tells you once: "This T5DR folder was set up by the T5DR
  launcher. OpenRecomp can build it, and the T5DR launcher keeps working with it too." Yes builds, No does nothing and
  asks again next time. The answer is remembered per folder in OpenRecomp's own config, not in the folder.
* **One build at a time.** While OpenRecomp builds it keeps `openrecomp-build.lock` in the folder (removed when the build
  ends, is cancelled or fails). Another OpenRecomp window refuses to build there ("OpenRecomp is already building in this
  folder"). OpenRecomp also refuses while the T5DR launcher is building: its `build.log` is being written and has no
  exit-code line yet. The T5DR launcher itself does not look for OpenRecomp's lock, so do not press its BUILD GAME while
  OpenRecomp builds.
* A folder path past Windows' 260 characters breaks the game's Python (WinError 206). OpenRecomp then says the folder path
  is too long and to move the game to a shorter path like `C:\Games\T5DR`, instead of asking you to reinstall.
* `tests/test_t5_folder_takeover.py` checks that a build leaves the folder as the T5DR launcher would after its own build
  and that the launcher's own checks still accept it. Set `OPENRECOMP_TEST_T5DR_ROOT` to an install to also run that
  launcher's real `core.py` checks (read only).

An install OpenRecomp downloaded itself (it has the marker) is OpenRecomp's own and was always buildable. Changing the
game build of a folder both launchers use still means the T5DR launcher's Play page sees the new build the next time it
looks, which is the point.

## Private update drill

Use a real settings-folder **copy** from a closed 1.1.9 installation. Make that
copy yourself in a private directory outside this checkout, outside both program
installations and outside the intended drill work directory. It may contain
saved-login tokens and personal paths. Never add it, reports containing its
contents, game data or recordings to this public repository.

The offline `tools/update_drill.py` tool checks preservation and coexistence with
an explicitly supplied copy. It does not start a launcher, game, build, updater
helper or network request. Run it with the repository's Python:

```text
.venv\Scripts\python.exe tools\update_drill.py --old-install <1.1.9-install> --settings-copy <private-settings-copy> --work <empty-private-work>
```

Use `--expect rollback` with a fresh, empty private work directory to exercise
the setup-rollback case. The tool accepts only a 1.1.9 (or v1.1.9) installation.
It creates `work/home/config.json` with the selected root and
`t5dr_settings_copy`, which tells OpenRecomp to read the supplied private copy.
It validates top-level `launcher.json`, `online.json` and `controls.json` as JSON
objects; it does not copy those files again. Other entries are counted and left
alone without traversal; links and junctions are refused.

The drill exercises the real OpenRecomp settings helper with an inert Settings
facade instead of importing the native runtime. It checks that every supplied
launcher setting is retained, that the supplied online/controls paths are used,
and that attachment creates no private settings file. It then saves and reloads
a synthetic explicit edit in its private home, removes that probe and checks
that the original copied values return. The synthetic edit is never left in the
retained setup. These checks exercise private persistence and edit rollback;
they do not exercise the native Settings constructor or a real login.

It compares the selected original metadata/settings and allowlisted copy files
before and after. Its report contains counts, booleans and fixed result labels,
without credentials, setting values, hashes or personal paths. The flags
`inert_settings_facade`, `private_write_checked` and
`private_edit_rollback_checked` describe those headless checks.

Rollback removes only the generated drill configuration and empty home, leaving
the private settings copy, original installation and report in place. Retain
the private source copy until the manual checks below are complete. A PASS from
this headless tool establishes the checks it reports; it does not establish that
a packaged launcher survives an actual update, the whole installation is
unchanged, or a real saved login still works.

For a later manual session, point `OPENRECOMP_HOME` at the retained
`<private-work>/home` before starting the packaged launcher yourself. That uses
the explicit settings copy instead of the live original settings. Close it and
restore your normal `OPENRECOMP_HOME` afterwards. A rollback drill removes its
generated home and therefore cannot be used as that manual-session home.

OpenRecomp's signed program updater is separate from the T5DR updater. A T5DR
release is never an OpenRecomp update. Neither updater should migrate the other
launcher's program or settings. See [Signed launcher updates](UPDATES.md) for
program transaction verification, confirmation and failure recovery.

## Rollback and real 1.1.9 acceptance

To return to 1.1.9, close OpenRecomp and start the original T5DR Online launcher
from its unchanged installation. Do not copy OpenRecomp preferences over the old
settings. OpenRecomp's own preferences can be retained for a later retry. Server
account changes, such as changing a password, are not undone by switching
launchers. A signed OpenRecomp program update has its own program-file rollback;
that transaction is distinct from returning to the old T5DR launcher.

A person must still try the following with a private real 1.1.9 installation:

1. With both launchers closed, keep a private backup and hashes of the original
   settings, saved login, custom controls and representative replay files. Record
   the build Code ID and custom output/replay folders privately.
2. Attach OpenRecomp using the controller alone. Check the selected installation,
   settings, replay list and controls before making an edit or logging in. Check
   the old files' hashes again. No automatic migration should have occurred.
3. Check non-default settings, an existing saved login and custom bindings.
   Exercise cancel and explicit save separately. Close OpenRecomp, return to
   1.1.9 and confirm that its preferences, login and bindings still work. Verify
   actual token-rotation behavior with the real lobby server.
4. Play the existing build offline, browse and play a representative old replay,
   and verify new recording and custom replay-folder behavior. Check the original
   launcher again. Do not rebuild or update the shared build during this test.
5. Try matching, changed and missing Code IDs on a separate disposable install.
   Check the Ready / Build again / unknown explanations and blocked actions.
   With two PCs, verify the installed lobby's mixed-launcher build checks.
6. On a disposable packaged OpenRecomp installation, try a valid signed update,
   settings preservation, a new launcher that exits before confirmation, and
   rollback. Confirm the original T5DR launcher still works afterwards.
7. Review controller focus and all new messages in English, German, Spanish,
   French, Japanese, Korean and Brazilian Portuguese. Unit tests do not establish
   physical-pad operation, readable layout or native-speaker wording quality.

Automated tests use fakes and inert temporary files. No real 1.1.9 installation,
saved-login server, game, build, launcher window or packaged update was exercised
as part of implementing this path.
