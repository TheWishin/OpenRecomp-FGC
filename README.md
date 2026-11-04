<picture>
  <source media="(prefers-color-scheme: dark)" srcset="openrecomp/ui/assets/logo-wordmark.svg">
  <img alt="OpenRecomp-FGC" src="openrecomp/ui/assets/logo-wordmark-light.svg" height="72">
</picture>

# OpenRecomp-FGC

**Launcher for all your Recomps.** One fullscreen launcher for native PC ports of console games, made to be used from
the couch: designed for controller use, with mouse and keyboard support too. Physical-pad acceptance is still required. Button prompts follow the device you
used last.

> OpenRecomp-FGC contains **no game data**: no ISO, no packages, no keys, no BIOS, no translated game code, no game art.
> You build each game from your own copy. Pictures on the launcher are read from your own build and stay on your PC.

## Status

T4 beta release candidate. Its scope is T4 offline play and online through a T4
lobby server (guest or account login, player list, lobby chat, quick match, challenges)
or by direct IP or VPN; no ranked. Release depends on the owner's two-PC test and the
clean-PC checks below; a Sunday release is a target, not a completed acceptance result.

| Game | How it connects | Sections |
|---|---|---|
| Tekken 5: Dark Resurrection | an installed [T5DR Online](https://github.com/TheWishin/T5DROnline) | Play, Online, Build, Replays, Settings |
| Tekken 4 (USA, SLUS-20328) | a portable T4 release, or the sibling T4 source in the test bundle | Play, Online (lobby or direct IP/VPN), Build, Settings |
| Free slots | a manifest (below) | what the manifest says |

T4 Online offers Host or Join, an on-screen keyboard for the host's IP address,
checks for matching build, compiler/MSVC, ISO hash and two-way UDP reachability,
then a separate Start game action. Collect logs saves local diagnostic zip files.
T4 Online opens on the lobby (the launcher ships the **T4 Online** server): guest
login, or your T5DR Online account (one account for both games, ranks per game), the
player list, lobby chat, quick match and challenges, then the same explicit Start game
and a result report. Direct IP / VPN stays one press away.
See [T4 Online and release checks](docs/T4_ONLINE.md). With a T4 server from the t4-parity branch,
T4 has T5DR's lobby: private chat, friends and invites, rooms, casual sets, tournaments, ranked,
profile, leaderboard and statistics; spectating and replays need the T4 game first. T5DR's Online section uses its installed
lobby client, with controller screens described in [T5DR_ONLINE.md](docs/T5DR_ONLINE.md).
The old T5DR Online launcher remains available during the transition. Seven language catalogs
are included; native-speaker and controller layout review remain release checks.
For the gradual move from 1.1.9, see [Keep both T5DR launchers](docs/T5DR_COEXISTENCE.md):
existing-install use, separate preferences, the private settings-copy drill and rollback.

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

The player release is intended for Windows 10/11: extract the whole release zip and open `OpenRecomp.exe`.
Its private runtime and native starter still need owner packaging and clean-PC acceptance. The controller walk and
remaining release gates are in [T4 first run](docs/T4_FIRST_RUN.md).

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
own unpacked `T5DR-Online-1.2.0` folder next to the two, where the launcher finds
it, and builds it once in its own `T5DR Online.exe` with their .pkg and .rap.
Keep the folders together and double-click `OpenRecomp-FGC/run.cmd`; the bundled
launcher runtime needs no separate installation or first-start download.
Dependency licences stay alongside the runtime. No ISO, package, executable game
build, game data or game pictures are included. See
[packaging details](docs/PACKAGING.md) for the exact runtime catalog and scans,
and the [hand check](docs/HAND_CHECK.md) for the two-PC walk through both games.

Follow the German [test-bundle walk](docs/T4_FIRST_RUN.md). The launcher finds
`T4/`, checks build tools by itself and installs missing ones with winget after one confirmation, verifies the
player's ISO and shows build progress. Compare Build-ID and compiler/MSVC before
Host/Join. Firewall, UDP 7400, port-forwarding and Tailscale steps are in the
[German network guide](docs/T4_ONLINE.md). After play, Collect logs displays the
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
stays in the format the game reads. T4 reads a fixed layout (the game has no bindings file yet), so it has no Pad bindings page.

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
| `openrecomp/app.py` | Window, QML scene, timers |
| `openrecomp/adapters/` | One per kind of game |
| `openrecomp/ui/` | The QML screens, the bundled fonts and the menu sounds (`ui/sounds`) |
| `games/` | The manifests that ship |
| `tests/` | `python -m unittest discover tests` |
| `tools/make_logo.py` | Draws the logo files in `openrecomp/ui/assets` |
| `tools/make_ui_sounds.py` | Synthesizes the menu sounds in `openrecomp/ui/sounds` |
| `tools/shots.py` | Manual screenshot helper using the real backend and installed artwork; not an isolated test |

## Licences

OpenRecomp-FGC is MIT licensed (`LICENSE`). The fonts in `openrecomp/ui/fonts` are under the SIL Open Font License (the
`OFL-*.txt` files next to them). The menu sounds in `openrecomp/ui/sounds` are made by `tools/make_ui_sounds.py` and
are part of this repository's MIT licence. OpenRecomp-FGC starts the games as separate programs and loads their launcher code from
your install at run time; none of that code is part of this repository, and each game keeps its own licence.

Tekken is a trademark of Bandai Namco Entertainment. This project is not affiliated with or endorsed by them.
