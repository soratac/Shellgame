#!/usr/bin/env python3
"""Generate a self-contained Compose deployment and unique slot credentials."""
import argparse
import csv
import json
import os
import secrets
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def write_private(path,text):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w") as f: f.write(text)
    path.chmod(0o600)


def credentials(folder):
    path=folder/"password"
    if not path.exists(): write_private(path,secrets.token_urlsafe(15)+"\n")
    password=path.read_text().strip()
    if not (folder/"shadow").exists():
        hashed=subprocess.run(["openssl","passwd","-6","-stdin"],input=password+"\n",text=True,capture_output=True,check=True).stdout.strip()
        write_private(folder/"shadow",f"root:!:20000:0:99999:7:::\nplayer:{hashed}:20000:0:99999:7:::\n")
    if not (folder/"authorized_keys").exists(): write_private(folder/"authorized_keys","")
    return password


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--players",type=int,default=23)
    parser.add_argument("--host",default="VM-IP",help="Address shown in the private access.csv")
    args=parser.parse_args()
    if not 1<=args.players<=23: parser.error("--players must be between 1 and 23")
    secret_dir=ROOT/"secrets"
    secret_dir.mkdir(mode=0o700,exist_ok=True)
    secret_dir.chmod(0o700)
    services={}
    volumes={}
    networks={}
    tokens={}
    access=[]

    def common(slot,role,port,nets):
        folder=secret_dir/slot
        folder.mkdir(mode=0o700,exist_ok=True)
        password=credentials(folder)
        access.append([slot,"player",password,str(port),f"ssh -p {port} player@{args.host}"])
        state=f"{slot}-state"
        home=f"{slot}-home"
        volumes[state]={}
        volumes[home]={}
        return {"image":"frostbyte:local","command":[role],
                "init":True,"restart":"unless-stopped","read_only":True,
                "security_opt":["no-new-privileges:true"],"cap_drop":["NET_RAW"],
                "pids_limit":96,"mem_limit":"256m","cpus":"0.50",
                "ports":[f"${{SSH_BIND:-0.0.0.0}}:{port}:22"],
                "tmpfs":["/run:rw,nosuid,nodev,size=16m","/tmp:rw,nosuid,nodev,size=32m,mode=1777"],
                "volumes":[f"{state}:/var/lib/frost",f"{home}:/home/player",
                           f"./secrets/{slot}/shadow:/run/bootstrap/shadow:ro",
                           f"./secrets/{slot}/authorized_keys:/run/bootstrap/authorized_keys:ro"],
                "networks":nets,
                "logging":{"driver":"json-file","options":{"max-size":"5m","max-file":"2"}}}

    for i in range(1,args.players+1):
        slot=f"player{i:02}"
        network=f"lane{i:02}"
        # Each slot gets its own bridge. Non-internal bridges allow published SSH
        # ports to be reachable from outside the VM (Docker drops these on internal networks).
        networks[network]={}
        services[slot]=common(slot,"player",2200+i,[network])
        token_path=secret_dir/slot/"token"
        if not token_path.exists(): write_private(token_path,secrets.token_hex(32))
        tokens[slot]=token_path.read_text().strip()
        services[slot]["volumes"].append(f"./secrets/{slot}/token:/run/bootstrap/score_token:ro")
        services[slot]["environment"]={"SCORE_URL":"http://scoreboard:8080"}
        services[slot]["depends_on"]={"scoreboard":{"condition":"service_healthy"}}
        services[slot]["healthcheck"]={"test":["CMD","python3","-c","from frost.client import request; request()"],"interval":"15s","timeout":"4s","retries":3,"start_period":"10s"}
    services["scoreboard"]=common("scoreboard","scoreboard",2200,list(networks))
    services["scoreboard"]["build"]={"context":"."}
    services["scoreboard"]["cpus"]="1.0"
    services["scoreboard"]["pids_limit"]=128
    services["scoreboard"]["ports"].append("${SCORE_BIND:-127.0.0.1}:8080:8080")
    services["scoreboard"]["volumes"].append("./secrets/scoreboard/tokens.json:/run/bootstrap/score_tokens:ro")
    services["scoreboard"]["healthcheck"]={"test":["CMD","python3","-c","import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2)"],"interval":"10s","timeout":"3s","retries":3}
    write_private(secret_dir/"scoreboard"/"tokens.json",json.dumps(tokens))
    gateway=common("gateway","gateway",2299,list(networks))
    gateway.update(mem_limit="512m",cpus="2.0",pids_limit=384)
    gateway["ports"]=["${GATEWAY_BIND:-127.0.0.1}:${GATEWAY_PORT:-2299}:22"]
    gateway["depends_on"]={slot:{"condition":"service_healthy"} for slot in services if slot.startswith("player") or slot=="scoreboard"}
    gateway["healthcheck"]={"test":["CMD","python3","-c","import socket; from frost.wire import send,receive; s=socket.socket(socket.AF_UNIX); s.settimeout(3); s.connect('/run/frost/gateway.sock'); send(s,b'J',{'action':'ping'}); assert receive(s)[0]==b'M'"],"interval":"15s","timeout":"4s","retries":3,"start_period":"15s"}
    router={slot:{"password":(secret_dir/slot/"password").read_text().strip()} for slot in [*tokens,"scoreboard"]}
    write_private(secret_dir/"gateway"/"router.json",json.dumps(router))
    shadow=secret_dir/"gateway"/"shadow"
    base="\n".join(line for line in shadow.read_text().splitlines() if not line.startswith("score:"))
    score_hash=(secret_dir/"scoreboard"/"shadow").read_text().split("player:",1)[1].split(":",1)[0]
    write_private(shadow,base+f"\nscore:{score_hash}:20000:0:99999:7:::\n")
    for role in ("player","score"):
        key=secret_dir/"gateway"/f"entry-{role}"
        if not key.exists(): subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
        key.chmod(0o600)
        gateway["volumes"].append(f"./secrets/gateway/entry-{role}.pub:/run/bootstrap/entry-{role}.pub:ro")
    gateway["volumes"].append("./secrets/gateway/router.json:/run/bootstrap/router.json:ro")
    for slot in router: gateway["volumes"].append(f"{slot}-state:/slots/{slot}:ro")
    services["gateway"]=gateway
    write_private(ROOT/"join-access.txt",f"Gemeinsamer Spielerzugang: ssh spiel@{args.host}\nPasswort: {(secret_dir/'gateway'/'password').read_text().strip()}\n\nLive-Scoreboard: ssh score@{args.host}\nPasswort: {(secret_dir/'scoreboard'/'password').read_text().strip()}\n\nStandard-Port-Zugaenge werden durch scripts/install_entry.py eingerichtet.\n")
    compose={"name":"shell-game","services":{"scoreboard":services.pop("scoreboard"),**services},"volumes":volumes,"networks":networks}
    (ROOT/"compose.yaml").write_text(json.dumps(compose,indent=2)+"\n")
    path=ROOT/"access.csv"
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,"w",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["slot","user","password","port","ssh_command"])
        writer.writerows(access)
    path.chmod(0o600)
    print(f"Prepared {args.players} player slots, shared SSH gateway and live scoreboard.")
    print("Private credentials: access.csv (0600). Existing passwords and tokens preserved.")
    print("Start: docker compose up -d --build")


if __name__=="__main__": main()
