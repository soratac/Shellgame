#!/usr/bin/env python3
"""Synchronize only the two game account passwords using their existing credentials.

Uses normal su/PAM authentication and passwd as the target account, never root.
No passwords in process arguments, output or terminal logs. Retries keep track of
already-updated accounts. Run after provision.py --rotate-passwords.
"""
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def change(user,old,new):
    master,slave=pty.openpty()
    proc=subprocess.Popen(['su','-s','/bin/sh',user,'-c','/usr/bin/passwd'],
                          stdin=slave,stdout=slave,stderr=slave,start_new_session=True,
                          env={**os.environ,'LC_ALL':'C','LANG':'C'})
    os.close(slave)
    prompts=[(b'Password:',old),(b'Current password:',old),(b'New password:',new),(b'Retype new password:',new)]
    output=b''; step=0
    try:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if select.select([master],[],[],.2)[0]:
                try: data=os.read(master,4096)
                except OSError: break
                if not data: break
                output+=data
                if step<len(prompts) and prompts[step][0] in output:
                    os.write(master,prompts[step][1].encode()+b'\n'); step+=1; output=b''
            if proc.poll() is not None: break
        if proc.poll() is None: proc.wait(timeout=3)
        if proc.returncode or step!=4:
            raise RuntimeError(user+': Passwortwechsel ueber die normale Benutzeranmeldung fehlgeschlagen; keine weiteren Konten geaendert.')
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try: proc.wait(timeout=2)
            except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
        os.close(master)


def main():
    marker=ROOT/'secrets/password-rotation.json'
    if not marker.exists(): raise SystemExit('Zuerst provision.py --rotate-passwords ausfuehren.')
    state=json.loads(marker.read_text())
    for user,slot in [('spiel','gateway'),('score','scoreboard')]:
        if user in state['host_updated']: continue
        old=(Path(state['backup'])/'secrets'/slot/'password').read_text().strip()
        new=(ROOT/'secrets'/slot/'password').read_text().strip()
        if len(new)!=12: raise SystemExit('Neues Passwort hat nicht 12 Zeichen.')
        if old!=new: change(user,old,new)
        state['host_updated'].append(user)
        marker.write_text(json.dumps(state)); marker.chmod(0o600)
        print(user+': 12-Zeichen-Passwort aktiviert.')


if __name__=='__main__': main()
