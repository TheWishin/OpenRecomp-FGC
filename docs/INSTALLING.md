# Launcher installation and owner checks

The release zip is designed to include its own Python 3.12 and PySide6. Players extract the
whole zip to a writable folder and open `OpenRecomp.exe`. They do not install Python or run
`run.cmd`; that command remains for development checkouts. The native starter and private
runtime must be prepared separately before the offline packaging tool can assemble a release.
No release binary or zip was built or packaged during this implementation.

The starter sets `OPENRECOMP_HOME` to the per-user local application data folder's
`OpenRecomp` directory unless the player already supplies an override. Configuration, game
manifests, locally extracted T4 installs and player-created pictures belong there. Keep an
override outside the launcher program directories. Updating replaces only launcher program
items and preserves that user directory and registered external game installs.

## First start and T4

No installed game is required to open the launcher. T4 is the first shelf item. Select it
with the D-pad and confirm to open the folder picker. Browse the drive and folder rows with
the pad. Inside the player's own T4 release folder, choose **Use this folder** (translated
in the player's language), or select its original release `.zip`. The adapter looks for
`launcher/t4core.py`, either directly or inside one enclosing release folder.

A chosen zip is checked before extraction and extracted under `OPENRECOMP_HOME`, never into
the launcher. An installed T4 is used in place. The adapter loads that install's own launcher
core at runtime; OpenRecomp does not supply a game, an ISO, a build, keys or game pictures.
If T4 still needs to be built from the player's own copy, its Build section explains the
requirements through the installed core. Registration itself never builds or starts a game.

The pad's Quick access button opens launcher preferences and **Check for launcher updates**.
An update offer shows its version, archive bytes and release-note preview. **No** is selected
initially. Choosing **Install and restart** downloads and verifies the release and hands off
to a separate helper. Games, builds, support work and online sessions must be closed before
installation. A new launcher must stay healthy for 15 seconds to confirm the transaction;
failure restores the prior version. See [UPDATES.md](UPDATES.md).

## Owner decisions before a release

- Choose this project's unique release channel name and GitHub release repository/numeric ID.
- Supply this project's release signing public key in the launcher. Keep the private signing
  key outside this public repository. Empty trust settings deliberately disable updates and
  refuse packaging; T4 and T5DR release channels and signing keys are independent.
- Prepare the reviewed private runtime, native starter, full license notices and exact
  corresponding Qt/PySide6/shiboken6 source archives described in [PACKAGING.md](PACKAGING.md).

The release tool reports `zip_bytes` and `unpacked_bytes` only after it actually assembles an
archive. This implementation has no measured shipment size. Publishing, signing a real
release, downloading dependencies and compiling the starter remain owner-run work.

## Clean Windows PC acceptance checks still required

Use a Windows 10/11 account with no Python, Qt or developer tools installed and a plain
user-writable extraction folder. Check the native starter, all private Qt/QML plugins and
fonts, first start with no games, a path containing spaces and non-ASCII characters, and
moving the extracted launcher to a second folder. Check both default data storage and an
`OPENRECOMP_HOME` override, with preferences surviving relocation and a signed update.

Use a controller alone to register a player's own T4 folder and its original release zip,
then check play/build handoff through that install's core. Check every supported controller
and language, including the pre-Python startup failure message. No real install was opened
and no game was started while implementing these changes.

On a private test release channel, exercise valid updates, a foreign project's zip, changed
checksum/signature, wrong channel, a prerelease tag, an occupied install, failed startup and
rollback. Verify that the previous launcher reopens, the rollback message appears and player
settings/game installs remain intact. Windows process handles, file locks, antivirus and
actual native executable behavior require these real-machine checks in addition to fakes.
