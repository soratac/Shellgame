# Verifikation — 18. November 2026

## Automatische Spielercontainer und .env

- **48 Unit-Tests bestanden**, einschließlich 60 paralleler Reservierungen ohne festen Spielerpool, Fortsetzen, verwaister Beitritte, fehlgeschlagener Containeranlage, dynamischer Score-Tokens und privater `.env`-Werte. Die Diensterkennung ignoriert von Compose-Builds geerbte Labels; neue Spielercontainer überschreiben diese, damit sie nicht als Scoreboard oder Compose-Dienst erscheinen.
- Isolierter Docker-/SSH-Test mit **25 gleichzeitig verbundenen Spielern**. Jede SSH-Sitzung erreichte eine interaktive Shell in einem eigenen Container mit eigenen Volumes und eigenem /29-Netz. Das Live-Scoreboard zeigte alle 25 Spieler. Nach dem Abmelden hielten die Container an. Geprüft wurden auch CPU- und RAM-Limits, die Isolation des Docker-Sockets und der Erhalt der Spielcontainer bei einem Dienstneustart.
- Weiterer vollständiger Test mit drei Spielern: abgebrochener Beitritt entfernt seinen unbenannten Container, Zugriff auf die Verwaltungs-Schnittstelle als Spieler verweigert, Offline-Sicherung plus Neuerstellung der Infrastruktur erhält Spieler und Codes, kompletter Reset entfernt dynamische Container/Volumes/Netze und Scores. Beim Gesamtreset werden Gateway und Board neu erstellt, damit keine gelöschten Netzwerkverweise zurückbleiben.
- Der bisherige komplette SSH-Spieltest mit zwei festen Spielern läuft weiter erfolgreich, einschließlich Charaktereditor, nano, Tab, Loop-Sieg, Live-Board und Reset.
- Frische Provisionierung erzeugt nur Gateway, Scoreboard und Verwaltungsdienst. `.env` hat Modus 0600, ist vom Git-/Build-Kontext ausgeschlossen und enthält passende 12-Zeichen-Passwörter. Es wird keine maximale Spielerzahl konfiguriert; reale Kapazität hängt von VM und Netzwerkpool ab.
- Produktivupdate mit Sicherung `backups/shell-game-20261118T103632.027515Z/`: Namen, Bestzeiten und Fortsetzen-Codes der 23 bisherigen Plätze erhalten. Beide Host-Zugänge vom Jumphost geprüft. Vollständiger Beitritt über Host-SSH bis zur Charakterauswahl erfolgreich; der unbenannte Testcontainer wurde nach Trennung automatisch entfernt.

## Ein gemeinsames Spiel und Live-Charaktere (Version 5)

- **41 Unit-Tests bestanden.** Alte Bestzeiten aus allen vier Kategorien werden zum schnellsten gemeinsamen Rekord zusammengeführt; laufende Werte und Charaktere bleiben erhalten. Ein separater Speedrun-Modus wird nicht mehr angeboten.
- Die zwei Board-Ansichten sortieren denselben Spielerbestand nach Punkten oder gemeinsamer Bestzeit. Layout auf 80 × 24, 120 × 42 und 160 × 48 sowie verkleinertem Terminal geprüft. Farbige Miniaturen und ausgewählter Live-Charakter mit Lebensleisten, Ort und Treffern.
- Echter SSH-Spieltest: gewählte Charakterfarben und gemeinsamer Rekord erreichen das Board; `connected` ist während der Sitzung wahr und nach Trennung falsch. Wiederverbinden, Loop-Sieg, Editor, Tab, vollständiger Reset mit Sicherung und Charaktereditor weiterhin erfolgreich.
- Alle **25 Spielpasswörter sind eindeutig und genau 12 Zeichen lang**, private Dateien haben Modus 0600. CSV und Router-Konfiguration enthalten passende Zugangsdaten. Beide Host-Konten wurden über ihre normale PAM-Anmeldung synchronisiert und vom Jumphost auf Port 22 mit den neuen Passwörtern geprüft.

- Produktivupdate gesichert unter `backups/shell-game-20261118T095526.463026Z/`. Für alle 23 Plätze Name, HP, Boss-HP, Punkte, Start/Ende und Charakter mit der Sicherung verglichen; Bestzeiten entsprechen jeweils dem Minimum aller alten Kategorien. Alle 25 Container gesund.
- Nach Deployment authentifizieren alle 23 Spielercontainer und das Board erfolgreich mit den neuen 12-Zeichen-Passwörtern. Beide Standard-SSH-Zugänge erneut vom Jumphost geprüft. Die produktive Score-API liefert gemeinsame Bestzeiten und Live-Charakterdaten.

## Charakter, Kampf und Ressourcen (Version 4)

- **37 Unit-Tests bestanden**, darunter Drei-Orte-Siegel, normaler Sieg, Loop-Abkürzung, Charaktervalidierung und Erhalt beim Neustart, begrenzte Animationsereignisse, beide Lebensleisten und Schadenszahlen.
- Isolierter SSH-Test: Haar-/Shirtfarbe gewählt und gespeichert; `aussehen` kehrt zur bedienbaren Shell zurück. `nano` schreibt und speichert eine Datei; nach Beenden ist die Shell wieder nutzbar. Terminal auf 90 × 32 verkleinert und zurückvergrößert; Bash antwortet weiter.
- Im tatsächlichen Spielercontainer geprüft: `memory.max=268435456`, `memory.swap.max=0`, `pids.max=96`, `cpu.max=50000 100000`. tmux ist weder im PATH noch als `/usr/bin/tmux` vorhanden.
- Vollständiger Spiel- und Resettest mit neuem PTY-Rahmen erfolgreich: Tab, Tab Tab, Dateiaufgaben, Boss-Abfrage, kein Rückweg, echter Loop-Sieg, Gewinnfenster, Wiederverbindung, Zuschauer und gesicherter Gesamtreset.
- Neuer Lasttest bestanden: 23 gleichzeitig interaktive Spieler mit festem PTY-Rahmen und ein Live-Scoreboard-Zuschauer. Alle Shells beantworteten Testbefehle.
- Produktivupdate mit Offline-Sicherung `backups/shell-game-20261118T094628.347739Z/`: Namen und Bestzeiten aller 23 Plätze mit der Sicherung verglichen; alle 25 Container gesund. RAM-/Swap-/CPU-/PID-Grenzen aller produktiven Container geprüft.
- Persistente Home-/State-Quotas: Installer vorbereitet und Vorschau geprüft. Die tatsächliche Einrichtung und Prüfung der ext4-Mounts erfordert noch den Root-Schritt `sudo python3 scripts/install_quotas.py`; bis dahin sind diese Volumes nicht quotiert.

## Gemeinsamer Einstieg und Bosskampf

- **23 gleichzeitig bedienbare SSH-Spielersitzungen über denselben Gateway-Port plus ein separater Live-Scoreboard-Zuschauer** im isolierten Testprojekt geprüft. Jeder Spieler erhielt einen eigenen Container. Alle 23 Shells beantworteten einen Testbefehl, die Gateway-Datenbank meldete 23 aktive Plätze.
- Automatische Vergabe ist zusätzlich mit 23 parallelen Anforderungen getestet; ein 24. Spieler wird abgewiesen. Fortsetzen-Codes bleiben über Neustarts erhalten, aktive Plätze können nicht doppelt geöffnet werden, alte Verbindungen können keine neueren Reservierungen freigeben.
- Der SSH-Spieltest prüft das Startfenster und `tree`. Vor dem Fund verweist `ssh grinch` auf die Spur. Nach dem Scan beginnt der Kampf mit einem einzigen SSH-Befehl. Der Test prüft auch die Torsperre bei `builtin cd` und die Sperre für nachträglich eingesammelte Zauber.
- Die zwei getrennten Host-Weiterleitungsschlüssel erreichen das produktive Gateway bzw. Scoreboard. Die SSH-Match-Konfiguration wurde mit `sshd -t` und `sshd -T` geprüft: neue Spielbenutzer verwenden Passwort plus erzwungenen Spielzugang; die bestehende öffentliche-Schlüssel-Anmeldung des Administrators bleibt erhalten.
- Der produktive Port-22-Einstieg wurde am 15. November vom Jumphost erfolgreich mit `scripts/check_entry.py --host 10.0.0.60 --via jump` geprüft: Spieler-Lobby und Live-Scoreboard ohne Portangabe, ohne einen Spielerplatz zu belegen.

## Aktuelle Überarbeitung

- **31 automatisierte Tests bestanden**: Kampf, Siegwege, Niederlage, einmalige Belohnungen, Inventar/Entfernen von Dateien, keine Ladungen durch erneutes Kopieren, tragbare Heilung, automatische Dateiabgabe ohne wiederholten Fehlerschaden, persönlicher Gesamtreset und alte Spielzustände.
- Punkte- und Bestzeiten-Ranglisten sortieren unabhängig und stabil. Tabellenspalten bleiben auch bei breiten Unicode-Namen und langen Werten ausgerichtet.
- Isolierter SSH-Test mit zwei Spielern und Zuschauer im eigenen Compose-Projekt `frostbyte-check`: Namensfenster, Tab/Tab Tab, echte `cp`-Befehle, Questabgabe, Beeren benutzen, Verbrauch der Datei, ausführbarer Funkenzauber, echte Bash-Endlosschleife, Sofortsieg und automatisch wieder bedienbare Shell.
- Vollbild-Gewinnanzeige mit Punkten und Laufzeit erschien tatsächlich im SSH-Terminal und wurde mit Enter geschlossen. Fester PTY-Rahmen vorhanden; keine tmux-Fenster oder F2/F3/F4-Bedienung.
- Neues Scoreboard per SSH geöffnet und zwischen Punkte- und Speedrun/Loop-Ansicht gewechselt.
- Normaler Neustart erhält Bestzeiten, `restart alles` entfernt sie.
- **Gesamtreset nur im Testprojekt ausgeführt**: Vorschau ändert nichts; Sicherungen enthalten die vorherigen Zustände; Namen, Scoreboard und komplette Spieler-Homes sind nach bestätigtem Reset leer. SSH-Hostschlüssel bleiben gleich und der nächste Login zeigt wieder das Namensfenster.
- Produktivupdate mit vorheriger Offline-Sicherung unter `backups/`. Keine produktiven Spielstände zurückgesetzt. Namen und vorhandene Bestzeiten aller 23 Plätze gegen die Sicherung geprüft. Alle 25 produktiven Container laufen mit erfolgreichem Healthcheck.

## Bereits bei der ersten Version geprüft

23 gleichzeitig offene SSH-Spielersitzungen, separate Zuschaueranmeldung, authentifizierte Score-Übertragung mit 23 parallelen Schreibvorgängen und SQLite-Persistenz, Erhalt von Spielständen bei Container-Neuerstellung sowie der Schutz von Score-Token, Passwortdatei und autoritativem Spielstand vor der Spieler-UID.

Der externe SSH-Port war aus einem unabhängigen Docker-Netz erreichbar. Vom tatsächlichen Jumphost läuft Port 2201 in einen Timeout, während Host-Port 22 erreichbar ist: der neue gemeinsame Host-Einstieg verwendet nach Aktivierung diesen bereits erreichbaren Port. Die neue Version verändert keine Netz-Firewallregeln.
