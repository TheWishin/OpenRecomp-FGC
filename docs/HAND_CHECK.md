# Pad-Check: 20 Minuten

Für den Besitzer, nach der Quellcodeprüfung. Dieser Kurztest ist **keine
Freigabe** für Online-Spiel, Migration oder Updates. Nur am eigenen PC;
Ergebnisse privat als „OK / Fehler / nicht geprüft“ notieren.

## Vorbereiten · 0–2 Min.

- Beide Launcher und alle Spiele schließen. Alte Installation behalten.
- Sicherung der Einstellungen, Anmeldung, Belegung und Replays bereithalten.
  Für Änderungen nur eine private Testkopie verwenden, getrennt von beiden
  Programmordnern und diesem Repository. Ein getrenntes OpenRecomp-Testprofil
  (`OPENRECOMP_HOME`) vorher einrichten. Vorbereitung zählt extra.
- Den geprüften Launcher mit Pad öffnen. Keine Anmeldung, kein **Refresh**,
  **Ranked**, **Quick Match**, **Check connection**, **Start game** oder
  Update-Prüfung auslösen. Diese Aktionen können Netzwerk oder Spiel starten.
- A/Cross bestätigt, B/Kreis geht zurück; LB/RB wechseln den Bereich.
  Start/Options kann **Play** auslösen: hier nicht drücken.

## Bedienung · 2–5 Min.

- Regal, Bereiche und Schnellzugriff mit dem Pad erreichen; Fokus stets sichtbar?
- B mehrmals: zurück zum Regal, dann Abfrage zum Beenden. Sichere Vorauswahl?
  Abbrechen. Kein Spiel oder Suchlauf darf beginnen.
- Taste kurz halten, loslassen; Pad abziehen und wieder verbinden.
  Keine hängen gebliebene Bewegung oder unbeabsichtigte Bestätigung?
- Deutsche lange Texte und Bildschirmtastatur lesen: abgeschnittene Zeilen,
  fehlende Zeichen oder englische Sätze notieren. Namen wie Host bleiben möglich.

## T4: direkte IP · 5–9 Min.

- Online öffnen: **Direkte IP / VPN** mit **Host / Join**, ohne Konto; die **T4-Lobby** nur als Angebot, kein Ranked.
- Join wählen. IP per Bildschirmtastatur bearbeiten, löschen, dann mit B
  abbrechen. Alter Wert erhalten? Danach einen Testwert bestätigen.
- Zurück zum Regal und erneut öffnen. Kein Check und kein Spiel allein durch
  Navigation. **Start game** ohne erfolgreichen Check gesperrt?
- Diagnose-Schalter prüfen: ursprünglich aus. Teständerung zurücknehmen.
  Keine Logs sammeln oder hochladen.

## T5DR und alter Launcher · 9–14 Min.

- Ohne Anmeldung Online öffnen und wieder verlassen. Keine Verbindung oder
  automatische Suche; gespeicherte Anmeldung nur als Angebot sichtbar?
- Auf der Testkopie Einstellungen, Replay-Liste und Belegung ansehen.
  Keine Aufnahme abspielen. Einen Belegungsdialog öffnen und abbrechen:
  bleibt die vorherige Belegung erhalten?
- Installation und Einstellungen dürfen nicht unbemerkt wechseln. Build und
  Paket-/Lizenzwechsel der geliehenen Installation müssen gesperrt bleiben.
- Änderungen nur ausdrücklich in der Testkopie speichern. Alte Dateien nachher
  separat privat gegen die Sicherung prüfen; diese Nachbereitung zählt extra. Den alten
  Launcher hier geschlossen lassen; sein möglicher Auto-Login ist nicht geprüft.

## Paket und Rückweg · 14–20 Min.

- Schnellzugriff und Update-Hinweise lesen; keine Prüfung oder Installation
  starten. Fehlende Update-Konfiguration muss verständlich erklärt werden.
- Launcher per Pad beenden und erneut öffnen. Fokus, Sprache und bewusst
  gespeicherte Testwerte erhalten?
- Ergebnis je Abschnitt notieren. Fehler: Aktion, erwartetes und tatsächliches
  Verhalten; keine Tokens, Passwörter, persönlichen Pfade, Spielbilder oder
  Spielerlogs ins öffentliche Repository aufnehmen.

## Separat und ausdrücklich planen

Mehr als 20 Minuten und eigene Freigabe nötig: zwei PCs mit T4 Host/Join,
Verbindungscheck, Abbruch und echtem Spiel; T5DR auf einem privaten Testserver
mit Login, Suche, Ready, Räumen, Turnieren und Zuschauen; Token-Rotation beim
Wechsel zum alten Launcher und dessen Auto-Login; reale Replay-Aufnahme; signiertes Paketupdate mit
Fehlstart und Rollback auf einer entbehrlichen Installation; sauberer Windows-PC,
alle sieben Sprachen sowie USB/Bluetooth-Pads. Der Kurztest ersetzt das nicht.

Details: [T4](T4_ONLINE.md), [T5DR](T5DR_ONLINE.md),
[Wechsel vom alten Launcher](T5DR_COEXISTENCE.md), [Updates](UPDATES.md),
[Paketprüfung](PACKAGING.md).

## Zusatz: T4-Testbundle mit beiden Spielen, zwei echte PCs

Dieser Durchlauf gehört nicht zum passiven 20-Minuten-Check oben. Der Besitzer
führt ihn mit dem Kollegen über Internet aus, beide mit **demselben** Test-ZIP
(`openrecomp-fgc-test-….zip`, SHA-256 beim Übergeben vergleichen; `BUNDLE.txt`
im ZIP nennt den Stand). Die Quelltexttests und der Skript-Check belegen diese
Punkte nicht. Ergebnisse privat als „OK / Fehler / nicht geprüft“ notieren,
keine Spielerlogs oder Screenshots ins Repository legen.

### Vorbereiten (je PC)

- Für Tekken 4: Visual Studio 2022 Build Tools (Desktopentwicklung mit C++),
  Git, CMake und Ninja. Eigene Tekken-4-USA-ISO (SLUS-20328 v1.00).
- Für Tekken 5 DR: einen eigenen, entpackten Ordner `T5DR-Online-1.2.0` und das
  eigene Paket (.pkg + .rap, US PSN NPUB30009).
- Test-ZIP in einen neuen, leeren Ordner entpacken (nicht direkt auf C:\ oder
  D:\). `T5DR-Online-1.2.0` in denselben Ordner legen. Danach liegen dort
  nebeneinander: `OpenRecomp-FGC`, `T4`, `T5DR-Online-1.2.0`, `START_HIER.txt`,
  `START_HERE.txt`, `BUNDLE.txt`. `START_HIER.txt` lesen: verständlich?
- Liegt dem ZIP eine `OpenRecomp-FGC-Setup-….exe` bei (gleicher Stand, aus dem
  ZIP gebaut): auf einem der PCs stattdessen damit in einen neuen Ordner
  installieren und `T5DR-Online-1.2.0` daneben legen; Startmenü-Eintrag und
  Start prüfen. Der Rest des Durchlaufs gilt gleich.

### Erster Start · beide Spiele im Regal

- `OpenRecomp-FGC/run.cmd` doppelklicken. Öffnet sich das Fenster ohne
  Installation und ohne Download? Kein Konsolenfenster bleibt hängen?
  Warnt Windows vor der heruntergeladenen Datei (SmartScreen / „Datei öffnen“),
  notieren, welche Meldung kam, und „Trotzdem ausführen“ wählen.
- Im Regal stehen **Tekken 4** und **Tekken 5 DR** als eigene Kacheln.
  `T4/` und `T5DR-Online-1.2.0` werden als Nachbarordner ohne Ordnerwahl
  erkannt? Ohne Bilder im Paket bleiben Titel, Schaltflächen und sichtbarer
  Fokus lesbar?
- Mit Pad allein, danach Maus: Regal, Bereiche (LB/RB), Zurück (B) und
  Beenden-Abfrage. View wechselt das Spiel.

### Tekken 4 bauen und offline spielen

- Tekken 4 > Build: alle Werkzeuge da = eine Zeile „Build-Werkzeuge bereit“
  (Versionen und genaue MSVC-Version in ihren Details). Auf einem sauberen
  Windows-PC: „Fehlende Werkzeuge installieren“ zeigt die Liste, „Installieren“
  installiert sie mit winget und prüft danach erneut; Kopieren („Befehle
  kopieren“ im selben Dialog) prüfen.
- Nur die USA-Version: Der Launcher nimmt nur einen T4-Ordner der USA-Linie
  (SLUS-20328). Wer einen Ordner eines PAL-Projekts (SCES-50878) wählt, muss
  „Dieser Tekken-4-Ordner ist nicht die USA-Version …“ sehen; ISO-Prüfung,
  Build und Play bleiben gesperrt, nichts wird gebaut.
- Falsche ISO ablehnen, eigene USA SLUS-20328 v1.00 akzeptieren. Fortschritt,
  Fehler, Abbruch und Wiederholung beim echten Build prüfen (ca. 6 Minuten).
  Stimmen die sichtbare Build-ID und Compiler/MSVC-Version auf beiden PCs
  überein?
- Play: ein Kampf mit Pad und Ton. Rückkehr in den Launcher mit
  View + Menu / Share + Options (2 Sekunden halten) und durch normales Beenden.

### Tekken 4 online

- Deutsche Hinweise für Firewall, UDP 7400, Portfreigabe und Tailscale lesen:
  vollständig, scrollbar, ohne abgeschnittene Zeilen bei 1080p/150 Prozent?
- **T4-Lobby** (nur wenn eine T4-Lobby-Adresse vom Server-Betreiber vorliegt):
  Lobby-Adresse und Spielername per Bildschirmtastatur, Gast-Anmeldung, Chat
  in beide Richtungen, Spieler herausfordern oder Quick Match, Match startet
  auf beiden PCs. Ohne Adresse: verständlicher Hinweis statt Fehler?
- **Ein Konto für beide Spiele**: mit Name und Passwort des T5DR-Kontos in der
  T4-Lobby anmelden (geht, sobald der T4-Server die T5DR-Konten teilt). Ist auf
  dem PC eine T5DR-Anmeldung gespeichert und der Server in der Liste als
  geteilt markiert: erscheint **Use your T5DR login** und meldet mit einem Druck
  an? T4-Rang getrennt vom T5DR-Rang? Lehnt der Server ab: klare Meldung, die
  T5DR-Anmeldung bleibt für Tekken 5 erhalten.
- Nach dem Kampf: Ergebnis in der T4-Lobby auf beiden PCs gleich, zurück in
  der Lobby.
- **Direkte IP / VPN**: Host/Join und IP-Eingabe per Bildschirmtastatur
  bedienen. Fehlerfälle wie falscher Build, andere ISO, ungültige IP,
  blockiertes UDP und Abbruch müssen vor Spielstart erklärt werden.
- Beide Rollen über die beabsichtigte Internetroute testen; mindestens
  15 Minuten Figurenwahl, mehrere Runden, Ton, Eingabe, Ergebnis und erneuten
  Kampf vergleichen. Gleichzeitige unterschiedliche Szenen oder Sieger melden.

### Tekken 5 DR offline

- Kachel Tekken 5 DR: Status „nicht gebaut“, solange kein Build da ist.
  Tekken 5 > Build: eigene .pkg und .rap wählen, **Bauen** (der Launcher fragt
  einmal nach, ob er den T5DR-Ordner bauen darf). Alternativ **T5DR Online
  launcher** öffnen: `T5DR Online.exe`, dort BUILD GAME (nie beide gleichzeitig).
  Danach den Launcher-Bereich neu
  öffnen: Status „bereit“, Version 1.2.0?
- Play: Spiel startet, Pad funktioniert, Ton an, Spielende führt zurück in den
  Launcher. Einstellungen (Auflösung, Anzeige, Bildschirmseite) und
  Replays-Liste per Pad ansehen.

### Tekken 5 DR online

- Online-Bereich: Anmeldung (vorhandene T5DR-Anmeldung als Angebot oder
  Gast), Lobby sichtbar, Chat. Gegeneinander: Quick Match oder eine
  Herausforderung, beide Spiele starten direkt im Kampf. Rematch per Pad im
  Spiel, danach zurück in die Lobby. Ranked nur, wenn beide es wollen.
- Ein Match vollständig spielen: kein Desync-Hinweis, Ergebnis erscheint auf
  beiden PCs gleich.

### Nachher

- Tekken 4: **Collect logs** per Pad auslösen: angezeigter Dateipfad ist
  vollständig, lesbar und führt zum vorhandenen ZIP? Tekken 5: Problembericht
  („Create local report“) ebenso. ZIPs privat auf Inhalt und Redaktion prüfen
  und privat schicken.
- Launcher schließen und erneut öffnen: Sprache, gebaute Spiele und gewählte
  Einstellungen erhalten?

Die Launcher-Oberfläche, echte Werkzeuginstallation, Builds, Router/VPN, zwei
physische Pads und das Internet-Spiel muessen von Menschen geprueft werden.
