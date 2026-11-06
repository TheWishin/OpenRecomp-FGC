# Changelog

Player-facing changes of OpenRecomp-FGC. The games have their own notes (TheWishin/T5DROnline,
TheWishin/Tekken4Recomp).

## Unreleased

- **Tekken 4 key and button bindings** (needs a Tekken 4 with the pad-bindings runtime): the Pad bindings page is
  editable like T5DR's. Pick the keyboard or a controller, select an action, press the new key or button (X clears),
  presets Default and Tekken arcade 1-2-3-4. Every device can play as player 1 or 2. Without changes the game keeps its
  old layout exactly. Stop the game before editing.

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
