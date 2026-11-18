"""Checkpoint a bounded player home. Only the supervisor opens the private store."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

from .isolation import ARCHIVE_BYTES

HOME = Path("/home/player")
PRIVATE = Path("/var/lib/frost-private")
ARCHIVE = PRIVATE/"saved"/"home.tar"
LEGACY = PRIVATE/"legacy"
STATE = Path("/var/lib/frost")
PLAYER = dict(user=1000, group=1000, extra_groups=[], env={"PATH":"/usr/bin:/bin","LC_ALL":"C"})
CREATE = ["tar","--create","--sparse","--one-file-system","--file=-","."]
EXTRACT = ["tar","--extract","--no-same-owner","--preserve-permissions","--file=-","-C",str(HOME)]


def save():
    # Never replace a good checkpoint with a partial, oversized or unreadable one.
    with (STATE/"checkpoint.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        temp = ARCHIVE.with_suffix(".partial")
        try:
            with os.fdopen(os.open(temp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600),"wb") as out:
                with subprocess.Popen(CREATE, cwd=HOME, stdout=subprocess.PIPE, **PLAYER) as tar:
                    try:
                        size = 0
                        while chunk := tar.stdout.read(128*1024):
                            size += len(chunk)
                            if size > ARCHIVE_BYTES:
                                raise OSError("Home-Checkpoint überschreitet das Archivlimit")
                            out.write(chunk)
                        if tar.wait():
                            raise OSError("Home-Checkpoint konnte nicht vollständig gelesen werden")
                    finally:
                        tar.stdout.close()
                        if tar.poll() is None:
                            tar.kill()
                out.flush()
                os.fsync(out.fileno())
            temp.replace(ARCHIVE)
        finally:
            temp.unlink(missing_ok=True)


def restore():
    if PRIVATE.stat().st_mode & 0o077 or PRIVATE.stat().st_uid != 0:
        raise RuntimeError("Home-Sicherung ist nicht privat")
    ARCHIVE.parent.mkdir(mode=0o700,exist_ok=True)
    fs=os.statvfs(HOME)
    if fs.f_blocks*fs.f_frsize > 64*1024**2 or fs.f_files>4096 or not HOME.is_mount():
        raise RuntimeError("Begrenztes Spieler-Home fehlt")
    if ARCHIVE.is_file():
        with ARCHIVE.open("rb") as saved:
            subprocess.run(EXTRACT, stdin=saved, check=True, **PLAYER)
    else:
        # Enter the protected legacy directory before dropping privileges. No
        # player can follow its path from a session or access the checkpoint.
        base=LEGACY if LEGACY.is_dir() else Path("/etc/skel")
        with subprocess.Popen(CREATE,cwd=base,stdout=subprocess.PIPE,**PLAYER) as source:
            try:
                subprocess.run(EXTRACT,stdin=source.stdout,check=True,**PLAYER)
            finally:
                source.stdout.close()
            if source.wait(): raise RuntimeError("Spieler-Home konnte nicht übernommen werden")
        save()


def clear():
    # Called only by the administrator after the offline backup.
    temp=ARCHIVE.with_suffix(".empty")
    with tarfile.open(temp,"w"): pass
    temp.replace(ARCHIVE)


if __name__=="__main__":
    action=sys.argv[1]
    if action=="restore": restore()
    elif action=="save": save()
    elif action=="clear": clear()
    elif action=="watch":
        from .daemon import connected
        last=time.monotonic()
        was_online=False
        while True:
            time.sleep(2)
            online=connected()
            due=(was_online and not online) or (online and time.monotonic()-last>=30)
            was_online=online
            if not due: continue
            last=time.monotonic()
            try: save()
            except (OSError,subprocess.SubprocessError) as exc:
                print("Home-Checkpoint ausstehend:",exc,file=sys.stderr,flush=True)
