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


def host_memory():
    # A virtualized /proc inside the 512 MiB spawner can describe the spawner
    # itself. New deployments bind this single file from the Docker host.
    try:
        source = Path("/run/frost-host-meminfo").read_text()
    except FileNotFoundError:
        source = Path("/proc/meminfo").read_text()
    fields = {}
    for line in source.splitlines():
        key, _, value = line.partition(":")
        if key in ("MemTotal", "MemAvailable"):
            fields[key] = int(value.split()[0])*1024
    return fields["MemTotal"], fields["MemAvailable"]


def check_capacity(root, active_players, resident_bytes=None, policy="reserved"):
    if policy not in ("reserved", "available"):
        raise ValueError("Ungültige JOIN_RAM_POLICY. Erlaubt sind reserved und available.")
    total, available = host_memory()
    reserve = max(1024*MIB, total//8)
    growth = active_players*PLAYER_MEMORY if policy=="reserved" else 0
    # Most joins pass without querying stats. Near the boundary, credit only
    # resident anonymous memory: reclaimable file cache can already be available.
    if resident_bytes and reserve+PLAYER_MEMORY <= available < reserve+PLAYER_MEMORY+growth:
        growth -= min(growth, resident_bytes())
        total, latest_available = host_memory()
        available = min(available, latest_available)
        reserve = max(1024*MIB, total//8)
    required = reserve+PLAYER_MEMORY+growth
    if available < required:
        raise ValueError(f"RAM: {available//MIB} von {total//MIB} MiB verfügbar, "
                         f"{required//MIB} MiB benötigt ({reserve//MIB} Reserve, "
                         f"{growth//MIB} möglicher Mehrverbrauch für {active_players} laufende Plätze, "
                         f"{PLAYER_MEMORY//MIB} neuer Platz).")
    fs = os.statvfs(root)
    if (fs.f_bavail*fs.f_frsize < max(2048*MIB, fs.f_blocks*fs.f_frsize//16)+(active_players+1)*2*ARCHIVE_BYTES
            or (fs.f_files and fs.f_favail < max(8192,fs.f_files//50))):
        raise ValueError("Die VM benötigt ihren freien Speicherplatz. Bitte den Veranstalter informieren.")
