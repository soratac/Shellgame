#!/usr/bin/env python3
"""Install persistent filesystem caps. Run with sudo; never uses privileged containers.

Each Docker volume gets its own preallocated ext4 filesystem. Existing volumes
stay intact for recovery. Containers are stopped while copying and validating.
"""
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVICE='frost-storage-shell-game.service'
MOUNTER='''#!/usr/bin/python3
import json,subprocess
from pathlib import Path
for entry in json.loads(Path('/etc/frost-storage-shell-game.json').read_text()):
    image,target=entry['image'],entry['target']
    if not subprocess.run(['mountpoint','-q',target]).returncode: continue
    subprocess.run(['mount','-o','loop,nosuid,nodev',image,target],check=True)
'''


def run(*cmd,**kw): return subprocess.run(list(cmd),check=True,**kw)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',action='store_true')
    args=parser.parse_args()
    if args.plan:
        print('Für Installationen mit begrenztem Arbeits-Home ist keine zusätzliche Einrichtung nötig.')
        print('Für ältere feste Volumes: 64 MiB persistentes Home + 16 MiB Spielstand; Board-Zustand 32 MiB.')
        print('Sichert alle Daten, stoppt das Spiel, kopiert in begrenzte ext4-Dateisysteme und startet es neu.')
        print('Alte Docker-Volumes bleiben erhalten. Mounts werden vor Docker beim Booten geladen.')
        return
    if os.geteuid()!=0: raise SystemExit('Bitte: sudo python3 /opt/shell-game/scripts/install_quotas.py')
    for binary in ('docker','fallocate','mkfs.ext4','mount','mountpoint','systemctl','cp','du'):
        if not shutil.which(binary): raise SystemExit('Fehlt: '+binary)
    dc=['docker','compose','-f',str(ROOT/'compose.yaml')]
    config=json.loads(subprocess.check_output([*dc,'config','--format','json']))
    if config['name']!='shell-game': raise SystemExit('Unerwartetes Compose-Projekt; nichts geaendert.')
    players=[v for k,v in config["services"].items() if k.startswith("player")]
    if (not players and "spawner" in config["services"]) or (players and all(v.get("labels",{}).get("frost.home")=="checkpoint" for v in players)):
        print("Spieler-Homes verwenden bereits begrenzte Arbeitsdateisysteme und private Sicherungen.")
        return
    # Inspect the actual current mounts; never assume Docker's storage path.
    sources={}
    for slot in config['services']:
        ident=subprocess.check_output([*dc,'ps','-q',slot],text=True).strip()
        if not ident: raise SystemExit('Zuerst alle Container starten: '+slot)
        info=json.loads(subprocess.check_output(['docker','inspect',ident]))[0]
        for mount in info['Mounts']:
            suffix={'/home/player':'home','/var/lib/frost':'state'}.get(mount['Destination'])
            if suffix: sources[slot+'-'+suffix]=mount['Source']
    storage=ROOT/'storage'
    manifest=storage/'volumes.json'
    if manifest.exists():
        run('systemctl','start',SERVICE)
        run(*dc,'up','-d','--wait')
        print('Quotas bereits aktiv; Mounts und Container geprueft.'); return
    required=sum((64 if key.endswith('-home') else 32 if key=='scoreboard-state' else 16)*1024**2 for key in sources)
    if shutil.disk_usage(ROOT).free < required+512*1024**2:
        raise SystemExit('Zu wenig freier Platz fuer Quotas und Reserve. Nichts geaendert.')
    if storage.is_symlink(): raise SystemExit('storage darf kein Symlink sein.')
    storage.mkdir(mode=0o755,exist_ok=True)
    os.chown(storage,0,0); storage.chmod(0o755)
    # Full offline backup must succeed before touching volume configuration.
    run('python3',str(ROOT/'scripts/reset_event.py'),'--backup-only')
    original=(ROOT/'compose.yaml').read_bytes()
    run(*dc,'stop')
    entries=[]; bounded={}; changed=False
    created_images=[]; created_targets=[]
    try:
        for key,source in sources.items():
            mib=64 if key.endswith('-home') else 32 if key=='scoreboard-state' else 16
            used=int(subprocess.check_output(['du','-s','-B1',source],text=True).split()[0])
            if used>mib*1024**2*.75: raise RuntimeError(key+' ist zu gross fuer die vorgesehene Quota. Alte Daten bleiben erhalten.')
            image=storage/(key+'.img'); target=storage/('mount-'+key)
            if image.exists() or image.is_symlink() or target.exists() or target.is_symlink(): raise RuntimeError('Vorhandene Quota-Datei pruefen: '+str(image))
            run('fallocate','-l',str(mib*1024**2),str(image)); image.chmod(0o600)
            created_images.append(image)
            run('mkfs.ext4','-q','-F','-m','0','-N','4096',str(image))
            target.mkdir(mode=0o700); created_targets.append(target)
            run('mount','-o','loop,nosuid,nodev',str(image),str(target))
            (target/'lost+found').rmdir()
            # Copy symlinks as links, never dereference a player's paths as root.
            run('cp','-a','--',source+'/.',str(target)+'/')
            entry=dict(image=str(image),target=str(target)); entries.append(entry)
            volume='shell-game_'+key+'-bounded'
            run('docker','volume','create','--driver','local','--opt','type=none','--opt','o=bind','--opt','device='+str(target),volume,stdout=subprocess.DEVNULL)
            bounded[key]=volume
        run('sync')
        mount_config=Path('/etc/frost-storage-shell-game.json')
        mount_config.write_text(json.dumps(entries)); mount_config.chmod(0o600)
        helper=Path('/usr/local/lib/frost-storage-mount')
        helper.write_text(MOUNTER); helper.chmod(0o755)
        unit=Path('/etc/systemd/system')/SERVICE
        unit.write_text('''[Unit]
Description=Frostbyte bounded persistent storage
Before=docker.service
After=local-fs.target
RequiresMountsFor=/opt/shell-game/storage
[Service]
Type=oneshot
ExecStart=/usr/local/lib/frost-storage-mount
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
''')
        dropin=Path('/etc/systemd/system/docker.service.d'); dropin.mkdir(exist_ok=True)
        (dropin/'frost-storage.conf').write_text('[Unit]\nRequires='+SERVICE+'\nAfter='+SERVICE+'\n')
        run('systemctl','daemon-reload'); run('systemctl','enable','--now',SERVICE)
        (storage/'compose.before-quotas.json').write_bytes(original)
        manifest.write_text(json.dumps(bounded,indent=2)); manifest.chmod(0o644)
        generated=json.loads(original)
        for key,volume in bounded.items(): generated['volumes'][key]={'external':True,'name':volume}
        for service in generated['services'].values(): service.setdefault('environment',{})['FROST_BOUNDED_STORAGE']='1'
        changed=True
        (ROOT/'compose.yaml').write_text(json.dumps(generated,indent=2)+'\n')
        run(*dc,'up','-d','--wait','--wait-timeout','120')
        print('Fertig: persistente Speicherquotas aktiv. Alte Volumes und Sicherungen bleiben erhalten.')
    except Exception:
        if changed:
            (ROOT/'compose.yaml').write_bytes(original)
        manifest.unlink(missing_ok=True)
        run(*dc,'up','-d','--wait','--wait-timeout','120')
        # Roll back mounts only after the old volumes are serving successfully.
        dropin=Path('/etc/systemd/system/docker.service.d/frost-storage.conf')
        dropin.unlink(missing_ok=True)
        run('systemctl','disable',SERVICE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) if Path('/etc/systemd/system',SERVICE).exists() else None
        Path('/etc/systemd/system',SERVICE).unlink(missing_ok=True)
        run('systemctl','daemon-reload')
        for volume in bounded.values(): run('docker','volume','rm',volume,stdout=subprocess.DEVNULL)
        for target in reversed(created_targets):
            if not subprocess.run(['mountpoint','-q',str(target)]).returncode: run('umount',str(target))
            target.rmdir()
        for image in created_images: image.unlink()
        raise


if __name__=='__main__': main()
