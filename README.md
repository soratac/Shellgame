# ❄ Frostbyte — Rettet Weihnachten

Ein Weihnachtsabenteuer in einer echten Linux-Shell: automatisch erzeugte, getrennte SSH-Spielercontainer, fünf Orte und ein Live-Scoreboard. Oben siehst du deinen gestaltbaren Charakter, die Orte oder den Kampf gegen den 3D-Boss. Unten liegt eine echte Bash in einem festen Rahmen. Es gibt keine tmux-Fenster oder F-Tasten-Bedienung.

## Spielen

Der gemeinsame Einstieg öffnet direkt den Frostbyte-Charaktereditor. Hier Name, Geschlecht, Haartyp, Haarfarbe und Shirtfarbe wählen. **↑/↓** oder **Tab** wechselt das Feld, **←/→** ändert die Auswahl, **Enter** startet. Die Pfeile neben den Werten und die Schaltfläche sind auch anklickbar. Die animierte 3D-Vorschau zeigt Änderungen sofort. Mit `aussehen` kannst du das Aussehen später ändern. Dein Aussehen bleibt bei `restart` erhalten.

Gib mit `&&` verkettete Befehle einzeln ein. Frostbyte verwirft die gesamte Kette vor der Ausführung.

Im Dorf starten:

```bash
cat AUFGABE.txt
cp post/wunschzettel.txt abgabe/gerettet.txt
mv funke ping kakao ~/rucksack/
cd ../wald
cp .lichtung/rindenzeichen abgabe/zeichen.txt
mv wurzeln/frost ~/rucksack/
cd ../werkstatt
cat AUFGABE.txt       # Maschine reparieren und abgeben
mv schild ~/rucksack/
karte                 # Folge der markierten Spur mit cd ~/welt/ORT
nmap grinch
ssh grinch
~/rucksack/funke
```

Die goldene Spur ✧ zeigt den aktuellen Aufenthaltsort des Grinch. Er wechselt jede Minute zwischen Wald, Werkstatt und Archiv. Gehe zum markierten Ort und gib `nmap grinch` ein. Der Spielscanner zeigt seine IP. Sie bleibt bis zum Neustart bekannt. Mit `ssh grinch` oder `ssh 127.12.24.1` beginnt der Kampf sofort. Die weiteren Orte und ihre Gegenstände sind freiwillig. Nach Kampfbeginn bleibt das Tor geschlossen. Wechsle zwischen Stab und Zaubern und nutze Frost oder Schild gegen die Gegenangriffe. Beim Sieg erscheint automatisch ein eigener Bildschirm mit Punkten und Zeit. **Enter** bringt dich zur Shell zurück.

| Was möchtest du tun? | Linux-Befehl |
|---|---|
| Hier umsehen | `ls` |
| Alle Orte als Baum ansehen | `tree ~/welt` |
| Einen Gegenstand mitnehmen | `mv DATEI ~/rucksack/` |
| Rucksack ansehen | `ls ~/rucksack/` |
| Gegenstand benutzen | `~/rucksack/funke` (Name entsprechend ersetzen) |
| Kurze Erklärung lesen | `cat DATEI` |
| Einen anderen Ort besuchen | `cd ~/welt/wald` |
| Eine Aufgabe abgeben | Fertige Datei nach `abgabe/` kopieren |

Mit `tipp` erhältst du bis zu drei Hinweise pro Runde. Jeder erscheint acht Sekunden über der Spielwelt. `restart` füllt den Vorrat wieder auf.

**Tab** vervollständigt, **Tab Tab** zeigt die Auswahl, **Strg+C** bricht ab. Die unteren Eingabezeilen bleiben automatisch aktiv. Normale Befehle, Editoren, Pipes, Umleitungen und Schleifen funktionieren weiterhin. Spielgegenstände sind echte ausführbare Shell-Dateien; `cp` und `mv` werden nicht umdefiniert.

## Weihnachtsmusik

Für Musik und Effekte starte Frostbyte im Terminal **auf dem Rechner mit deinen Lautsprechern**. Im aktuellen Repository genügt über den Jumphost dieser Befehl.

```bash
python3 scripts/spielmusik.py -J jump spiel@10.0.0.60
```

Bei direkter Verbindung entfällt `-J jump`. Der Starter spielt „Schneefunken“ automatisch ab und mischt Treffer, Zauber, Heilung und Bossangriffe dazu. Mit dem Schließen der SSH-Sitzung endet auch die Wiedergabe. Du brauchst lokal Python 3.9+, OpenSSH und eines der Programme `aplay` (unter Debian/Ubuntu im Paket `alsa-utils`), `paplay`, SoX (`play`) oder `ffplay`. Der Starter verwendet die lokale Standard-Tonausgabe. Die Spielereignisse laufen über dieselbe SSH-Verbindung.

Unten rechts ändern **[−]** und **[+]** die Lautstärke. Ein Klick auf die Prozentzahl schaltet stumm und wieder laut. An der Shell funktionieren `musik 30` und `musik mute`. Im Regler `musik` ändern **← / →** die Lautstärke, **M** schaltet stumm und **Enter** schließt ihn.

Bei einem gewöhnlichen `ssh spiel@HOST` bleibt der persönliche Browserlink über `musik link` verfügbar. Dafür muss das Gerät den Musikport erreichen (Standard **8094/tcp**). Die Adresse wird über `GAME_HOST`, `MUSIC_PORT` oder `MUSIC_URL` in `.env` festgelegt.

## Fünf Orte

| Verzeichnis | Fund / Aufgabe |
|---|---|
| `~/welt/dorf` | `funke`, `kakao`; Wunschzettel retten |
| `~/welt/wald` | `wurzeln/frost`, `.lichtung/beeren`; beim ersten Besuch −8 Leben |
| `~/welt/werkstatt` | `schild`; Geschenkband einschalten |
| `~/welt/archiv` | `ls -a`, dann `mv .depot/stern ~/rucksack/`; Passwort finden, kurze Profi-Tipps |
| `~/welt/zitadelle` | Grinch mit 240 Leben |

Beispiel: `cp post/wunschzettel.txt abgabe/gerettet.txt` löst die Dorfaufgabe automatisch. In jedem Aufgabenordner steht in `AUFGABE.txt` ein kurzer Hinweis. Die Werkstatt erwartet `abgabe/maschine.conf`, das Archiv `abgabe/passwort.txt`. Der Inhalt zählt; `cp`, `mv`, `echo > …` und Pipes sind möglich. Eine unveränderte falsche Abgabe kostet nur einmal Leben, nicht bei jedem Prompt.

Dorf, Wald, Werkstatt und Archiv haben je eine `AUFGABE.txt`. Erst die richtige Abgabe lässt die Zauberdateien des Ortes erscheinen. Im Dorf werden Funke und Echo gemeinsam freigeschaltet. Heilmittel sind frei sammelbar.

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

Dein 3D-Charakter steht links unten, der grüne Grinch rechts oben. `ping -c 4 127.12.24.1` wirkt als Echo-Zauber mit vier Treffern à 1 HP. Der Rucksack zeigt während der Erkundung und im Kampf die Dateien aus `~/rucksack`. Zauber fliegen zum Gegner, Gegenangriffe zurück; beide Lebensleisten bewegen sich und zeigen Treffer als Zahlen. Der Kampf läuft rundenweise. Lesen und Nachdenken kosten keine Leben. Bei 120 Boss-LP sprengt der Grinch einmal deinen aktiven Schild und Frost. Seine normalen Gegenangriffe kosten dann 11 statt 7 Leben. Der Eispanzer zieht 8 Schaden ab. Wiederholst du denselben Schadensangriff, kommt nur ein Viertel des verbleibenden Schadens durch. Das Echo trifft immer für 4. Fehlgeschlagene Shell-Befehle im Bossraum und falsche Kampfaktionen kosten zusätzlich Leben. Vor dem Kampf fragt ein schwebendes Fenster nach deiner Zustimmung und erklärt Angreifen und Heilen. Nach **Ja** gibt es keinen Rückweg; neue Funde und Aufgaben zählen erst im nächsten Lauf. Bereits mitgebrachte Gegenstände bleiben nutzbar. Beim Sieg steigen über dem Dorf Raketen auf und der Weihnachtsstern erscheint in 3D. Mit **Zur Shell** kehrst du zur Eingabe zurück. Mit `restart` kannst du jederzeit eine neue Runde beginnen.

Punkte gibt es einmal je Ort (40), Zauberfund (80), Aufgabe (150), Heilquelle (25), unterstützter Shell-Befehlsart (10), Angriffsart (30), entferntem Treiber (120) und Sieg (500).

### Profi-Wege

```bash
# Im Bossraum: spielinterne Treiber entfernen
lsmod
modprobe -r frost_armor
modprobe -r blizzard
```

Der Grinch setzt bei jedem dritten ungeschützten Zug eine stärkere Sturmböe ein. `systemctl status` zeigt den Spieldienst. Mit `systemctl disable eissturm.service` schaltest du ihn für die Runde ab (+100 Punkte). Alle Funde lassen sich mit `mv` mitnehmen. Schild und Stern müssen verschoben werden.

Diese Befehle verändern nur das Spiel, keine Kernelmodule der VM.

## Neustarten oder alles zurücksetzen

Im Spiel:

```bash
restart           # Neue Runde, eigene Bestzeiten bleiben
restart alles     # Auch die eigenen Bestzeiten löschen
```

Diese Befehle setzen `~/welt` und `~/rucksack` zurück. Name und sonstige eigene Dateien bleiben erhalten. `restart alles` betrifft nur deinen Spielerplatz.

Auch `restart game` startet die eigene Runde neu.

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

Es ist keine Portangabe nötig. Alle SSH-Spielpasswörter sind genau **12 Zeichen** lang. Die gemeinsamen Passwörter stehen in `/opt/shell-game/.env` als `PLAYER_PASSWORD` und `DASHBOARD_PASSWORD`; zusätzlich gibt es `join-access.txt`. Alle Spieler verwenden denselben Einstieg und dasselbe Einstiegspasswort; jeder neue Spieler erhält beim Beitritt einen frisch erzeugten eigenen Container. Es gibt keine fest eingestellte maximale Spielerzahl; verfügbare VM-Ressourcen und der Netzwerkadressraum begrenzen die tatsächliche Kapazität. Die SSH-Einstellungen für eure bisherigen Admin-Benutzer bleiben erhalten.

Der gemeinsame SSH-Einstieg öffnet direkt die Charaktererstellung. Jeder neue Login erhält einen eigenen Platz. Der Name wird dort einmal eingegeben. Benannte Spielstände bleiben für das Scoreboard und die Administration gespeichert.

Die bisherigen direkten Zugänge bleiben als Alternative vorhanden: auf developer `ssh -t -p 2201 player@127.0.0.1` (Spieler 1) bzw. `ssh -t -p 2200 player@127.0.0.1` (Scoreboard). Ihre individuellen Passwörter stehen in `access.csv`. Spielerports: 2201–2223. Vom Jumphost war dieser Portbereich nicht erreichbar; der neue Einstieg verwendet den dort erreichbaren Host-Port 22.

Das Live-Scoreboard zeigt ausschließlich verbundene Spieler. Tab oder L wechselt zwischen Raster und Liste. In der Liste wählt ↑/↓ einen Spieler. Unter der Liste stehen der laufende Bash-Befehl und die drei zuletzt abgeschlossenen Befehle, inklusive Argumenten, Anführungszeichen und Pipes. Enter öffnet den umgebrochenen Verlauf, ↑/↓ und Bild↑/Bild↓ scrollen. Pro Eingabe werden bis zu 16.384 Zeichen übertragen. Der Verlauf wird im Arbeitsspeicher der Live-Dienste gehalten. Eingaben innerhalb laufender Programme sind nicht Teil der Bash-Befehlszeile.

Alle Siege zählen gemeinsam, unabhängig vom Lösungsweg. Alte Kategorien werden zur jeweils schnellsten persönlichen Bestzeit zusammengeführt; Namen, Punkte und laufender Fortschritt bleiben erhalten. **ONLINE** bedeutet eine tatsächlich verbundene Spielsitzung; bei Abbruch oder Ausloggen wechselt der Status nach wenigen Sekunden. Ein nicht mehr erreichbarer Container gilt nach spätestens acht Sekunden ohne Update als offline.

```bash
docker compose exec scoreboard scorewatch
curl http://127.0.0.1:8080/api/scores
```

## Installation und Betrieb

Voraussetzungen auf der VM: Linux, Docker Engine mit API 1.48 oder neuer (Docker 28+), Docker Compose, Python 3 und OpenSSL. Keine pip-Abhängigkeiten. Für die Terminalansicht sind UTF-8, 256 Farben und etwa 100 × 38 Zeichen sinnvoll.

```bash
cd /opt/shell-game
python3 scripts/provision.py --host DEINE-VM-IP
docker compose up -d --build
docker compose ps
sudo python3 scripts/install_entry.py
python3 scripts/check_entry.py  # Beide Standard-SSH-Zugaenge pruefen
```

`install_entry.py --plan` zeigt die Host-Änderungen ohne Schreibzugriff. Die Installation erstellt die eingeschränkten Host-Benutzer `spiel` und `score`, sichert die SSH-Konfiguration unter `/etc/frost-entry/`, prüft sie und lädt SSH neu. Diese beiden Benutzer erhalten ausschließlich den Spiel- bzw. Zuschauerzugang. Die Host-Anpassung braucht einmalig `sudo`; die Spielcontainer selbst laufen vollständig unter Compose.

Der Gateway-Container lauscht standardmäßig nur auf `127.0.0.1:2299`; der Host-Einstieg leitet dorthin weiter. `GATEWAY_BIND` und `GATEWAY_PORT` sind in `.env.example` dokumentiert. Bei einer Änderung des internen Ports das Installationsskript erneut ausführen. Der öffentliche Host-Port 22 bleibt gleich.

Wiederholtes Provisionieren erhält Zugangsdaten. `provision.py --rotate-passwords --host DEINE-VM-IP` bereitet neue 12-Zeichen-Passwörter vor und sichert die alten privat unter `backups/credentials-…`. Anschließend synchronisiert `python3 scripts/update_entry_passwords.py` die beiden Host-Konten über deren bestehende Passwörter und die normale PAM-Anmeldung; danach die Container neu erstellen. Bei einem Fehler nennt das Skript das betroffene Konto, bereits synchronisierte Konten werden bei Wiederholung übersprungen. Tokens und SSH-Schlüssel ändern sich dabei nicht. Auf einem frischen Checkout richtet `make prepare` den Einstieg, das Scoreboard und den Verwaltungsdienst ein. Weitere Spielercontainer entstehen bei der Anmeldung. Die Kapazität hängt von der VM und dem konfigurierten Netzwerkpool ab. Die bestehenden alten Spielercontainer werden bei einem Update für ihre direkten Ports beibehalten. Neue Beitritte verwenden immer neue Container. Quellen und Konfiguration liegen im Projekt; persistente Laufzeitdaten liegen in benannten Docker-Volumes. `docker compose down` erhält diese. `docker compose down -v` löscht sie ohne Sicherung und erneuert beim nächsten Start auch die SSH-Hostschlüssel. Für ein neues Event deshalb `reset-all.sh` verwenden.

Jeder neue Spieler erhält ein internes Docker-Netz aus `PLAYER_NETWORK_POOL` (Standard `10.240.0.0/16`, ein /29 pro Spieler). Docker betreibt die Bridge im Modus `isolated`. Der Spielerprozess startet ohne Linux-Capabilities. Ein vererbter Seccomp-Filter erlaubt ihm und seinen Unterprozessen ausschließlich Unix-Sockets. Die SSH-Verbindung zum Grinch läuft über einen lokalen Socket mit festem Ziel. SSH-Weiterleitungen sind deaktiviert. Das Image ist schreibgeschützt. Nur der Verwaltungsdienst `spawner` hat Zugriff auf den Docker-Socket. Docker-Administratoren gehören damit zum Vertrauensbereich des Hosts.

Vor dem Erzeugen oder Starten eines dynamischen Spielercontainers prüft der Spawner RAM, freien Plattenplatz und freie Inodes. Für das System reserviert er mindestens 1 GiB oder ein Achtel des RAM, je nachdem, welcher Wert größer ist. Bei der Prüfung zieht er das volle RAM-Budget aller laufenden Spieler vom aktuell verfügbaren Speicher ab. Auf der Docker-Platte bleiben mindestens 2 GiB oder ein Sechzehntel der Kapazität sowie Platz für die Home-Sicherungen laufender Spieler reserviert. Für neue Plätze sind kurzzeitig bis zu 32 Anmeldungen zugelassen. Danach wird alle fünf Sekunden wieder eine Anmeldung freigegeben. Bereits laufende Spiele können währenddessen weiterlaufen.

Pro Spieler gelten 256 MiB RAM und 0,5 CPU, fürs Board 256 MiB und 1 CPU, fürs Gateway 512 MiB und 2 CPU. Zusätzlicher Swap ist deaktiviert. Prozesslimits: 96 pro Spieler, 128 fürs Board, 384 fürs Gateway; maximal 2048 offene Dateien pro Prozess. Temporäre Dateisysteme sind auf 32 MiB (`/tmp`) und 16 MiB (`/run`) begrenzt, Logs auf zweimal 5 MiB. Das Gateway nutzt Debian-Pakete für Paramiko und prüft die Hostschlüssel der Zielcontainer. Limits stehen in `scripts/provision.py`. Spielstände und Hostschlüssel überleben Container-Neustarts. Beim Abmelden wird dein automatisch erzeugter Container angehalten. Beim nächsten gemeinsamen Login öffnet sich eine neue Charaktererstellung. Der feste Rahmen verwendet einen PTY-Renderer, tmux ist nicht installiert. Eine echte Bash erlaubt weiterhin normale Unterprozesse und Skripte innerhalb der Containerlimits. Beim Update werden unveränderte alte Hilfedateien ersetzt; bearbeitete Questdateien und gespeicherte Ergebnisse bleiben erhalten.

## Passwörter und automatisches Erzeugen

Die private `.env` enthält:

```dotenv
PLAYER_PASSWORD=Abcdef123456
DASHBOARD_PASSWORD=Ghijkl789012
GAME_HOST=10.0.0.60
PLAYER_NETWORK_POOL=10.240.0.0/16
```

Die Beispielwerte ersetzen; beide Passwörter müssen genau zwölf ASCII-Buchstaben/Ziffern enthalten. `DASHBOARD_PASSWORD` gilt für den SSH-Live-Scoreboard-Zugang `score`. Änderungen anwenden:

```bash
cd /opt/shell-game
python3 scripts/apply_env.py
```

Dabei werden die Konfiguration erzeugt, geänderte Host-Passwörter über die bisherigen Zugangsdaten synchronisiert und die Dienste aktualisiert. Namen und Spielstände bleiben erhalten. `.env` hat Modus 0600 und ist von Git und Docker-Builds ausgeschlossen. Passwörter landen nicht als Umgebungsvariablen in den Spielercontainern; diese erhalten eigene interne SSH-Zugangsdaten und Score-Tokens.

Automatisch erzeugte Container heißen `shell-game-elf-…` und sind zusätzlich mit `frost.managed=shell-game` markiert. Sie werden vom Compose-Verwaltungsdienst betreut; `docker compose ps` allein listet sie nicht auf:

```bash
docker ps -a --filter label=frost.managed=shell-game
docker compose exec gateway python3 -m frost.gateway --list
```

`reset-all.sh` sichert und entfernt auch automatisch erzeugte Spieler, ihre Volumes, Netzwerke und Codes. `scripts/reset_slot.py elf-ID --expected-name NAME` entfernt gezielt einen Spieler. Bei Updates dynamische Container vorher über `reset-all.sh` **nicht** zurücksetzen; `scripts/reset_event.py --backup-only` sichert und hält sie an, ihre Daten bleiben erhalten.

## Speichergrenzen und Sicherung

Das Home jedes neuen Spielers hat 64 MiB Platz und maximal 4096 Inodes. Eine einzelne Datei aus der Spieler-Shell darf bis zu 16 MiB groß werden. Diese Grenzen gelten auch bei vielen kleinen Dateien und benötigen keine zusätzliche Host-Installation.

Das aktive Home liegt auf einem begrenzten tmpfs. Der Container sichert es bei aktiver Sitzung ungefähr alle 30 Sekunden, beim Abmelden und beim regulären Herunterfahren in ein privates Docker-Volume. Erst ein vollständiges Archiv ersetzt die letzte Sicherung. Bei einem harten Ausfall können Dateiänderungen seit der letzten erfolgreichen Sicherung verloren gehen. Punktestand und Spielfortschritt werden separat gespeichert.

Beim Update bestehender fester Plätze übernimmt der Container das alte Home beim ersten Start. Das ursprüngliche Volume bleibt als schreibgeschützte Rückfallkopie erhalten. Bereits eingerichtete ext4-Quota-Volumes aus `storage/volumes.json` werden für feste Plätze weiterverwendet. Früher erzeugte dynamische Container behalten ihre ursprüngliche Konfiguration. Für neue Anmeldungen gelten die aktuellen Limits.

## Tests

```bash
python3 -m unittest discover -s tests -v
docker compose build scoreboard
python3 tests/integration.py
python3 tests/integration.py --players 23 --load-only
python3 tests/dynamic_integration.py
```

Der Integrationstest erstellt das **separate Projekt `frostbyte-check`** mit freien lokalen Ports, eigenen Volumes und zwei Spielercontainern. Dort prüft er automatische Platzvergabe, direkten Charaktereinstieg, volle Belegung, echte SSH-Logins, Tab-Vervollständigung, `tree`, `cp`, Aufgabenabgabe, direkten Kampfeinstieg und Rückwegsperre, ausführbare Gegenstände, Bosskampf, Gewinnbildschirm, separaten Scoreboard-Zugang und den vollständigen Reset samt Sicherung. Der zusätzliche Lasttest hält 23 Spielersitzungen und einen Zuschauer über das Gateway gleichzeitig offen. Nur im Test teilen sich die Container ein Bridge-Netz, um neben den produktiven Netzen nicht den Docker-Adresspool zu erschöpfen. Anschließend entfernt er nur dieses Testprojekt. Bestehende Spielerplätze werden nicht verwendet.

Der dynamische Test verwendet ausschließlich `frost-dynamic-check`: 25 neue Spieler ohne vorab angelegte Plätze, getrennte Netze, Anhalten nach Abmeldung, neuer Einstieg nach Dienstneustart und kompletter Reset mit Sicherung.
