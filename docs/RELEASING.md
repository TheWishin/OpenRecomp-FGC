# Making a release (launcher and Tekken 4)

One command makes every file of an OpenRecomp-FGC release and of the matching Tekken 4 release. It uploads,
pushes and tags nothing.

## Before

* The launcher commit is final, `openrecomp/__init__.py` `__version__` is the new version without `v`, the
  checkout has no uncommitted changes, and the commit carries the tag (`git tag vX.Y.Z`).
* The portable runtime is fetched and verified once: `powershell -NoProfile -File
  tools\fetch_portable_runtime.ps1` (pinned archives, see [PACKAGING.md](PACKAGING.md)), or pass
  `--runtime/--runtime-cache` of a verified one.
* Visual Studio 2022 Build Tools (C++) for Setup.exe ([INSTALLER.md](INSTALLER.md)).
* The two private key files ([RELEASE_KEYS.md](RELEASE_KEYS.md)).
* The Tekken 4 source commit (US line, SLUS-20328) in a Tekken4Recomp checkout.

## The command

```
python tools\make_release.py --version v0.1.0 --t4-tag v0.1.0 ^
    --t4-repo <Tekken4Recomp checkout> --t4-ref <T4 commit> ^
    --launcher-key <keys>\openrecomp-release\openrecomp-fgc-release.key ^
    --t4-key <keys>\tekken4-release\tekken4-release.key [--out <folder>]
```

`--rehearsal` builds from an untagged commit for a dry run (the notes then say "do not publish").
`--t4-stable` marks the T4 release as a full release in the printed commands (default: pre-release).

Output (default `dist\release-<version>`, never overwritten):

| Folder | Files | GitHub release |
| --- | --- | --- |
| `launcher\` | `OpenRecomp-vX.Y.Z.zip`, `OpenRecomp-FGC-Setup-X.Y.Z.exe`, `SHA256SUMS`, `SHA256SUMS.sig` (+ `NOTES.md`) | tag `vX.Y.Z` of TheWishin/OpenRecomp-FGC |
| `t4\` | `OpenRecomp-Tekken4-<tag>.zip`, `SHA256SUMS`, `SHA256SUMS.sig` (+ `NOTES.md`) | `<tag>` of TheWishin/Tekken4Recomp |

plus `COMMANDS.txt` (the `gh` commands for both releases) and `release-facts.json` (commits, sizes, SHA-256).

### With the games inside: `--full`

```
python tools\make_release.py ... --full --t5dr-release <folder> [--t4-release <folder>]
```

adds `OpenRecomp-FGC-Full-Setup-X.Y.Z.exe` to `launcher\` (and to its signed `SHA256SUMS`): the same Setup with
Tekken 5 DR Online and Tekken 4 inside. `--t5dr-release` is a folder with exactly T5DR's published release files
(`T5DR-Online-<v>.zip`, `SHA256SUMS`, `SHA256SUMS.sig`, downloaded from its GitHub release). Tekken 4's are the ones
this run makes in `t4\`, or exactly the files in `--t4-release` (an already published T4 release). The files go
into Setup unchanged; Setup's checkboxes "Tekken 5 DR" and "Tekken 4" (both on) let the installed launcher install
them with its own release checks ([INSTALLER.md](INSTALLER.md) "Full Setup"). Before the full Setup is kept, the
tool checks T5DR's signature with the launcher's built-in key, scans its zip for this PC's private words, installs
both games from exactly those files the way Setup's launcher does and checks that the launcher finds them, and
checks the full Setup's payload: the launcher zip's folder + the six release files, byte for byte, nothing else.
It stays below GitHub's 2 GiB limit per file (about 300 MB with T5DR 1.2.0 and T4 0.1.0). The small Setup and
the zip stay as they are; updates afterwards still come per game from their own repositories.

What it does: exports the tagged launcher commit and the T4 commit with `git -c core.autocrlf=false archive`
(the committed bytes); builds the launcher zip (`OpenRecomp-FGC/` with `release.json`) and the T4 zip (the
same launcher + `T4/`) with the bundle scanners (source catalogs, pinned runtime, this PC's private words);
builds Setup.exe from the launcher zip; writes and signs both `SHA256SUMS`; then checks everything the way a
player's launcher does, with the keys built into it: signature, checksums, every path of the program folder,
`release.json`, Setup's payload = the zip's folder, the T4 zip's `T4/` folder through the game installer's own
unpack. Any failure removes the half-made files.

## Publishing

1. Push the launcher commit and its tag, then run the `gh release create ... --draft` lines from
   `COMMANDS.txt`.
2. VirusTotal check of `OpenRecomp-FGC-Setup-X.Y.Z.exe` (unsigned program).
3. Publish the launcher draft as a normal release (not pre-release). Launchers offer only published plain
   `vX.Y.Z` releases to everyone; a test build is tagged `vX.Y.Z-<test>` and published as a pre-release
   (players with Test versions on get it).
4. Tekken 4: TheWishin/Tekken4Recomp needs at least one commit on `main` (a README is enough; the T4 source
   travels in the zip, the release notes name its commit). Create the release from `COMMANDS.txt`
   (`--target main`) and publish it. While Tekken 4 is in beta (`SOURCES["t4"].beta`), launchers offer its
   published pre-releases to everyone; drafts never.
5. Check (read only): `gh api repos/TheWishin/OpenRecomp-FGC/releases/latest` names the tag and the four files;
   a launcher of the previous version offers the update a few seconds after its start.

The first launcher release (v0.1.0) has no predecessor that updates to it: players install it with Setup or
the zip. Every later release is offered to them in the launcher.
