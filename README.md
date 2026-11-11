<picture>
  <source media="(prefers-color-scheme: dark)" srcset="openrecomp/ui/assets/logo-wordmark.svg">
  <img alt="OpenRecomp-FGC" src="openrecomp/ui/assets/logo-wordmark-light.svg" height="72">
</picture>

# OpenRecomp-FGC

**Launcher for all your Recomps.** One fullscreen launcher for native PC ports of console games, made to be used from
the couch: designed for controller use, with mouse and keyboard support too. Physical-pad acceptance is still required. Button prompts follow the device you
used last.

**Release 0.1.7.** Download `OpenRecomp-v0.1.7.zip` or `OpenRecomp-FGC-Setup-0.1.7.exe` from
https://github.com/TheWishin/OpenRecomp-FGC/releases. What is new: [CHANGELOG.md](CHANGELOG.md).

> OpenRecomp-FGC contains **no game data**: no ISO, no packages, no keys, no BIOS, no translated game code, no game art.
> You build each game from your own copy. Pictures on the launcher are read from your own build and stay on your PC.

## Status

Release 0.1.7. The launcher runs Tekken 5: Dark Resurrection (through an installed T5DR Online) and Tekken 4 (USA)
and has a free slot for more. Online opens the same login and lobby screens as T5DR:
guest or account login, player list, rooms, chat, quick match and challenges through a T4
lobby server (Tekken 4) or the T5DR lobby (Tekken 5 DR). Ranked is available when the server enables it and requires an account;
T4 keeps separate ratings and uses the shared 37-rank T5DR ladder for tier labels,
retaining server-supplied labels when no known tier is available. Direct IP or VPN is under
Settings > Advanced > **Direct connection (LAN / no server)**.

Known issues (the same list as in the changelog): pads, including the PlayStation reader and the Pad bindings pages,
are tested with stand-ins and not yet on real hardware; Tekken 4 online through the launcher needs a T4 lobby server
and direct entry into a fight is not verified against a real Tekken 4 build; the Tekken 5 DR in-game rematch has not
had its two-PC test yet.

## Requirements

- Windows 10 or 11, 64-bit. Nothing else to install for the launcher: the zip brings its own Python and Qt (no
  Python, Visual Studio, Git or Microsoft download). Linux and macOS: not supported
  ([Steam Deck notes](docs/LINUX_STEAM_DECK.md)).
- Each game has its own needs, the same as in its own notes: **Tekken 5 DR** needs a DirectX 12 graphics card, a
  processor with SSE4.1 and 4 GB RAM (see the
  [T5DR Online requirements](https://github.com/TheWishin/T5DROnline#requirements)); **Tekken 4** needs OpenGL 4.3, 4 GB
  RAM and any 64-bit processor.
- Your own copy of each game: the PSN package (`.pkg`) and licence (`.rap`) of Tekken 5 DR, an ISO of Tekken 4 USA
  (SLUS-20328). No game data is in the download.
- A folder you can write to (not Program Files), with a short path.
- Internet: for lobbies and updates; the first Tekken 5 DR build fetches about 50 KB of public key data from github.com.
  **Tekken 4 downloads nothing to build** (since Tekken 4 0.1.4: the compiler is in the zip, no Microsoft files).

## Install

1. Download `OpenRecomp-FGC-Setup-0.1.7.exe` (installs the launcher) or `OpenRecomp-v0.1.7.zip` from the Releases page.
   Windows may warn once about an unsigned program.
2. Setup: run it. Zip: extract **everything** into its own folder and open `OpenRecomp.exe`. Do not run it from
   inside the zip viewer.
3. On the shelf choose a game and install it (Tekken 5 DR: T5DR Online; Tekken 4: its release). The launcher checks
   every download.
4. **Build** the game from your own copy (Tekken 5 DR: `.pkg` and `.rap`; Tekken 4: the ISO) and press Play.

| Game | How it connects | Sections |
|---|---|---|
| Tekken 5: Dark Resurrection | an installed [T5DR Online](https://github.com/TheWishin/T5DROnline) | Play, Online, Build, Replays, Settings |
| Tekken 4 (USA, SLUS-20328) | a portable T4 release, or the sibling T4 source in the test bundle | Play, Online (lobby), Build, Settings (advanced direct IP/VPN) |
| Free slots | a manifest (below) | what the manifest says |

T4 Online always opens on login or the lobby, including when the shipped **T4 Online**
server entry is an empty placeholder: enter the server address on the login screen.
Use a guest name or your T5DR Online account (one account for both games, ratings per game).
Incoming challenges open an accept/decline pop-up showing ping and connection path.
The lobby negotiates NAT punching with relay fallback and shows a match-found card.
Supported T4 builds report results automatically; the result screen offers a rematch or
return to the lobby, and ranked sets advance through the server's countdown.
The launcher requests `TEKKEN4_NET_AUTO_VS=1`; direct entry into a fight and the game's
fighter/stage selection contract are not verified against a real T4 build.
The advanced direct IP screen retains Host/Join, checks and local log collection.
See [T4 Online and release checks](docs/T4_ONLINE.md). With a T4 server from the t4-parity branch,
T4 has T5DR's lobby: private chat, friends and invites, rooms, casual sets, tournaments, ranked,
profile, leaderboard and statistics; spectating and replays need the T4 game first. T5DR's Online section uses its installed
lobby client, with controller screens described in [T5DR_ONLINE.md](docs/T5DR_ONLINE.md).
The old T5DR Online launcher remains available during the transition. Seven language catalogs
are included; native-speaker and controller layout review remain release checks.
For the gradual move from 1.1.9, see [Keep both T5DR launchers](docs/T5DR_COEXISTENCE.md):
existing-install use, separate preferences, the private settings-copy drill and rollback.

Play time is kept per game on this PC in `OPENRECOMP_HOME/playtime.json` (the launcher's
local data folder by default), with separate offline and online totals, last played date
and session count. Only games started through this launcher, including through a native
launcher it opened, count. Totals are saved atomically every 60 seconds while playing and
when the game exits; a launcher crash retains the last checkpoint. These records are never
uploaded or added to public profiles. The shelf, game pages and your own profile show the
local totals in your selected language.

Automated tests exercise launcher logic with fakes and inert temporary files.
They do not prove real two-PC synchronization, physical pad operation, visual
readability, the compiled starter or a packaged update. See the acceptance checks
in [INSTALLING.md](docs/INSTALLING.md), [PACKAGING.md](docs/PACKAGING.md) and the
online guide. Before handover run
`.venv\Scripts\python.exe -m unittest discover -s tests` and record its result.
The source-only package check is
`.venv\Scripts\python.exe tools\package_release.py --scan-only`.
The owner can start with the German [20-minute pad check](docs/HAND_CHECK.md);
it does not replace the longer release checks.

## Start

The player release is for Windows 10/11: extract the whole release zip and open `OpenRecomp.exe` (see Install above).
The controller walk is in [T4 first run](docs/T4_FIRST_RUN.md).

For this source checkout, you need Python 3.12:

```bat
run.cmd
```

The first start creates `.venv` and installs PySide6. `run.cmd --windowed` opens a window instead of fullscreen.

For the owner/colleague internet test with both games, run
`tools\make_t4_test_bundle.ps1` (or its alias `tools\make_test_bundle.ps1`)
once in Windows PowerShell. It fetches the pinned portable CPython 3.12.10 for
Windows x64, PySide6-Essentials 6.8.2.1 and shiboken6 6.8.2.1, checks SHA-256
sums, then creates one dated test ZIP in `dist/` (or `-OutputDirectory`) after
both source scans pass and no file holds this PC's user name, profile path,
computer name or Git e-mail. The runtime is reused on later runs. It contains
`START_HERE.txt`, `START_HIER.txt`, `BUNDLE.txt`, `OpenRecomp-FGC/` and the
sibling `T4/` source catalog. Tekken 5 DR is not inside: each player puts their
own unpacked T5DR Online folder (1.2.3 or newer) next to the two, where the launcher finds
it, and builds it once in its own `T5DR Online.exe` with their .pkg and .rap.
Keep the folders together and double-click `OpenRecomp-FGC/run.cmd`; the bundled
launcher runtime needs no separate installation or first-start download.
Dependency licences stay alongside the runtime. No ISO, package, executable game
build, game data or game pictures are included. See
[packaging details](docs/PACKAGING.md) for the exact runtime catalog and scans,
and the [hand check](docs/HAND_CHECK.md) for the two-PC walk through both games.

Follow the German [test-bundle walk](docs/T4_FIRST_RUN.md). The launcher finds
`T4/`, checks build tools by itself (this **source** test bundle only: it installs missing ones with winget or
verified official downloads; the player release of Tekken 4 needs no tools and downloads nothing), verifies the
player's ISO and shows build progress. Then open Online and log in to the T4 lobby.
For the optional advanced direct IP route, compare Build-ID and compiler/MSVC before
Host/Join. Firewall, UDP 7400, port-forwarding and Tailscale steps for that route are in the
[German network guide](docs/T4_ONLINE.md). Its Collect logs action displays the
local ZIP path. No typed PowerShell build or netplay commands are required.
This source test bundle needs a real clean-PC build and two-PC acceptance.

## Controls

| Pad | Keyboard | |
|---|---|---|
| D-pad, left stick | Arrow keys | Move |
| A | Enter | Confirm |
| B | Esc | Back |
| LB / RB | Q / E | Sections |
| Start | Space | Play |
| Y | F | Quick access |
| X | X | Secondary (show a replay's result, delete in the on-screen keyboard) |
| View | G | Next game |

Xbox-style pads go through XInput. A Windows joystick reader supports recognized Sony PlayStation controllers without
a game install; an installed T5DR Online can also supply its HID reader. Real USB/Bluetooth acceptance remains required.
Normal launcher navigation pauses while a game runs. During T4, hold View + Menu (Share + Options) on one controller
for two seconds to stop the game and return to the launcher.

**Pad bindings** (T5DR Online, when its installed launcher has the controls editor). One tab per connected controller
and the keyboard (player shown, type detected: Xbox, PlayStation, other, keyboard); LT/RT (L2/R2, PgUp/PgDn) or the
tabs switch. The game's actions are listed in Tekken notation -- 1 2 3 4, the combos (1+2, 3+4, 1+3, 2+4, 1+2+3+4
and the others), Start, Select, the PS3 shoulder buttons, the four directions -- each with the controller's own
button drawn next to it (`openrecomp/pad_glyphs.py`, `ui/PadGlyph.qml`: our own shapes). Confirm an action, then
press a button within 5 seconds; a short tap on Back binds Back, holding it for a second cancels (Esc on the
keyboard). A button another action already uses is named and swapped on Yes (that action gets this one's old
button); X clears an action. Presets (`openrecomp/pad_presets.py`): Default (the game's own), Tekken Classic,
Arcade stick, Hitbox / Leverless (stick as d-pad, SOCD neutral), Left-handed, and for the keyboard Number pad;
Reset to default, Plays as (player pin), Left + right at once (SOCD) and Left stick (analog / d-pad). Input test:
the actions light up and the bottom strip shows held bindings in Tekken notation (d/f+1+2), before the game's
SOCD filtering; opposite directions stay visible (b+f or u+d). Hold Back for a second to finish.
Every change is the installed T5DR editor's own edit of `controls.ini`, so the file
stays in the format the game reads.

**Pad bindings of Tekken 4** (a T4 release with the pad-bindings runtime, PS2Recomp patch 99). The same page, editable:
the keyboard and every XInput controller found are tabs (`openrecomp/adapters/t4_controls.py`; XInput and the keyboard are
read by `openrecomp/t4_pad_reader.py`, only while a button is captured or the input test runs). Each device plays as a
player (Plays as: Automatic, P1, P2; the keyboard can be player 2), 1 2 3 4 are Square Triangle Cross Circle, and L1 R1 L2
R2 L3 R3 Start Select and the directions can be bound too. Presets: Default (the game's fixed layout), Tekken arcade 1-2-3-4
(controller X Y RB RT, keyboard W A S D and U I J K) and, for the keyboard, Number pad. Esc cancels a keyboard capture, F11
is the game window's. The page writes `controls.ini` in the game's save folder (`openrecomp/t4_controls_ini.py`: `[playerN]
device = ...`, `[playerN.pad]`, `[playerN.keys]`, only the buttons that differ from the fixed layout) and the launcher hands
the path to the game as `TEKKEN4_CONTROLS`; the game re-reads it within a second, and the page asks to stop the game before
an edit. No file = the game's old layout, exactly. DirectInput controllers (DualShock without DS4Windows or Steam) keep the
fixed layout. Online play uses the mapped buttons: bindings change which input is which PS2 button, never what is sent.

**Menu sounds.** Moving, confirming, going back, switching sections, toggling a setting, opening and closing a panel,
a refused press and a found match each have a short sound (40-150 ms); the pad, the keyboard and the mouse make the
same one. They play only while the launcher's window is in front and no game runs, follow Windows' default output
device, and stay silent without one. Settings > Audio: **Menu sounds** On/Off and **Menu sound volume** (default On,
50 %). The sounds are synthesized by `tools/make_ui_sounds.py` (no sound pack, nothing from a game);
`openrecomp/ui_sound.py` says which press makes which sound and plays them (`OPENRECOMP_UI_SOUND=0` = silent).

## Community and problem reports

**OpenRecomp-FGC Discord** (top bar, and Quick access for pads) opens the players' one Discord server for T5DR
Online, Tekken 4 Online and this launcher in the browser (the invite lives in `openrecomp/community.py`).

T5DR's **Problem report** page starts with **Send to the developer**: one press makes the same cleaned report zip as
"Create local report" (user names, internet addresses, passwords, tokens and lobby names taken out; no game files,
keys, .pkg or .rap), sends it with the game version, build id, Windows version, the optional note and contact, and the
lobby name to the install's own lobby server (the default of its `lobby/servers.json`), and shows "Sent, thanks
(report #ID)". A server that takes no reports yet hides the row; saving the zip stays. The server side: T5DR's
`lobby/t5lobby/server/reports.py` and docs/HOSTING.md "Problem reports".

## Add a game

Press A on a free slot, then enter a GitHub `owner/repo` or choose a local folder.
Review the author, required files and third-party warning before accepting the game.
Each game keeps its own releases, login and servers; removing it from the shelf leaves
its files and player data in place. The T5DR launcher remains available alongside this one.

Recomp authors can publish one `openrecomp-game.json` file using the
[versioned manifest specification](docs/ADD_YOUR_GAME.md). The Generic adapter needs no
launcher code from them for basic launching and declared JSON settings. Tekken Tag
Tournament 2 has a placeholder in the small known-games catalog until its repository is known.

## Layout

| Path | What |
|---|---|
| `openrecomp/nav.py` | Navigation state, action dispatch, timers, and one plain dict out. No Qt |
| `openrecomp/nav_common.py` | Shared constants and plain helpers, also exported by `nav.py` |
| `openrecomp/nav_shelf.py` | Game shelf input and view |
| `openrecomp/nav_hub.py`, `openrecomp/nav_sections.py` | Hub navigation and view; play, online, build, replays, and settings items |
| `openrecomp/nav_dialog.py`, `openrecomp/nav_drawer.py`, `openrecomp/nav_grid.py`, `openrecomp/nav_keyboard.py`, `openrecomp/nav_picker.py` | Each overlay's input and view |
| `openrecomp/file_dialog.py` | The Windows Explorer open dialog (ctypes, no Qt Widgets) for mouse and keyboard |
| `openrecomp/pad.py` | Controllers to actions |
| `openrecomp/ui_sound.py`, `openrecomp/nav_sound.py` | Menu sounds: which press makes which sound, the player |
| `openrecomp/nav_controls_page.py`, `openrecomp/pad_glyphs.py`, `openrecomp/pad_presets.py` | Pad bindings page: rows, button glyphs, Tekken notation, presets |
| `openrecomp/t4_controls_ini.py`, `openrecomp/t4_pad_reader.py`, `openrecomp/adapters/t4_controls.py` | Tekken 4 Pad bindings: `controls.ini` model (parse, write, devices, presets), XInput and keyboard reader, the page's edits |
| `openrecomp/app.py` | Window, QML scene, timers |
| `openrecomp/adapters/` | One per kind of game |
| `openrecomp/ui/` | The QML screens, the bundled fonts and the menu sounds (`ui/sounds`) |
| `games/` | The manifests that ship |
| `tests/` | `python -m unittest discover tests` |
| `tools/make_logo.py` | Draws the logo files in `openrecomp/ui/assets` |
| `tools/make_ui_sounds.py` | Synthesizes the menu sounds in `openrecomp/ui/sounds` |
| `tools/shots.py` | Manual screenshot helper using the real backend and installed artwork; not an isolated test |
| `tools/t4_flow_shots.py` | Synthetic T4 login, lobby, challenge, match-found and result screens; no game discovery or artwork |

## Licences

OpenRecomp-FGC is MIT licensed (`LICENSE`). The fonts in `openrecomp/ui/fonts` are under the SIL Open Font License (the
`OFL-*.txt` files next to them). The menu sounds in `openrecomp/ui/sounds` are made by `tools/make_ui_sounds.py` and
are part of this repository's MIT licence. OpenRecomp-FGC starts the games as separate programs and loads their launcher code from
your install at run time; none of that code is part of this repository, and each game keeps its own licence.

Tekken is a trademark of Bandai Namco Entertainment. This project is not affiliated with or endorsed by them.
