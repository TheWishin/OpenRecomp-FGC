# Installing and updating the games from the launcher

OpenRecomp-FGC can download and update the two fighting games' own programs. It never downloads game data:
you still bring your own Tekken 5 DR package + license and your own Tekken 4 disc image, and the game is built on
your PC as before.

| Game | Comes from | What is downloaded |
| --- | --- | --- |
| Tekken 5 DR Online | github.com/TheWishin/T5DROnline, releases | `T5DR-Online-X.Y.Z.zip`, `SHA256SUMS`, `SHA256SUMS.sig` |
| Tekken 4 | github.com/TheWishin/Tekken4Recomp, releases | the release's launcher zip; only its `T4` folder is used |

## Install

Select a game tile that says **Install or choose folder** and confirm. The game's Build section opens with
**Install Tekken 5 DR Online** (or **Install Tekken 4**) first; the old "choose the folder you already have" stays
below it. Install looks up the newest release, then asks where: the default is beside OpenRecomp-FGC's own folder
(where Setup put it), **Other folder** picks any drive or folder. Before anything is downloaded the launcher checks
free space (download + unpacked files + room for the build) and that it can write there.

The download is checked like T5DR's own updater does: only this project's GitHub addresses, `SHA256SUMS` must name
the zip and agree with GitHub's digest, and for T5DR the release signature (Ed25519, T5DR's release key; an
installed T5DR's own key list counts too) must be valid. Every path in the zip is checked before it is written; the
files are unpacked into a staging folder beside the target and moved in at the end, so a failed or cancelled
install leaves nothing behind. Afterwards the launcher attaches the new install and opens its Build section:
choose your own package/license (T5DR) or disc image (T4) and build.

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

**Quick access -> Test versions: On** also offers published pre-releases (testers; T4's beta, T5DR test builds).
Drafts are never offered. Off (default) = published `vX.Y.Z` releases only, the same rule as T5DR's own updater.

## For developers

`openrecomp/game_releases.py` (download, checks, unpack, update), `game_setup.py` (worker state),
`app_game_setup.py` (backend), `nav_game_setup.py` (rows, dialogs, badge). Tests: `tests/test_game_setup.py`,
`tests/test_game_setup_nav.py` with the fake GitHub in `tests/release_fixtures.py`. Test hook (only for an
address on this PC): `OPENRECOMP_RELEASES_TEST=http://127.0.0.1:<port>` serves the API and files,
`OPENRECOMP_RELEASES_TEST_KEY=<64 hex>` adds a test signing key. `OPENRECOMP_NO_GAME_CHECKS=1` turns the automatic
check off.

T4 has no published release yet: the launcher takes the release's one zip named like `OpenRecomp-Tekken4-<tag>.zip`
(or another single `OpenRecomp*/Tekken4*/T4*.zip`) with `SHA256SUMS` or `<zip>.sha256`, and uses its `T4` folder,
which must be a complete T4 source tree. If the T4 release looks different, change `SOURCES["t4"]`.
