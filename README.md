# ❄ Frostbyte — Rettet Weihnachten

Ein Weihnachtsabenteuer in einer echten Linux-Shell: 23 getrennte SSH-Spielercontainer, fünf Orte und ein Live-Scoreboard. Oben siehst du Karte oder 3D-Boss, unten liegt die Bash in einem schlichten Rahmen. Keine F-Tasten-Bedienung nötig.

## Spielen: vier Befehle

Im Dorf starten:

```bash
ls
cp funke ~/rucksack/
cd ../zitadelle
~/rucksack/funke
```

Beim Betreten der Zitadelle erscheint ein Hinweisfenster. **J, dann Enter** startet den Kampf; **N, dann Enter** lässt dich draußen. Nach dem Start bleibt das Tor geschlossen. Den letzten Befehl wiederholen, bis Krampus besiegt ist. Beim Sieg erscheint automatisch ein eigener Bildschirm mit Punkten und Zeit. **Enter** bringt dich zur Shell zurück.

| Was möchtest du tun? | Linux-Befehl |
|---|---|
| Hier umsehen | `ls` |
| Alle Orte als Baum ansehen | `tree ~/welt` |
| Einen Gegenstand mitnehmen | `cp DATEI ~/rucksack/` oder `mv DATEI ~/rucksack/` |
| Rucksack ansehen | `ls ~/rucksack/` |
| Gegenstand benutzen | `~/rucksack/funke` (Name entsprechend ersetzen) |
| Kurze Erklärung lesen | `cat DATEI` |
| Einen anderen Ort besuchen | `cd ~/welt/wald` |
| Eine Aufgabe abgeben | Fertige Datei nach `abgabe/` kopieren |

**Tab** vervollständigt, **Tab Tab** zeigt die Auswahl, **Strg+C** bricht ab. Die unteren Eingabezeilen bleiben automatisch aktiv. Normale Befehle, Editoren, Pipes, Umleitungen und Schleifen funktionieren weiterhin. Spielgegenstände sind echte ausführbare Shell-Dateien; `cp` und `mv` werden nicht umdefiniert.

## Fünf Orte

| Verzeichnis | Fund / Aufgabe |
|---|---|
| `~/welt/dorf` | `funke`, `kakao`; Wunschzettel retten |
| `~/welt/wald` | `wurzeln/frost`, `beeren`; beim ersten Besuch −8 Leben |
| `~/welt/werkstatt` | `schild`; Geschenkband einschalten |
| `~/welt/archiv` | `stern`; Passwort finden, kurze Profi-Tipps |
| `~/welt/zitadelle` | Krampus mit 240 Leben |

Beispiel: `cp post/wunschzettel.txt abgabe/gerettet.txt` löst die Dorfaufgabe automatisch. In jedem Aufgabenordner steht in `AUFGABE.txt` ein kurzer Hinweis. Die Werkstatt erwartet `abgabe/maschine.conf`, das Archiv `abgabe/passwort.txt`. Der Inhalt zählt; `cp`, `mv`, `echo > …` und Pipes sind möglich. Eine unveränderte falsche Abgabe kostet nur einmal Leben, nicht bei jedem Prompt.

## Kämpfen und heilen

| Datei im Rucksack | Wirkung |
|---|---|
| `funke` | 30 Schaden, unbegrenzt |
| `frost` | 38 Schaden und zwei geblockte Gegenangriffe, 3 Ladungen |
| `stern` | 75 Schaden, 2 Ladungen |
| `schild` | Blockt drei Gegenangriffe, 2 Ladungen |
| `kakao` | Einmal bis zu +35 Leben, auch beim Boss |
| `beeren` | Einmal bis zu +25 Leben, auch beim Boss |

Aufgebrauchte Gegenstände verschwinden aus dem Rucksack. Erneutes Kopieren füllt keine verbrauchten Ladungen auf. Nur ein Gegenstand im Rucksack kann über seinen Dateibefehl benutzt werden. Bereits vor dem Update erlernte Zauber erscheinen beim ersten Login als Dateien im Rucksack.

Der Kampf läuft rundenweise. Lesen und Nachdenken kosten keine Leben. Normale Gegenangriffe kosten 7 Leben; der Panzer vermindert deinen Schaden um 8. Fehlgeschlagene Shell-Befehle im Bossraum und falsche Kampfaktionen kosten zusätzlich Leben. Vor dem Kampf fragt ein schwebendes Fenster nach deiner Zustimmung und erklärt Angreifen und Heilen. Nach **Ja** gibt es keinen Rückweg; neue Funde und Aufgaben zählen erst im nächsten Lauf. Bereits mitgebrachte Gegenstände bleiben nutzbar. Mit `neustart` kannst du jederzeit eine neue Runde beginnen.

Punkte gibt es einmal je Ort (40), Zauberfund (80), Aufgabe (150), Heilquelle (25), unterstützter Shell-Befehlsart (10), Angriffsart (30), entferntem Treiber (120), Schleifentrick (200) und Sieg (500).

### Profi-Wege

```bash
# Im Bossraum: spielinterne Treiber entfernen
lsmod
modprobe -r frost_armor
modprobe -r blizzard
```

Diese Befehle verändern nur das Spiel, keine Kernelmodule der VM.

```bash
# Speedrun mit einer echten Bash-Endlosschleife
neustart speedrun
cp funke ~/rucksack/
cd ../zitadelle
while true; do ~/rucksack/funke; done
```

Sechs schnelle Funken innerhalb von zwei Sekunden bringen den Sofortsieg. Die Schleife wird dabei automatisch beendet; danach erscheint der Gewinnbildschirm.

## Neuer Lauf oder alles zurücksetzen

Im Spiel:

```bash
neustart           # Neue Runde, eigene Bestzeiten bleiben
neustart speedrun  # Neuer Speedrun
neustart alles     # Auch die eigenen Bestzeiten löschen
```

Diese Befehle setzen `~/welt` und `~/rucksack` zurück. Name und sonstige eigene Dateien bleiben erhalten. `neustart alles` betrifft nur deinen Spielerplatz.

**Als Veranstalter auf developer / der VM:**

```bash
cd /opt/shell-game
./reset-all.sh                  # Nur Vorschau, ändert nichts
./reset-all.sh --confirm ALLES  # Das gesamte Event zurücksetzen
```

Der Gesamtreset beendet die Verbindungen, sichert zuerst **alle Spieler-Homes und Zustände sowie das Scoreboard**, löscht dann Namen, Punkte, Bestzeiten, Platzreservierungen/Fortsetzen-Codes und komplette Spieler-Homes und startet die Container wieder. Die bisherigen Passwörter, Ports und SSH-Hostschlüssel bleiben erhalten. Beim nächsten Login kommt wieder das Namensfenster. Die Sicherung liegt unter `backups/PROJEKT-ZEITSTEMPEL/` in privaten TAR-Dateien; der Zeitstempel ist UTC. Scheitert die Sicherung, findet kein Datenreset statt. Der Gesamtreset wurde ausschließlich in separaten Testcontainern geprüft, nicht auf euren laufenden Spielständen ausgeführt.

Einzelnen Platz administrativ zurücksetzen:

```bash
python3 scripts/reset_slot.py player01 --expected-name 'Bisheriger Name'
```

## Verbinden und Scoreboard

Nach einmaliger Aktivierung des Host-Einstiegs (siehe Installation) direkt vom Jumphost:

```bash
ssh spiel@DEIN-SERVER  # Automatisch einen freien Spielercontainer erhalten
ssh score@DEIN-SERVER  # Separater Zuschauerzugang zum Live-Scoreboard
```

Es ist keine Portangabe nötig. Die beiden Passwörter stehen privat in `/opt/shell-game/join-access.txt`. Alle Spieler verwenden denselben Einstieg und dasselbe Einstiegspasswort; jeder neue Spieler erhält einen eigenen der 23 Container. Die SSH-Einstellungen für eure bisherigen Admin-Benutzer bleiben erhalten.

Im Einstiegsfenster **Enter** für einen neuen Spielerplatz drücken. Den angezeigten persönlichen **Fortsetzen-Code** speichern. Bei einem Verbindungsabbruch bleibt der Platz reserviert: erneut verbinden, **R** wählen und den Code eingeben. So kommt niemand versehentlich in einen fremden Spielstand. Der Code ist ein privater Zugang zum eigenen Platz. Eine zweite gleichzeitige Sitzung desselben Platzes wird abgewiesen. Verbindungsabbruch pausiert die Laufzeit nicht.

Bestehende benannte Spielerplätze werden übernommen. Als Veranstalter kannst du ihre Codes nachsehen oder einen verlorenen Code wiederfinden:

```bash
cd /opt/shell-game
docker compose exec gateway python3 -m frost.gateway --list
```

Der Gesamtreset gibt alle Plätze frei und erneuert die Codes; `reset_slot.py` gibt einen einzelnen Platz frei. `neustart` im Spiel behält die Zuordnung.

Die bisherigen direkten Zugänge bleiben als Alternative vorhanden: auf developer `ssh -t -p 2201 player@127.0.0.1` (Spieler 1) bzw. `ssh -t -p 2200 player@127.0.0.1` (Scoreboard). Ihre individuellen Passwörter stehen in `access.csv`. Spielerports: 2201–2223. Vom Jumphost war dieser Portbereich nicht erreichbar; der neue Einstieg verwendet den dort erreichbaren Host-Port 22.

Das Board hat feste, bei kleinen Fenstern reduzierte Spalten. Es sortiert stabil nach Punkten oder nach der schnellsten Bestzeit. **1** Punkte, **2** Abenteuer, **3** Abenteuer/Loop, **4** Speedrun, **5** Speedrun/Loop. Pfeiltasten blättern, **Q** schließt die Ansicht. Bestzeiten-Kategorien werden getrennt gehalten. Der Live-Status bedeutet Container-Erreichbarkeit, nicht zwingend eine aktive Person.

```bash
docker compose exec scoreboard scorewatch
curl http://127.0.0.1:8080/api/scores
```

## Installation und Betrieb

Voraussetzungen auf der VM: Linux, Docker Engine mit Compose, Python 3 und OpenSSL. Keine pip-Abhängigkeiten. Für die Terminalansicht sind UTF-8, 256 Farben und etwa 100 × 38 Zeichen sinnvoll.

```bash
cd /opt/shell-game
python3 scripts/provision.py --players 23 --host DEINE-VM-IP
docker compose up -d --build
docker compose ps
sudo python3 scripts/install_entry.py
python3 scripts/check_entry.py  # Beide Standard-SSH-Zugaenge pruefen
```

`install_entry.py --plan` zeigt die Host-Änderungen ohne Schreibzugriff. Die Installation erstellt die eingeschränkten Host-Benutzer `spiel` und `score`, sichert die SSH-Konfiguration unter `/etc/frost-entry/`, prüft sie und lädt SSH neu. Diese beiden Benutzer erhalten ausschließlich den Spiel- bzw. Zuschauerzugang. Die Host-Anpassung braucht einmalig `sudo`; die Spielcontainer selbst laufen vollständig unter Compose.

Der Gateway-Container lauscht standardmäßig nur auf `127.0.0.1:2299`; der Host-Einstieg leitet dorthin weiter. `GATEWAY_BIND` und `GATEWAY_PORT` sind in `.env.example` dokumentiert. Bei einer Änderung des internen Ports das Installationsskript erneut ausführen. Der öffentliche Host-Port 22 bleibt gleich.

Wiederholtes Provisionieren erhält Zugangsdaten. Quellen und Konfiguration liegen im Projekt; persistente Laufzeitdaten liegen in benannten Docker-Volumes. `docker compose down` erhält diese. `docker compose down -v` löscht sie ohne Sicherung und erneuert beim nächsten Start auch die SSH-Hostschlüssel. Für ein neues Event deshalb `reset-all.sh` verwenden.

Jeder Spieler hat einen eigenen Container und ein eigenes Bridge-Netz. Das Root-Dateisystem ist nur lesbar, Ressourcen sind begrenzt, der Docker-Socket und Host-Kernelmodule sind nicht zugänglich. Das ist ein Workshop-Spiel, kein manipulationssicheres CTF: fortgeschrittene Teilnehmer können mit einer echten Shell das lokale Spielprotokoll direkt ansprechen. Die Container haben keine Festplattenquoten und ausgehender Netzwerkverkehr ist nicht gesperrt.

Pro Spieler gelten 256 MiB und 0,5 CPU, fürs Board 256 MiB und 1 CPU, fürs Gateway 512 MiB und 2 CPU. Das Gateway nutzt Debian-Pakete für Paramiko und prüft die Hostschlüssel der Zielcontainer. Limits stehen in `scripts/provision.py`. Spielstände und Hostschlüssel überleben Container-Neustarts; tmux-Sitzungen überleben nur SSH-Abbrüche. Beim Update werden unveränderte alte Hilfedateien ersetzt; bearbeitete Questdateien und gespeicherte Ergebnisse bleiben erhalten.

## Tests

```bash
python3 -m unittest discover -s tests -v
docker compose build scoreboard
python3 tests/integration.py
python3 tests/integration.py --players 23 --load-only
```

Der Integrationstest erstellt das **separate Projekt `frostbyte-check`** mit freien lokalen Ports, eigenen Volumes und zwei Spielercontainern. Dort prüft er automatische Platzvergabe, private Wiederverbindung, volle Belegung, echte SSH-Logins, Tab-Vervollständigung, `tree`, `cp`, Aufgabenabgabe, Boss-Abfrage und Rückwegsperre, ausführbare Gegenstände, Schleifensieg, Gewinnbildschirm, separaten Scoreboard-Zugang und den vollständigen Reset samt Sicherung. Der zusätzliche Lasttest hält 23 Spielersitzungen und einen Zuschauer über das Gateway gleichzeitig offen. Nur im Test teilen sich die Container ein Bridge-Netz, um neben den produktiven Netzen nicht den Docker-Adresspool zu erschöpfen. Anschließend entfernt er nur dieses Testprojekt. Bestehende Spielerplätze werden nicht verwendet.
