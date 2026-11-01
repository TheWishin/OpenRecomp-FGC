# Launcher installation and owner checks

The release zip is designed to include its own Python 3.12 and PySide6. Players extract the
whole zip to a writable folder and open `OpenRecomp.exe`. They do not install Python or run
`run.cmd`; that command remains for development checkouts. The native starter and private
runtime must be prepared separately before the offline packaging tool can assemble a release.
No release binary or zip was built or packaged during this implementation.

For the owner/colleague T4 test bundle, the maintainer instead runs
`tools\make_t4_test_bundle.ps1` once in Windows PowerShell. It downloads and
checks the pinned portable runtime before assembling the source test ZIP.
Extract the entire test ZIP, keep `OpenRecomp-FGC/` beside `T4/`, and double-click
`OpenRecomp-FGC/run.cmd`. Its `portable/` runtime needs no separate installation
or first-start dependency download. The source-checkout fallback in `run.cmd`
still creates `.venv` when no portable runtime is present. This test bundle has
no native `OpenRecomp.exe`; see [PACKAGING.md](PACKAGING.md) and the German
[test-bundle walk](T4_FIRST_RUN.md).

This release candidate is a T4 beta: offline play plus online by direct IP or
VPN, with no lobby and no ranked. Lobby-based T4 online remains hidden until its
server exists. T5DR's Online section uses its installed lobby client; the
old T5DR Online launcher remains available. See [T5DR_ONLINE.md](T5DR_ONLINE.md)
for its controller screens and acceptance checks. A Sunday release depends on the owner's successful
two-PC test; see [T4_ONLINE.md](T4_ONLINE.md).

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

Selecting the first T5DR install refreshes the PlayStation controller reader immediately.
If a different T5DR install's native modules are already loaded, selecting another install
can require restarting OpenRecomp. Origin checks refuse to reuse modules from the old
install; native modules are not unloaded. The old controller reader is paused and removed
instead of continuing to read from the previous install.

The pad's Quick access button opens launcher preferences and **Check for launcher updates**.
An update offer shows its version, archive bytes and release-note preview. **No** is selected
initially. Choosing **Install and restart** downloads and verifies the release and hands off
to a separate helper. Games, builds, support work and online sessions must be closed before
installation. Confirmation requires QML to load and its event loop to reach the 15-second
timer; this is a limited startup check, not a test of every workflow. A missing confirmation
attempts rollback to the prior version. See [UPDATES.md](UPDATES.md) for recovery limits.

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
and language at 1080p and Windows 150% scaling, including the pre-Python startup failure
message. Complete the host/join/check/start/log-collection/Back walk on two physical PCs.
No real install was opened
and no game was started while implementing these changes.

On a private test release channel, exercise valid updates, a foreign project's zip, changed
checksum/signature, wrong channel, a prerelease tag, an occupied install, failed startup and
rollback. Verify that the previous launcher reopens, the rollback message appears and player
settings/game installs remain intact. Windows process handles, file locks, antivirus and
actual native executable behavior require these real-machine checks in addition to fakes.
