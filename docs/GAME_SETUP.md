# Installing and updating the games from the launcher

OpenRecomp-FGC can download and update the two fighting games' own programs. It never downloads game data:
you still bring your own Tekken 5 DR package + license and your own Tekken 4 disc image, and the game is built on
your PC as before.

| Game | Comes from | What is downloaded |
| --- | --- | --- |
| Tekken 5 DR Online | github.com/TheWishin/T5DROnline, releases | `T5DR-Online-X.Y.Z.zip`, `SHA256SUMS`, `SHA256SUMS.sig` |
| Tekken 4 | github.com/TheWishin/Tekken4Recomp, releases | `OpenRecomp-Tekken4-<tag>.zip`, `SHA256SUMS`, `SHA256SUMS.sig`; only the zip's `T4` folder is used |

## Install

Select a game tile that says **Install or choose folder** and confirm. The game's Build section opens with
**Install Tekken 5 DR Online** (or **Install Tekken 4**) first; the old "choose the folder you already have" stays
below it. Install looks up the newest release, then asks where: the default is beside OpenRecomp-FGC's own folder
(where Setup put it), **Other folder** picks any drive or folder. Before anything is downloaded the launcher checks
free space (download + unpacked files + room for the build) and that it can write there.

The download is checked like T5DR's own updater does: only this project's GitHub addresses, `SHA256SUMS` must name
the zip and agree with GitHub's digest, and the release signature must be valid: T5DR's own release key
(Ed25519; an installed T5DR's own key list counts too) for T5DR, the T4 release key built into the launcher for
Tekken 4 ([RELEASE_KEYS.md](RELEASE_KEYS.md); an unsigned T4 release is refused). Every path in the zip is checked before it is written; the
files are unpacked into a staging folder beside the target and moved in at the end, so a failed or cancelled
install leaves nothing behind. Afterwards the launcher attaches the new install and opens its Build section:
choose your own package/license (T5DR) or disc image (T4) and build.

## The Build page

Build is a page of cards: **Get the game** (Install, or the folder you already have), **Your game files** (T4: the
disc image; T5DR: package and licence; after a file is chosen the focus moves to the next missing one, then to the
button), **Build tools** (T4 from source only) and on the right one big button with the step's name, the time so far
and about how long it still takes (from your last build's step times, else from the progress, else the usual
range). If a step prints nothing for two minutes the card says it is still working on it. X opens the build log.

The build tools are never listed. The launcher checks them by itself; when some are missing, **Build** installs them
first with winget ("Installing build tools (x of y): name ..."), checks again and builds. If winget is missing or fails,
the launcher downloads only the remaining tools over HTTPS from their official vendors, without Microsoft Store:
VS 2022 Build Tools from `aka.ms/vs/17/release/vs_BuildTools.exe`, Git from `git-for-windows/git`, CMake from
`Kitware/CMake`, and Ninja from `ninja-build/ninja` GitHub release assets. Signed installers require WinVerifyTrust
and the expected publisher; release SHA-256 digests are checked when available and are mandatory for unsigned Ninja.
The selected digest is pinned before downloading the asset. Unverifiable downloads are never run. The complete
fallback batch uses one Windows permission prompt, rechecks its staged copies before running silent installers, and
suppresses automatic restarts. No new package manager or Store component is installed. A failed install shows the error
with Try again and Help (what is needed, the commands to copy). When Windows needs a restart to finish, the launcher
remembers it and continues the build after the restart. A T4 disc image that was verified stays verified while it is
the same file (path, size, time), also after a launcher restart.

An install made by the launcher belongs to OpenRecomp-FGC: building in it changes no other launcher's game. A T5DR
you installed yourself keeps the coexistence rules (docs/T5DR_COEXISTENCE.md).

## Updates

The launcher looks for new versions a few seconds after it starts (and when you choose **Quick access -> Check
game updates**); answers are kept for an hour. When an update exists, the game's tile shows **UPDATE** or
**UPDATE NEEDED** and the Play / Online / Build sections start with an Update row. **X** on the tile, or the row,
updates. Offline play stays possible without updating.

"Needed" means: the T5DR lobby said so (its announced release, which the game's own online client receives when you
go online, or its "update this game" refusal of an old build), or, when the lobby has said nothing, a newer
release than yours is out. The launcher opens no lobby connection of its own for this.

Updating exchanges only the release's own files, in place, with the old ones kept aside until the new ones are in
(on any failure they come back). Never touched: T5DR's `native` (built game, replays), `launcher.json`, `gamedata`,
`logs`, `keys`, `game`, `build`; T4's `deps`, `game`, `generated`, `out`, `logs`, `build`, `settings.json`.
Close the game first (the update refuses while a program from that folder runs).

- T5DR: when the new release has another Code ID than your build stamp, build again before playing online
  (docs/T5DR_COEXISTENCE.md "One build rule"). After a T5DR update the launcher asks to restart, because it uses
  T5DR's own Python code.
- T4 has no Code ID: when its source files changed, its Play section says **build the game again** until the next
  build finished.

## Test versions

**Quick access -> Test versions: On** also offers published pre-releases (testers; T5DR test builds, and the
launcher's own test builds, see [UPDATES.md](UPDATES.md)). Drafts are never offered. Off (default) = published
`vX.Y.Z` releases only, the same rule as T5DR's own updater, with two exceptions:

- Tekken 4 is in beta and has only pre-releases: its published pre-releases are offered to everyone
  (`SOURCES["t4"].beta`; a launcher update turns that off once T4 has a stable release).
- An install that is itself a test version (installed from a pre-release, or its version has a test suffix)
  keeps getting newer test versions, so a tester is not stuck until the next stable release.

## For developers

`openrecomp/game_releases.py` (download, checks, unpack, update), `game_setup.py` (worker state),
`app_game_setup.py` (backend), `nav_game_setup.py` (rows, dialogs, badge). Tests: `tests/test_game_setup.py`,
`tests/test_game_setup_nav.py` with the fake GitHub in `tests/release_fixtures.py`. Test hook (only for an
address on this PC): `OPENRECOMP_RELEASES_TEST=http://127.0.0.1:<port>` serves the API and files,
`OPENRECOMP_RELEASES_TEST_KEY=<64 hex>` adds a test signing key. `OPENRECOMP_NO_GAME_CHECKS=1` turns the automatic
check off (the launcher's own check too).

T4's release is made by `tools/make_release.py` ([RELEASING.md](RELEASING.md)): `OpenRecomp-Tekken4-<tag>.zip` (the
both-games bundle: the launcher + `T4/`), `SHA256SUMS` and `SHA256SUMS.sig` (T4 key). The launcher also takes another
single `OpenRecomp*/Tekken4*/T4*.zip` with `SHA256SUMS` or `<zip>.sha256`, but always needs the T4 signature. It uses
only the `T4` folder, which must be a complete T4 source tree. A T4 folder that Setup or an older test bundle put
there has no `openrecomp-release.json`, so its version is unknown and no update is offered: install T4 once from
the launcher (a new folder) to get updates.
