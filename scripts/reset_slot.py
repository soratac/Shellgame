#!/usr/bin/env python3
"""Operator-only reset of one slot, guarded by its exact current player name."""
import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(slot,code,user="root",check=True):
    return subprocess.run(["docker","compose","exec","-T","--user",user,slot,"python3","-c",code],
                          cwd=ROOT,check=check,text=True,capture_output=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slot",help="player01 oder automatisch erzeugte elf-ID")
    parser.add_argument("--expected-name",required=True)
    args=parser.parse_args()
    if not re.fullmatch(r"player[0-9]+|elf-[0-9a-f]{16}",args.slot): raise SystemExit("Ungueltiger Spielerplatz.")
    if args.slot.startswith("elf-"):
        run("gateway",f"from frost.dynamic import Client; Client().call('forget', {args.slot!r}, expected_name={args.expected_name!r})")
        run("scoreboard",f"import sqlite3; db=sqlite3.connect('/var/lib/frost/scoreboard.sqlite'); db.execute('DELETE FROM scores WHERE slot=?', ({args.slot!r},)); db.commit()")
        subprocess.run(["docker","compose","exec","-T","gateway","python3","-m","frost.gateway","--release-slot",args.slot],cwd=ROOT,check=True)
        print(f"{args.slot}: Container und gespeicherte Daten entfernt; gemeinsame Zugaenge bleiben.")
        return
    state=json.loads(run(args.slot,"from frost.client import request; import json; print(json.dumps(request()['state']))").stdout)
    if state["name"]!=args.expected_name:
        raise SystemExit("Current name does not match; no changes made.")
    # All mutations are scoped to this one slot. Credentials and SSH host keys stay intact.
    subprocess.run(["docker","compose","exec","-T",args.slot,"pkill","-KILL","-u","player"],
                   cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    result=json.loads(run(args.slot,f"from frost.client import request; import json; print(json.dumps(request('admin-reset', [{args.expected_name!r}])))").stdout)
    if not result["ok"]: raise SystemExit(result["message"])
    subprocess.run(["docker","compose","exec","-T","--user","player",args.slot,"python3","-m","frost.world","reset"],cwd=ROOT,check=True)
    run(args.slot,"import os; from frost.home_store import save; save() if os.environ.get('FROST_CHECKPOINT_HOME')=='1' else None")
    run("scoreboard",f"import sqlite3; db=sqlite3.connect('/var/lib/frost/scoreboard.sqlite'); db.execute('DELETE FROM scores WHERE slot=?', ({args.slot!r},)); db.commit()")
    config=json.loads(subprocess.check_output(["docker","compose","config","--format","json"],cwd=ROOT,text=True))
    if "gateway" in config["services"]:
        subprocess.run(["docker","compose","exec","-T","gateway","python3","-m","frost.gateway","--release-slot",args.slot],cwd=ROOT,check=True)
    print(f"{args.slot}: cleared; credentials and SSH host keys preserved.")


if __name__=="__main__": main()
