"""Small literal .env parser: passwords are never evaluated as shell code."""
from pathlib import Path


def read_env(path):
    values={}
    if not Path(path).exists(): return values
    for number,line in enumerate(Path(path).read_text().splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line: raise ValueError(f'.env Zeile {number}: KEY=VALUE erwartet')
        key,value=line.split('=',1); key=key.strip(); value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in '\"\'': value=value[1:-1]
        values[key]=value
    return values


def write_env(path,values):
    text=''.join(f"{k}='{v}'\n" for k,v in values.items())
    if any("'" in v or '\n' in v or '\r' in v for v in values.values()): raise ValueError('Ungueltiger .env-Wert')
    import os
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f: f.write(text)
    Path(path).chmod(0o600)
