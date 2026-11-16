#!/usr/bin/env python3
"""Full event reset with offline backup. Dry-run unless --confirm ALLES is given."""
import argparse
import datetime
import json
import os
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file",type=Path,default=ROOT/"compose.yaml")
    parser.add_argument("--backup-dir",type=Path,default=ROOT/"backups")
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument("--confirm",choices=["ALLES"])
    modes.add_argument("--backup-only",action="store_true",help="Nur sichern, keine Daten zuruecksetzen")
    args=parser.parse_args()
    compose=["docker","compose","-f",str(args.compose_file.resolve())]

    def run(*words,**kwargs):
        return subprocess.run([*compose,*words],check=True,**kwargs)

    config=json.loads(run("config","--format","json",capture_output=True,text=True).stdout)
    players=sorted(s for s in config["services"] if s.startswith("player"))
    targets=[*players,"scoreboard"]+(["gateway"] if "gateway" in config["services"] else [])
    if not players or "scoreboard" not in config["services"]:
        raise SystemExit("Keine Frostbyte-Konfiguration. Nichts geaendert.")
    print(f"Projekt: {config['name']} / {len(players)} Spieler + Scoreboard",flush=True)
    print("Nur Sicherung; keine Daten werden zurueckgesetzt." if args.backup_only else
          "Loescht Namen, Punkte, Rekorde und komplette Spieler-Homes (inkl. Welt/Rucksack).",flush=True)
    print("Passwoerter, Ports und SSH-Hostschluessel bleiben. Vorher entsteht eine Sicherung.",flush=True)
    if args.confirm!="ALLES" and not args.backup_only:
        print("Nur Vorschau. Ausfuehren mit: ./reset-all.sh --confirm ALLES")
        return
    ids={s:run("ps","-a","-q",s,capture_output=True,text=True).stdout.strip() for s in targets}
    if not all(ids.values()):
        raise SystemExit("Zuerst alle Container mit docker compose up -d erstellen. Nichts geloescht.")
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup=args.backup_dir.resolve()/f"{config['name']}-{stamp}"
    backup.mkdir(parents=True,mode=0o700)
    backup.chmod(0o700)
    run("stop")
    try:
        # Complete every backup before the first mutation. Stopped containers cannot
        # submit stale scores or create files while the reset is in progress.
        for slot in targets:
            target=backup/slot
            target.mkdir(mode=0o700)
            for location,label in [("/var/lib/frost","state"),("/home/player","home")]:
                with (target/(label+".tar")).open("wb") as archive:
                    subprocess.run(["docker","cp",f"{ids[slot]}:{location}/.","-"],stdout=archive,check=True)
                (target/(label+".tar")).chmod(0o600)
        (backup/"manifest.json").write_text(json.dumps({"project":config["name"],"players":players,"created_utc":stamp},indent=2))
        print(f"Sicherung vollstaendig: {backup}",flush=True)
        if args.backup_only:
            print("Keine Spielstaende geloescht. Container werden wieder gestartet.",flush=True)
            return
        for slot in players:
            run("run","--rm","--no-deps","--user","root","--entrypoint","python3",slot,"-c",
                "from pathlib import Path; Path('/var/lib/frost/state.json').unlink(missing_ok=True)",stdout=subprocess.DEVNULL)
            run("run","--rm","--no-deps","--user","player","--entrypoint","python3",slot,"-m","frost.world","wipe",stdout=subprocess.DEVNULL)
            print(f"{slot}: zurueckgesetzt",flush=True)
        run("run","--rm","--no-deps","--user","root","--entrypoint","python3","scoreboard","-c",
            "from pathlib import Path; [Path('/var/lib/frost/'+name).unlink(missing_ok=True) for name in ('scoreboard.sqlite','scoreboard.sqlite-wal','scoreboard.sqlite-shm')]",stdout=subprocess.DEVNULL)
        if "gateway" in targets:
            run("run","--rm","--no-deps","--user","root","--entrypoint","python3","gateway","-c",
                "from pathlib import Path; [Path('/var/lib/frost/'+name).unlink(missing_ok=True) for name in ('joins.sqlite','joins.sqlite-wal','joins.sqlite-shm')]",stdout=subprocess.DEVNULL)
    finally:
        run("up","-d","--wait","--wait-timeout","90")
    print("Fertig. Alle Namen, Spielstaende und Bestzeiten sind leer. Die bisherigen Zugaenge gelten weiter.",flush=True)


if __name__=="__main__": main()
