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

First working version. On the launcher today:

| Game | How it connects | Sections |
|---|---|---|
| Tekken 5: Dark Resurrection | an installed [T5DR Online](https://github.com/TheWishin/T5DROnline) | Play, Online, Build, Replays, Settings |
| Tekken 4 (USA, SLUS-20328) | a checkout or release of the Tekken 4 recomp with its installed `t4lobby` client | Play, Online, Build, Settings |
| Free slots | a manifest (below) | what the manifest says |

T4 Online includes casual quick match, player challenges, open rooms, chat, and one game process per match with manual
results. Ranked is unavailable for T4. See [T4 Online and release checks](docs/T4_ONLINE.md), including the shared-account
server requirement. T5DR currently provides login and search through the same lobby integration; its match handover
still stops at a found match. Other native online features remain reachable through each game's launcher. Texts are
available in seven languages.

## Start

You need Windows 10/11 and Python 3.12.

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

Xbox-style pads go through XInput. PlayStation pads are read through the HID reader of an installed T5DR Online. The
launcher reads pads only while it is in front, and not while a game runs.

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
| `tools/shots.py` | Drives every screen without a window, in a dry run, and saves pictures |

## Licences

OpenRecomp-FGC is MIT licensed (`LICENSE`). The fonts in `openrecomp/ui/fonts` are under the SIL Open Font License (the
`OFL-*.txt` files next to them). OpenRecomp-FGC starts the games as separate programs and loads their launcher code from
your install at run time; none of that code is part of this repository, and each game keeps its own licence.

Tekken is a trademark of Bandai Namco Entertainment. This project is not affiliated with or endorsed by them.
