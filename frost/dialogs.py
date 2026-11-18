"""Small, keyboard-friendly floating hints; no function keys needed."""
import curses
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
    from .terminal import fullscreen
    with fullscreen():
        try: return curses.wrapper(floating,title,lines,choice)
        except KeyboardInterrupt: return False


def confirm_boss(state):
    from .engine import route_count
    count=route_count(state)
    return show("BOSSKAMP STARTEN?",[
        f"Du {state['hp']}/100   ·   Krampus {state['boss_hp']}/240",
        "",
        "Angriff:  ~/rucksack/funke",
        "Heilung:  ~/rucksack/kakao",
        "",
        f"Orte {min(3,count)}/3: "+("Frostsiegel offen." if count>=3 else "Nur der schnelle Loop kann schon gewinnen!"),
        "Nach JA kein Rueckweg. Neustart: neustart",
        "",
        "J / N waehlen · Enter bestaetigt",
    ],choice=True)
