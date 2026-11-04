# T4 beta first run and release acceptance

This beta offers T4 offline play and online through a T4 lobby server using T5DR's
shared login and lobby screens. Online always opens login or the lobby; the shipped
**T4 Online** entry may be a placeholder, in which case enter a server address.
Use a guest name or a T5DR account on a server sharing those accounts. Ranked requires
an account and a server that enables it. Direct IP or VPN is available under
Settings > Advanced > **Direct connection (LAN / no server)** for this launcher session;
old saved direct-mode choices do not change the normal Online entry.
See [T4_ONLINE.md](T4_ONLINE.md). T5DR's
installed-client Online screens have their own [acceptance scope](T5DR_ONLINE.md);
the old T5DR Online launcher remains available during the transition.

Sunday is a possible release date only after the owner's two-PC test passes.
This document describes the implemented launcher flow and required acceptance;
it is not a clean-PC, hardware or gameplay test result.

## Quelltext-Testbundle: Start ohne eingegebene Befehle

Dieses Testbundle ist der Quelltext-Weg fuer den Besitzer und seinen Kollegen;
es ist keine portable Spielerfreigabe. Beide entpacken dasselbe ZIP aus `dist/`
in einen neuen, beschreibbaren Ordner. `START_HIER.txt` liegt neben
`OpenRecomp-FGC/` und `T4/`. Diese beiden Ordner zusammenlassen: der Launcher
findet das benachbarte `T4` automatisch. Das Bundle enthaelt keine ISO, fertige
Spiel-EXE, Spieldaten oder Spielbilder. Die portable CPython-3.12.10-Laufzeit
fuer Windows x64 mit PySide6-Essentials 6.8.2.1 und shiboken6 6.8.2.1 samt
Lizenzen ist enthalten.

Dasselbe ZIP traegt auch Tekken 5 DR, aber ohne T5DR selbst: jeder legt seinen
eigenen, entpackten Ordner `T5DR-Online-1.2.0` daneben (neben `OpenRecomp-FGC/`
und `T4/`) und baut ihn einmal in dessen `T5DR Online.exe` mit BUILD GAME und
der eigenen .pkg und .rap. Der Launcher findet den Nachbarordner selbst. Der
ganze Zwei-PC-Ablauf mit beiden Spielen steht in [HAND_CHECK.md](HAND_CHECK.md).

1. `OpenRecomp-FGC/run.cmd` im Explorer doppelklicken und dem Bildschirm
   folgen. Fuer den Launcher ist keine separate Laufzeitinstallation oder
   Internetverbindung beim ersten Start erforderlich. Die Laufzeit liegt in
   `OpenRecomp-FGC/portable/`. Die folgenden Build-Werkzeuge fuer T4 werden
   vom Launcher selbst geprueft und bei Bedarf installiert (Schritt 2).
2. T4 waehlen, dann **Build**. Die Seite zeigt Karten: deine Spieldateien, die
   Build-Werkzeuge und rechts einen grossen Knopf **Bauen**. Der Launcher prueft
   Python, Git, CMake, Ninja und VS 2022 Build Tools (MSVC) automatisch im
   Hintergrund; eine Liste wird nicht gezeigt, nur eine Zeile (**Bereit** oder
   **Automatisch**). Fehlt etwas, installiert **Bauen** es zuerst selbst mit
   **winget** (eine Zeile **Installiere Build-Werkzeuge (x von y) ...**;
   Windows fragt eventuell nach Erlaubnis; VS 2022 mit C++-Buildwerkzeugen und
   Windows SDK dauert eine Weile), uebernimmt den neuen PATH ohne Neustart und baut
   danach weiter. Verlangt Windows einen Neustart, merkt sich der Launcher das und
   baut nach dem Neustart von selbst weiter. Klappt eine Installation nicht, zeigt
   die Karte den Fehler mit **Erneut versuchen** und **Hilfe**; in der Hilfe stehen
   die genauen winget-Befehle zum Kopieren (**Befehle kopieren**), wer lieber selbst
   im Terminal installiert. Fehlt danach noch etwas, den Launcher vollstaendig
   schliessen und neu starten, damit er den neuen PATH erbt; dann die Werkzeuge
   erneut pruefen lassen (einfach wieder **Bauen**).
3. **Game ISO** waehlen und die eigene USA **SLUS-20328 v1.00** auswaehlen.
   Die Pruefung laeuft im Hintergrund; eine falsche oder veraenderte ISO muss
   verstaendlich abgelehnt werden. Keine ISO vom anderen Spieler anfordern.
4. **Bauen** waehlen. Fortschritt (Schrittname, bisherige Zeit, etwa verbleibende Zeit),
   Fehler und Abbruch bleiben im Launcher; **X** zeigt das Build-Log.
   Der erste Build laedt seine Quelltext-Abhaengigkeiten und kann lange dauern.
   Erst nach erfolgreichem Build fortfahren. Beide vergleichen vor dem Spiel
   die sichtbare **Build-ID** und die genaue **Compiler/MSVC-Version**;
   derselbe Name "VS 2022" reicht nicht.
5. Mit Pad oder Maus **Online** waehlen. Namen und gegebenenfalls Lobby-Adresse mit
   der Bildschirmtastatur eingeben, als Gast oder mit dem T5DR-Konto anmelden.
   Die Lobby zeigt Spieler, Raeume und Chat. Spieler herausfordern oder eine schnelle
   Partie suchen; Ranglistenspiele brauchen ein Konto und Serverunterstuetzung.
   Eine eingehende Herausforderung oeffnet ein Fenster mit Ping, Verbindungsweg,
   Annehmen und Ablehnen. Bei gefundenem Match **Start match** waehlen.
6. Unterstuetzte T4-Builds melden das Spielergebnis automatisch. Danach Revanche
   anfordern oder zur Lobby zurueckkehren; Ranglistensaetze gehen nach dem Countdown
   des Servers weiter. Die Verbindung ohne Server steht unter Einstellungen > Erweitert.
   Nur dort gelten Host/Join, **Check connection**, **Collect logs** und die
   [Netzwerkhinweise](T4_ONLINE.md). Der angezeigte Dateipfad nennt das lokale Diagnose-ZIP;
   Inhalt vor privater Weitergabe pruefen. Logs bleiben ausserhalb des oeffentlichen Repositorys.

Alle Launcher-Schritte muessen mit Richtungen, Confirm und Back auf einem Pad
sowie per Maus funktionieren. Werkzeuginstallation und Router-/VPN-Einrichtung
sind Vorbereitung im jeweiligen Windows- oder Router-Dialog. Niemand muss fuer
Build oder Host/Join PowerShell-Befehle abtippen.

Der Maintainer erstellt das Bundle mit `tools\make_t4_test_bundle.ps1` in
Windows PowerShell. Beim ersten Mal laedt das Skript die festgelegten Laufzeit-
Archive und prueft ihre SHA-256-Summen; weitere Aufrufe verwenden den geprueften
Cache. Beide Quelltext-Scans und der genaue Laufzeitkatalog muessen vor dem
Schreiben bestehen; ein Fund verweigert das ZIP. Der Befehl meldet den datierten
Dateinamen in `dist/` sowie die gemessene ZIP- und entpackte Groesse. Einzelheiten
zu Dateien und Lizenzen stehen in [PACKAGING.md](PACKAGING.md).

## Portable release player walk

1. Extract the complete launcher release to a writable folder and open
   `OpenRecomp.exe`. The release must include its private runtime; a player
   should not install Python, Qt or developer tools. `run.cmd` is for source
   checkouts, not the player installation procedure.
2. With a pad, select T4 on the shelf and confirm. Choose the player's complete
   portable T4 release zip or its extracted folder. Browse folders/drives and
   choose files using directions, Confirm and Back. No manifest editing is
   needed. Registration never starts a game or a build.
3. In Build, select **Game ISO** and choose the player's own USA SLUS-20328 ISO.
   Verification runs in the background. A refusal stays visible and preserves
   a previously accepted choice. A changed file must be checked again. No ISO,
   game code, executable game build, saves or pictures are shipped here.
   Once an accepted ISO is known, the launcher reads Jin's character-select
   portrait from that disc once (`openrecomp/t4_art.py`: DATA.BIN entry 253,
   only when the program's SHA-1 is SLUS-20328 v1.00) and keeps it as
   `<user folder>\art\t4\hero_jin.png` for the T4 tile and hub. A
   `hero.png` the player puts in that folder wins. Without an ISO, or with
   another disc, the tile stays plain. Delete the PNG to have it read again.
4. Select **Build game**. Stage progress, cancellation and retry stay in the
   launcher. The installed T4 core performs the local build. An incomplete
   portable release must be replaced through **Complete T4 release**; the
   launcher does not ask the player to install developer tools.
5. Select **Play** when the build is ready. Normal launcher navigation pauses
   while T4 runs. To stop the owned game and return, hold View + Menu on Xbox,
   or Share + Options on PlayStation, on one pad for two seconds. This stops
   the process; it is not an in-game save/quit command.
6. Select **Settings** with LB/RB. Directions and Confirm change options.
   **Connection diagnostics** is **off by default** and optional for online
   tests. Experimental run-ahead and transport/harness controls are hidden.
   Existing graphics and sound defaults remain unchanged. Quick access offers
   launcher language, fullscreen and motion preferences.
7. For online, open **Online** and log in as a guest or with your T5DR account.
   Enter the lobby server address with the on-screen keyboard if needed.
   The shared lobby has players, rooms and chat; challenge a player or search a
   quick match. An incoming challenge opens an accept/decline pop-up with ping and
   connection path. Ranked requires a supported server and an account. Ready the
   match-found card to launch. Supported games report results automatically; request
   a rematch, continue the set or return to the lobby. The launcher requests automatic
   VS entry, but direct-to-fight behavior and fighter/stage selection remain unverified.
   For LAN without a server, use Settings > Advanced > **Direct connection (LAN / no server)**;
   matching build, compiler/MSVC and ISO hash plus two-way UDP checks precede Start game.
   See [T4_ONLINE.md](T4_ONLINE.md) for the complete flow and network limits.
8. Back returns to the shelf and then the quit dialog. An import or ISO check
   must finish before exit; an active build offers its cancellation row.
   Quick access also offers launcher update checks. Updates remain disabled
   until the owner supplies this launcher's release identity and signing trust;
   see [UPDATES.md](UPDATES.md).

## Owner checks before release

Use a Windows 10/11 account without Python, Qt, developer tools, installed games
or saved launcher settings. Prepare the complete launcher runtime/starter and
the complete portable T4 release separately; neither is created by this review.

- Follow the whole player walk with Xbox and supported Sony USB/Bluetooth pads.
  Check hotplug, two pads, held buttons, visible focus and Back at every step.
- Read every screen in all seven languages at 1080p and Windows 150% scaling.
  Check long error text, labels, values, keyboard pages, scrolling and button
  prompts. Source layout checks cannot establish visual acceptance.
- Extract into a path with spaces/non-ASCII characters, relocate it and retry.
  Check missing-runtime/early-crash recovery and private Qt/QML plugin loading.
- Register the real T4 zip and folder; reject incomplete/wrong releases. Check
  denied access, failed extraction and library replacement while work is busy.
- Try supported and unsupported discs, changed/moved ISO files, missing helpers,
  build failure/cancel/retry and a failed rebuild with an older working runtime.
  Failures must remain understandable and recoverable with a pad.
- Play, return, restart and verify settings/ISO persistence, saves and input
  release. Check normal stop, crash and short startup failures.
- Complete the **two physical PCs** gate in [T4_ONLINE.md](T4_ONLINE.md), with
  both Host/Join roles and the intended direct IP or VPN route. Failed checks
  must prevent launch. A successful preflight is insufficient without real play.
- Check T5DR separately against [T5DR_ONLINE.md](T5DR_ONLINE.md), including its
  controller screens and old-launcher fallback.
- Review the real package contents, licenses and runtime inventory. Test signed
  updates and rollback on a private channel if enabled; follow
  [PACKAGING.md](PACKAGING.md) and [INSTALLING.md](INSTALLING.md).

Before handover run `.venv\Scripts\python.exe -m unittest discover -s tests`
and `.venv\Scripts\python.exe tools\package_release.py --scan-only`, then record
the actual results. Games, builds and real network checks were not started for this
source review; screenshot checks use synthetic data without installed game art. Passing automated tests
does not replace the owner checks above.
