#!/usr/bin/env python3
"""Apply .env credentials/config without resetting players or their codes."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(ROOT/'scripts/provision.py')],cwd=ROOT,check=True)
if (ROOT/'secrets/password-rotation.json').exists():
    subprocess.run([sys.executable,str(ROOT/'scripts/update_entry_passwords.py')],cwd=ROOT,check=True)
subprocess.run(['docker','compose','build','scoreboard'],cwd=ROOT,check=True)
subprocess.run([sys.executable,str(ROOT/'scripts/reset_event.py'),'--backup-only','--recreate'],cwd=ROOT,check=True)
print('Konfiguration aktiv. Spielstaende und Fortsetzen-Codes bleiben erhalten.')
