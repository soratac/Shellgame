import curses
import fcntl
import os
import re
import subprocess
import time
import sys
from pathlib import Path

from .client import request
from .render import colors, put


def name_dialog(screen):
    from .avatar import OPTIONS, appearance
    from .render import box, hero_frame
    colors()
    screen.keypad(True)
    state=request()["state"]
    existing=bool(state["name"])
    name=state["name"]
    avatar=appearance(state.get("avatar",{}))
    fields=[("Name",None),("Geschlecht","gender"),("Haartyp","style"),("Haarfarbe","hair"),("Shirtfarbe","shirt")]
    screen.timeout(160)
    field=1 if existing else 0
    error=""
    while True:
        screen.erase()
        h,w=screen.getmaxyx()
        width=min(70,w-2); left=max(0,(w-width)//2); height=min(21,h); top=(h-height)//2
        box(screen,top,left,height,width,2)
        logo=("█▀▀ █▀█ █▀█ █▀▀ ▀█▀ █▀▄ █ █ ▀█▀ █▀▀",
              "█▀  █▀▄ █ █ ▀▀█  █  █▀▄ ▀█▀  █  █▀ ",
              "▀   ▀ ▀ ▀▀▀ ▀▀▀  ▀  ▀▀   ▀   ▀  ▀▀▀")
        for row,line in enumerate(logo):
            put(screen,top+1+row,left+max(1,(width-len(line))//2),line if width>=40 else ("FROSTBYTE" if row==1 else ""),[1,2,3][row],True)
        base=top+(6 if height>=17 else 4)
        put(screen,base-1,left+3,"❄ CHARAKTER",2,True)
        spacing=2 if height>=19 else 1
        visible=max(1,(height-(base-top)-3+spacing-1)//spacing)
        first_visible=max(0,field-visible+1)
        for i,(label,part) in enumerate(fields[first_visible:first_visible+visible],first_visible):
            value = f"‹ {avatar[part]} ›" if part else name+("_" if field==0 else "")
            put(screen,base+1+(i-first_visible)*spacing,left+2,("› " if i==field else "  ")+f"{label:11}"+value,
                5 if i==field else 1,i==field)
        if width>=45:
            pw=min(30,width-32); ph=min(14,max(5,height-6))
            preview=hero_frame(pw,ph,time.monotonic(),avatar,walking=True)
            for y,row in enumerate(preview.cells):
                for x,(char,color) in enumerate(row):
                    if char!=" ": put(screen,top+4+y,left+width-pw-1+x,char,color)
        put(screen,top+height-2,left+3,error or "↵ Spielen",6 if error else 2)
        screen.refresh()
        try: key=screen.get_wch()
        except curses.error: continue
        if key in ("\n","\r",curses.KEY_ENTER):
            if not existing:
                result=request("name",[name])
                if not result["ok"]:
                    error="Name: 2–20 Buchstaben oder Zahlen."; field=0; continue
            request("avatar",[avatar[k] for k in OPTIONS]); return
        elif key in ("\t", curses.KEY_DOWN, curses.KEY_UP, curses.KEY_BTAB):
            first=1 if existing else 0
            step=-1 if key in (curses.KEY_UP,curses.KEY_BTAB) else 1
            field=first+(field-first+step)%(len(fields)-first)
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT) and field:
            part=fields[field][1]
            options=list(OPTIONS[part])
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
    audio = re.fullmatch(r"frost-music(2?)-(\d{1,5})-([A-Za-z0-9_-]{16})", os.environ.get("TERM",""))
    if audio and 0 < int(audio[2]) <= 65535:
        os.environ["TERM"] = "xterm-256color"
        if audio[1]: os.environ["FROST_LOCAL_SFX"] = "1"
        os.environ["FROST_LOCAL_MUSIC"] = f"http://127.0.0.1:{audio[2]}/#{audio[3]}"
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
