#!/usr/bin/env python3
"""Real SSH + reset tests in their own Compose project. Never reset live players."""
import copy
import json
import os
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import re
import argparse
import threading
from pathlib import Path

from ssh_smoke import Session

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--players",type=int,default=2)
    parser.add_argument("--load-only",action="store_true")
    args=parser.parse_args()
    if not 2<=args.players<=23: parser.error("--players must be between 2 and 23")
    slots=[f"player{i:02}" for i in range(1,args.players+1)]
    folder=ROOT/".integration"
    folder.mkdir(mode=0o700,exist_ok=True)
    config=json.loads((ROOT/"compose.yaml").read_text())
    config["name"]="frostbyte-check"
    config["services"]={k:v for k,v in config["services"].items() if k in ["scoreboard","gateway",*slots]}
    # A single test-only bridge avoids exhausting Docker's address pools while
    # the live project keeps its separate per-player bridges.
    config["networks"]={"test":{}}
    config["volumes"]={key:{} for key in config["volumes"]}
    config["volumes"]={k:v for k,v in config["volumes"].items() if k.startswith(tuple(f"{s}-" for s in config["services"]))}
    router=json.loads((ROOT/"secrets/gateway/router.json").read_text())
    (folder/"router.json").write_text(json.dumps({k:v for k,v in router.items() if k in ["scoreboard",*slots]}))
    listeners=[]
    ports={}
    for name in ["scoreboard",*slots,"api","gateway"]:
        sock=socket.socket()
        sock.bind(("127.0.0.1",0))
        listeners.append(sock)
        ports[name]=sock.getsockname()[1]
    for name,service in config["services"].items():
        service.pop("build",None)
        service.get("environment",{}).pop("FROST_BOUNDED_STORAGE",None)
        service.get("environment",{}).pop("FROST_DYNAMIC",None)
        service["volumes"]=[v for v in service["volumes"] if ":/run/controller" not in v]
        service["networks"]=["test"]
        service["healthcheck"]["interval"]="2s"
        service["ports"]=[f"127.0.0.1:{ports[name]}:22"]
        service["volumes"]=[str(ROOT/v[2:]) if v.startswith("./") else v for v in service["volumes"]]
        if name=="gateway":
            service["networks"]=["test"]
            service["depends_on"]={k:v for k,v in service["depends_on"].items() if k in config["services"]}
            service["volumes"]=[v for v in service["volumes"] if ":/slots/" not in v or v.split(":",1)[0] in config["volumes"]]
            service["volumes"]=[f"{folder}/router.json:/run/bootstrap/router.json:ro" if ":/run/bootstrap/router.json:" in v else v for v in service["volumes"]]
        if name=="scoreboard":
            service["networks"]=["test"]
            service["ports"].append(f"127.0.0.1:{ports['api']}:8080")
    path=folder/"compose.yaml"
    path.write_text(json.dumps(config,indent=2))
    dc=["docker","compose","-f",str(path)]
    def run(*args,**kw): return subprocess.run([*dc,*args],check=True,**kw)
    def state(slot="player01"):
        result=run("exec","-T",slot,"python3","-c","import json; from frost.client import request; print(json.dumps(request()['state']))",capture_output=True,text=True)
        return json.loads(result.stdout)
    def wait_state(predicate, slot="player01", timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            value=state(slot)
            if predicate(value): return value
            time.sleep(.15)
        raise AssertionError(f"State timeout: {value}")
    def scores():
        with urllib.request.urlopen(f"http://127.0.0.1:{ports['api']}/api/scores",timeout=3) as r: return json.load(r)["players"]
    def capture(label):
        content=s.output.decode(errors="replace")
        (folder/(label+".txt")).write_text(content)
        return content
    sessions=[]
    codes={}
    drain_stop=threading.Event()
    drain_threads=[]
    for sock in listeners: sock.close()
    try:
        run("up","-d","--wait","--wait-timeout","90")
        askpass=folder/"askpass"
        askpass.write_text('#!/bin/sh\ncat "$FROST_PASSWORD_FILE"\n')
        askpass.chmod(0o700)
        (folder/"known_hosts").unlink(missing_ok=True)
        for slot in slots:
            name="雪Elf" if slot=="player02" else "TestElf"+slot[-2:]
            session=Session("gateway",ports["gateway"],folder)
            sessions.append(session)
            session.expect("GEMEINSAMER EINSTIEG")
            session.send("\r")
            session.expect("DEIN FORTSETZEN-CODE:")
            codes[slot]=re.search(r"[A-F0-9]{4}(?:-[A-F0-9]{4}){3}",session.output.decode(errors="ignore")).group()
            session.send("\r")
            session.expect("Winterheld?")
            assert b"DEIN WINTERHELD" in session.output
            session.send(name+"\t\x1bOC\t\x1bOC\r")
            session.expect("DEINE SHELL")
            session.drain(.5)
            if args.load_only:
                def drain(session=session):
                    while not drain_stop.is_set(): session.drain(.1)
                worker=threading.Thread(target=drain,daemon=True)
                worker.start(); drain_threads.append(worker)
                print(f"Connected via shared gateway: {slot}",flush=True)
        if args.load_only:
            for i,session in enumerate(sessions,1): session.send(f"printf 'LOAD_%s\\n' {i:02}\r")
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if all(f"LOAD_{i:02}".encode() in session.output for i,session in enumerate(sessions,1)): break
                time.sleep(.2)
            assert all(f"LOAD_{i:02}".encode() in session.output for i,session in enumerate(sessions,1))
            assert all(session.proc.poll() is None for session in sessions)
            active=run("exec","-T","gateway","python3","-c","import sqlite3; print(sqlite3.connect('/var/lib/frost/joins.sqlite').execute('SELECT count(*) FROM joins WHERE active=1').fetchone()[0])",capture_output=True,text=True)
            assert int(active.stdout)==args.players
            spectator=Session("scoreboard",ports["gateway"],folder,user="score")
            sessions.append(spectator)
            spectator.expect("LIVE-SCOREBOARD")
            print(f"PASS: {args.players} concurrent interactive gateway players plus a separate live scoreboard viewer",flush=True)
            return
        s=sessions[0]
        # Native terminal behavior remains usable inside the fixed compositor.
        s.send("nano /tmp/editor-check\r")
        s.expect("GNU nano")
        s.send("winter-test\x0f"); s.drain(.3); s.send("\r"); s.drain(.3); s.send("\x18")
        s.drain(.4); s.send("cat /tmp/editor-check; printf 'EDITOR_%s\\n' OK\r")
        s.expect("EDITOR_OK")
        content=run("exec","-T","player01","cat","/tmp/editor-check",capture_output=True,text=True).stdout
        assert content.strip()=="winter-test",content
        import fcntl,termios,struct
        fcntl.ioctl(s.fd,termios.TIOCSWINSZ,struct.pack("HHHH",32,90,0,0)); s.drain(.6)
        s.send("printf 'RESIZE_%s\\n' OK\r"); s.expect("RESIZE_OK")
        fcntl.ioctl(s.fd,termios.TIOCSWINSZ,struct.pack("HHHH",42,120,0,0)); s.drain(.5)
        s.send("aussehen\r"); s.expect("DEIN WINTERHELD"); s.send("\r"); s.drain(.3)
        s.send("printf 'AVATAR_%s\\n' RETURN\r"); s.expect("AVATAR_RETURN")
        limits=run("exec","-T","player01","sh","-c","cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.swap.max /sys/fs/cgroup/pids.max /sys/fs/cgroup/cpu.max",capture_output=True,text=True).stdout.splitlines()
        assert limits==["268435456","0","96","50000 100000"],limits
        print("PASS: nano save/exit, terminal resize, avatar editor return, RAM/swap/PID/CPU limits",flush=True)
        extra=Session("gateway",ports["gateway"],folder)
        sessions.append(extra)
        extra.expect("GEMEINSAMER EINSTIEG"); extra.send("\r")
        extra.expect("Alle Spielerplaetze sind vergeben")
        extra.send("\r"); extra.close(); sessions.remove(extra)
        print("PASS: common SSH entry allocates distinct containers and rejects capacity overflow",flush=True)
        s.send("tree -L 2 ~/welt\r")
        s.expect("wurzeln")
        wait_state(lambda v:"shell:tree" in v["rewards"])
        s.send("neustart\r")
        s.expect("Neuer Lauf")
        s.drain(.3)
        s.send("cp fun\t ~/rucksack/\r")
        wait_state(lambda v:"funke" in v["bag"])
        s.send("cd ../\t\t")
        s.expect("archiv/")
        s.send("\x03")
        s.drain(.3)
        s.send("cp kakao ~/rucksack/; cp post/wunschzettel.txt abgabe/gerettet.txt\r")
        wait_state(lambda v:"quest:wunschzettel" in v["rewards"])
        s.send("cd ../wald; cp wurzeln/frost beeren ~/rucksack/; ~/rucksack/beeren\r")
        wait_state(lambda v:"heal:beeren" in v["rewards"] and v["hp"]==100)
        s.send("test ! -e ~/rucksack/beeren && printf 'HEAL_%s\\n' CONSUMED\r")
        s.expect("HEAL_CONSUMED")
        s.send("cd ../zitadelle\r")
        s.expect("BOSSKAMP STARTEN?")
        capture("boss-hints")
        s.send("n\r")
        s.drain(.4)
        assert not state()["boss_started"] and state()["area"]=="wald"
        s.send("cd ../zitadelle\r")
        s.expect("BOSSKAMP STARTEN?")
        s.send("j\r")
        wait_state(lambda v:v["boss_started"])
        s.send("cd ../dorf; printf 'LOCK_%s\\n' \"$PWD\"\r")
        s.expect("LOCK_/home/player/welt/zitadelle")
        s.send("builtin cd ../dorf\r")
        s.expect("Kein Rueckweg")
        s.drain(.3)
        s.send("printf 'BUILTIN_%s\\n' \"$PWD\"\r")
        s.expect("BUILTIN_/home/player/welt/zitadelle")
        capture("combat-arena")
        s.send("cp ../archiv/stern ~/rucksack/\r")
        s.drain(.5)
        assert "stern" not in state()["bag"]
        s.send("while true; do ~/rucksack/funke; done\r")
        s.expect("ENTER - ZUR SHELL",timeout=15)
        won=wait_state(lambda v:v["status"]=="won")
        assert won["method"]=="loop",won
        result=capture("victory-screen")
        assert "WEIHNACHTEN GERETTET" in result and "PUNKTE" in result,result
        s.send("\r")
        s.drain(.5)
        s.send("printf 'LOOP_%s\\n' FINISHED\r")
        s.expect("LOOP_FINISHED")
        print("PASS: real cp, Tab/Tab-Tab, automatic quest, carried heal, executable loop, full-screen victory, usable Bash",flush=True)
        run("exec","-T","player01","sh","-c","! command -v tmux && test ! -e /usr/bin/tmux")
        assert state()["avatar"]=={"hair":"blond","shirt":"blau"},state()["avatar"]
        print("PASS: avatar customization persists; tmux is absent",flush=True)
        board=Session("scoreboard",ports["gateway"],folder,user="score")
        sessions.append(board)
        board.expect("LIVE-SCOREBOARD")
        board.send("2")
        board.expect("BESTZEIT")
        board.send("1")
        board.expect("PUNKTE")
        payload=scores()
        hero=next(r for r in payload if r["slot"]=="player01")
        assert hero["avatar"]=={"hair":"blond","shirt":"blau"},hero
        assert hero["connected"] and "mode" not in hero and "best" in hero["bests"],hero
        print("PASS: live scoreboard contains chosen avatar, real presence and one shared best time",flush=True)
        print("PASS: tree, boss hints/confirmation, no retreat, framed shell and separate live score login",flush=True)
        s.close(); sessions.remove(s)
        deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            if not next(r for r in scores() if r["slot"]=="player01")["connected"]: break
            time.sleep(.2)
        assert not next(r for r in scores() if r["slot"]=="player01")["connected"]
        s=Session("gateway",ports["gateway"],folder)
        sessions.append(s)
        s.expect("GEMEINSAMER EINSTIEG"); s.send("r"+codes["player01"]+"\r")
        s.expect("DEIN FORTSETZEN-CODE:"); s.send("\r")
        s.expect("DEINE SHELL")
        assert state()["name"]=="TestElf01" and state()["status"]=="won"
        print("PASS: reconnect code restores the same player and finished run",flush=True)
        s.send("neustart\r")
        s.expect("Neuer Lauf")
        wait_state(lambda v:v["score"]==40 and v["bag"]==[] and "best" in v["bests"])
        s.send("neustart alles\r")
        s.expect("Neuer Lauf")
        wait_state(lambda v:not v["bests"])
        s.send("touch ~/reset-test-marker\r")
        s.drain(.3)
        print("PASS: normal restart keeps records; personal full reset clears records and inventory",flush=True)
        fingerprints={slot:run("exec","-T",slot,"ssh-keygen","-lf","/var/lib/frost/hostkeys/ssh_host_ed25519_key.pub",capture_output=True,text=True).stdout for slot in ("player01","player02","scoreboard","gateway")}
        for session in sessions: session.close()
        sessions=[]
        reset=["python3",str(ROOT/"scripts/reset_event.py"),"--compose-file",str(path),"--backup-dir",str(folder/"backups")]
        subprocess.run(reset,check=True)
        assert state()["name"]=="TestElf01"
        subprocess.run([*reset,"--confirm","ALLES"],check=True)
        wait_state(lambda v:v["name"]=="" and v["score"]==0 and not v["bests"])
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            try:
                if scores()==[]: break
            except OSError: pass
            time.sleep(.2)
        assert scores()==[]
        for slot, fingerprint in fingerprints.items():
            after=run("exec","-T",slot,"ssh-keygen","-lf","/var/lib/frost/hostkeys/ssh_host_ed25519_key.pub",capture_output=True,text=True).stdout
            assert after==fingerprint
        run("exec","-T","--user","player","player01","test","!","-e","/home/player/reset-test-marker")
        backup=sorted((folder/"backups").iterdir())[-1]
        with tarfile.open(backup/"player01"/"state.tar") as archive:
            member=next(m for m in archive.getmembers() if m.name.endswith("state.json"))
            assert json.load(archive.extractfile(member))["name"]=="TestElf01"
        new=Session("gateway",ports["gateway"],folder)
        sessions.append(new)
        new.expect("GEMEINSAMER EINSTIEG"); new.send("\r")
        new.expect("DEIN FORTSETZEN-CODE:"); new.send("\r")
        new.expect("Winterheld?")
        print("PASS: global reset backup, all names/scores/homes cleared, host keys preserved, fresh login modal",flush=True)
    finally:
        drain_stop.set()
        for worker in drain_threads: worker.join(timeout=1)
        for session in sessions: session.close()
        run("logs","--no-color",stdout=(folder/"containers.log").open("w"))
        run("down","-v")


if __name__=="__main__": main()
