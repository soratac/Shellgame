# Verifikation — 12. November 2026

## Gemeinsamer Einstieg und Boss-Abfrage

- **23 gleichzeitig bedienbare SSH-Spielersitzungen über denselben Gateway-Port plus ein separater Live-Scoreboard-Zuschauer** im isolierten Testprojekt geprüft. Jeder Spieler erhielt einen eigenen Container. Alle 23 Shells beantworteten einen Testbefehl, die Gateway-Datenbank meldete 23 aktive Plätze.
- Automatische Vergabe ist zusätzlich mit 23 parallelen Anforderungen getestet; ein 24. Spieler wird abgewiesen. Fortsetzen-Codes bleiben über Neustarts erhalten, aktive Plätze können nicht doppelt geöffnet werden, alte Verbindungen können keine neueren Reservierungen freigeben.
- Reale SSH-Tests prüfen das Startfenster, `tree`, Boss-Hinweise, Ablehnen und Bestätigen des Kampfes, gesperrten Rückweg (auch nach `builtin cd`) und die Sperre für nachträglich eingesammelte Zauber. Vor Bestätigung gibt es keinen Kampf oder Fehlbefehlsschaden.
- Die zwei getrennten Host-Weiterleitungsschlüssel erreichen das produktive Gateway bzw. Scoreboard. Die SSH-Match-Konfiguration wurde mit `sshd -t` und `sshd -T` geprüft: neue Spielbenutzer verwenden Passwort plus erzwungenen Spielzugang; die bestehende öffentliche-Schlüssel-Anmeldung des Administrators bleibt erhalten.
- Der produktive Port-22-Einstieg benötigt noch die einmalige Root-Aktivierung mit `sudo python3 scripts/install_entry.py`. Danach prüft `python3 scripts/check_entry.py --via jump` beide vollständigen Zugänge vom Jumphost ohne Portangabe und ohne einen Spielerplatz zu belegen.

## Aktuelle Überarbeitung

- **31 automatisierte Tests bestanden**: Kampf, Siegwege, Niederlage, einmalige Belohnungen, Inventar/Entfernen von Dateien, keine Ladungen durch erneutes Kopieren, tragbare Heilung, automatische Dateiabgabe ohne wiederholten Fehlerschaden, persönlicher Gesamtreset und alte Spielzustände.
- Punkte- und Bestzeiten-Ranglisten sortieren unabhängig und stabil. Tabellenspalten bleiben auch bei breiten Unicode-Namen und langen Werten ausgerichtet.
- Isolierter SSH-Test mit zwei Spielern und Zuschauer im eigenen Compose-Projekt `frostbyte-check`: Namensfenster, Tab/Tab Tab, echte `cp`-Befehle, Questabgabe, Beeren benutzen, Verbrauch der Datei, ausführbarer Funkenzauber, echte Bash-Endlosschleife, Sofortsieg und automatisch wieder bedienbare Shell.
- Vollbild-Gewinnanzeige mit Punkten und Laufzeit erschien tatsächlich im SSH-Terminal und wurde mit Enter geschlossen. Rahmen-Panes vorhanden; keine F2/F3/F4-Bindings in der Spieloberfläche.
- Neues Scoreboard per SSH geöffnet und zwischen Punkte- und Speedrun/Loop-Ansicht gewechselt.
- Normaler Neustart erhält Bestzeiten, `neustart alles` entfernt sie.
- **Gesamtreset nur im Testprojekt ausgeführt**: Vorschau ändert nichts; Sicherungen enthalten die vorherigen Zustände; Namen, Scoreboard und komplette Spieler-Homes sind nach bestätigtem Reset leer. SSH-Hostschlüssel bleiben gleich und der nächste Login zeigt wieder das Namensfenster.
- Produktivupdate mit vorheriger Offline-Sicherung unter `backups/`. Keine produktiven Spielstände zurückgesetzt. Namen und vorhandene Bestzeiten aller 23 Plätze gegen die Sicherung geprüft. Alle 25 produktiven Container laufen mit erfolgreichem Healthcheck.

## Bereits bei der ersten Version geprüft

23 gleichzeitig offene SSH-Spielersitzungen, separate Zuschaueranmeldung, authentifizierte Score-Übertragung mit 23 parallelen Schreibvorgängen und SQLite-Persistenz, Erhalt von Spielständen bei Container-Neuerstellung sowie der Schutz von Score-Token, Passwortdatei und autoritativem Spielstand vor der Spieler-UID.

Der externe SSH-Port war aus einem unabhängigen Docker-Netz erreichbar. Vom tatsächlichen Jumphost läuft Port 2201 in einen Timeout, während Host-Port 22 erreichbar ist: der neue gemeinsame Host-Einstieg verwendet nach Aktivierung diesen bereits erreichbaren Port. Die neue Version verändert keine Netz-Firewallregeln.
