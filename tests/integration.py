#!/usr/bin/env python3
"""Real SSH + reset tests in their own Compose project. Never reset live players."""
import json
import socket
import sys
import subprocess
import tarfile
import time
import urllib.request
import re
import argparse
import threading
from pathlib import Path
from functools import partial
from unittest.mock import patch
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
    # Provision the fixed-port test independently of the installed player pool.
    sys.path.insert(0,str(ROOT))
    from scripts import provision
    fixture=folder/"static"
    fixture.mkdir(mode=0o700,exist_ok=True)
    with patch.object(provision,"ROOT",fixture):
        provision.main(["--static","--players",str(args.players),"--host","localhost"])
    connect=partial(Session,secret_root=fixture/"secrets")
    config=json.loads((fixture/"compose.yaml").read_text())
    config["name"]="frostbyte-check"
    config["services"]={k:v for k,v in config["services"].items() if k in ["scoreboard","gateway",*slots]}
    # A single test-only bridge avoids exhausting Docker's address pools while
    # the live project keeps its separate per-player bridges.
    config["networks"]={"test":{}}
    config["volumes"]={key:{} for key in config["volumes"]}
    config["volumes"]={k:v for k,v in config["volumes"].items() if k.startswith(tuple(f"{s}-" for s in config["services"]))}
    router=json.loads((fixture/"secrets/gateway/router.json").read_text())
    (folder/"router.json").write_text(json.dumps({k:v for k,v in router.items() if k in ["scoreboard",*slots]}))
    listeners=[]
    ports={}
    for name in ["scoreboard",*slots,"api","music","gateway"]:
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
        service["volumes"]=[str(fixture/v[2:]) if v.startswith("./") else v for v in service["volumes"]]
        if name=="gateway":
            service["networks"]=["test"]
            service["depends_on"]={k:v for k,v in service["depends_on"].items() if k in config["services"]}
            service["volumes"]=[v for v in service["volumes"] if ":/slots/" not in v or v.split(":",1)[0] in config["volumes"]]
            service["volumes"]=[f"{folder}/router.json:/run/bootstrap/router.json:ro" if ":/run/bootstrap/router.json:" in v else v for v in service["volumes"]]
        if name=="scoreboard":
            service["networks"]=["test"]
            service["ports"].append(f"127.0.0.1:{ports['api']}:8080")
            service["ports"].append(f"127.0.0.1:{ports['music']}:8094")
            service["environment"]["MUSIC_URL"]=f"http://127.0.0.1:{ports['music']}"
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
            sessions[0].drain(.15)
        capture("state-timeout")
        raise AssertionError(f"State timeout: {value}")
    def scores():
        with urllib.request.urlopen(f"http://127.0.0.1:{ports['api']}/api/scores",timeout=3) as r: return json.load(r)["players"]
    def capture(label):
        content=s.output.decode(errors="replace")
        (folder/(label+".txt")).write_text(content)
        return content
    sessions=[]
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
            session=connect("gateway",ports["gateway"],folder,music=slot=="player02" and not args.load_only)
            sessions.append(session)
            session.expect("CHARAKTER",timeout=45)
            assert b"FORTSETZEN-CODE" not in session.output
            session.send(name+"\t\x1bOC\t\x1bOC\t\x1bOC\t\x1bOC\r")
            session.expect("Rucksack")
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
            spectator=connect("scoreboard",ports["gateway"],folder,user="score")
            sessions.append(spectator)
            spectator.expect("LIVE-SCOREBOARD")
            print(f"PASS: {args.players} concurrent interactive gateway players plus a separate live scoreboard viewer",flush=True)
            return
        s=sessions[0]
        s.send("\x1b[<0;100;42M\x1b[<0;100;42m")
        s.expect("http://127.0.0.1:")
        s.send("musik\r")
        s.expect("Enter zurück")
        link = re.search(rb"http://127\.0\.0\.1:\d+/#([\w-]{16})", s.output)
        assert link, "Missing personal music link"
        audio_url = f"http://127.0.0.1:{ports['music']}"
        stream_url = audio_url + "/stream/" + link[1].decode()
        def volume_event(stream):
            while line := stream.readline():
                if line.startswith(b"data: "):
                    return json.loads(line[6:])
            raise AssertionError("Music stream ended")
        from array import array
        from frost.sound.compose import soundtrack
        track_samples=soundtrack()
        native=sessions[1]
        recording=folder/"terminal.pcm"
        assert b"Terminalton aktiv" in native.output and b"Musik im Browser:" not in native.output
        native.send("musik 0\r")
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            data=recording.read_bytes()
            if len(data)>4410 and not any(data[-4410:]): break
            native.drain(.1)
        else: raise AssertionError("Native mixer did not go silent")
        native.send("musik 70\r")
        native.send("cd ../wald; mv .lichtung/beeren ~/rucksack/\r")
        wait_state(lambda v:"beeren" in v["bag"],slot="player02")
        native.drain(.4)
        start=recording.stat().st_size//2
        native.send("~/rucksack/beeren\r")
        wait_state(lambda v:"heal:beeren" in v["rewards"],slot="player02")
        native.drain(.8)
        samples=array("h",recording.read_bytes())
        if sys.byteorder!="little": samples.byteswap()
        # Ordinary music matches the score exactly. The berry tone changes its samples.
        differences=sum(samples[i]!=round(track_samples[i%len(track_samples)]*.43*.70)
                        for i in range(start,len(samples)))
        assert 1000<differences<len(samples)-start-1000,differences
        assert b"frost-volume=" not in native.output and b"frost-sound=" not in native.output
        print("PASS: native SSH soundtrack, mute, volume and audible berry PCM mixed locally",flush=True)
        with urllib.request.urlopen(stream_url, timeout=6) as stream:
            assert volume_event(stream)==40
            s.send("\x1b[C")
            assert volume_event(stream)==50
            s.send("m")
            assert volume_event(stream)==0
            s.send("m")
            assert volume_event(stream)==50
            s.send("\r")
            # Click the shell footer at 120×42 while Bash has unfinished input.
            s.send("printf 'MOUSE_%s\\n' ")
            def click(x):
                s.send(f"\x1b[<0;{x};42M\x1b[<0;{x};42m")
            click(116)
            assert volume_event(stream)==60
            click(106)
            assert volume_event(stream)==50
            click(111)
            assert volume_event(stream)==0
            click(111)
            assert volume_event(stream)==50
            s.send("OK\r")
            s.expect("MOUSE_OK")
        s.send("tipp\r")
        wait_state(lambda v:v.get("hints_left")==2)
        with urllib.request.urlopen(audio_url+"/winter.wav") as track:
            assert track.read(4)==b"RIFF" and int(track.headers["Content-Length"])>100000
        print("PASS: personal audio link, real mixer arrows, mute/unmute and loop audio", flush=True)
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
        s.send("aussehen\r"); s.expect("CHARAKTER")
        # Editor at 120×42: advance hair colour and commit with the mouse.
        s.send("\x1b[<0;57;23M\x1b[<0;57;23m")
        s.expect("schwarz")
        s.send("\x1b[<0;60;34M\x1b[<0;60;34m")
        wait_state(lambda v:v["avatar"]["hair"]=="schwarz")
        s.send("aussehen\r"); s.expect("CHARAKTER")
        s.send("\x1b[<0;31;23M\x1b[<0;31;23m")
        s.expect("blond")
        s.send("\r")
        wait_state(lambda v:v["avatar"]["hair"]=="blond")
        s.send("printf 'AVATAR_%s\\n' RETURN\r"); s.expect("AVATAR_RETURN")
        limits=run("exec","-T","player01","sh","-c","cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.swap.max /sys/fs/cgroup/pids.max /sys/fs/cgroup/cpu.max",capture_output=True,text=True).stdout.splitlines()
        assert limits==["268435456","0","96","50000 100000"],limits
        print("PASS: nano save/exit, terminal resize, avatar editor return, RAM/swap/PID/CPU limits",flush=True)
        extra=connect("gateway",ports["gateway"],folder)
        sessions.append(extra)
        extra.expect("Alle Spielerplaetze sind vergeben")
        extra.send("\r"); extra.close(); sessions.remove(extra)
        print("PASS: common SSH entry allocates distinct containers and rejects capacity overflow",flush=True)
        # Both sides, and earlier commands in the same parsed input, must be inert.
        for line in ("touch /tmp/chain-a&&touch /tmp/chain-b",
                     "touch /tmp/chain-a; (true && touch /tmp/chain-b)",
                     "touch /tmp/chain-a &&\r touch /tmp/chain-b",
                     'echo "$(touch /tmp/chain-a && touch /tmp/chain-b)"',
                     "eval 'touch /tmp/chain-a && touch /tmp/chain-b'"):
            s.send(line+"\r")
            s.expect("Gib die Befehle einzeln ein.")
        run("exec","-T","player01","sh","-c","test ! -e /tmp/chain-a && test ! -e /tmp/chain-b")
        s.send("printf 'LITERAL_%s_OK\\n' '&&'\r")
        s.expect("LITERAL_&&_OK")
        print("PASS: interactive && chains rejected before execution, literal ampersands preserved",flush=True)
        s.send("tree -L 2 ~/welt\r")
        s.expect("wurzeln")
        wait_state(lambda v:"shell:tree" in v["rewards"])
        s.send("restart game\r")
        s.expect("Neuer Lauf")
        s.drain(.3)
        run("exec","-T","player01","sh","-c","cd /home/player/welt && test -d dorf/abgabe && test ! -e dorf/abgabe/.gitkeep && test ! -e dorf/funke && test ! -e dorf/ping && test ! -e wald/wurzeln/frost && test ! -e archiv/.depot/stern && test ! -e werkstatt/schild")
        s.send("cp post/wunschzettel.txt abgabe/gerettet.txt\r")
        wait_state(lambda v:"quest:wunschzettel" in v["rewards"])
        s.send("mv fun\t ping ~/rucksack/\r")
        wait_state(lambda v:"funke" in v["bag"])
        s.send("cd ../\t\t")
        s.expect("archiv/")
        s.send("\x03")
        s.drain(.3)
        s.send("mv kakao ~/rucksack/; cp post/wunschzettel.txt abgabe/gerettet.txt\r")
        wait_state(lambda v:"quest:wunschzettel" in v["rewards"])
        s.send("cd ../werkstatt; printf 'band=an\\nlicht=an\\nziel=weihnachten\\n' > abgabe/maschine.conf\r")
        wait_state(lambda v:"quest:geschenkband" in v["rewards"])
        s.send("cp schild ~/rucksack/\r")
        wait_state(lambda v:v["area"]=="werkstatt")
        assert "schild" not in state()["bag"]
        s.send("mv -f schild ~/rucksack/; cd ../archiv; echo AURORA > abgabe/passwort.txt\r")
        wait_state(lambda v:"quest:passwort" in v["rewards"])
        s.send("mv .depot/stern ~/rucksack/\r")
        wait_state(lambda v:{"schild","stern"}<=set(v["bag"]))
        s.send("cd ../wald; mv .lichtung/beeren ~/rucksack/; ~/rucksack/beeren\r")
        wait_state(lambda v:"heal:beeren" in v["rewards"] and v["hp"]==100)
        s.send("cp .lichtung/rindenzeichen abgabe/zeichen.txt\r")
        wait_state(lambda v:"quest:waldzeichen" in v["rewards"])
        s.send("mv wurzeln/frost ~/rucksack/\r")
        wait_state(lambda v:"frost" in v["bag"])
        run("exec","-T","player01","test","!","-e","/home/player/rucksack/beeren")
        # Visit the marked hiding place rather than assuming a fixed arena.
        place=run("exec","-T","player01","python3","-c",
                  "from frost.client import request; from frost.trail import hiding_place; print(hiding_place(request()['state']))",
                  text=True,capture_output=True).stdout.strip()
        s.send(f"cd ~/welt/{place}\r")
        wait_state(lambda v:v["area"]==place)
        s.send("nmap grinch\r"); wait_state(lambda v:v["grinch_found"])
        s.send("ssh grinch\r")
        s.expect("BOSSKAMP STARTEN?")
        capture("boss-hints")
        s.send("n\r")
        s.drain(.4)
        assert not state()["boss_started"] and state()["area"]==place
        s.send("ssh grinch\r")
        s.expect("BOSSKAMP STARTEN?")
        s.send("j\r")
        wait_state(lambda v:v["boss_started"])
        s.send("systemctl disable eissturm.service\r")
        wait_state(lambda v:not v["storm_service"])
        with urllib.request.urlopen(stream_url, timeout=6) as stream:
            assert volume_event(stream)==50
            s.send("ping -c 4 127.12.24.1\r")
            assert volume_event(stream)==["ping","claw"]
        wait_state(lambda v:v["boss_hp"]==236)
        s.send("cd ../dorf; printf 'LOCK_%s\\n' \"$PWD\"\r")
        s.expect("LOCK_/home/player/welt/zitadelle")
        s.send("builtin cd ../dorf\r")
        s.expect("Kein Rueckweg")
        s.drain(.3)
        s.send("printf 'BUILTIN_%s\\n' \"$PWD\"\r")
        s.expect("BUILTIN_/home/player/welt/zitadelle")
        capture("combat-arena")
        s.send("cp ../wald/wurzeln/frost ~/rucksack/\r")
        s.drain(.5)
        assert set(state()["bag"])<=set(state()["battle_items"])
        with urllib.request.urlopen(stream_url, timeout=6) as stream:
            assert volume_event(stream)==50
            for module,title in (("frost_armor","EISPANZER ZERBROCHEN"),("blizzard","SCHNEESTURM ERLOSCHEN")):
                s.send(f"modprobe -r {module}\r")
                s.expect(title)
                assert volume_event(stream)[0]==module
        print("PASS: both modprobe commands animate the arena and reach the SSH player's audio stream",flush=True)
        s.send("while true; do ~/rucksack/funke; done\r")
        s.expect("Zur Shell",timeout=15)
        won=wait_state(lambda v:v["status"]=="won")
        assert won["method"]=="loop",won
        result=capture("victory-screen")
        assert "WEIHNACHTEN GERETTET" in result and "PUNKTE" in result,result
        # Press the festival's return button in the full-screen inner terminal.
        s.send("\x1b[<0;60;41M\x1b[<0;60;41m")
        s.drain(.5)
        s.send("printf 'LOOP_%s\\n' FINISHED\r")
        s.expect("LOOP_FINISHED")
        print("PASS: real cp, Tab/Tab-Tab, automatic quest, carried heal, executable loop, full-screen victory, usable Bash",flush=True)
        run("exec","-T","player01","sh","-c","! command -v tmux && test ! -e /usr/bin/tmux")
        assert state()["avatar"]=={"hair":"blond","shirt":"blau","gender":"weiblich","style":"Locken"},state()["avatar"]
        print("PASS: avatar customization persists; tmux is absent",flush=True)
        board=connect("scoreboard",ports["gateway"],folder,user="score")
        sessions.append(board)
        board.expect("LIVE-SCOREBOARD")
        board.send("\t")
        board.expect("Enter Verlauf")
        cmds=["echo 'two  spaces' | wc -c","pwd","pwd","true","printf '%s' winter"]
        for cmd in cmds:
            s.send(cmd+"\r")
        s.send("sleep 4; echo 'two  words'\r")
        deadline=time.monotonic()+9
        while time.monotonic()<deadline:
            raw=run("exec","-T","scoreboard","python3","-c",
                    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/api/live').read().decode())",
                    text=True,capture_output=True).stdout
            hero=next(r for r in json.loads(raw)["players"] if r["slot"]=="player01")
            if hero.get("command_active") and hero["command_label"]=="sleep 4; echo 'two  words'": break
            time.sleep(.1)
        assert hero["command_label"]=="sleep 4; echo 'two  words'" and hero["command_history"]==cmds[::-1][:3],hero
        board.send("\r"); board.expect("Befehlsverlauf")
        assert "funke" in hero["bag"]
        s.drain(3.1)
        payload=scores()
        hero=next(r for r in payload if r["slot"]=="player01")
        assert hero["avatar"]=={"hair":"blond","shirt":"blau","gender":"weiblich","style":"Locken"},hero
        assert hero["connected"] and "mode" not in hero and "best" in hero["bests"],hero
        print("PASS: live scoreboard contains chosen avatar, real presence and one shared best time",flush=True)
        print("PASS: tree, boss hints/confirmation, no retreat, framed shell and separate live score login",flush=True)
        s.close(); sessions.remove(s)
        deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            if not next(r for r in scores() if r["slot"]=="player01")["connected"]: break
            time.sleep(.2)
        assert not next(r for r in scores() if r["slot"]=="player01")["connected"]
        with urllib.request.urlopen(stream_url, timeout=4) as stream:
            assert volume_event(stream) is None
        s=connect("player01",ports["player01"],folder)
        sessions.append(s)
        s.expect("Rucksack")
        assert state()["name"]=="TestElf01" and state()["status"]=="won"
        print("PASS: direct slot login restores the same player and finished run",flush=True)
        s.send("restart\r")
        s.expect("Neuer Lauf")
        wait_state(lambda v:v["score"]==40 and v["bag"]==[] and "best" in v["bests"])
        s.send("restart alles\r")
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
        new=connect("gateway",ports["gateway"],folder)
        sessions.append(new)
        new.expect("CHARAKTER")
        print("PASS: global reset backup, all names/scores/homes cleared, host keys preserved, fresh login modal",flush=True)
    finally:
        drain_stop.set()
        for worker in drain_threads: worker.join(timeout=1)
        for session in sessions: session.close()
        run("logs","--no-color",stdout=(folder/"containers.log").open("w"))
        run("down","-v")


if __name__=="__main__": main()
