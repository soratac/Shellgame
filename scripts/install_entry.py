#!/usr/bin/env python3
"""Install two forced-command SSH accounts on the VM's existing port 22.

Run as root only after the Compose gateway is healthy. Existing admin SSH policy
is compared before/after; changes are validated and rolled back on failure.
"""
import argparse
import json
import os
import pwd
import shutil
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ENTRY=Path("/etc/frost-entry")
MAIN=Path("/etc/ssh/sshd_config")
WRAPPER=Path("/usr/local/lib/frost-entry")
MATCH="""# Managed by Frostbyte: game-only users; existing admin logins are unchanged.
Match User spiel,score
    AuthenticationMethods password
    PasswordAuthentication yes
    KbdInteractiveAuthentication no
    PubkeyAuthentication no
    ForceCommand /usr/local/lib/frost-entry
    DisableForwarding yes
    PermitTTY yes
    PermitUserRC no
    X11Forwarding no
    PermitTunnel no
    MaxSessions 1
"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",action="store_true",help="Zeigt die Aenderungen ohne Schreibzugriff")
    args=parser.parse_args()
    if args.plan:
        print("Erstellt die Host-Benutzer spiel und score mit reinen Spiel-/Scoreboard-Zugaengen.")
        print("Ergaenzt am Ende von /etc/ssh/sshd_config einen Include fuer diese zwei Benutzer.")
        print(MATCH)
        print("Prueft sshd-Konfiguration und unveraenderte Admin-Anmeldung vor dem Reload.")
        print("Passwoerter aus secrets/gateway bzw. secrets/scoreboard; kein Host-Shell-Zugang.")
        return
    if os.geteuid()!=0:
        raise SystemExit("Bitte auf developer ausfuehren: sudo python3 /opt/shell-game/scripts/install_entry.py")
    dc=["docker","compose","-f",str(ROOT/"compose.yaml")]
    pub=subprocess.check_output([*dc,"exec","-T","gateway","cat","/var/lib/frost/hostkeys/ssh_host_ed25519_key.pub"],text=True).strip()
    published=subprocess.check_output([*dc,"port","gateway","22"],text=True).strip().splitlines()[0]
    port=int(published.rsplit(":",1)[1])
    if not pub.startswith("ssh-ed25519 "): raise SystemExit("Gateway-Hostschluessel fehlt.")
    marker=ENTRY/"managed.json"
    managed=json.loads(marker.read_text()) if marker.exists() else {}
    if not managed and (WRAPPER.exists() or (ENTRY.exists() and any(ENTRY.iterdir()))):
        raise SystemExit("Unverwaltete Dateien fuer frost-entry vorhanden; nichts geaendert.")
    if managed and managed.get("project")!=str(ROOT): raise SystemExit("Andere Installation vorhanden; nichts geaendert.")
    for user in ("spiel","score"):
        try: pwd.getpwnam(user)
        except KeyError: continue
        if user not in managed.get("users",[]):
            raise SystemExit(f"Benutzer {user} existiert bereits und gehoert nicht zu Frostbyte. Nichts geaendert.")
    admin=os.environ.get("SUDO_USER","debian")
    def effective(user):
        out=subprocess.check_output(["/usr/sbin/sshd","-T","-C",f"user={user},host=localhost,addr=192.0.2.1"],text=True)
        return dict(line.split(" ",1) for line in out.splitlines() if " " in line)
    subprocess.run(["/usr/sbin/sshd","-t"],check=True)
    before_admin=effective(admin)
    original=MAIN.read_bytes()
    old_match=(ENTRY/"sshd-match.conf").read_bytes() if (ENTRY/"sshd-match.conf").exists() else None
    ENTRY.mkdir(mode=0o755,exist_ok=True)
    ENTRY.chmod(0o755)
    backup=ENTRY/f"sshd_config.before-{time.time_ns()}"
    backup.write_bytes(original)
    backup.chmod(0o600)
    for user,role,source in [("spiel","player","gateway"),("score","score","scoreboard")]:
        home=Path("/var/lib/frost-entry")/user
        home.mkdir(parents=True,mode=0o755,exist_ok=True)
        home.chmod(0o755)
        os.chown(home,0,0)
        try: account=pwd.getpwnam(user)
        except KeyError:
            subprocess.run(["useradd","-M","-U","-d",str(home),"-s","/bin/sh",user],check=True)
            account=pwd.getpwnam(user)
        hashed=next(line.split(":")[1] for line in (ROOT/"secrets"/source/"shadow").read_text().splitlines() if line.startswith("player:"))
        subprocess.run(["chpasswd","-e"],input=f"{user}:{hashed}\n",text=True,check=True)
        key=ENTRY/f"entry-{role}"
        key.write_bytes((ROOT/"secrets/gateway"/f"entry-{role}").read_bytes())
        os.chown(key,account.pw_uid,account.pw_gid)
        key.chmod(0o600)
    marker.write_text(json.dumps({"project":str(ROOT),"users":["spiel","score"]}))
    marker.chmod(0o600)
    (ENTRY/"known_hosts").write_text(f"[127.0.0.1]:{port} {pub}\n")
    (ENTRY/"known_hosts").chmod(0o644)
    WRAPPER.write_text(f'''#!/bin/sh
set -eu
[ -t 0 ] || {{ echo "Bitte interaktiv verbinden: ssh -t spiel@HOST"; exit 1; }}
case "$(id -un)" in
  spiel) role=player ;;
  score) role=score ;;
  *) exit 1 ;;
esac
exec /usr/bin/ssh -F /dev/null -e none -tt \\
  -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes \\
  -o UserKnownHostsFile=/etc/frost-entry/known_hosts -o ClearAllForwardings=yes \\
  -o PermitLocalCommand=no -i "/etc/frost-entry/entry-$role" \\
  -p {port} "$role@127.0.0.1"
''')
    WRAPPER.chmod(0o755)
    include=b"\n# Frostbyte game-only entry accounts\nInclude /etc/frost-entry/sshd-match.conf\n"
    try:
        (ENTRY/"sshd-match.conf").write_text(MATCH)
        (ENTRY/"sshd-match.conf").chmod(0o644)
        if b"Include /etc/frost-entry/sshd-match.conf" not in original:
            MAIN.write_bytes(original.rstrip()+b"\n"+include)
        subprocess.run(["/usr/sbin/sshd","-t"],check=True)
        for user in ("spiel","score"):
            current=effective(user)
            expected={"authenticationmethods":"password","passwordauthentication":"yes","pubkeyauthentication":"no",
                      "forcecommand":str(WRAPPER),"disableforwarding":"yes","permituserrc":"no","permittty":"yes"}
            for key,value in expected.items():
                if current.get(key)!=value: raise RuntimeError(f"SSH-Pruefung {user}: {key} ist nicht {value}")
            allowed=current.get("allowusers","").split()
            if allowed and user not in allowed: raise RuntimeError(f"Bestehendes AllowUsers erlaubt {user} nicht.")
        if effective(admin)!=before_admin: raise RuntimeError("Admin-SSH-Konfiguration wuerde sich aendern.")
        subprocess.run(["systemctl","reload","ssh"],check=True)
    except Exception:
        MAIN.write_bytes(original)
        if old_match is None: (ENTRY/"sshd-match.conf").unlink(missing_ok=True)
        else: (ENTRY/"sshd-match.conf").write_bytes(old_match)
        subprocess.run(["/usr/sbin/sshd","-t"],check=False)
        subprocess.run(["systemctl","reload","ssh"],check=False)
        raise
    print("Fertig: ssh spiel@DEIN-SERVER   /   ssh score@DEIN-SERVER")
    print("Zugangsdaten: /opt/shell-game/join-access.txt")
    print("Bestehende Admin-SSH-Einstellungen wurden unveraendert geprueft.")


if __name__=="__main__": main()
