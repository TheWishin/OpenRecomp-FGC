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
