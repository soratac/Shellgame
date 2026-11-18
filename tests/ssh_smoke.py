#!/usr/bin/env python3
"""PTY helper and entrypoint for the isolated Docker integration tests."""
import argparse
import fcntl
import json
import os
import pty
import re
import select
import struct
import sys
import subprocess
import tempfile
import termios
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class Session:
    def __init__(self,slot,port,folder,user="player",key=None,host="127.0.0.1",music=False,secret_root=ROOT/"secrets"):
        master,slave=pty.openpty()
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack("HHHH",42,120,0,0))
        env={**os.environ,"TERM":"xterm-256color","DISPLAY":":0","SSH_ASKPASS_REQUIRE":"force",
             "SSH_ASKPASS":str(folder/"askpass"),"FROST_PASSWORD_FILE":str(secret_root/slot/"password")}
        authentication=["-o","PreferredAuthentications=password","-o","PubkeyAuthentication=no"] if key is None else ["-i",str(key),"-o","BatchMode=yes","-o","IdentitiesOnly=yes"]
        launcher=[sys.executable,str(ROOT/"scripts/spielmusik.py")] if music else ["ssh","-tt"]
        if music: env["BROWSER"]="/bin/true"
        self.proc=subprocess.Popen([*launcher,*(["-p",str(port)] if port!=22 else []),*authentication,"-o","StrictHostKeyChecking=accept-new",
                                    "-o",f"UserKnownHostsFile={folder/'known_hosts'}","-o","ConnectTimeout=5",
                                    f"{user}@{host}"],stdin=slave,stdout=slave,stderr=slave,env=env,start_new_session=True)
        os.close(slave)
        self.fd=master
        self.output=b""

    def send(self,text): os.write(self.fd,text.encode())

    def drain(self,seconds=.2):
        end=time.monotonic()+seconds
        data=b""
        while time.monotonic()<end:
            ready,_,_=select.select([self.fd],[],[],max(0,end-time.monotonic()))
            if ready:
                try: chunk=os.read(self.fd,65536)
                except OSError: break
                if not chunk: break
                data+=chunk
        self.output+=data
        return data.decode(errors="replace")

    def expect(self,needle,timeout=10):
        start=len(self.output)
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.drain(.15)
            clean=re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]|\x1b[()][A-Z0-9a-z]",b"",self.output[start:])
            if needle.encode() in clean: return
            if self.proc.poll() is not None: break
        raise AssertionError(f"Missing {needle!r}; terminal tail: {self.output[-2000:].decode(errors='replace')!r}")

    def close(self):
        self.proc.terminate()
        try: self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        os.close(self.fd)



def main():
    from integration import main as isolated_main
    isolated_main()


if __name__ == "__main__": main()
