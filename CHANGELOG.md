# Changelog

Player-facing changes of OpenRecomp-FGC. The games have their own notes (TheWishin/T5DROnline,
TheWishin/Tekken4Recomp).

## v0.1.1

- **Full Setup**: `OpenRecomp-FGC-Full-Setup-0.1.1.exe` installs the launcher together with Tekken 5 DR Online 1.2.0
  and Tekken 4 0.1.0 (beta) in one go (a checkbox per game, both on). The games are the published, signed release
  files, checked exactly like an install from inside the launcher. The small Setup and the zip stay as before.
- **T5DR lobby address**: on a new PC the Lobby field already names the T5DR Online server; an empty field means the
  same server. A server that cannot be reached now says "Lobby not reachable" instead of a general error.
- **One launcher online at a time**: when T5DR's own launcher or another OpenRecomp window is open, OpenRecomp says so
  and does not log in by itself against it (no more logging each other out). "Use OpenRecomp here" logs in with this
  launcher's remembered login.
- Adding or removing a game keeps the other games logged in.
- **OpenRecomp-FGC Discord** button in the top bar and in Quick access. T5DR's Problem report page gets
  "Send to the developer" (one press) as soon as the lobby server supports it.
- Tekken 4 gets **Problem report** too: send cleaned diagnostics to the T4 developer with one press, or save a ZIP
  locally. Older servers offer Save only. Game files and memory cards are never included.
- Quick access > Test versions re-checks the games right away.
- Linux / Steam Deck (Proton, Wine): Tekken 4's Build says why it cannot run there (it needs Windows PowerShell)
  instead of failing silently; Japanese and Korean text uses Linux fonts when Windows' are missing.
- Games can be described in one JSON file (`docs/ADD_A_GAME.md`): start, stop, settings, picture and a signed update
  check. A Tekken Tag Tournament 2 (TAG2 PC) folder on this PC shows its own tile.

## v0.1.0

First release: one launcher for Tekken 4 (USA) and Tekken 5 DR Online (USA), with installs and signed updates of the
launcher and both games, online pages, staying logged in, the Build page with automatic build tools, seven languages.
