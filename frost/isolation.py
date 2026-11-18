"""Resource policy shared by fixed slots and on-demand SSH players."""
import os
from pathlib import Path

MIB = 1024**2
PLAYER_MEMORY = 256*MIB
FILE_BYTES = 16*MIB
ARCHIVE_BYTES = 80*MIB
HOME_TMPFS = "rw,exec,nosuid,nodev,size=64m,nr_inodes=4096,uid=1000,gid=1000,mode=0700"
# sshd separates users, chroots its pre-auth child and sets up PTYs.
SSH_CAPS = ["CHOWN", "DAC_OVERRIDE", "FOWNER", "KILL", "SETGID", "SETUID", "SYS_CHROOT", "NET_BIND_SERVICE", "AUDIT_WRITE"]


def check_capacity(root, active_players):
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in ("MemTotal","MemAvailable"):
            mem[key] = int(value.split()[0])*1024
    reserve = max(1024*MIB, mem["MemTotal"]//8)
    # Idle containers can still grow to their full limits. Conservatively
    # budget that growth from currently available RAM, including other VM users.
    if mem["MemAvailable"] < reserve+(active_players+1)*PLAYER_MEMORY:
        raise ValueError("Zu wenig RAM-Reserve auf der VM. Bitte später erneut verbinden.")
    fs = os.statvfs(root)
    if (fs.f_bavail*fs.f_frsize < max(2048*MIB, fs.f_blocks*fs.f_frsize//16)+(active_players+1)*2*ARCHIVE_BYTES
            or (fs.f_files and fs.f_favail < max(8192,fs.f_files//50))):
        raise ValueError("Die VM benötigt ihren freien Speicherplatz. Bitte den Veranstalter informieren.")
