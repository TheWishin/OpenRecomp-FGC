<picture>
  <source media="(prefers-color-scheme: dark)" srcset="openrecomp/ui/assets/logo-wordmark.svg">
  <img alt="OpenRecomp-FGC" src="openrecomp/ui/assets/logo-wordmark-light.svg" height="72">
</picture>

# OpenRecomp-FGC

**Launcher for all your Recomps.** One fullscreen launcher for native PC ports of console games, made to be used from
the couch: everything works with a controller, and mouse and keyboard still work. Button prompts follow the device you
used last.

> OpenRecomp-FGC contains **no game data**: no ISO, no packages, no keys, no BIOS, no translated game code, no game art.
> You build each game from your own copy. Pictures on the launcher are read from your own build and stay on your PC.

## Status

T4 beta release candidate. Its scope is T4 offline play and online by direct IP or
VPN: no lobby and no ranked. Release depends on the owner's two-PC test and the
clean-PC checks below; a Sunday release is a target, not a completed acceptance result.

| Game | How it connects | Sections |
|---|---|---|
| Tekken 5: Dark Resurrection | an installed [T5DR Online](https://github.com/TheWishin/T5DROnline) | Play, Online, Build, Replays, Settings |
| Tekken 4 (USA, SLUS-20328) | a portable release of the Tekken 4 recomp with its bundled build tools | Play, Online (direct IP/VPN), Build, Settings |
| Free slots | a manifest (below) | what the manifest says |

T4 Online offers Host or Join, an on-screen keyboard for the host's IP address,
checks for matching build, compiler/MSVC, ISO hash and two-way UDP reachability,
then a separate Start game action. Collect logs saves local diagnostic zip files.
See [T4 Online and release checks](docs/T4_ONLINE.md). There is no T4 account,
matchmaking, room, chat, relay or result-reporting service in this beta. Lobby-based
online stays hidden until its server exists. T5DR's Online section uses its installed
lobby client, with controller screens described in [T5DR_ONLINE.md](docs/T5DR_ONLINE.md).
The old T5DR Online launcher remains available during the transition. Seven language catalogs
are included; native-speaker and controller layout review remain release checks.

Automated tests exercise launcher logic with fakes and inert temporary files.
They do not prove real two-PC synchronization, physical pad operation, visual
readability, the compiled starter or a packaged update. See the acceptance checks
in [INSTALLING.md](docs/INSTALLING.md), [PACKAGING.md](docs/PACKAGING.md) and the
online guide. Before handover run
`.venv\Scripts\python.exe -m unittest discover -s tests` and record its result.
The source-only package check is
`.venv\Scripts\python.exe tools\package_release.py --scan-only`.

## Start

The player release is intended for Windows 10/11: extract the whole release zip and open `OpenRecomp.exe`.
Its private runtime and native starter still need owner packaging and clean-PC acceptance. The controller walk and
remaining release gates are in [T4 first run](docs/T4_FIRST_RUN.md).

For this source checkout, you need Python 3.12:

```bat
run.cmd
```

The first start creates `.venv` and installs PySide6. `run.cmd --windowed` opens a window instead of fullscreen.

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

## Add a game

Press A on a free slot and pick a manifest, or copy the file to `%LOCALAPPDATA%\OpenRecomp\games`. A finished recomp only
needs this:

```json
{
 "id": "mygame",
 "title": "My Game",
 "subtitle": "PS2 Recomp",
 "platform": "PS2",
 "numeral": "M",
 "accent": "#2FC4B2",
 "adapter": "generic",
 "exe": "D:\\MyGame\\game.exe",
 "args": [],
 "env": {},
 "sections": ["play", "settings"]
}
```

A game with its own build, settings or online play gets an adapter in `openrecomp/adapters/`. The screens only talk to
the interface in `adapters/base.py`, so a new adapter changes no screen.

## Layout

| Path | What |
|---|---|
| `openrecomp/nav.py` | Navigation state, action dispatch, timers, and one plain dict out. No Qt |
| `openrecomp/nav_common.py` | Shared constants and plain helpers, also exported by `nav.py` |
| `openrecomp/nav_shelf.py` | Game shelf input and view |
| `openrecomp/nav_hub.py`, `openrecomp/nav_sections.py` | Hub navigation and view; play, online, build, replays, and settings items |
| `openrecomp/nav_dialog.py`, `openrecomp/nav_drawer.py`, `openrecomp/nav_grid.py`, `openrecomp/nav_keyboard.py`, `openrecomp/nav_picker.py` | Each overlay's input and view |
| `openrecomp/pad.py` | Controllers to actions |
| `openrecomp/app.py` | Window, QML scene, timers |
| `openrecomp/adapters/` | One per kind of game |
| `openrecomp/ui/` | The QML screens and the bundled fonts |
| `games/` | The manifests that ship |
| `tests/` | `python -m unittest discover tests` |
| `tools/make_logo.py` | Draws the logo files in `openrecomp/ui/assets` |
| `tools/shots.py` | Manual screenshot helper using the real backend and installed artwork; not an isolated test |

## Licences

OpenRecomp-FGC is MIT licensed (`LICENSE`). The fonts in `openrecomp/ui/fonts` are under the SIL Open Font License (the
`OFL-*.txt` files next to them). OpenRecomp-FGC starts the games as separate programs and loads their launcher code from
your install at run time; none of that code is part of this repository, and each game keeps its own licence.

Tekken is a trademark of Bandai Namco Entertainment. This project is not affiliated with or endorsed by them.
