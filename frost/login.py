import curses
import fcntl
import os
import subprocess
import sys
from pathlib import Path

from .client import request
from .render import colors, put


def name_dialog(screen):
    from .avatar import HAIR, SHIRTS, DEFAULT, sprite
    from .render import Canvas, box
    colors()
    screen.keypad(True)
    state=request()["state"]
    existing=bool(state["name"])
    name=state["name"]
    avatar=dict(state.get("avatar",DEFAULT))
    field=1 if existing else 0
    error=""
    while True:
        screen.erase()
        h,w=screen.getmaxyx()
        width=min(68,w-2); left=max(0,(w-width)//2); top=max(0,(h-18)//2)
        box(screen,top,left,18,width,2)
        put(screen,top+1,left+3,"DEIN WINTERHELD",5,True)
        put(screen,top+3,left+3,"Wie heisst du, Winterheld?",1)
        labels=["Name   "+(name or "_")+ ("_" if field==0 and name else ""),
                "Haare  < "+avatar["hair"]+" >", "Shirt  < "+avatar["shirt"]+" >"]
        for i,label in enumerate(labels):
            put(screen,top+5+i*2,left+3,("› " if field==i else "  ")+label,2 if field==i else 1,field==i)
        preview=Canvas(10,6); sprite(preview,1,0,avatar)
        for y,row in enumerate(preview.cells):
            for x,(char,color) in enumerate(row):
                put(screen,top+5+y,left+width-15+x,char,color)
        put(screen,top+12,left+3,error or "Tab: Feld   Pfeile: Farbe   Enter: Spielen",6 if error else 3)
        put(screen,top+14,left+3,"ls umsehen  ·  cp mitnehmen  ·  cd gehen",1)
        put(screen,top+15,left+3,"3 Orte erkunden → Boss besiegen",2)
        screen.refresh()
        try: key=screen.get_wch()
        except curses.error: continue
        if key in ("\n","\r",curses.KEY_ENTER):
            if not existing:
                result=request("name",[name])
                if not result["ok"]:
                    error="Name: 2–20 Buchstaben oder Zahlen."; field=0; continue
            request("avatar",[avatar["hair"],avatar["shirt"]]); return
        elif key=="\t": field=(field+1)%3; field=1 if existing and field==0 else field
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT) and field in (1,2):
            options=list(HAIR if field==1 else SHIRTS); part="hair" if field==1 else "shirt"
            avatar[part]=options[(options.index(avatar[part])+(1 if key==curses.KEY_RIGHT else -1))%len(options)]
        elif key in ("\x03","\x1b"): raise KeyboardInterrupt
        elif field==0 and not existing:
            if key in ("\x7f","\b",curses.KEY_BACKSPACE): name=name[:-1]
            elif isinstance(key,str) and (key.isalnum() or key in " _-") and len(name)<20: name+=key


def edit_avatar():
    from .terminal import fullscreen
    with fullscreen(): curses.wrapper(name_dialog)


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
    state=request()["state"]
    if not state["name"] or not state.get("avatar_set"):
        curses.wrapper(name_dialog)
    subprocess.run([sys.executable,"-m","frost.world","init"],check=True)
    from .terminal import main as terminal
    terminal()
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: pass
