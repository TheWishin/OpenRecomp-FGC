# Signed launcher updates

The updater is implemented, but production updates remain disabled until the owner chooses
the release channel and public signing key. No T4 or T5DR release can be used as a launcher
update. Game installations and the player's settings are outside the program transaction.

## Owner decisions before the first release

Set these constants in `openrecomp/updater.py`, review them, and include them in the initial
package:

* `RELEASE_REPOSITORY`: the launcher's own GitHub `owner/repository`.
* `RELEASE_REPOSITORY_ID`: that repository's immutable numeric ID.
* `RELEASE_CHANNEL`: a unique stable channel name, chosen for this launcher only.
* `RELEASE_PUBLIC_KEYS`: the launcher's Ed25519 public key, 64 lowercase hexadecimal digits.

Use a new launcher key. Never reuse a game's key. Empty or incomplete trust configuration
disables checks and installation; there is no unsigned fallback. Public keys are public;
private keys must never enter the repository, package, chat or logs.

The offline `tools/release_sign.py` tool uses Python's standard library. The owner can run
`keygen --out <private-file-outside-checkout>` once, then `public-key --key-file <private-file>`.
It refuses private key paths inside the checkout and never overwrites a key. Keep a separate
offline backup. The tool prints only the public key and its ID. No key was generated as part
of implementing this feature.

After packaging, the owner runs:

```
python tools/release_sign.py sign --key-file <private-file> --channel <chosen-channel> --version vX.Y.Z --sums <SHA256SUMS> --out <SHA256SUMS.sig>
```

Publish the zip, `SHA256SUMS`, and `SHA256SUMS.sig` together in the launcher's own release.
Release tags must be exactly `vX.Y.Z`, with no preview suffix, build metadata, capital V or
leading zeroes. Drafts and prereleases are refused. The package's `release.json` must identify
`project: openrecomp-fgc`, the exact channel, and the same version. The archive and top folder
are both named `OpenRecomp-vX.Y.Z` (the archive adds `.zip`).

## Verification and installation

Checks ask only the configured repository's latest release. Every download and redirect is
restricted to HTTPS and that repository's release URLs or numeric GitHub asset-storage ID.
The archive must match both the signed SHA-256 checksum and GitHub's API digest and size.
Signatures bind this launcher project, channel, version and exact checksum-file bytes. An
unsigned release, a foreign channel, an invalid signature or a checksum mismatch changes no
installed files. Downloads, metadata and extraction have bounded sizes.

The signature envelope is JSON with `algorithm: ed25519`, `channel`, `version`, `key_id`
(the first 16 hexadecimal characters of SHA-256 of the public key), and `signature`
(128 hexadecimal characters). The signed bytes are:

```
OpenRecomp-FGC release signature v1\n<channel>\n<vX.Y.Z>\n<exact SHA256SUMS bytes>
```

The player explicitly confirms an offered update. A copied private Python runs the old
updater beside the installation, waits until the launcher exits and no program from the
installation is running, then renames program files on the same drive. The archive permits
only the program items listed in `PROGRAM_ITEMS`, rejects unsafe Windows paths, duplicate
names, links and special files, and validates the staged manifest before swapping.

The transaction retains the downloaded archive and exact signed checksum and signature
files. Worker preparation verifies their signature context and the archive hash, then
compares the staged file and directory set and every staged file's hash with the
authenticated archive. Runtime copying and hashing run in the update worker. The UI
checks that it is still safe to quit before starting the prepared helper. After the
launcher exits, the helper repeats authentication, checks that the target is still an
upgrade, and checks for running installation processes again before moving program files.
These checks detect intervening changes when verification runs; they do not protect
against a malicious process with the same user's permissions changing files between the
last check and a rename, or tampering with the installed updater itself.

The new launcher schedules confirmation after QML loads and its event loop reaches
a timer after 15 seconds. This checks scene loading and event-loop survival; it does
not verify every screen, controller input or adapter. A failed
move, start, early exit or missing confirmation restores the previous program and restarts
it. Existing backups are retained beside the installation for recovery. If restoring a
locked file itself fails, the backup is retained; close programs using the folder before
manual recovery. A killed helper, power loss or machine crash during renames can also need
manual recovery from that backup. This is a rollback mechanism, not a crash-proof filesystem
transaction.

An `apply.lock` directory in `<installation>.update` beside the installation,
alongside the transaction folders, serializes helpers for that installation through the
swap and any rollback. A second helper refuses to proceed while the lock exists.
Successful completion or a completed rollback removes it. An interrupted helper
or unresolved recovery leaves it in place to prevent another update from moving
files before recovery is reviewed. Close all launcher and update-helper processes,
review the transaction's backup and restore the previous program as needed, then
remove the empty `apply.lock` directory before retrying. Do not remove the lock
while a helper may still be working, and retain the transaction and backup until
recovery is complete.

Player data in `OPENRECOMP_HOME` is never moved. Other unrecognized files in the installation
are kept too. Updating refuses an `OPENRECOMP_HOME` that overlaps a program item. The launcher
must not be installed into its own player-data directory. Sufficient space is needed for the
archive, staged program, old backup and copied helper runtime.

For planned key rotation, ship both public keys in an update signed by the old key, then
ship the next update signed by the new key and remove the old public key. Losing the old
private key before that transition requires one manual launcher installation. Changing a
channel or repository similarly needs a deliberately reviewed transition release.

## Verification still required

Tests use fake releases, inert files and processes, plus an RFC 8032 verification vector.
Filesystem swap tests exercise real temporary-file moves with injected process and
restart behavior; the service tests replace the updater API and do not independently
verify signature checking or installation. Source-string assertions about the starter
are not a test of its compiled behavior.
They do not exercise a public release, a real packaged executable, Windows process locking,
network/proxy behavior or a clean PC. Before release, test on a clean Windows PC without
Python: extraction into a moved folder, first start with no game, controller-only operation,
settings preservation, a valid signed update, wrong-channel and tampered updates, a failed
start and rollback. No package was built or measured during this task.
