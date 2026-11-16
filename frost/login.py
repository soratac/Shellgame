import curses
import fcntl
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .client import request
from .render import colors, put


def name_dialog(screen):
    colors()
    name=""
    error=""
    while True:
        screen.erase()
        h,w=screen.getmaxyx()
        for y in range(0,h,3):
            put(screen,y,(y*17+5)%max(1,w-1),"·",3)
        width=min(76,w-2)
        left=max(0,(w-width)//2)
        top=max(0,(h-23)//2)
        for row in range(23):
            if row in (0,22):
                put(screen,top+row,left,"╭"+"─"*(width-2)+"╮" if row==0 else "╰"+"─"*(width-2)+"╯",2)
            else:
                put(screen,top+row,left,"│"+" "*(width-2)+"│",2)
        put(screen,top+2,left+4,"❄  F R O S T B Y T E",2,True)
        put(screen,top+3,left+4,"Der Weihnachtsstern wurde gestohlen.",1)
        put(screen,top+5,left+4,"Wie heisst du, Winterheld?",5)
        put(screen,top+7,left+4,"❯ "+name+"_",1,True)
        put(screen,top+9,left+4,error or "2–20 Zeichen · Enter beginnt deinen Lauf",6 if error else 3)
        for i,line in enumerate([
            "SO SPIELST DU — RETTE DEN WEIHNACHTSSTERN:",
            "ls / tree ~/welt        Orte und Gegenstaende anschauen",
            "cp funke ~/rucksack/     Einen Zauber mitnehmen",
            "cd ../wald              Andere Orte besuchen, mehr finden",
            "cd ../zitadelle         Zum Boss (du wirst vorher gefragt)",
            "~/rucksack/funke         Im Bossraum angreifen",
            "Kakao / Beeren vorher mitnehmen: Sie heilen dich.",
            "",
            "Tab ergaenzt Befehle. Tab Tab zeigt die Auswahl.",
            "Nach Kampfstart kein Rueckweg. Neue Runde: neustart",
        ]): put(screen,top+11+i,left+4,line,2 if i==0 else 1)
        screen.refresh()
        try: key=screen.get_wch()
        except curses.error: continue
        if key in ("\n","\r",curses.KEY_ENTER):
            result=request("name",[name])
            if result["ok"]: return
            error="Bitte 2–20 Buchstaben/Ziffern, _ oder -."
        elif key in ("\x7f","\b",curses.KEY_BACKSPACE): name=name[:-1]
        elif key in ("\x03","\x1b"): raise KeyboardInterrupt
        elif isinstance(key,str) and (key.isalnum() or key in " _-") and len(name)<20:
            name+=key


def main():
    if not sys.stdin.isatty():
        print("Bitte ein Terminal anfordern: ssh -t -p PORT player@HOST")
        return 1
    role=Path("/run/frost/role").read_text().strip()
    if role=="gateway":
        from .gateway_client import main as join
        return join()
    if role=="scoreboard":
        from .board import watch
        watch()
        return 0
    lock=open("/tmp/frost-login.lock","w")
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print("Dieser Spielerplatz hat bereits eine aktive SSH-Verbindung.")
        return 1
    first_login=not request()["state"]["name"]
    tutorial=Path.home()/".frost-tutorial"
    if first_login:
        curses.wrapper(name_dialog)
    elif not tutorial.exists():
        from .dialogs import show
        show("SO SPIELST DU",[
            "Ziel: Finde Zauber und besiege Krampus in der Zitadelle.",
            "",
            "ls / tree ~/welt       Umschauen und Wege finden",
            "cp funke ~/rucksack/    Gegenstaende mitnehmen",
            "cd ~/welt/wald         Zu anderen Orten gehen",
            "~/rucksack/funke        Im Bossraum angreifen",
            "",
            "Nimm vorher Kakao oder Beeren zum Heilen mit.",
            "Der Boss fragt dich vorher. Nach JA gibt es keinen Rueckweg.",
            "Tab hilft beim Tippen. Neuer Lauf: neustart",
        ])
    tutorial.write_text("3\n")
    subprocess.run([sys.executable,"-m","frost.world","init"],check=True)
    if subprocess.run(["tmux","has-session","-t","frost"],stderr=subprocess.DEVNULL).returncode:
        size=shutil.get_terminal_size((100,38))
        hud=subprocess.run(["tmux","-f","/etc/frost/tmux.conf","new-session","-d","-s","frost",
                            "-x",str(size.columns),"-y",str(size.lines),"-P","-F","#{pane_id}","python3 -m frost.render"],check=True,capture_output=True,text=True).stdout.strip()
        for flags in (["-b"],[]):
            subprocess.run(["tmux","split-window","-h","-l","1",*flags,"-t",hud,"python3 -m frost.gutter"],check=True)
        shell=subprocess.run(["tmux","split-window","-v","-p","52","-t",hud,"-P","-F","#{pane_id}",
                              "bash --rcfile /etc/frost/bashrc -i"],check=True,capture_output=True,text=True).stdout.strip()
        subprocess.run(["tmux","set-option","-t","frost","@frost-hud",hud],check=True)
        subprocess.run(["tmux","set-option","-t","frost","@frost-shell",shell],check=True)
        subprocess.run(["tmux","select-pane","-t",hud,"-T"," NORDPOL "])
        subprocess.run(["tmux","set-option","-p","-t",hud,"remain-on-exit","on"])
        subprocess.run(["tmux","select-pane","-t",shell,"-T"," DEINE SHELL "])
    subprocess.run(["tmux","select-pane","-t",subprocess.check_output(["tmux","show-option","-v","-t","frost","@frost-shell"],text=True).strip()])
    return subprocess.call(["tmux","attach-session","-t","frost"])


if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: pass
