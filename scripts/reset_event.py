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
    parser.add_argument("--recreate",action="store_true",help="Dienste nach der Sicherung neu erstellen, z.B. fuer geaenderte Secrets")
    args=parser.parse_args()
    compose=["docker","compose","-f",str(args.compose_file.resolve())]

    def run(*words,**kwargs):
        return subprocess.run([*compose,*words],check=True,**kwargs)

    config=json.loads(run("config","--format","json",capture_output=True,text=True).stdout)
    players=sorted(s for s in config["services"] if s.startswith("player"))
    targets=[*players,"scoreboard"]+(["gateway"] if "gateway" in config["services"] else [])+(["spawner"] if "spawner" in config["services"] else [])
    if "scoreboard" not in config["services"]:
        raise SystemExit("Keine Frostbyte-Konfiguration. Nichts geaendert.")
    print(f"Projekt: {config['name']} / {len(players)} Spieler + Scoreboard",flush=True)
    if "spawner" in config["services"]: print("Automatisch erzeugte Spielercontainer werden ebenfalls gesichert/zurueckgesetzt.",flush=True)
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
    dynamic={}
    checkpointed=set()
    if players:
        live_info=json.loads(subprocess.check_output(["docker","inspect",*(ids[s] for s in players)]))
        checkpointed.update(s for s,info in zip(players,live_info)
                            if info["Config"]["Labels"].get("frost.home")=="checkpoint")
    if "spawner" in config["services"]:
        import sys
        sys.path.insert(0,str(ROOT))
        from frost.docker_api import Docker
        docker=Docker()
        run("exec","-T","spawner","python3","-c","from frost.dynamic import Client; Client().call('pause')",stdout=subprocess.DEVNULL)
        managed=docker.containers(['frost.managed='+config['name']])
        checkpointed.update(r['Labels']['frost.slot'] for r in managed if r['Labels'].get('frost.home')=='checkpoint')
        dynamic={r['Labels']['frost.slot']:r['Id'] for r in managed if not r['Names'][0].endswith('-init')}
        for ident in dynamic.values(): docker.call('POST','/containers/'+ident+'/stop?t=30')
    run("stop")
    try:
        # Complete every backup before the first mutation. Stopped containers cannot
        # submit stale scores or create files while the reset is in progress.
        if checkpointed:
            containers = [ids.get(slot, dynamic.get(slot)) for slot in sorted(checkpointed)]
            stopped = json.loads(subprocess.check_output(["docker", "inspect", *containers]))
            for slot, info in zip(sorted(checkpointed), stopped):
                state = info["State"]
                if state["Running"] or state["ExitCode"] or state["OOMKilled"]:
                    raise SystemExit(f"{slot} wurde nicht sauber beendet. Letzte Home-Sicherung prüfen. Kein Reset.")
        for slot in [*targets,*dynamic]:
            target=backup/slot
            target.mkdir(mode=0o700)
            for location,label in [("/var/lib/frost","state"),("/home/player","home")]:
                if label=="home" and slot in checkpointed:
                    ident=ids.get(slot,dynamic.get(slot))
                    subprocess.run(["docker","cp",ident+":/var/lib/frost-private/saved/home.tar",str(target/"home.tar")],check=True)
                    (target/"home.tar").chmod(0o600)
                    continue
                with (target/(label+".tar")).open("wb") as archive:
                    subprocess.run(["docker","cp",f"{ids.get(slot,dynamic.get(slot))}:{location}/.","-"],stdout=archive,check=True)
                (target/(label+".tar")).chmod(0o600)
        (backup/"manifest.json").write_text(json.dumps({"project":config["name"],"players":players,"dynamic_players":list(dynamic),"created_utc":stamp},indent=2))
        print(f"Sicherung vollstaendig: {backup}",flush=True)
        if args.backup_only:
            print("Keine Spielstaende geloescht. Container werden wieder gestartet.",flush=True)
            return
        for slot in players:
            run("run","--rm","--no-deps","--user","root","--entrypoint","python3",slot,"-c",
                "from pathlib import Path; Path('/var/lib/frost/state.json').unlink(missing_ok=True)",stdout=subprocess.DEVNULL)
            if config["services"][slot].get("labels",{}).get("frost.home")=="checkpoint":
                run("run","--rm","--no-deps","--entrypoint","python3",slot,"-I","-m","frost.home_store","clear",stdout=subprocess.DEVNULL)
            else:
                run("run","--rm","--no-deps","--user","player","--entrypoint","python3",slot,"-I","-m","frost.world","wipe",stdout=subprocess.DEVNULL)
            print(f"{slot}: zurueckgesetzt",flush=True)
        run("run","--rm","--no-deps","--user","root","--entrypoint","python3","scoreboard","-c",
            "from pathlib import Path; [Path('/var/lib/frost/'+name).unlink(missing_ok=True) for name in ('scoreboard.sqlite','scoreboard.sqlite-wal','scoreboard.sqlite-shm')]",stdout=subprocess.DEVNULL)
        if "spawner" in targets:
            from dynamic_cleanup import cleanup
            cleanup(config['name'])
            run("run","--rm","--no-deps","--user","root","--entrypoint","python3","spawner","-c",
                "from pathlib import Path; Path('/var/lib/frost/dynamic.json').write_text('{}'); Path('/run/controller/registry.json').write_text('{}')",stdout=subprocess.DEVNULL)
        if "gateway" in targets:
            run("run","--rm","--no-deps","--user","root","--entrypoint","python3","gateway","-c",
                "from pathlib import Path; [Path('/var/lib/frost/'+name).unlink(missing_ok=True) for name in ('joins.sqlite','joins.sqlite-wal','joins.sqlite-shm')]",stdout=subprocess.DEVNULL)
    finally:
        run("up","-d",*(["--force-recreate"] if args.recreate or (args.confirm=="ALLES" and "spawner" in targets) else []),"--wait","--wait-timeout","90")
    print("Fertig. Alle Namen, Spielstaende und Bestzeiten sind leer. Die bisherigen Zugaenge gelten weiter.",flush=True)


if __name__=="__main__": main()
