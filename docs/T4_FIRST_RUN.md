# T4 first-run walk and release acceptance

This is a code walk, not a clean-PC acceptance result. No launcher, game, build,
server connection or screenshot was started for this task. The authorized T4
source was read to check its launcher-core contract; no game code or data was
copied. All task changes remain in the working tree.

The required `.venv\Scripts\python.exe -m unittest discover -s tests` command
cannot start because this checkout's virtual environment references an unavailable
base Python interpreter. The regression tests below have been added and reviewed,
but no passing test result is claimed. The maintainer must restore a usable Python
3.12 environment and run the full command before accepting this change.

## Walk, in player order

1. **Install the launcher.** Extract the complete player release and open
   `OpenRecomp.exe`. The starter uses its private runtime; the player should not
   install Python, Qt or developer tools. A missing runtime already gives an
   extraction instruction; an early nonzero runtime exit now gives that same
   visible recovery message instead of disappearing. The native starter and
   runtime have not been compiled or packaged here. `run.cmd` remains a developer
   checkout entry point, not the player installation procedure.

2. **First start, with no installed games.** The shipped T4 and T5DR manifests
   create shelf entries without game assets. T4 is first. Choose its folder/release
   prompt with A/Cross. Directional input, Confirm and Back operate the picker.
   XInput is standalone; a Windows joystick reader now supplies recognized Sony
   pads without requiring T5DR. Actual controller detection remains a hardware check.

3. **Add T4.** Choose the original portable release zip or its extracted folder
   in the launcher picker. No manifest editing or separate file dialog is needed.
   Zip registration runs in a worker; the shelf explains that it is adding T4 and
   that ISO selection comes next. Registration errors stay visible. A completed
   import waits safely for another game's activity to end before reloading the
   library. On success the player enters T4's Build section at the ISO choice.

4. **Choose the ISO by pad.** Select Game ISO. The picker filters `.iso` files,
   starts with an available suggested folder, and offers parent folders and drives
   so another location is reachable without typing a path. Confirm selects a file;
   Back cancels. Files remain on the player's PC. No ISO is distributed here.

5. **Check SLUS-20328.** Verification now runs off the UI thread through the
   installed core's verifier. The player can navigate while it runs; another check,
   build or library replacement cannot overlap it. Accepted input is saved only
   after successful verification and an unchanged-file check. The refusal identifies
   Tekken 4 USA, SLUS-20328, preserves the previous choice, and directs the player
   to Game ISO to try again. The refusal remains in the source detail after its
   toast expires. Acceptance focuses Build. A changed file must be checked again
   before building. The actual disc serial/content check belongs to the installed
   T4 verifier and still needs a real correct and incorrect disc test.

6. **Build.** Confirm Build game. Stage progress remains visible, duplicate work
   and source changes are blocked, and cancellation is available through Confirm
   on the build row. Completed builds reach 100 percent only when the adapter says
   the game is ready. Failures show a cause and retry action inside the launcher;
   the player need not open a log. Retry resets old progress and resumes the core's
   unfinished steps. A failed rebuild keeps its failure visible even if an older
   runtime still works. A source checkout without bundled build tools is refused
   with a Complete T4 release picker, rather than directing the player to install
   developer tools. A marker alone does not prove the actual release is complete.

7. **First play.** A successful build offers Play on the same row. Play on later
   starts also shows the return instruction. Confirm starts T4 through the existing
   core, and the launcher minimizes and stops normal navigation input. Settings
   saves and the ISO worker now serialize writes so one cannot overwrite the other.

8. **Return to the launcher.** Hold View + Menu on Xbox, or Share + Options on
   PlayStation, on one pad for two seconds. This is an explicit stop request through
   the adapter, not an in-game save/quit menu. The T4 source documents only window
   close as its native exit, so a pad return route was missing. The chord now stops
   the owned T4 game and restores its Play screen (or Online after a match stop).
   Held buttons cannot become accidental launcher commands. Short failures and late
   process/build results are polled even if they occur between running-state polls.
   A failed run remains visible with a recovery action. T5DR gameplay receives no
   new return chord.

9. **Settings.** LB/RB selects Settings; directions and Confirm cycle options.
   Changes save through the adapter. Resolution/fullscreen quick settings remain
   on Play. Quick access provides launcher language, fullscreen and motion choices.
   No configuration file editing is needed. Test persistence after checking an ISO,
   changing a setting during the check, playing, returning and restarting.

10. **Online entry.** LB/RB selects Online. T4 explains Player name, guest/account
    login and Lobby address. The on-screen keyboard has case/punctuation pages,
    delete and Done; passwords are masked. Login refuses a missing build or empty
    name locally before importing/connecting the client, with a recovery instruction.
    The installed default server or a typed server must actually work; a local
    fallback address is not a production service. Ranked remains unavailable for
    T4. T5DR's Online section now opens only its old native launcher. Its adapter,
    builds, settings and gameplay were left unchanged.

11. **Quit.** Back returns to the shelf; Back opens the safe-default quit dialog.
    Choose Yes and Confirm. Native window close uses the same navigation guard.
    An active import/check asks the player to wait; an active build focuses its
    cancellation row. Confirmation rechecks activity before exiting so no worker
    is orphaned by the normal quit flow.

12. **Update.** Quick access offers Check for launcher updates without entering a
    game. A valid offer defaults to No; Yes explicitly downloads/prepares it and
    restarts when idle. If activity begins during preparation, the launcher now
    explains what must close and retains the prepared update. Failures give a retry
    instruction. Update verification, program replacement, restart confirmation
    and rollback remain the existing signed transaction. Game data and player
    settings stay separate. Production updating is still disabled until the owner
    supplies the launcher's repository identity, channel and public verification
    keys; see [UPDATES.md](UPDATES.md).

## Clean-PC checks the owner must perform

Use a Windows 10/11 account with no Python, Qt, developer tools, game installation
or saved OpenRecomp settings. The owner first needs a complete launcher runtime and
native starter, a complete portable T4 release with its verifier/build tools/lobby
client, and configured launcher update trust plus a working T4 service default.
These are release gates, not tasks a player should repair by keyboard.

- Extract and start the real release in a writable path with spaces and non-ASCII
  characters; relocate it and start again. Exercise missing-runtime and early-crash
  messages. Verify user data stays outside replaceable program files.
- Repeat the entire numbered walk with Xbox and supported Sony USB/Bluetooth pads,
  including hotplug, two controllers, held buttons and every supported language.
  Confirm Sony names/layouts on real Windows devices; mocks cannot prove exposure
  through WinMM. Check the long translated refusal/recovery text fits the screen.
- Register both the real T4 zip and extracted folder. Try wrong/incomplete releases,
  denied access and extraction failure. During a long import, use Back and another
  shelf entry; ensure the completed import eventually reloads once activity ends.
- Select the owner's correct USA disc and an unsupported disc. Check serial/content
  refusal, missing helper, renamed/moved/changed ISO, persistent refusal and retry.
  Confirm no unsupported choice replaces a previous accepted ISO.
- Run the real portable build without system tools. Check progress during its long
  stages; force a controlled failure, cancel, retry, and inspect recovery entirely
  within the launcher. Repeat a failing rebuild with an old playable build present.
- Play and return with the chord; verify focus, fullscreen/window mode, input release
  and game saves. Test short runtime failure, normal stop and crash. Confirm ordinary
  pad input continues to reach the game and the chord is intentional.
- Change settings during ISO verification, play and return; restart and verify both
  the ISO choice and settings persist. Check native-window and pad quit during work.
- Enter name/server/password by pad; verify the shipped T4 default, TLS/account
  behavior, cancellation and logout against the owner-operated service. Matchmaking
  and actual matches remain separate owner acceptance work; none was started here.
  Confirm T5DR Online opens its old launcher and its other shelf behavior is unchanged.
- On a private signed launcher channel, test offer No/Yes, download failure/retry,
  busy waiting/restart, valid update, wrong project/channel, tampering, failed startup
  and rollback with settings preserved. Follow [PACKAGING.md](PACKAGING.md) and
  [UPDATES.md](UPDATES.md) for the release/runtime checks.

## Regression coverage and review

New first-run tests cover adapter verification/import/build outcomes and settings
interleaving, navigation handoffs and busy reload, bridge refresh and return handling,
native controller input/chord timing, update waiting and starter failure, and catalog
keys/placeholders. Existing fake-only tests were updated for the source-state interface
and preserved game-input suppression. No test replaces real disc/build/hardware/runtime
acceptance. The separate final-diff review found and prompted fixes for lost reloads,
settings races, hidden rebuild failures, scan churn and missing Play return guidance.

Sub-agents: `t4_adapter`, `pad_navigation`, `t4_online`, `install_update`,
`standalone_pads`, `first_run_text`, and independent reviewer `final_review`.
