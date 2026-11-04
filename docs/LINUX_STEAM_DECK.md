# OpenRecomp-FGC on Linux and the Steam Deck (Proton, Wine)

OpenRecomp-FGC is a Windows program (Python 3.12 + Qt 6.8 / QML). On Linux and the Steam Deck it can run through
**Proton** (Steam) or **Wine**. **We have not tried it**: no Linux PC, no Steam Deck. This page comes from reading
the launcher's code against what Wine and Proton do. Reports are welcome ([checklist](#test-checklist)).

Each game has its own page too:

- T5DR Online: `docs/LINUX_STEAM_DECK.md` in its release (Direct3D 12 through vkd3d-proton; dark blue window =
  the game's renderer did not start; what to try).
- Tekken 4: `docs/LINUX_STEAM_DECK.md` in its release. **Building Tekken 4 does not work under Wine or Proton**:
  its build and its online check are PowerShell scripts, and Wine/Proton have no working PowerShell. The launcher
  says so (instead of starting a build that cannot run).

## Set-up with Steam (also Steam Deck)

1. Use the **zip**, not Setup.exe: extract it into your Linux home, for example `~/Games/OpenRecomp`. (Setup.exe
   installs into the Proton prefix, deep inside `steamapps/compatdata`, where Steam has no shortcut to it.) On a
   Steam Deck do this in Desktop Mode.
2. Steam -> **Games -> Add a Non-Steam Game to My Library** -> Browse -> `OpenRecomp.exe` in the extracted folder.
   (A test bundle has no OpenRecomp.exe: pick `OpenRecomp-FGC/portable/pythonw.exe` and set the launch options to
   `%command% -B -m openrecomp`, with "Start in" = the `OpenRecomp-FGC` folder.)
3. Right-click it -> **Properties -> Compatibility** -> force **Proton Experimental** (or GE-Proton,
   proton-cachyos).
4. Start it. Install T5DR from the launcher as on Windows; its game folder goes next to the launcher.

The launcher's settings are in `%LOCALAPPDATA%\OpenRecomp` inside the shortcut's Proton prefix
(`steamapps/compatdata/<number>/pfx`). Removing that prefix removes them.

## If the window stays black, empty or the text is wrong

Steam -> the entry's **Properties -> Launch options** (one at a time, then start again):

| Try | Launch options | Why |
|---|---|---|
| 1 | `QSG_RHI_BACKEND=opengl %command%` | Qt draws with Direct3D 11 (DXVK under Proton); this makes it use OpenGL instead |
| 2 | `QSG_RHI_BACKEND=vulkan %command%` | the same through Vulkan |
| 3 | `QT_QPA_PLATFORM=windows:fontengine=gdi %command%` | text missing or boxes: Qt 6.8 reads fonts through DirectWrite, Wine's is incomplete; this uses GDI (untested) |
| 4 | `QT_QUICK_BACKEND=software %command%` | last resort, no GPU (slow, some effects missing) |

Japanese and Korean text: Windows' CJK fonts are not in a Proton prefix. Since this version the launcher also
falls back to Noto Sans CJK / Source Han Sans, which most Linux systems (and SteamOS) have.

## What differs under Wine (from the code)

| Part | Under Wine / Proton |
|---|---|
| Qt Quick (D3D11 RHI) | DXVK in Proton; plain Wine: wined3d (OpenGL) -- see the table above if it fails |
| File picker (IFileOpenDialog) | Wine's own dialog; your Linux files are under drive **Z:** (`Z:\home\<you>`) |
| Controllers (XInput, WinMM) | Steam Input gives an Xbox pad (the Deck's controls too): the launcher and the games see it |
| Taskbar icon, Apps & Features entry, Start menu shortcuts (Setup.exe) | only inside the prefix; use the Steam shortcut |
| tasklist / taskkill (is a game running, cancel a build) | Wine's versions; when they cannot answer, the launcher treats it as "unknown" |
| T5DR's Report a problem / Check my problem | as in T5DR 1.2.0: the zip goes to your Linux Desktop |
| Tekken 4 Build, online check, log collection (PowerShell) | not possible: "@t4.no_powershell" message |
| Tekken 4 winget tool installs (source bundle) | no winget under Wine: the existing "winget is not available" message |
| Self-update | replaces files and restarts like on Windows; not tried under Wine |

## Test checklist

| # | Step | Expected |
|---|---|---|
| 0 | Note: Linux / SteamOS version, Proton build, GPU | |
| 1 | Start OpenRecomp.exe through Steam | the hub with the T5DR and T4 tiles, readable text |
| 2 | Pad / Deck controls in the hub | the selection moves |
| 3 | Settings -> each language (Japanese, Korean too) | text readable, no boxes |
| 4 | Install T5DR from the hub, then Build | as T5DR's own checklist |
| 5 | Online page: log in as guest | the lobby list shows |
| 6 | Tekken 4 tile -> Build | the PowerShell message (not a silent nothing) |
| 7 | Report a problem (T5DR) | a zip on the Linux Desktop |

Send the results with T5DR's report zip and, if the launcher misbehaves, the Proton log (launch options
`PROTON_LOG=1 %command%`, file `~/steam-<number>.log`; it contains your Linux user name: check before posting).
