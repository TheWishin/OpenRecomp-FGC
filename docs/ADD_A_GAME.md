# Add a game with one JSON file (manifest version 2)

A game can be put on OpenRecomp-FGC's shelf with one JSON file and no launcher code: where the game is, how
to start and stop it, its tile picture, which settings to show, whether it has its own online mode, and where
its releases are for the update check. The launcher reads it as data only: no code, no shell commands, no
`%VAR%` expansion; every path stays inside the game's folder and is checked again when it is used.

(Version 1 is the public manifest an author publishes in a GitHub repository for the "Add a game" flow:
[ADD_YOUR_GAME.md](ADD_YOUR_GAME.md). Version 2 is a local file and adds environment, Stop, finding an existing
install, settings that go into the environment / arguments / INI files, and signed update checks.)

## Where the files go

| File | Who | What it may do |
| --- | --- | --- |
| `games\<id>.json` in the launcher | comes with the launcher (e.g. `games\tag2.json`) | everything below, and name a built-in adapter in `code_adapter` |
| `%OPENRECOMP_HOME%\games\<id>.json` (default `%LOCALAPPDATA%\OpenRecomp\games\`) | the player | everything below except `code_adapter` |

The player's file of an id replaces the launcher's file of that id. `t4` and `t5dr` cannot be replaced. The
launcher reads the files when it starts.

## Checks

- The file is UTF-8 JSON, at most 64 KiB, no duplicate keys, no `NaN`.
- **Unknown fields** are listed as a problem ("tag2.json: online.colour: unknown field, ignored") and ignored.
- **Anything else wrong** (a missing `start.exe`, a path with `..`, a forbidden variable name, a setting without
  options...) makes the manifest *broken*: the shelf shows a grey tile with its title and the exact reason
  ("tag2.json: start.exe: must be a path inside the game's folder (with /, no drive, no ..)"). Nothing of it runs.
- Paths: relative, `/` as separator, no drive, no `..`, no `:*?"<>|%$`, no Windows device names; resolved
  against the game's folder and refused when a link points outside it.
- `start.env` and `target.env` names: `A-Z 0-9 _`; never `PATH`, `PATHEXT`, `COMSPEC`, `SYSTEMROOT`, `WINDIR`,
  `TEMP`/`TMP`, the player's folders (`APPDATA`, `LOCALAPPDATA`, `USERPROFILE`, ...), `PYTHON*`, `QT_*`,
  `OPENRECOMP*`, proxies. Values are literal text.

## Fields

Required: `schema_version` (2), `id`, `title`, `platform`, `numeral`, `accent`, `start`. Optional top-level
fields: `short`, `subtitle`, `order`, `sections`, `author`, `license`, `credits`, `source`, `shelf`,
`code_adapter`, `install`, `stop`, `art`, `online`, `settings`, `updates`. Nothing else.

| Field | Meaning |
| --- | --- |
| `id` | lower-case letters, digits, `-` `_` (at most 64) |
| `title`, `short`, `subtitle` | shelf texts (`short` defaults to `title`) |
| `platform`, `numeral`, `accent` | the tile's badge, big letters and colour (`#RRGGBB`) |
| `order` | place on the shelf (T4 10, T5DR 20) |
| `sections` | which of `play`, `online`, `build`, `replays`, `settings` the game has (default play, settings) |
| `author`, `license`, `credits`, `source` | shown as given (`source`: what the player needs, e.g. "Xbox 360 disc ISO") |
| `shelf` | `always` (default) or `found`: the tile shows only on a PC where the game is found |
| `code_adapter` | launcher files only: the built-in adapter that does what needs code (`tag2`). While this launcher has no such adapter, the manifest alone is the game |
| `install.detect` | files that must all be in the game's folder (default: `start.exe`) |
| `install.search` | where to look when the player has not chosen a folder: `{beside}/NAME*` (beside the launcher's folder), `%USERPROFILE%/...`, `%LOCALAPPDATA%/...`; `*` only in the last part |
| `start.exe` | the game's own `.exe` inside its folder |
| `start.args` | argument strings, passed as they are (no shell) |
| `start.cwd` | working folder inside the game's folder (default: the game's folder) |
| `start.env` | `{"NAME": "value"}` added to the game's environment |
| `stop.close_window_seconds` | 0..30. Stop first asks the game's windows to close (WM_CLOSE, like closing it with X) and ends the process after that many seconds; 0 (default) ends it at once. A second Stop always ends it at once |
| `art.cache` | a picture file name in `%OPENRECOMP_HOME%\art\<id>\` (the player's own picture, or one the launcher made from the player's own game files) |
| `art.file` | a PNG/JPG/WebP inside the game's folder (at most 8 MiB). Never a web address; never a picture in this repository |
| `online.mode` | `none` (default) or `external`: the Online section has "Play online (the game's own online mode)", which starts the game; its own launcher or menus do the rest |
| `online.note` | the text shown there |
| `settings` | see below |
| `updates` | see below |

Every label (`settings[].label`, option labels, `online.note`) is one text or one text per language:
`{"en": "...", "de": "...", "es": ..., "fr": ..., "ja": ..., "ko": ..., "pt-BR": ...}` (`en` required; the
launcher's language is used, else English).

### Settings

```json
"settings": [
 {"id": "scale", "label": "Internal resolution", "type": "choice",
  "options": [{"value": 1, "label": "Native"}, {"value": 2, "label": "2x"}], "default": 1,
  "target": {"arg": "--draw_resolution_scale={value}"}},
 {"id": "vsync", "label": "VSync", "type": "toggle", "default": true, "target": {"env": "GAME_VSYNC"}},
 {"id": "window", "label": "Windowed", "type": "toggle", "target": {"ini": "config/game.ini", "section": "Display", "key": "Windowed"}},
 {"id": "lang", "label": "Game language", "type": "choice",
  "options": [{"value": "en", "label": "English"}, {"value": "ja", "label": "Japanese"}],
  "target": {"json": "settings.json", "key": "language"}}
]
```

`type`: `choice` (options with a text, whole-number or true/false `value`) or `toggle` (on/off). `target`, one of:
`env` (environment variable at start), `arg` (one argument at start; `{value}` is replaced), `ini` (a key in an
INI file of the game: only that line changes, the rest stays), `json` (a top-level key of a JSON file of the
game). `env`/`arg` values are kept in OpenRecomp's own settings; `ini`/`json` are read from and written to the
game's file (not while the game runs). A toggle writes `1` / `0` into env, arg and INI (`true` / `false` in JSON).

### Updates

```json
"updates": {
 "repository": "owner/repo", "repository_id": "123456789",
 "asset": "Game-{version}.zip", "channel": "stable",
 "verification": {"method": "ed25519", "key": "<64 hex>", "sums": "SHA256SUMS", "signature": "SHA256SUMS.sig"},
 "installed_version": [{"file": "version.json", "json_key": "version"}, {"file": "README.txt", "prefix": "Game "}]
}
```

- `repository` / `repository_id`: the GitHub repository and its number (`https://api.github.com/repos/owner/repo`
  -> `id`): downloads are accepted only from that repository's release files (as for T5DR and T4).
- `asset`: the release zip's name with `{version}` (tag without `v`) or `{tag}`.
- `channel`: `stable` (published plain `vX.Y.Z` only) or `prerelease` (also published pre-releases). Drafts never.
- `verification.method`:
  - `ed25519`: the release carries `SHA256SUMS` and `SHA256SUMS.sig` (`format` / `statement` default to
    `openrecomp-game-sig/1` / `OpenRecomp-game-release-signature-v1:<id>`, the same envelope T4 uses); the check
    downloads those two small files and offers the update only when the signature verifies with `key` and
    `SHA256SUMS` names the zip with GitHub's digest.
  - `github-sha256`: no signature; GitHub's SHA-256 digest of the asset is the only check.
  - `unsigned`: the author signs nothing; the launcher says so ("not signed by its author") and leaves the choice
    to the player.
- `installed_version`: where the installed version is read (the first rule that finds `X.Y.Z` wins): a key of a
  JSON file, or the version right after a text in a text file (no pattern language). An install the launcher
  made has its own marker, which comes first.

The launcher checks once after its start (at most once an hour per game) and, when GitHub has a newer release,
the tile and the Play page say "Version X is out (owner/repo). Update it with the game's own updater." A manifest
does not download or install releases; a game whose updates need more (TAG2's signed update manifest, its build
from the player's disc) does that in its adapter (`code_adapter`).

## Example: Tekken Tag Tournament 2 (`games/tag2.json`)

TAG2 PC (frameperfectlab.com) is the first game added this way. What its manifest does, what stays in the tag2
adapter:

| TAG2 adapter (branch tag2) | `games/tag2.json` |
| --- | --- |
| finds the install: the chosen folder, beside the launcher, Downloads, Desktop (`TAG2*`) | `install.detect` `Tag2Launcher.exe`, `install.search` the same three places |
| starts the built game with its 40 arguments, shader preparation, audio check | `start.exe` = TAG2's own launcher (`Tag2Launcher.exe`): it builds, updates and starts the game |
| Stop: WM_CLOSE, 5 s, then end | `stop.close_window_seconds: 5` |
| tile picture `%OPENRECOMP_HOME%\art\tag2\hero.png` | `art.cache: "hero.png"` |
| update check: TAG2's signed manifest (RSA) + GitHub releases | `updates`: GitHub `adageshi/tag2-pc`, `TAG2-PC-Launcher-{version}.zip`, GitHub digest; installed version from `state.json` `highest_version`, else `README.txt` after "TAG2 PC " |
| accounts, ranked, Play online | `online.mode: external` (TAG2's launcher does it) |
| build from ISO + Title Update, engine updates, repair, controls, settings | stays in the adapter (`code_adapter: "tag2"`) |

It is `"shelf": "found"`: the tile appears only on a PC where a TAG2 folder is found, so players without TAG2
see nothing new. To always show it, copy the file to `%OPENRECOMP_HOME%\games\tag2.json`, remove
`code_adapter` (a player's file may not name code) and set `"shelf": "always"`; then choose TAG2's folder in
its Build page.

```json
{
 "schema_version": 2,
 "id": "tag2",
 "order": 30,
 "title": "Tekken Tag Tournament 2",
 "subtitle": "TAG2 PC",
 "short": "TAG2",
 "platform": "Xbox 360",
 "numeral": "TT2",
 "accent": "#F2A33A",
 "author": "frameperfectlab.com",
 "source": "Xbox 360 disc ISO + Title Update",
 "code_adapter": "tag2",
 "shelf": "found",
 "sections": ["play", "online", "build"],
 "install": {
  "detect": ["Tag2Launcher.exe"],
  "search": ["{beside}/TAG2*", "%USERPROFILE%/Downloads/TAG2*", "%USERPROFILE%/Desktop/TAG2*"]
 },
 "start": {"exe": "Tag2Launcher.exe"},
 "stop": {"close_window_seconds": 5},
 "art": {"cache": "hero.png"},
 "updates": {
  "repository": "adageshi/tag2-pc",
  "repository_id": "1428232403",
  "asset": "TAG2-PC-Launcher-{version}.zip",
  "channel": "stable",
  "verification": {"method": "github-sha256"},
  "installed_version": [
   {"file": "state.json", "json_key": "highest_version"},
   {"file": "README.txt", "prefix": "TAG2 PC "}
  ]
 },
 "online": {"mode": "external", "note": {"en": "TAG2's own launcher signs you in and finds matches; rooms are made in the game's Online menu.", "de": "..."}}
}
```

(The shipped file has the note in all seven languages.)

## Not part of version 2

Building a game from the player's files, controller bindings, replays, a lobby, downloading or installing
releases: these need code, i.e. an adapter. A manifest never runs anything but `start.exe`, and only when the
player presses Start.
