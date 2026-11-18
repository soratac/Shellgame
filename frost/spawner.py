"""Create fixed, resource-limited player containers. Only root gateway RPC is accepted."""
import base64
import io
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import socketserver
import struct
import subprocess
import tarfile
import threading
import time

from .docker_api import Docker,DockerError
from .dynamic import SOCKET

LABEL='frost.managed'


def archive(files):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as tar:
        for name,content in files.items():
            data=content.encode(); info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o600
            tar.addfile(info,io.BytesIO(data))
    return output.getvalue()


def read_file(docker,container,path):
    import urllib.parse
    data=docker.call('GET',f'/containers/{container}/archive?path='+urllib.parse.quote(path),raw=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        member=next(m for m in tar.getmembers() if m.isfile())
        if member.size>65536: raise ValueError('State file too large')
        return tar.extractfile(member).read().decode()


class Manager:
    def __init__(self,config,docker=None,root=Path('/var/lib/frost')):
        self.config=config; self.docker=docker or Docker(); self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True); self.root.chmod(0o700)
        self.path=self.root/'dynamic.json'
        self.rows=json.loads(self.path.read_text()) if self.path.exists() else {}
        self.lock=threading.RLock(); self.paused=False
        self.project=config['project']
        self.pool=ipaddress.ip_network(config.get('network_pool','10.240.0.0/16'))
        if self.pool.version!=4 or not self.pool.is_private: raise ValueError('Private IPv4 pool required')
        self.save()
        for slot,row in list(self.rows.items()):
            try: self.docker.call('GET',f"/containers/{row['container']}/json")
            except DockerError as exc:
                if str(exc).startswith('404:'): self.remove(slot)
                else: raise

    def save(self):
        temp=self.path.with_suffix('.tmp'); temp.write_text(json.dumps(self.rows)); temp.chmod(0o600); temp.replace(self.path)
        # Only root scoreboard/gateway can read this shared registry directory.
        target=Path('/run/controller/registry.json')
        target.parent.mkdir(mode=0o700,exist_ok=True); target.parent.chmod(0o700)
        tmp=target.with_suffix('.tmp'); tmp.write_text(json.dumps({k:v['token'] for k,v in self.rows.items()})); tmp.chmod(0o600); tmp.replace(target)

    def service(self,name):
        rows=self.docker.containers([f'com.docker.compose.project={self.project}',f'com.docker.compose.service={name}'])
        live=[r for r in rows if r['State']=='running' and LABEL not in r.get('Labels',{})]
        if len(live)!=1: raise ValueError(name+' momentan nicht erreichbar.')
        return live[0]['Id']

    def attach(self,row):
        for role in ('gateway','scoreboard'):
            ident=self.service(role)
            info=self.docker.call('GET',f'/containers/{ident}/json')
            if row['network'] not in info['NetworkSettings']['Networks']:
                self.docker.call('POST',f"/networks/{row['network']}/connect",{'Container':ident,'EndpointConfig':{'Aliases':[role],'GwPriority':-1}})

    def allocate_network(self,name,labels):
        used=[]
        for net in self.docker.call('GET','/networks'):
            for part in net.get('IPAM',{}).get('Config',[]) or []:
                if part.get('Subnet'):
                    try: used.append(ipaddress.ip_network(part['Subnet']))
                    except ValueError: pass
        subnet=next((net for net in self.pool.subnets(new_prefix=29) if not any(net.overlaps(other) for other in used if other.version==4)),None)
        if subnet is None: raise ValueError('Kein freies Spielernetz mehr. Der Veranstalter muss den Netzwerkpool erweitern.')
        self.docker.call('POST','/networks/create',{'Name':name,'Driver':'bridge','Labels':labels,'IPAM':{'Config':[{'Subnet':str(subnet)}]}})

    def create(self):
        with self.lock:
            if self.paused: raise ValueError('Wartung: Bitte gleich erneut verbinden.')
            slot='elf-'+secrets.token_hex(8)
            prefix=self.project+'-'+slot
            # Compose adds its own project/service labels to built images. Clear
            # those inherited labels so players cannot impersonate infrastructure
            # or be treated as Compose services during recreation/down.
            labels={LABEL:self.project,'frost.slot':slot,
                    'com.docker.compose.project':'','com.docker.compose.service':'','com.docker.compose.version':''}
            row={'slot':slot,'container':prefix,'network':prefix+'-net','home':prefix+'-home','state':prefix+'-state',
                 'bootstrap':prefix+'-bootstrap','password':secrets.token_urlsafe(9),'token':secrets.token_hex(32)}
            self.rows[slot]=row; self.save()
            try:
                self.allocate_network(row['network'],labels)
                for key in ('home','state','bootstrap'):
                    self.docker.call('POST','/volumes/create',{'Name':row[key],'Labels':labels})
                hashed=subprocess.check_output(['openssl','passwd','-6','-stdin'],input=row['password']+'\n',text=True).strip()
                bootstrap={'shadow':f'root:!:20000:0:99999:7:::\nplayer:{hashed}:20000:0:99999:7:::\n',
                           'authorized_keys':'','score_token':row['token']}
                helper=prefix+'-init'
                self.docker.call('POST','/containers/create?name='+helper,{'Image':self.config['image'],'Entrypoint':['/bin/true'],
                    'Labels':labels,'HostConfig':{'NetworkMode':'none','ReadonlyRootfs':True,'Binds':[row['bootstrap']+':/run/bootstrap'],
                    'Memory':64*1024**2,'MemorySwap':64*1024**2,'PidsLimit':16,'CapDrop':['ALL'],'SecurityOpt':['no-new-privileges:true']}})
                try: self.docker.call('PUT',f'/containers/{helper}/archive?path=/run/bootstrap',archive(bootstrap))
                finally: self.docker.call('DELETE',f'/containers/{helper}?force=1')
                spec={'Image':self.config['image'],'Cmd':['player'],'Labels':labels,'Env':['SCORE_URL=http://scoreboard:8080'],
                      'Healthcheck':{'Test':['CMD','python3','-c','from frost.client import request; request()'],'Interval':2_000_000_000,'Timeout':3_000_000_000,'Retries':3},
                      'HostConfig':{'Init':True,'ReadonlyRootfs':True,'Memory':256*1024**2,'MemorySwap':256*1024**2,
                           'NanoCpus':500_000_000,'PidsLimit':96,'CapDrop':['NET_RAW'],'SecurityOpt':['no-new-privileges:true'],
                           'RestartPolicy':{'Name':'unless-stopped'},'NetworkMode':row['network'],
                           'Tmpfs':{'/run':'rw,nosuid,nodev,size=16m','/tmp':'rw,nosuid,nodev,size=32m,mode=1777'},
                           'Binds':[row['home']+':/home/player',row['state']+':/var/lib/frost',row['bootstrap']+':/run/bootstrap:ro'],
                           'Ulimits':[{'Name':'nofile','Soft':1024,'Hard':2048},{'Name':'core','Soft':0,'Hard':0}],
                           'LogConfig':{'Type':'json-file','Config':{'max-size':'5m','max-file':'2'}}}}
                self.docker.call('POST','/containers/create?name='+prefix,spec)
                self.start(slot)
                return {'slot':slot}
            except Exception:
                self.remove(slot)
                raise

    def start(self,slot):
        with self.lock:
            if self.paused: raise ValueError('Wartung: Bitte gleich erneut verbinden.')
            row=self.rows[slot]
            self.attach(row)
            info=self.docker.call('GET',f"/containers/{row['container']}/json")
            if not info['State']['Running']: self.docker.call('POST',f"/containers/{row['container']}/start")
            deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                info=self.docker.call('GET',f"/containers/{row['container']}/json")
                if info['State'].get('Health',{}).get('Status')=='healthy': break
                time.sleep(.25)
            else: raise ValueError('Spielcontainer startet noch. Bitte erneut verbinden.')
            pub=read_file(self.docker,row['container'],'/var/lib/frost/hostkeys/ssh_host_ed25519_key.pub').strip()
            row['hostkey']=pub; self.save()
            return {'host':row['container'],'password':row['password'],'hostkey':pub}

    def name(self,slot):
        with self.lock:
            row=self.rows.get(slot)
            if not row: return None
            try: return json.loads(read_file(self.docker,row['container'],'/var/lib/frost/state.json'))['name']
            except (DockerError,ValueError,KeyError,StopIteration): return None

    def idle(self,slot):
        with self.lock:
            row=self.rows.get(slot)
            if not row: return
            if self.name(slot)=='': self.remove(slot); return
            self.docker.call('POST',f"/containers/{row['container']}/stop?t=3")

    def remove(self,slot):
        row=self.rows.get(slot)
        if not row: return
        for name in (row['container']+'-init',row['container']):
            try: self.docker.call('DELETE',f'/containers/{name}?force=1')
            except DockerError: pass
        for role in ('gateway','scoreboard'):
            try: self.docker.call('POST',f"/networks/{row['network']}/disconnect",{'Container':self.service(role),'Force':True})
            except (DockerError,ValueError): pass
        try: self.docker.call('DELETE','/networks/'+row['network'])
        except DockerError: pass
        for key in ('home','state','bootstrap'):
            try: self.docker.call('DELETE','/volumes/'+row[key])
            except DockerError: pass
        self.rows.pop(slot,None); self.save()


def main():
    config=json.loads(Path('/run/bootstrap/spawn-config.json').read_text())
    manager=Manager(config)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            uid=struct.unpack('3i',self.connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
            if uid!=0: return
            self.connection.settimeout(5)
            try:
                data=json.loads(self.rfile.readline(2048)); action=data.get('action'); slot=data.get('slot')
                if action in ('start','name','idle','forget') and slot not in manager.rows: raise ValueError('Spieler nicht gefunden.')
                if action=='create': result=manager.create()
                elif action=='start': result=manager.start(slot)
                elif action=='name': result=manager.name(slot)
                elif action=='idle': result=manager.idle(slot)
                elif action=='forget':
                    with manager.lock:
                        if manager.name(slot)!=data.get('expected_name'): raise ValueError('Spielername stimmt nicht ueberein.')
                        manager.remove(slot)
                    result=True
                elif action=='list': result=list(manager.rows)
                elif action=='pause':
                    with manager.lock: manager.paused=True
                    result=True
                elif action=='ping': result=True
                else: raise ValueError('Unbekannte Verwaltungsaktion.')
                reply={'ok':True,'result':result}
            except ValueError as exc: reply={'ok':False,'error':str(exc)}
            except Exception as exc:
                print('Controller:',type(exc).__name__,str(exc),flush=True)
                reply={'ok':False,'error':'Container konnte nicht bereitgestellt werden. Bitte gleich erneut versuchen.'}
            self.wfile.write(json.dumps(reply).encode()+b'\n')
    Path(SOCKET).unlink(missing_ok=True)
    class Server(socketserver.ThreadingUnixStreamServer): daemon_threads=True; request_queue_size=128
    with Server(SOCKET,Handler) as server:
        os.chmod(SOCKET,0o600); server.serve_forever()


if __name__=='__main__': main()
