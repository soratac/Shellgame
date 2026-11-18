"""Read-only assertions run from the interactive player's SSH shell in the test stack."""
import errno
import os
from pathlib import Path
import resource
import socket

assert os.getuid()==1000
status=dict(line.split(":",1) for line in Path("/proc/self/status").read_text().splitlines())
assert int(status["NoNewPrivs"])==1 and int(status["Seccomp"])==2
assert int(status["CapEff"],16)==0
home=os.statvfs("/home/player")
assert home.f_blocks*home.f_frsize==64*1024**2 and home.f_files==4096
assert resource.getrlimit(resource.RLIMIT_FSIZE)==(16*1024**2,16*1024**2)
assert not os.access("/var/lib/frost-private",os.X_OK)
assert not os.path.exists("/var/run/docker.sock")
for family in (socket.AF_INET,socket.AF_INET6):
    try:
        with socket.socket(family,socket.SOCK_STREAM): pass
    except PermissionError as exc: assert exc.errno==errno.EPERM
    else: raise AssertionError("Player network filter missing")
print("ISOLATION_OK")
