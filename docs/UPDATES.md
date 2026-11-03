# Signed launcher updates

OpenRecomp-FGC updates itself from the signed releases of
[TheWishin/OpenRecomp-FGC](https://github.com/TheWishin/OpenRecomp-FGC/releases). Games and the player's
settings are not part of a launcher update; the games update from their own releases
([GAME_SETUP.md](GAME_SETUP.md)).

For a gradual move from T5DR Online 1.1.9, use the separate
[coexistence and private update-drill guide](T5DR_COEXISTENCE.md). Its headless
`tools/update_drill.py` checks an explicitly supplied settings-folder copy;
it does not run this signed update transaction or qualify a packaged release.

## The release channel

Built into `openrecomp/updater.py`:

| | |
| --- | --- |
| `RELEASE_REPOSITORY` | `TheWishin/OpenRecomp-FGC` |
| `RELEASE_REPOSITORY_ID` | `1439720330` (GitHub's numeric ID; release downloads must come from that ID's storage) |
| `RELEASE_CHANNEL` | `openrecomp-fgc` |
| `RELEASE_PUBLIC_KEYS` | one Ed25519 key, key id `240b33a1229ca79b` |

The private key never enters a repository, a package, a chat or a log. How it is kept, backed up and
replaced: [RELEASE_KEYS.md](RELEASE_KEYS.md). With an empty or incomplete channel the launcher checks
nothing and installs nothing; there is no unsigned fallback.

## What a release contains

`tools/make_release.py` makes every file ([RELEASING.md](RELEASING.md)):

* `OpenRecomp-vX.Y.Z.zip`: the `OpenRecomp-FGC/` program folder (launcher source, its private
  `portable/` Python and Qt, `run.cmd`, `release.json`) and the start texts beside it.
* `OpenRecomp-FGC-Setup-X.Y.Z.exe`: Setup, built from exactly that zip.
* `SHA256SUMS`: both files, one `<sha256>  <name>` line each.
* `SHA256SUMS.sig`: JSON `{algorithm: ed25519, channel, version, key_id, signature}`; the signed bytes are

```
OpenRecomp-FGC release signature v1\n<channel>\n<tag>\n<exact SHA256SUMS bytes>
```

`release.json` names `project: openrecomp-fgc`, the channel and the same tag.

## Stable and test versions

Everyone gets published plain `vX.Y.Z` releases (GitHub's "latest release"). **Quick access -> Test
versions: On** (the same switch as for the games) also offers published pre-releases tagged
`vX.Y.Z-<test>` (for example `v0.2.0-beta.1`): the newest of the last 30 releases. A test tag must be marked
pre-release on GitHub and a pre-release must have a test tag, so a stable player is never offered a test build.
Order: `v0.2.0-beta.1 < v0.2.0-beta.2 < v0.2.0-rc.1 < v0.2.0`. Drafts never. Turning the switch off offers
the next stable release that is newer than the installed test version.

## When it checks

A few seconds after the start (together with the game checks; `OPENRECOMP_NO_GAME_CHECKS=1` turns both off),
when the Test versions switch changes, and on **Quick access -> Check for launcher updates**. The automatic
check says nothing unless there is an update; then the update dialog opens once (not during a game, build
or online session). No release published yet counts as up to date.

## Verification and installation

Every download and redirect is restricted to HTTPS, this repository's release URLs and GitHub's storage
for its numeric ID. The zip must match the signed checksum and GitHub's own digest and size. A wrong key,
another channel or version, a changed zip or checksum changes no installed file.

The player confirms the offered update. The launcher unpacks it beside the installation
(`OpenRecomp-FGC.update\<transaction>\new`), checks every path (no links, devices, traversal, duplicates;
only the program items `portable openrecomp games docs LICENSE README.md requirements.txt run.cmd
release.json`), copies its private Python interpreter (not Qt) into the transaction and starts the copied
updater, then quits. The helper waits until no program from the installation runs, authenticates the
retained zip, signature and every staged file again, renames the program items into place on the same
drive and starts the new launcher the way Setup's shortcut does
(`portable\pythonw.exe -B -m openrecomp`, the same switches such as `--windowed`). The new launcher
confirms a healthy start after 15 seconds; a failed move, start or confirmation puts the old program back
and starts it.

After a confirmed update:

* Setup installs (`OpenRecomp-install.txt` beside `OpenRecomp-FGC`): the record lists the new program's
  files, so the uninstall and the next Setup remove exactly these; Apps & Features and Setup's own key show
  the new version. A zip install has no record and nothing changes.
* The next start says "Launcher updated to vX.Y.Z" and removes finished update folders (10 minutes after
  their result was shown). A folder that needs recovery, or a helper's lock, is never removed.

Player data in `OPENRECOMP_HOME` (default `%LOCALAPPDATA%\OpenRecomp`: settings, saved logins, imported
games) is never moved. Updating refuses an `OPENRECOMP_HOME` inside a program item. Free space is needed for
the zip, the staged program, the old backup and the copied interpreter.

An `apply.lock` folder in `OpenRecomp-FGC.update` serializes helpers through the swap and any rollback. An
interrupted helper or an unresolved recovery leaves it: close all launcher and helper processes, restore
the transaction's `backup` if needed, then remove the empty `apply.lock`.

## Test hook

Never for players: `OPENRECOMP_RELEASES_TEST=http://127.0.0.1:<port>` makes the launcher and the game
installer ask a fake GitHub on this PC (API under `/repos/...`, files under `/<repo>/releases/download/...`,
storage under `/storage/<id>/...`); `OPENRECOMP_RELEASES_TEST_KEY=<64 hex>` adds a test public key. Both are
ignored for any other address. Tests: `tests/test_updater.py`, `tests/test_release_updates.py` (fake GitHub in
`tests/release_fixtures.py`).

## Not covered by the automatic checks

A clean Windows PC without Python, SmartScreen and antivirus on other PCs, network proxies, and a real
GitHub release (the first one is checked by hand after publishing, see [RELEASING.md](RELEASING.md)).
