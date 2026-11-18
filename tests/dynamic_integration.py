#!/usr/bin/env python3
"""On-demand provisioning beyond 23 players in a disposable labelled project."""
import argparse
import json
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from frost.docker_api import Docker
from scripts.dynamic_cleanup import cleanup
from ssh_smoke import Session

ROOT=Path(__file__).resolve().parents[1]
PROJECT='frost-dynamic-check'


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--players",type=int,default=25);args=parser.parse_args()
    count=args.players
    if count<1: parser.error("--players must be positive")
    folder=ROOT/'.integration/dynamic'; folder.mkdir(parents=True,mode=0o700,exist_ok=True)
    config=json.loads((ROOT/'compose.yaml').read_text()); config['name']=PROJECT
    config['services']={k:v for k,v in config['services'].items() if k in ('gateway','scoreboard','spawner')}
    config['networks']={'control':{}}
    config['volumes']={k:{} for k in config['volumes'] if k.startswith(('gateway-','scoreboard-','spawner-','controller-'))}
    sockets=[];ports={}
    for key in ('gateway','scoreboard','api'):
        s=socket.socket();s.bind(('127.0.0.1',0));ports[key]=s.getsockname()[1];sockets.append(s)
    router=json.loads((ROOT/'secrets/gateway/router.json').read_text())
    (folder/'router.json').write_text(json.dumps({'scoreboard':router['scoreboard']}))
    (folder/'spawn-config.json').write_text(json.dumps({'project':PROJECT,'image':'frostbyte:local','network_pool':'10.241.0.0/16'}))
    for name,service in config['services'].items():
        service.pop('build',None)
        service.get('environment',{}).pop('FROST_BOUNDED_STORAGE',None)
        if name!='spawner': service['networks']=['control'];service['ports']=[f'127.0.0.1:{ports[name]}:22']
        if name=='scoreboard': service['ports'].append(f'127.0.0.1:{ports["api"]}:8080')
        service['healthcheck']['interval']='2s'
        service['depends_on']={k:v for k,v in service.get('depends_on',{}).items() if k in config['services']}
        service['volumes']=[str(ROOT/v[2:]) if v.startswith('./') else v for v in service['volumes']]
        service['volumes']=[v for v in service['volumes'] if ':/slots/player' not in v]
        service['volumes']=[f'{folder}/router.json:/run/bootstrap/router.json:ro' if ':/run/bootstrap/router.json:' in v else
                            f'{folder}/spawn-config.json:/run/bootstrap/spawn-config.json:ro' if ':/run/bootstrap/spawn-config.json:' in v else v for v in service['volumes']]
    path=folder/'compose.yaml';path.write_text(json.dumps(config,indent=2))
    (folder/'askpass').write_text('#!/bin/sh\ncat "$FROST_PASSWORD_FILE"\n');(folder/'askpass').chmod(0o700)
    (folder/'known_hosts').unlink(missing_ok=True)
    dc=['docker','compose','-f',str(path)]
    def run(*args,**kw): return subprocess.run([*dc,*args],check=True,**kw)
    docker=Docker();sessions=[];codes=[];slot_ids=[]
    def managed(): return docker.containers(['frost.managed='+PROJECT])
    def scores():
        with urllib.request.urlopen(f'http://127.0.0.1:{ports["api"]}/api/scores') as r: return json.load(r)['players']
    for s in sockets:s.close()
    try:
        run('up','-d','--wait','--wait-timeout','120')
        assert managed()==[]
        for i in range(count):
            s=Session('gateway',ports['gateway'],folder);sessions.append(s)
            s.expect('GEMEINSAMER EINSTIEG');s.send('\r');s.expect('DEIN FORTSETZEN-CODE:',timeout=60)
            codes.append(re.search(r'[A-F0-9]{4}(?:-[A-F0-9]{4}){3}',s.output.decode(errors='ignore')).group())
            s.send('\r');s.expect('Winterheld?');s.send(f'DynamicElf{i:02}\r');s.expect('Rucksack')
            s.send("printf 'DYNAMIC_%s\\n' OK\r");s.expect('DYNAMIC_OK')
            s.close();sessions.remove(s)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                all_rows=managed()
                if len(all_rows)==i+1 and all(r['State']=='exited' for r in all_rows): break
                time.sleep(.2)
            assert len(all_rows)==i+1 and all(r['State']=='exited' for r in all_rows),all_rows
            print(f'PASS: new container {i+1}/{count} created and stopped after disconnect',flush=True)
        rows=managed(); assert len(rows)==count
        first=next(r for r in scores() if r['name']=='DynamicElf00')['slot']
        before=next(r['Id'] for r in rows if r['Labels']['frost.slot']==first)
        for row in rows:
            info=docker.call('GET','/containers/'+row['Id']+'/json')
            assert info['HostConfig']['Memory']==268435456 and info['HostConfig']['NanoCpus']==500000000
            assert not info['HostConfig']['PortBindings']
            assert not info['Config']['Labels'].get('com.docker.compose.project')
            assert not info['Config']['Labels'].get('com.docker.compose.service')
            assert all(m['Destination']!='/var/run/docker.sock' for m in info['Mounts'])
        assert len({next(iter(r['NetworkSettings']['Networks'])) for r in rows})==count
        # An abandoned name prompt must leave neither a slot nor a container.
        abandoned=Session('gateway',ports['gateway'],folder);sessions.append(abandoned)
        abandoned.expect('GEMEINSAMER EINSTIEG');abandoned.send('\r');abandoned.expect('DEIN FORTSETZEN-CODE:',timeout=60)
        abandoned.close();sessions.remove(abandoned)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline and len(managed())!=count: time.sleep(.2)
        assert len(managed())==count
        run('exec','-T','--user','player','gateway','python3','-c',
            "from frost.dynamic import Client\ntry: Client().call('create')\nexcept PermissionError: pass\nelse: raise SystemExit('Player could access controller')")
        backup_only=['python3',str(ROOT/'scripts/reset_event.py'),'--compose-file',str(path),
                     '--backup-dir',str(folder/'backups'),'--backup-only','--recreate']
        subprocess.run(backup_only,check=True)
        print('PASS: abandoned joins cleaned up; unprivileged controller access denied; forced service recreation preserves players',flush=True)
        s=Session('gateway',ports['gateway'],folder);sessions.append(s)
        s.expect('GEMEINSAMER EINSTIEG');s.send('r'+codes[0]+'\r');s.expect('DEIN FORTSETZEN-CODE:',timeout=60);s.send('\r');s.expect('Rucksack')
        assert next(r['Id'] for r in managed() if r['Labels']['frost.slot']==first)==before
        s.send("printf 'RESUMED_%s\\n' OK\r");s.expect('RESUMED_OK')
        board=Session('scoreboard',ports['gateway'],folder,user='score');sessions.append(board);board.expect('LIVE-SCOREBOARD')
        assert len(scores())==count
        print(f'PASS: {count} unique containers, isolated networks, resource limits, shared board and same-container resume after service restart',flush=True)
        for s in sessions:s.close()
        sessions=[];time.sleep(1)
        reset=['python3',str(ROOT/'scripts/reset_event.py'),'--compose-file',str(path),'--backup-dir',str(folder/'backups')]
        subprocess.run([*reset,'--confirm','ALLES'],check=True)
        assert managed()==[] and scores()==[]
        print('PASS: global reset backs up and removes dynamic players, volumes, networks and scoreboard entries',flush=True)
    finally:
        for s in sessions:s.close()
        run('logs','--no-color',stdout=(folder/'containers.log').open('w'))
        run('down','-v')
        cleanup(PROJECT)


if __name__=='__main__':main()
