"""Root-owned allocator + SSH relay. No Docker socket or user-controlled targets."""
import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import select
import socket
import socketserver
import sqlite3
import struct
import threading
from pathlib import Path

from .wire import send,receive

SOCKET="/run/frost/gateway.sock"


def normalize(code): return re.sub(r"[-\s]","",code).upper()


class Allocator:
    def __init__(self, path, slots, state_root=Path("/slots"), provider=None):
        self.provider=provider
        self.slots=list(slots)
        self.state_root=Path(state_root)
        self.lock=threading.RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS joins (slot TEXT PRIMARY KEY, code TEXT NOT NULL, digest TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 0, lease TEXT)")
        self.db.execute("UPDATE joins SET active=0, lease=NULL")
        for slot in self.slots:
            if self.player_name(slot) and not self.db.execute("SELECT 1 FROM joins WHERE slot=?",(slot,)).fetchone():
                self._insert(slot)
        if self.provider:
            for slot in self.provider.call("list"):
                if not self.db.execute("SELECT 1 FROM joins WHERE slot=?",(slot,)).fetchone():
                    if self.provider.player_name(slot): self._insert(slot)
                    else: self.provider.idle(slot)
        self.db.commit()
        Path(path).chmod(0o600)

    def player_name(self,slot):
        if self.provider and slot.startswith("elf-"): return self.provider.player_name(slot)
        try: return json.loads((self.state_root/slot/"state.json").read_text())["name"]
        except (OSError,ValueError,KeyError): return None

    def _insert(self,slot):
        raw=secrets.token_hex(8).upper()
        code="-".join(raw[i:i+4] for i in range(0,16,4))
        self.db.execute("INSERT INTO joins(slot,code,digest) VALUES (?,?,?)",(slot,code,hashlib.sha256(raw.encode()).hexdigest()))
        return code

    def reserve(self,code=None):
        if not code and self.provider:
            slot=self.provider.create()
            with self.lock:
                code=self._insert(slot)
                lease=secrets.token_hex(16)
                self.db.execute("UPDATE joins SET active=1,lease=? WHERE slot=?",(lease,slot)); self.db.commit()
                return slot,code,lease
        with self.lock:
            if code:
                if not isinstance(code,str) or not re.fullmatch(r"[A-F0-9]{16}",normalize(code)):
                    raise ValueError("Dieser Fortsetzen-Code ist nicht gueltig.")
                row=self.db.execute("SELECT slot,code,active FROM joins WHERE digest=?",(hashlib.sha256(normalize(code).encode()).hexdigest(),)).fetchone()
                if not row: raise ValueError("Code nicht gefunden. Pruefe deinen Fortsetzen-Code.")
                slot,code,active=row
                if active: raise ValueError("Dieser Spieler ist noch verbunden. Trenne zuerst die andere Sitzung.")
            else:
                occupied={r[0] for r in self.db.execute("SELECT slot FROM joins")}
                slot=next((s for s in self.slots if s not in occupied and self.player_name(s)==""),None)
                if slot is None: raise ValueError("Alle Spielerplaetze sind vergeben. Nutze deinen Code zum Fortsetzen.")
                code=self._insert(slot)
            lease=secrets.token_hex(16)
            self.db.execute("UPDATE joins SET active=1,lease=? WHERE slot=?",(lease,slot))
            self.db.commit()
            return slot,code,lease

    def release(self,slot,lease):
        with self.lock:
            if not self.db.execute("SELECT 1 FROM joins WHERE slot=? AND lease=?",(slot,lease)).fetchone(): return
            try: name=self.player_name(slot)
            except (OSError,ValueError): name=None
            if self.provider and slot.startswith("elf-"):
                try: self.provider.idle(slot)
                except (OSError,ValueError): print("Container idle pending:",slot,flush=True)
            # A dropped connection before naming must not consume a slot forever.
            if name=="":
                self.db.execute("DELETE FROM joins WHERE slot=? AND lease=?",(slot,lease))
            else:
                self.db.execute("UPDATE joins SET active=0,lease=NULL WHERE slot=? AND lease=?",(slot,lease))
            self.db.commit()

    def list_rows(self):
        with self.lock:
            return [dict(slot=slot,name=self.player_name(slot),code=code,active=bool(active))
                    for slot,code,active in self.db.execute("SELECT slot,code,active FROM joins ORDER BY slot")]


def make_handler(config, allocator):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            sock=self.request
            sock.settimeout(5)
            slot=lease=None
            client=None
            try:
                uid=struct.unpack("3i",sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
                kind,payload=receive(sock)
                data=json.loads(payload)
                if kind!=b"J" or not isinstance(data,dict): return
                if uid==0 and data.get("action")=="ping":
                    send(sock,b"M",{"ok":True}); return
                if uid not in (1000,1001): return
                if uid==1001:
                    target="scoreboard"
                    metadata={"role":"score"}
                else:
                    action=data.get("action")
                    if action not in ("new","resume"): raise ValueError("Waehle Neu oder Fortsetzen.")
                    if action=="resume" and not data.get("code"): raise ValueError("Bitte deinen Fortsetzen-Code eingeben.")
                    slot,code,lease=allocator.reserve(data.get("code") if action=="resume" else None)
                    target=slot
                    metadata={"role":"player","slot":slot,"code":code,"resumed":action=="resume"}
                # The only destinations and credentials come from the root-owned file.
                import paramiko
                if allocator.provider and target.startswith("elf-"):
                    destination=allocator.provider.destination(target)
                    host=destination["host"]; pub=destination["hostkey"].split()
                else:
                    destination=config[target]; host=target
                    pub=(Path("/slots")/target/"hostkeys/ssh_host_ed25519_key.pub").read_text().split()
                client=paramiko.SSHClient()
                key=paramiko.Ed25519Key(data=base64.b64decode(pub[1]))
                client.get_host_keys().add(host,key.get_name(),key)
                client.set_missing_host_key_policy(paramiko.RejectPolicy())
                client.connect(host,username="player",password=destination["password"],allow_agent=False,
                               look_for_keys=False,timeout=5,auth_timeout=5,banner_timeout=5)
                client.get_transport().set_keepalive(15)
                channel=client.get_transport().open_session(timeout=5)
                term=data.get("term","xterm-256color")
                if not isinstance(term,str) or not re.fullmatch(r"[\w-]{1,40}",term): term="xterm-256color"
                width=max(40,min(400,int(data.get("width",100))))
                height=max(16,min(200,int(data.get("height",38))))
                channel.get_pty(term=term,width=width,height=height)
                channel.invoke_shell()
                channel.settimeout(5)
                send(sock,b"M",metadata)
                while True:
                    ready,_,_=select.select([sock,channel],[],[],1)
                    if sock in ready:
                        kind,payload=receive(sock)
                        if kind==b"I": channel.sendall(payload)
                        elif kind==b"R":
                            size=json.loads(payload)
                            channel.resize_pty(width=max(20,min(400,int(size[0]))),height=max(10,min(200,int(size[1]))))
                        else: break
                    if channel.recv_ready():
                        output=channel.recv(32768)
                        if output: send(sock,b"O",output)
                    if channel.exit_status_ready() and not channel.recv_ready():
                        send(sock,b"D",{"status":channel.recv_exit_status()})
                        break
            except ValueError as exc:
                try: send(sock,b"E",{"error":str(exc)})
                except OSError: pass
            except (OSError,EOFError,KeyError,TypeError) as exc:
                print("Gateway session ended:",type(exc).__name__,flush=True)
            except Exception as exc:
                print("Gateway connection failed:",type(exc).__name__,flush=True)
                try: send(sock,b"E",{"error":"Spielplatz momentan nicht erreichbar. Bitte erneut verbinden."})
                except OSError: pass
            finally:
                if client: client.close()
                if slot and lease: allocator.release(slot,lease)
    return Handler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--list",action="store_true")
    parser.add_argument("--release-slot")
    args=parser.parse_args()
    database=Path("/var/lib/frost/joins.sqlite")
    if args.list or args.release_slot:
        if os.getuid()!=0: raise SystemExit("Nur der Administrator darf Beitrittscodes verwalten.")
        db=sqlite3.connect(database)
        if args.release_slot:
            db.execute("DELETE FROM joins WHERE slot=?",(args.release_slot,)); db.commit()
        else:
            for slot,code,active in db.execute("SELECT slot,code,active FROM joins ORDER BY slot"):
                try: name=json.loads((Path('/slots')/slot/'state.json').read_text())["name"]
                except (OSError,ValueError,KeyError):
                    from .dynamic import Client
                    name=Client().player_name(slot) if slot.startswith("elf-") and os.environ.get("FROST_DYNAMIC")=="1" else ""
                print(f"{slot:10} {name:20} {code} {'verbunden' if active else 'frei zum Fortsetzen'}")
        db.close()
        return
    config=json.loads(Path("/run/bootstrap/router.json").read_text())
    slots=sorted(s for s in config if s.startswith("player"))
    from .dynamic import Client
    provider=Client() if os.environ.get("FROST_DYNAMIC")=="1" else None
    allocator=Allocator(database,slots,provider=provider)
    Path(SOCKET).unlink(missing_ok=True)
    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads=True
        request_queue_size=64
    with Server(SOCKET,make_handler(config,allocator)) as server:
        os.chmod(SOCKET,0o666)
        server.serve_forever(poll_interval=.2)


if __name__=="__main__": main()
