"""Small, keyboard-friendly floating hints; no function keys needed."""
import curses
import os
import subprocess
from .render import colors, put, box


def floating(screen, title, lines, choice=False):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.keypad(True)
    selected=False
    while True:
        screen.erase()
        h,w=screen.getmaxyx()
        width=min(78,max(20,w-4))
        height=min(len(lines)+7,max(8,h-2))
        x=max(1,(w-width)//2)
        y=max(0,(h-height)//2)
        box(screen,y,x,height,width,2)
        put(screen,y+1,x+3,title[:width-6],5,True)
        for i,line in enumerate(lines[:max(0,height-6)]):
            put(screen,y+3+i,x+3,line[:width-6],1)
        if choice:
            put(screen,y+height-2,x+3,"[ JA, KAEMPFEN ]" if selected else "  JA, KAEMPFEN  ",4 if selected else 3,selected)
            put(screen,y+height-2,x+24,"[ NEIN, ZURUECK ]" if not selected else "  NEIN, ZURUECK  ",2 if not selected else 3,not selected)
        else:
            put(screen,y+height-2,x+3,"[ ENTER - WEITER ]",2,True)
        screen.refresh()
        key=screen.getch()
        if key in (10,13,curses.KEY_ENTER): return selected if choice else True
        if key==27: return False
        if choice:
            if key in (ord("j"),ord("J"),curses.KEY_LEFT): selected=True
            if key in (ord("n"),ord("N"),curses.KEY_RIGHT): selected=False
            if key==9: selected=not selected


def show(title,lines,choice=False):
    pane=os.environ.get("TMUX_PANE")
    zoomed=False
    if pane:
        flag=subprocess.run(["tmux","display-message","-p","-t",pane,"#{window_zoomed_flag}"],capture_output=True,text=True)
        if flag.stdout.strip()=="0":
            zoomed=subprocess.run(["tmux","resize-pane","-Z","-t",pane],stderr=subprocess.DEVNULL).returncode==0
    try:
        return curses.wrapper(floating,title,lines,choice)
    except KeyboardInterrupt:
        return False
    finally:
        if zoomed: subprocess.run(["tmux","resize-pane","-Z","-t",pane],stderr=subprocess.DEVNULL)


def confirm_boss(state):
    bag=", ".join(state.get("bag",[])) or "LEER — sammle besser zuerst einen Zauber!"
    return show("BOSSKAMP STARTEN?",[
        f"Du: {state['hp']}/100 Leben  |  Krampus: {state['boss_hp']}/240",
        "Rucksack: "+bag,
        "",
        "ANGREIFEN  ~/rucksack/funke     (mehrmals ausfuehren)",
        "HEILEN     ~/rucksack/kakao     (vorher einsammeln)",
        "Weitere Zauber: ~/rucksack/frost, stern oder schild.",
        "",
        "Nach JA schliesst das Tor. Du kannst NICHT zurueck!",
        "Keine neuen Funde oder Aufgaben waehrend des Kampfes.",
        "Lesen kostet keine Leben. Falsche Befehle schon.",
        "Neu anfangen geht jederzeit mit: neustart",
        "",
        "J oder N waehlen, dann Enter. Standard: Nein.",
    ],choice=True)
