# Changelog

Player-facing changes of OpenRecomp-FGC. The games have their own notes (TheWishin/T5DROnline,
TheWishin/Tekken4Recomp).

## v0.1.8

0.1.7 was never released on its own: **this release includes everything planned for 0.1.7** (the section below),
among it the Tekken 5 Pad bindings fix (L1, R2 and every later binding are saved again), the progress bar in the top
bar for builds and updates, Tekken 4's "Delay intro sound" setting (default Off) and the first step for Tekken Tag
Tournament 2 (offline Play; its online rows are off).

- **Tekken 4: the rematch question in the game is on by default.** After a casual online match the game itself asks
  "Rematch?" (Cross = yes, Circle = no); when both say yes the next match plays on in the running game, without a
  new start. It appears online only when the lobby server offers it -- the Tekken 4 lobby does not have it yet, so
  until the server is updated nothing changes. Both players need Tekken 4 0.1.5-beta. With an older game, server or
  opponent everything is as before; `T4_INGAME_REMATCH=0` turns it off.
- **Tekken 5 DR on processors without SSE4.1** (T5DR Online 1.2.3 and newer ship a second, slower build for them):
  Build game picks it by itself, the same way T5DR's own launcher does (it is the T5DR install's own check: Windows
  first, then the processor itself through the bundled compiler, because Windows 10 before 2004 always answers "no").
  When a build has the other version, the Play page says so and Build again makes the right one. Check my problem
  shows "No SSE4.1: the game uses its slower build" with the speed to expect; with an older T5DR install it now says
  the processor is too old instead of "another issue".
- Fixed for testers: a test run of the launcher could list a real Tekken 4 folder beside the program as one of its
  installs (nothing was removed; players were never affected).

### Known issues

- **Tekken 4: the intro's sound and picture are not in sync** (the music starts about 2 seconds before the first
  scene). Settings > Tekken 4 > Delay intro sound: 1770 holds the sound until the first scene.
- **Tekken 4 HON-MARU stage:** not yet confirmed by a player.
- The known issues of 0.1.7 below still apply.

## v0.1.7

Never released on its own: everything in this section is part of 0.1.8.

A calmer look, one set of settings and one controls file shared with Tekken 5 DR's own launcher, a ranked costume
choice, and fixes for stuck builds and cut-off updates. The ranked costume needs T5DR Online 1.2.3 or newer.

- **A calmer launcher by default.** Settings > Video > Interface colours: **Calm** (default) uses neutral greys for
  every game and the game's colour only as the accent (focus, active tab, the main action); **Vivid** is the 0.1.6
  palette. The Online page has 7 sections instead of 9 (Statistics opens on "Leaderboard & stats", account tools
  on "Profile & account"). A settings tab with only one or two rows joins the tab before it.
- **Tekken 5 DR ranked: pick the costume of your fighter.** In the fighter grid the focused fighter shows its ranked
  costume; X (or a click) shows the next one. It is remembered per fighter (the same choice T5DR's own launcher
  keeps) and sent with the ranked search. Needs T5DR Online 1.2.3 or newer and the new lobby server; fighters with
  one costume, Random and older installs show no choice.
- **Tekken 5 DR in-game rematch:** for installs that have it (T5DR 1.2.0 and newer) the rematch question in the game is
  announced by default, as in T5DR Online's own launcher; `T5_INGAME_REMATCH=0` turns it off.
- **Tekken 5 DR opens on the monitor the launcher is on**, as T5DR's own launcher does.
- **Tekken 4 starts with the settings its own launcher gives:** Low keeps anti-aliasing off and no anisotropic
  filtering, and a 16:9 choice made in T4's launcher counts here (and the other way round).
- **A game starts with the environment its own launcher gives it:** the launcher's interface style no longer leaks
  into the games.
- **The build check is steadier.** Only a real build process blocks a build (a cut-off `build.log` no longer does),
  and **Build anyway** (with a confirmation) is offered while T5DR's launcher looks busy. Long command lines no
  longer make the process check answer "could not look".
- Every Tekken 5 DR game start writes one line to the install's launcher log (process, log file, settings given;
  user names and paths masked). Rank plates and fighter pictures are decoded in a short helper process, only while no
  game or online match runs. The "Free items offline" hint says it unlocks the greyed-out customization items.

- **A running build or update stays in the top bar.** On every screen the top bar shows the step, the
  percentage and the time left of the build, install or update that runs. A click (F7; on a pad: Quick access >
  Show progress) opens its card. The bar goes when the job ends.
- **Tekken 5 DR: one set of settings for both launchers.** What you set in OpenRecomp (display, resolution, graphics, input delay, training, sounds, replays, name ...) is what T5DR's own launcher shows, and the other way round, like the controls since 0.1.7. Nothing to do: your existing settings are taken over at the first start (where both launchers had a different value, the one saved last wins; the old files are kept as backups in `%APPDATA%\T5DROnline\settings-backup`). Package, licence and language stay per launcher. Details: docs/SETTINGS_SYNC.md.
- **New: `--offline` starts the game at once.** `OpenRecomp.exe --offline` (or `--offline t5dr` / `--offline t4`)
  starts the game offline in fullscreen without the main menu or the Online page: for a desktop shortcut or Steam's
  launch options, and for playing with a controller only.
- **Fixed: Tekken 4's Build could stay at "Checking the build tools" for ever.** A tool on the PC that did not answer
  (a PATH shim whose helper kept running) held the check, and with it the build. Each tool now gets 8 seconds.
- **A cut-off launcher update no longer blocks later updates.** When the PC was switched off or the update helper was
  killed mid-way, every later update was refused ("another update owns this installation"). The next start now sees
  that the helper is gone; files that were half exchanged are put back before the next update.
- **A cut-off game install cleans up after itself:** the work folder of an install whose launcher is gone (download and
  half unpacked game, several GB) is removed at the next install instead of staying for good.
- The "another OpenRecomp is building here" lock is only believed while that very launcher process lives (not when
  Windows gave its process number to another program after a restart).
- **Fixed: Tekken 5 Pad bindings gave errors on L1, R2 and every second binding.** Only the first binding of a session
  was saved; the next one failed with "changed on disk". Fixed.
- **One controls.ini for Tekken 5 DR:** a binding saved here or in T5DR Online's own launcher is the one the game uses
  and the one the other shows. Saves are atomic and retried while the game or an antivirus holds the file. Controls
  OpenRecomp kept of its own before are moved in once and backed up; nothing is lost.
- A PlayStation pad's trigger resting position is no longer taken for a press while binding.
- **PlayStation pads read directly (DualShock 4, DualSense, Edge):** Tekken 4's Pad bindings page now sees them like the
  game does (XInput slots 5-8, USB and Bluetooth, also the extended Bluetooth report Steam/DS4Windows switch them to),
  and the launcher can be navigated with them without a T5DR install. Read-only, shared with the game, only while the
  page is open; a pad Steam Input hands on as an Xbox pad is left to Steam.
- **Tekken 4: Delay intro sound (ms).** Settings > Tekken 4: **Off** (default) or **1770**. The intro movie's music
  starts over 1.77 s of black before the first picture; 1770 starts the sound with the picture. Only a value other
  than 0 is given to the game (`TEKKEN4_MOVIE_AUDIO_DELAY_MS`); needs a Tekken 4 build that knows the switch
  (Tekken 4 0.1.5-beta).
- **Tekken Tag Tournament 2 (TAG2 PC), first step.** When a TAG2 PC install of the published version 0.16.33 is
  found, Play starts it offline directly and four quick settings (skip intros, graphics backend, internal
  resolution, VSync) can be changed here. Any other TAG2 version works as before: through TAG2's own launcher.
  Sign-in, online play and Ranked stay in TAG2's own launcher (the rows for them exist but are switched off), and so
  do updates, build, repair and controller setup. Before a start without an audio output the launcher warns: TAG2
  can close with an error right after start when Windows has no speakers or headphones. Details: docs/TAG2.md.

### Known issues

- **Pads are not tried on real hardware yet.** The PlayStation pad reader (DualShock 4, DualSense, Edge) and the
  Tekken 5 and Tekken 4 Pad bindings pages are tested with stand-ins only.
- **Tekken 4 online through the launcher needs a T4 lobby server.** Without one, use the direct connection under
  Settings > Advanced. Direct entry into a fight and the game's fighter and stage choice are not verified against a
  real Tekken 4 build.
- **The Tekken 5 DR in-game rematch has not had its two-PC test yet.**
- **The pad binding fix was tested with simulated pads only,** not yet with a real controller or from a packaged
  build.
- **TAG2:** sign-in, online play and Ranked were never tried against TAG2's live service and are off; nothing of the
  TAG2 part was tried with a real TAG2 install yet.
- **Tekken 5 DR quick-match button bindings:** the fix was not ready for this version.

## v0.1.6

- **Fixed: the launcher could not update itself** ("The update could not be completed. Nothing was installed.").
  Launchers 0.1.4 and 0.1.5 downloaded and checked the new version, then failed at the last check because the verified
  download was kept under another name. Players on 0.1.4 or 0.1.5 install 0.1.6 once by hand (Setup or zip from the
  release page); from 0.1.6 on, updates from inside the launcher work again. Settings, games and saves stay.

## v0.1.5

Updates you can hide, and button bindings like in Tekken 8.

- **Updates run in the background.** The progress window blocks the page behind it; Hide (the default) closes it and the
  update keeps going. A small card at the bottom right shows every running install or update -- both games at once --
  with step, %, MB and time left; click it, press F7 or use Quick access > Show progress to open it again. Cancel is
  only offered while it is safe (download, check, unpack); once files are being replaced it says "Installing, please
  wait". While a game updates, its Play, Build and Online say "Update running".
- **Tekken 4 Pad bindings like Tekken 8:** one row per action -- 1 2 3 4, then the combos, Start, Select, shoulder
  buttons, movement -- with the assigned button shown as its symbol (Xbox or PlayStation, following Settings > Button
  prompts; keys as key caps), tabs per player, Reset to default and a live strip of what your buttons trigger.
- **Combos:** 1+2, 3+4, 1+3, 2+4, 1+4, 2+3, 1+2+3, 1+3+4, 2+3+4, 1+2+4 and 1+2+3+4 on one button, for pad and keyboard,
  plus the preset "Tekken arcade with combos". Combos written by hand in controls.ini show up and are kept.
- **Fixed:** a second binding was not saved while the game or an antivirus held controls.ini; the bottom bar of a
  progress window showed an old prompt; PlayStation symbols were drawn as boxes on some PCs.

## v0.1.4

Made so that Tekken 4 needs nothing from the internet and an update never ends in "damaged zip".

- **Tekken 4 0.1.4 downloads nothing.** Its game program comes ready-made; Build only translates the code from your own
  ISO with the compiler in the zip (about 2 minutes the first time, a few seconds when nothing changed). No Microsoft
  files, no licence screen, no Visual Studio, Git or internet. Every PC gets the same build.
- **Update all:** a game release names the launcher it needs. An older launcher says so ("This Tekken 4 needs
  OpenRecomp-FGC X -- update the launcher first") and Update all updates the launcher, restarts it and then updates
  the game by itself -- also when the needed launcher is still a test version (pre-release).
- **"The launcher is up to date"** now also names a newer test version when there is one; Confirm installs it.
- **Progress for game installs and updates:** MB, percent, speed and time left for each step (download, check, unpack).
- **Language in Settings** (it was only in Quick access).
- Being logged in to a lobby no longer blocks installs and updates (only a search, match or game start does).
- A game folder without a version reads "own version" instead of "?".
- The zips have one file to start at the top: `Start OpenRecomp-FGC.cmd`; START_HERE / START_HIER rewritten for
  players (no more "install Visual Studio"). The Tekken 4 zip no longer carries the old standalone Tekken4.cmd.

## v0.1.3

Made so that every player gets the same Tekken 4 build and the launcher always runs the folder you chose.

- **Tekken 4 0.1.3 brings its own compiler.** The T4 release now carries clang-cl, lld-link, CMake, Ninja and Python;
  Build never uses a Visual Studio (2022, 2026 or none) or Git installed on the PC. The first Build downloads
  Microsoft's C++ headers and libraries once, straight from Microsoft with fixed checksums (the Build card names the
  licence). Two players on 0.1.3 now always get the same build id, whatever Microsoft tools their PCs have. Everybody
  builds once more after updating (the new compiler is a new build).
- **One Tekken 4 folder for everything.** Play, Build, Online, Direct IP and the logs use the folder you chose, and the
  Play and Build pages show it with its version. When that folder is gone or is not a Tekken 4 install the page says
  so instead of quietly using another one (an older copy, a developer folder).
- **Why can't I play him?** In the T4 lobby a player whose build differs shows the reason: another Tekken 4 version
  (both numbers), or the same version with other game files / another compiler. Direct IP names the same reasons.
- **Choose and switch installs at any time**: the Build page lists the Tekken 4 folder in use; pick another install's
  folder (or a release zip) to use that one. Installing asks where first and warns about long folder paths (over 60
  characters; over 120 is refused: choose something like C:\Games).
- **Uninstall OpenRecomp completely** (Settings > Advanced): shows the list first -- the game folders the launcher
  installed, its data folder, the launcher with its shortcuts and Windows Apps entry -- then removes them, keeping
  saves and replays if you want (moved to an OpenRecomp-kept folder). Your ISO, .pkg and .rap are never removed, nor
  folders the launcher did not create.
- The T4 online identity uses the game files from your ISO (SLUS_203.28, DATA.BIN, IRX) instead of the whole ISO file:
  two clean rips of the same disc can play each other.
- **Faster Tekken 4 builds, Microsoft's files once per PC.** They are kept in one shared folder for every Tekken 4 install
  and update (no second download after an update or reinstall), checked once; a rebuild with nothing changed takes
  about 2 seconds (was 40), the first build shows the download in % and MB. Visual Studio on a developer's PC (2022,
  2026, a developer prompt) can no longer change the compiled game.
- **Pad bindings for Tekken 5 are back** with T5DR 1.2.1: its controller editor needs no Tk any more (the entry was
  missing on a fresh install). Tekken 4 gets a Pad bindings page too, showing its fixed buttons for keyboard and
  controller (they cannot be changed yet).
- **Several installs:** the Build page lists the installs of a game this launcher knows and switches between them; the
  Tekken 5 page shows its folder like Tekken 4's; an update notice names the folder it updates.

## v0.1.2

v0.1.1 was an earlier pre-release; v0.1.2 contains everything planned for it.

- **Full Setup**: `OpenRecomp-FGC-Full-Setup-0.1.2.exe` installs the launcher together with Tekken 5 DR Online 1.2.1
  and Tekken 4 0.1.2 (beta) in one go (a checkbox per game, both on). The games are the published, signed release
  files, checked exactly like an install from inside the launcher. The small Setup and the zip stay as before.
- **T5DR lobby address**: on a new PC the Lobby field already names the T5DR Online server; an empty field means the
  same server. A server that cannot be reached now says "Lobby not reachable" instead of a general error.
- **One launcher online at a time**: when T5DR's own launcher or another OpenRecomp window is open, OpenRecomp says so
  and does not log in by itself against it (no more logging each other out). "Use OpenRecomp here" logs in with this
  launcher's remembered login.
- Adding or removing a game keeps the other games logged in.
- **OpenRecomp-FGC Discord** button in the top bar and in Quick access. T5DR's Problem report page gets
  "Send to the developer" (one press) as soon as the lobby server supports it.
- Tekken 4 gets **Problem report** too: send cleaned diagnostics to the T4 developer with one press, or save a ZIP
  locally. Older servers offer Save only. Game files and memory cards are never included.
- Quick access > Test versions re-checks the games right away.
- A slow first start of T5DR's own Python (antivirus scan, busy PC) no longer reads as "install damaged": the check gets
  one longer try before it asks you to reinstall.
- Linux / Steam Deck (Proton, Wine): Tekken 4's Build says why it cannot run there (it needs Windows PowerShell)
  instead of failing silently; Japanese and Korean text uses Linux fonts when Windows' are missing.
- **A T5DR folder set up by T5DR's own launcher can be built from OpenRecomp** (it was "playable, cannot be built"). You
  get a one-time notice, then the build runs with the folder's own Python. The T5DR launcher keeps working on the same
  folder: its settings, `release.json` and layout are not changed, and only one launcher builds at a time (a lock file
  in the folder; each refuses while the other builds). Saves and settings stay.
- A game folder whose path is too long for Windows (WinError 206) now says "move the game to a shorter path like
  C:\Games\T5DR" instead of asking you to reinstall.
- Games can be described in one JSON file (`docs/ADD_A_GAME.md`): start, stop, settings, picture and a signed update
  check. A Tekken Tag Tournament 2 (TAG2 PC) folder on this PC shows its own tile.

## v0.1.0

First release: one launcher for Tekken 4 (USA) and Tekken 5 DR Online (USA), with installs and signed updates of the
launcher and both games, online pages, staying logged in, the Build page with automatic build tools, seven languages.
