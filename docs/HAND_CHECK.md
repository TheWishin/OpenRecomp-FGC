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

- Online öffnen: **Host / Join**, kein Konto, keine Lobby, kein Ranked.
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
