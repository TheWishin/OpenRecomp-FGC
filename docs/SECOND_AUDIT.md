# Zweite skeptische Quellcodeprüfung

Geprüfter Verlauf: `a41099f..HEAD`, insbesondere die Änderungen nach
`13d12c0`, und der aktuelle Arbeitsbaum. Keine Commits oder anderen
schreibenden Git-Aktionen. Die folgenden Korrekturen liegen im Arbeitsbaum.
Die Priorität bezeichnet die mögliche Auswirkung, keinen nachgewiesenen
Schaden bei einem Spieler.

## Befunde nach Priorität

| Priorität | Befund | Korrektur im Quellcode |
| --- | --- | --- |
| P1 | Leeres T5DR-Serverfeld suchte gespeicherte Tokens für Loopback, verband aber zum installierten Standardserver. Ein Token konnte am falschen Ziel landen. | Leeres Feld bedeutet durchgehend Loopback; ausdrücklich gewählte Server bleiben möglich. |
| P1 | Geerbte oder vom T4-Core gelieferte `TEKKEN4_NET*`-Werte konnten gewöhnliches Play als Netzspiel starten. | T4 entfernt Netzwerkwerte vor dem Start und setzt nur die ausdrücklich gewählten Werte. Abgebrochene Checks starten keinen neuen Prüfprozess. |
| P1 | Ein Fehler direkt nach einem nativen T4- oder T5DR-Prozessstart, auch beim Einrichten der Überwachung, konnte einen laufenden Prozess von seiner Startsperre trennen. | Eigenen Lauf behalten, Stop anfordern und die Sperre erst nach bestätigtem Stop freigeben; bei laufendem oder unbekanntem Zustand bleibt sie erhalten. |
| P1 | Ein gerade erzeugter T5DR-Matchtreiber konnte beim Abbruch vor der Übernahme seines Worker-Ergebnisses weiterlaufen. | Treiber wird unter der Sitzungssperre übernommen; ein während der Erzeugung abgebrochener Treiber wird geschlossen. Ein abweichendes Match-Ticket wird abgewiesen. |
| P1 | Ein fehlgeschlagener Belegungsspeichervorgang konnte vorhandene private Pad-Einstellungen teilweise überschreiben. | Zunächst in eine temporäre Nachbardatei schreiben, danach atomar ersetzen; vorherige Einstellungen bleiben bei Fehlern erhalten. |
| P1 | Ein verlinkter benachbarter Update-Arbeitsordner konnte Schreiben, Bereinigung und Ergebnislesen in fremde Ordner umleiten. | Links im Arbeitsordnerpfad werden abgewiesen. Zusätzlich wird eine Überschneidung mit dem Spielerprofil verweigert. |
| P1 | Wartende Turnier-, Zuschauer- und Raumaktionen konnten veraltete Einladungen, Abmeldung oder inzwischen gestartete Spiele übersehen. | Zustand im Worker und unmittelbar vor der Aktion erneut prüfen; veraltete und nicht mehr zulässige Aktionen abbrechen. |
| P2 | Veraltete Turnierdetails oder fehlerhafte Serverwerte konnten falsche Änderungen freigeben oder Ansichten abbrechen lassen. | Details vor Änderungen erneut prüfen und fehlerhafte Metadaten sowie unendliche oder übergroße Zahlen abweisen. |
| P2 | Neue Profilergebnisse oder verschwundene native Launcher-Einträge konnten die fokussierte Pad-Aktion auf eine andere Zeile verschieben. | Stabile Aktionskennungen und erneute bewusste Auswahl bei geänderten Zeilen. |
| P2 | Paket-Ausgaben konnten Links folgen oder eine während der Erstellung angelegte Prüfsummendatei überschreiben. | Ausgabe-Vorfahren und verlinkte Ausgaben abweisen; Prüfsummen exklusiv neu anlegen. |
| P2 | Ein ungültiger oder fehlschlagender nativer Einladungstimer konnte Polling abbrechen oder Einladungen falsch freigeben. | Ungültige Timer blockieren Einladungen konservativ. |
| P2 | Die unabhängige Diff-Prüfung fand einen Startabbruch beim Lesen eines unzugänglichen Update-Arbeitsordners in der neuen Schutzprüfung. | Dateisystemfehler an dieser Grenze werden abgefangen; eine Regression wurde ergänzt. |
| P2 | Optionale Integrationstests konnten beim normalen Testlauf externe native Quellordner suchen und lesen. | Native Integration ist ausdrücklich freizuschalten; der Standardlauf bleibt ohne diese Quellordner. |
| P3 | Dokumentation konnte einen frischen Vergleich externer Versionen, vollständige Pad-Bedienbarkeit oder geprüfte Übersetzungsqualität nahelegen. | Aussagen als beabsichtigtes Verhalten beziehungsweise noch ausstehende Abnahme präzisiert. Englische Anweisungen und Hinweise auf das leere Serverfeld in den Katalogen korrigiert. |

Für die Korrekturen wurden Regressionstests hinzugefügt. Der kurze deutsche
[Pad-Check](HAND_CHECK.md) trennt 20 Minuten Navigation von ausdrücklich
geplanten Netzwerk-, Spiel- und Updateprüfungen.

## Testergebnis und Grenzen

**Blockiert vor dem ersten Test:**
`.venv\Scripts\python.exe -m unittest discover -s tests` kann den in `.venv`
konfigurierten Python-Interpreter nicht starten. Auch über den Suchpfad steht
kein verwendbarer Python-Interpreter bereit. Daher sind weder alte noch neue
Tests für diese Prüfung als bestanden nachgewiesen. Die Regressionen müssen
in einer funktionsfähigen Python-3.12-Umgebung ausgeführt werden. Ein statischer
Diff- oder Linkcheck ersetzt diesen Lauf nicht.

Es wurden keine Launcherfenster, Spiele, Builds, Suchläufe, echten
Serververbindungen, Paketbauten oder Update-Drills gestartet. Externe
Spielinstallationen wurden nicht geöffnet. Physische Pads, Darstellung,
native APIs, TLS/NAT, echte Rollbacks, Dateisperren, ein sauberer Windows-PC
und die tatsächliche Vollständigkeit eines Release-Pakets sind ungeprüft.

## Offen vor einer Freigabe

- T5DR gewöhnliches Play delegiert an den installierten `GameRun`. Dessen
  Umgang mit geerbten `T5_NET_*`-Werten ist im Repository nicht definiert.
  Ohne den nativen Vertrag ist eine sichere Neutralisierung nicht belegt.
  Offline-Start aus sauberer Umgebung und absichtlich gesetzten Altwerten
  auf einer entbehrlichen Installation separat prüfen.
- Den vollständigen Testlauf nach Reparatur der lokalen Python-Umgebung
  ausführen; danach die noch offenen nativen Release-Grenzen prüfen.
- Zwei-PC-T4 mit beiden Rollen, T5DR-Gegenstelle und alte Launcher-Version,
  Token-Rotation, echte Replays, Raum-/Turnier-/Zuschauerabläufe sowie
  signierte Updates und Rückkehr zur alten Installation benötigen eigene
  Abnahmen. Synthetische Regressionen beweisen diese Kompatibilität nicht.
- Alle sieben Kataloge von Muttersprachlern und mit Pad prüfen. Gleiche
  Schlüssel und Platzhalter beweisen weder gute Sprache noch lesbare Zeilen.
- Release-Kanal und Signaturvertrauen bleiben Besitzerentscheidungen;
  Produktionsupdates sind bisher nicht konfiguriert. Native Runtime,
  Starter, Lizenz- und Quellpakete müssen separat geprüft werden.

## Eingesetzte Unteragenten

`online_safety`, `t4_direct_ip`, `t5_match_launch`, `t5_social_parity`,
`migration_data`, `update_safety`, `packaging`, `pad_navigation`,
`tests_catalogs`, `docs_handcheck`; unabhängige Prüfung des abschließenden
Diffs: `final_diff_review`.
