# Setup (Windows installer)

`OpenRecomp-FGC-Setup-<version>.exe` installs the launcher for the current Windows user. The zip stays
available as the alternative: unpack it and double-click `OpenRecomp-FGC\run.cmd`, as before.

## What Setup does

- Asks for a folder (default `%LOCALAPPDATA%\Programs\OpenRecomp`, any drive works, for example
  `D:\Games\OpenRecomp`). A chosen folder that already holds other things gets its own `OpenRecomp` folder
  inside. Free space and write access are checked first. No administrator rights: folders that need them
  (Program Files, Windows) are refused with a plain message.
- Puts the launcher into `<folder>\OpenRecomp-FGC` and, when the bundle carries one, the T4 source into
  `<folder>\T4` (only the first time; later the launcher updates T4 itself). T5DR installed from the launcher
  goes into `<folder>\T5DR-Online-<version>`, where the launcher finds it.
- Start menu shortcut `OpenRecomp-FGC` (always) and a desktop shortcut (optional). Both start
  `OpenRecomp-FGC\portable\pythonw.exe -B -m openrecomp` with the launcher's own app ID.
- Apps & Features entry "OpenRecomp-FGC" under `HKEY_CURRENT_USER` (version, size, uninstall).
- Running Setup again updates in place: the folder is fixed to the installed one, files the new version no
  longer has are removed, nothing else is touched. Settings live in `%LOCALAPPDATA%\OpenRecomp`
  (`OPENRECOMP_HOME`), outside the install, so they stay. Setup refuses while the launcher or a game started
  from it runs ("close it, then Retry").
- `<folder>\OpenRecomp-install.txt` lists what Setup placed: an update and the uninstall touch only those files.

## Full Setup (with the games)

`OpenRecomp-FGC-Full-Setup-<version>.exe` is the same program with Tekken 5 DR Online and Tekken 4 inside
(about 300 MB; the small Setup stays for players who want only the launcher). Its window has two more
checkboxes, both on: "Tekken 5 Dark Resurrection Online <version>" and "Tekken 4 <version>, beta".

- What it carries: each game's GitHub release files exactly as published (T5DR Online's own release:
  `T5DR-Online-<v>.zip`, `SHA256SUMS`, `SHA256SUMS.sig`; Tekken 4's: `OpenRecomp-Tekken4-<tag>.zip` and its two
  files), in `bundled-games\<game>\` of the payload. No game data: as always, each game is built once from the
  player's own package / disc image.
- How it installs them: the files are unpacked into Setup's staging folder (never into the install) and checked
  against their SHA-256 like every file. After the launcher is in place, Setup runs the installed launcher's
  `portable\pythonw.exe -B -m openrecomp.bundled_games`, which installs every chosen game exactly as
  "Install" in the launcher does, only from the local files instead of GitHub: the release signature with the
  keys built into the launcher, the zip's line in `SHA256SUMS`, the same unpack rules and the same
  `openrecomp-release.json` marker. T5DR goes to `<folder>\T5DR-Online-<version>`, Tekken 4 to `<folder>\T4`,
  where the launcher finds both: it starts with both games installed and only Build (own files) left.
- A game that is already beside the launcher (any `T5DR-Online-*`, a `T4` folder) is left as it is; the launcher
  offers its updates. Updates of the games keep coming from their own repositories, as after a launcher install.
- A game that cannot be installed (not enough space for it and its build, a damaged file) does not stop the
  launcher's install: Setup shows the launcher's message for it (in the player's language) and the game can be
  installed later from the launcher. The staging folder is removed in every case.
- Command line: `/games=t5dr,t4` (or one of them), `/nogames`; silent exit code 4 = the launcher is installed but a
  game is not (the log has the launcher's message).

## Uninstall

Apps & Features -> OpenRecomp-FGC -> Uninstall (or `<folder>\Uninstall OpenRecomp.exe`). It removes the
launcher files (also those a launcher self-update brought: the update keeps Setup's record current, see
[UPDATES.md](UPDATES.md)), the launcher's update folder `OpenRecomp-FGC.update`, the shortcuts and the Apps entry. It never removes `T4`, `T5DR-Online-*`, builds or saves.
It then asks whether to remove OpenRecomp-FGC's own settings (`config.json`, pictures from the player's builds,
the player's game manifests, private T5DR preferences and saved logins). T4 saves (`t4-source\*\save`) and
registered game zips (`installs\`) stay either way. The uninstaller copies itself to `%TEMP%` to be able to
delete itself; that small copy stays there (Windows' disk cleanup removes it).

## Building it

```text
python tools\make_installer.py --bundle dist\openrecomp-fgc-test-<time>.zip [--version 0.1.0] [--out dist]
```

The input is the bundle zip from `tools\make_test_bundle.ps1` (its scans stay the content gate). The tool
compiles `tools\installer\setup.cpp` twice with the Visual Studio 2022 Build Tools (cl, rc, link; `/O2 /MT
/GS /guard:cf`, `/DYNAMICBASE /NXCOMPAT /GUARD:CF`): once as the uninstaller, once as Setup with the payload.
The payload is our own format: every file compressed with the Windows Compression API (LZMS or XPRESS
Huffman, whichever is smaller, else stored) with its SHA-256; Setup unpacks and checks every file into a
staging folder beside the install before it moves anything in. No installer framework, no packer, nothing is
downloaded; version information and an `asInvoker` manifest are in the program. It prints the sizes and the
SHA-256 and writes `<setup>.sha256`. The program is not signed: check it on VirusTotal before handing it out.

Command line: Setup `/S /D=<folder> /desktop /nodesktop /nostart /lang=<en|de|es|fr|ja|ko|pt> /log=<file>`;
Uninstall `/S /removesettings /keepsettings /lang=.. /log=<file>`. Exit codes: 0 done, 1 cancelled, 2 failed,
3 the launcher still runs (silent mode). Texts: the 7 launcher languages, from the Windows display language.

## Checked

`tests\test_installer.py` (payload round trip and damage, bundle refusals, all texts in 7 languages, per-user
manifest; `OPENRECOMP_SETUP_BUILD_TEST=1` also compiles). The full install / shortcut start / update / uninstall
walk was run on a second drive with a scratch `OPENRECOMP_HOME` (see the agent notes). Not checked: a clean
Windows PC, SmartScreen and antivirus on other PCs, a path with non-ASCII characters by hand, 150 % scaling.

## Games from the launcher

Setup installs the launcher (and, from a bundle that carries it, the T4 source). Installing and updating T5DR
Online and T4 themselves happens in the launcher: see [GAME_SETUP.md](GAME_SETUP.md). Both put the games beside
`OpenRecomp-FGC` by default, so Setup's update and uninstall never touch them.
