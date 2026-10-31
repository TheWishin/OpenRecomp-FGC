# Launcher distribution and updates

The release is a Windows x64 zip with a native `OpenRecomp.exe`, a private CPython
3.12, PySide6 Essentials 6.8.2.1, shiboken6 6.8.2.1 and the launcher source.
Players extract the entire zip and run the executable; Python installation,
administrator access and a game installation are not prerequisites. Keep the
install in a player-writable folder so an update can rename it on the same drive.
The starter resolves its own directory, starts only its private `pythonw.exe`
with isolated Python and forwards arguments. It does not search PATH or start a
game. Settings, imported manifests and artwork belong under `OPENRECOMP_HOME`
(default `%LOCALAPPDATA%\OpenRecomp`), separate from the replaceable program.
Do not set that variable inside the program directory.

The native starter is supplied as source, ready for the maintainer's compiler;
no executable has been built or tested as part of this change. No release was
packaged. There is no measured
download or installed size yet. `package_release.py` prints `zip_bytes` and
`unpacked_bytes` only after assembling the actual payload. Publish those measured
facts, never an estimate based on the development environment.

## Offline preparation by the maintainer

The tool neither downloads dependencies nor invokes a compiler. Before running
it, prepare reviewed offline inputs in a separate release workspace. Never place
game data, player information, keys, executable game code or screenshots in this
repository. No installed virtual environment is accepted as a runtime input.

Before preparing a payload, check this source tree without a runtime, starter,
download, compiler or game:

    .venv\Scripts\python.exe tools\package_release.py --scan-only

This validates the launcher source selection and scans the selected files. It
does not assemble an archive or prove that separately prepared runtime inputs
are complete. Ship the README and T4 first-run/online guides with the launcher:
the beta is offline plus direct IP/VPN only, with no lobby and no ranked. The
T4 portable release remains a separate player-selected install; never bundle it
or a built game into this launcher's zip. T5DR Online opens the old launcher.

1. Supply the official Windows CPython 3.12 embeddable distribution, including its
   standard-library `python312.zip`, `python312.dll`, `pythonw.exe` and required
   runtime DLLs. Unpack the pinned PySide6 Essentials and shiboken6 wheels into
   `Lib/site-packages`. Preserve the Qt QML modules, plugins, fonts, resources and
   notices needed by this application. Exclude development executables, tests,
   pip, scripts and unrelated packages. Only the two pinned package dist-info
   directories are accepted. The packager writes its own relative
   `python312._pth`; do not supply one in the input.
2. Compile the MIT starter source using a Windows SDK/MSVC developer prompt:

       cl /nologo /O2 /W4 /DUNICODE /D_UNICODE tools\starter\openrecomp.c /link /SUBSYSTEM:WINDOWS /OUT:<workspace>\OpenRecomp.exe shell32.lib user32.lib

   This is a maintainer command, not a command run by the packaging tool. The
   supplied file must have a PE header and match the reviewed inventory hash.
   Optional Windows publisher signing is distinct from the mandatory Ed25519
   release signature; signing a release checksum does not add a publisher name
   to the executable.
3. Prepare the license directory described below. Build a reviewed inventory
   containing the SHA-256 of every input file. The tree must match it exactly;
   additions, missing files and changed bytes stop packaging. Audit the input
   distributions and their origins before approving those hashes. An inventory
   is an operator trust boundary, not evidence of authenticity by itself.
4. The owner chooses a unique project release channel and this project's signing
   key. Configure only public keys in the launcher updater. Never reuse another
   project's channel or signing key. The packager refuses an unconfigured updater
   or a channel different from its embedded trust. Follow `UPDATES.md` for the
   signed checksum format, signing and rollback procedure.
5. Explicitly run, after those reviews:

       .venv\Scripts\python.exe tools\package_release.py --runtime <runtime> --starter <workspace>\OpenRecomp.exe --licenses <licenses> --inventory <inventory.json> --out <output> --version v1.0.0 --channel <chosen-channel>

The inventory JSON has these fields (all placeholder hashes must be replaced):

```json
{
  "python": "3.12",
  "pyside6": "6.8.2.1",
  "starter_sha256": "<64 lowercase hex digits>",
  "runtime": {
    "pythonw.exe": "<sha256>",
    "python312.dll": "<sha256>",
    "python312.zip": "<sha256>",
    "Lib/site-packages/PySide6/__init__.py": "<sha256>"
  },
  "licenses": {
    "LGPL-3.0.txt": "<sha256>",
    "GPL-3.0.txt": "<sha256>",
    "Qt-NOTICES.txt": "<sha256>",
    "PySide6-NOTICES.txt": "<sha256>",
    "shiboken6-NOTICES.txt": "<sha256>",
    "Python-LICENSE.txt": "<sha256>",
    "REPLACEMENT.txt": "<sha256>",
    "sources/qt-6.8.2.tar.xz": "<sha256>",
    "sources/pyside6-6.8.2.1.tar.xz": "<sha256>",
    "sources/shiboken6-6.8.2.1.tar.xz": "<sha256>"
  },
  "sources": {
    "Qt": {"version": "6.8.2", "path": "sources/qt-6.8.2.tar.xz"},
    "PySide6": {"version": "6.8.2.1", "path": "sources/pyside6-6.8.2.1.tar.xz"},
    "shiboken6": {"version": "6.8.2.1", "path": "sources/shiboken6-6.8.2.1.tar.xz"}
  }
}
```

This example abbreviates the runtime map: list **every** supplied file, including
Qt plugins and DLLs, shiboken6 and dist-info. The license map must likewise list
every file, including third-party notices and any additional source archives.
Source archive entries identify reviewed complete corresponding source; renaming
an unrelated archive does not meet the distribution duties. When updating the
pinned libraries, update the version gates, inventory and source together.

The output is `OpenRecomp-vX.Y.Z.zip` containing one `OpenRecomp-vX.Y.Z/` folder,
and `SHA256SUMS`. It refuses overwrites. `release.json` binds project, version and
channel. Only launcher source/assets and built-in JSON manifests are selected;
game install locations in those manifests must be empty. Runtime binaries are
separate, hash-inventoried inputs. Symlinks, junctions, archive traversal, Windows
path aliases, known game image/executable headers, game/player folders, game
extensions, private-key markers and personal paths are refused. That scan is
defense in depth: an approved runtime inventory and human payload review remain
required, since no filename scanner proves arbitrary bytes are not game data.

## LGPL distribution duties

Use the LGPL distribution of Qt, PySide6 and shiboken6; do not accidentally ship
commercial-only or GPL-only modules without addressing their terms. The launcher
loads DLLs dynamically and ships its Python/QML source. Keep all library DLLs,
plugins and Python packages replaceable. Do not freeze, encrypt, statically link,
or add a check that prevents a player using compatible modified Qt/PySide6 files.
Release verification protects the downloaded update and is not a startup library
integrity restriction. Permit reverse engineering for debugging modifications to
these libraries; do not impose a conflicting end-user license.

The release gate requires the full LGPLv3 and GPLv3 texts, component copyright
notices and third-party notices, the Python license, replacement instructions and
the exact Qt/PySide6/shiboken6 corresponding source archives alongside the binary
in `LICENSES/`. Include build scripts, patches, configuration and installation
information needed to rebuild any modified covered libraries; identify whether
the libraries are unmodified. A source URL alone is not this tool's compliance
strategy. Keep the reviewed original archives and provenance with the release.
The maintainer must review the actual chosen wheel's notices and dependencies;
the tool checks presence and hashes, not the legal completeness of prose or an
archive's contents. Compressed corresponding-source archives are trusted
reviewed inputs: their inner files are not exhaustively classified by the game
scanner. Embedded standard-library archive members are path/size checked and
streamed through the header/key scanner without extraction. Font OFL notices
travel with launcher fonts.

`LICENSES/REPLACEMENT.txt` must explain: close the launcher, retain a backup,
replace compatible PySide6/shiboken6 packages under `python/Lib/site-packages`
and their Qt DLLs/plugins, then restart `OpenRecomp.exe`. Replace the matching
component set together. Self-updates install the release's library set again;
keep modified copies and reapply them afterwards. No vendor lock prevents that.

## Clean-PC checks still required

Use a Windows PC without Python and without a game: extract into a directory
containing spaces/non-ASCII characters, launch the real executable, and verify
Qt QML/plugin loading, controller-only first-run folder selection and user-data
placement. Move the extracted directory and run again. Test denied install-folder
write access as a clear update failure. Install a signed project update with fake
game adapters, confirm only after the new UI is healthy, then force early exit
and interrupted swap to verify rollback. Verify settings/artwork/manifests survive.
Review each release's actual archive contents and license/source payload before
publication. None of these native/runtime checks is replaced by the fake tests.
