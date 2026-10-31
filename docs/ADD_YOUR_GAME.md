# Add your game — manifest specification v1

Keep your repository, GitHub releases, login and servers. Publish one UTF-8 JSON file named
`openrecomp-game.json` at your repository's default-branch root, or as the unique asset of
that name in your latest stable GitHub release. The release asset is used only when the root
file is missing. The Generic adapter needs no launcher code from you. The controller flow
accepts `owner/repo` or a local folder containing that file.

Before accepting a game, players see its author, source and required files, plus a warning:
third-party games belong to their authors, not OpenRecomp-FGC. Preview fetches only bounded
manifest metadata; it does not download a game. The launcher never imports or evaluates code
from a public manifest. Only an explicit Start game action launches the game's executable.

## One complete example

Replace the example repository, author, release filename and all-zero input hash with your
own public metadata. Paths use `/` and stay relative to the player's game folder.

```json
{
  "schema_version": 1,
  "id": "example-recomp",
  "adapter": "generic",
  "title": "Example Recomp",
  "short": "Example",
  "subtitle": "An independently maintained recomp",
  "platform": "PS3",
  "numeral": "E",
  "accent": "#5B93FF",
  "author": "Example recomp team",
  "repository": "example/recomp",
  "version": "v1.0.0",
  "releases": {
    "channel": "stable",
    "asset": "example-recomp.zip",
    "verification": {"method": "github-sha256"}
  },
  "requirements": [
    {
      "id": "disc",
      "label": "Your own disc image",
      "kind": "iso",
      "version": "Supported disc revision",
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    }
  ],
  "exe": "bin/example.exe",
  "args": [],
  "cwd": "bin",
  "build": {"instructions": "Use your own disc image with the build tool supplied by our project."},
  "settings": {
    "file": "settings.json",
    "cyclers": [
      {
        "id": "display",
        "label": "Display mode",
        "key": "fullscreen",
        "options": [
          {"value": true, "label": "Fullscreen"},
          {"value": false, "label": "Windowed"}
        ]
      }
    ]
  },
  "controls": {"file": "controls.json"},
  "online": {"mode": "own"},
  "replays": "replays",
  "logo": "assets/logo.png",
  "license": "Your recomp's licence identifier or public licence notice",
  "credits": ["Your recomp team", "Your contributors"],
  "sections": ["play", "online", "build", "replays", "settings"]
}
```

## Field contract

`schema_version: 1` is this public version. Required fields are `id`, `adapter: "generic"`,
`title`, `platform` (the badge text), `numeral`, `accent` (`#RRGGBB`), `author`,
`repository` (`owner/repo`), `exe`, `license` and `credits` (a list of credit strings).
`short`, `subtitle`, `version`, `order` and `sections` describe shelf presentation.
Unknown fields and unsupported schema versions are rejected. Manifests are limited to
64 KiB; text, collections and referenced downloads also have size limits.

| Optional field | Meaning |
|---|---|
| `releases` | Your GitHub repository's release asset, channel and integrity policy; omit for a local-only game. |
| `requirements` | Player-supplied files: unique `id`, plain `label`, `kind` (`iso` or `file`), required `version` and exact SHA-256. Never include the files. |
| `args`, `cwd` | Argument strings passed directly to your executable, and a relative working folder. No shell command, script, environment substitution or plugin is accepted. |
| `build.instructions` | Plain instructions shown to the player. The Generic adapter does not execute build commands; your project supplies and documents its own build tool. |
| `settings` | A relative JSON `file` and `cyclers`: each has a unique `id`, display `label`, top-level JSON `key`, and `options` of scalar `value` plus display `label`. Unrelated settings remain intact. |
| `controls.file` | Your relative controls file; your own game handles binding. This declaration does not add a controller-binding plugin. |
| `online.mode` | `none`: offline; `own`: Start opens your executable, whose own login and servers remain yours; `lobby`: requires an `arrangement` description and an agreed integration before launcher lobby support exists. |
| `replays` | Your relative replay folder. The declaration does not teach Generic how to play your replay format. |
| `logo` | A relative PNG, JPG, JPEG or WebP bitmap supplied by your project, at most 8 MiB, kept on the player's PC. SVG is not displayed. Do not send game-derived pictures to this repository. |

All file references must remain inside the game folder, including after resolving links.
Absolute paths, `..`, device paths, alternate data streams and executable Python hooks are
not part of this spec. Local registration reuses the selected folder in place.

## Releases and trust

Versions use `vMAJOR.MINOR.PATCH` release tags; prereleases append `-identifier`.
`channel: "stable"` selects stable releases;
`"prerelease"` permits the author's prerelease channel.
`verification: {"method": "github-sha256"}` requires the matching GitHub release asset's
SHA-256 digest. Alternatively, `{"method": "sha256", "sha256": "<64 hexadecimal digits>"}`
pins one exact archive hash in the accepted manifest; publish a revised manifest for a new
pinned archive. Missing or mismatching integrity information refuses installation. This
version verifies hashes; it does not claim independent publisher-signature verification.

Game updates are explicitly requested and confirmed per game, use that game's own
repository and channel, and never enter the launcher's signed update channel. Files are
checked before extraction; unsafe or oversized archives are refused. Updates install in a
separate version folder and preserve the previous installation. OpenRecomp-FGC links
to authors' releases and never rehosts them. Keep saves, login state and other player data
in your project's documented data location. Removing a registration leaves the game's
files and data untouched.

The small [known-games catalog](../openrecomp/data/known_games.json) has a disabled
Tekken Tag Tournament 2 placeholder until its author supplies the repository and manifest.
No repository or support claim is guessed. The existing T5DR launcher stays active beside
OpenRecomp-FGC; see [T5DR coexistence](T5DR_COEXISTENCE.md).

Before asking to be listed, publish your manifest, supported input revision/hash, release
asset and integrity metadata, your logo and licence/credits. Test local registration,
controller-only preview/cancel/accept, settings preservation, own-login handoff, a tampered
update and removal on your own installation. These checks require the author's real build;
launcher unit tests use inert files and do not establish game compatibility.
