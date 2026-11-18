#!/usr/bin/env python3
"""Login smoke check for installed host SSH accounts, optionally from a jump host.

Uses a temporary PTY and pinned host keys, opens the character editor and the scoreboard,
and disconnects before naming the temporary player. Passwords travel over stdin, not shell arguments.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROBE=r'''
import fcntl,json,os,pty,select,struct,subprocess,tempfile,termios,time
from pathlib import Path
config=json.load(__import__('sys').stdin)
with tempfile.TemporaryDirectory(prefix='frost-entry-check-') as folder:
    folder=Path(folder)
    (folder/'known_hosts').write_text(config['hostkeys'])
    askpass=folder/'askpass'
    askpass.write_text('#!/bin/sh\ncat "$FROST_PASSWORD_FILE"\n'); askpass.chmod(0o700)
    for user,password,expected in config['accounts']:
        secret=folder/'password'; secret.write_text(password); secret.chmod(0o600)
        master,slave=pty.openpty()
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',42,120,0,0))
        env={**os.environ,'TERM':'xterm-256color','DISPLAY':':0','SSH_ASKPASS_REQUIRE':'force',
             'SSH_ASKPASS':str(askpass),'FROST_PASSWORD_FILE':str(secret)}
        proc=subprocess.Popen(['ssh','-F','/dev/null','-tt','-o','ConnectTimeout=5',
            '-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no',
            '-o','StrictHostKeyChecking=yes','-o',f'UserKnownHostsFile={folder/"known_hosts"}',
            user+'@'+config['host']],stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True)
        os.close(slave)
        output=b''
        try:
            deadline=time.monotonic()+20
            while time.monotonic()<deadline and proc.poll() is None:
                if select.select([master],[],[],.2)[0]:
                    try: output+=os.read(master,65536)
                    except OSError: break
                if expected.encode() in output: break
            if expected.encode() not in output:
                raise SystemExit('FAIL: '+user+' default-port login did not reach '+expected)
            print('PASS: ssh '+user+'@'+config['host']+' reaches '+expected,flush=True)
        finally:
            proc.terminate()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            os.close(master)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--via',help='SSH alias of a jump host with Python 3 and OpenSSH installed')
    args=parser.parse_args()
    keys=list(Path('/etc/ssh').glob('ssh_host_*_key.pub'))
    if not keys: raise SystemExit('Host SSH public keys unavailable')
    payload=dict(host=args.host,hostkeys=''.join(args.host+' '+p.read_text().strip()+'\n' for p in keys),
                 accounts=[('spiel',(ROOT/'secrets/gateway/password').read_text().strip(),'GEMEINSAMER EINSTIEG'),
                           ('score',(ROOT/'secrets/scoreboard/password').read_text().strip(),'LIVE-SCOREBOARD')])
    if args.via:
        import shlex
        command=['ssh',args.via,'python3 -c '+shlex.quote(PROBE)]
    else: command=[sys.executable,'-c',PROBE]
    subprocess.run(command,input=json.dumps(payload),text=True,check=True)


if __name__=='__main__': main()
