"""A real full-screen result view, shown once per completed run."""
import curses
import os
import subprocess
import sys
import time
from pathlib import Path

from .client import request
from .render import colors, put, box, fit


def result_screen(screen, state):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.timeout(120)
    won = state["status"] == "won"
    tick = 0
    while True:
        h, w = screen.getmaxyx()
        screen.erase()
        if h < 16 or w < 44:
            put(screen, 1, 1, "GEWONNEN!" if won else "VERSUCH BEENDET", 5, True)
            put(screen, 3, 1, f"{state['score']} Punkte / {state['elapsed']:.2f}s", 1)
            put(screen, 5, 1, "ENTER - ZUR SHELL", 2)
        else:
            box(screen, 1, 2, h-3, w-4, 2)
            for i in range(12):
                put(screen, 3+(i*7+tick//5) % max(1,h-9), 4+(i*17) % max(1,w-9), "·", 3)
            width = min(64,w-10)
            left = (w-width)//2
            top = max(3,(h-16)//2)
            title = "WEIHNACHTEN GERETTET!" if won else "DEIN LICHT KOMMT ZURUECK."
            for row,text in enumerate(["       *       ","      /|\\      ","  ---< + >---  ","      \\|/      ","       *       "]):
                put(screen,top+row,(w-len(text))//2,text,5 if won else 3,True)
            put(screen,top+6,left,fit(title,width,center=True),5 if won else 6,True)
            put(screen,top+8,left,fit(state["name"],width,center=True),1)
            put(screen,top+10,left,fit(f"{state['score']} PUNKTE     {state['elapsed']:.2f} SEKUNDEN",width,center=True),2,True)
            if won:
                method={"loop":"SCHLEIFEN-TRICK", "driver":"TREIBER-TRICK", "spell":"ZAUBER", "staff":"ZUCKERSTAB"}.get(state["method"],"SIEG")
                put(screen,top+11,left,fit(f"{method}  /  {state['hp']} LEBEN UEBRIG",width,center=True),3)
            put(screen,min(h-5,top+14),left,fit("[ ENTER - ZUR SHELL ]",width,center=True),4,True)
            put(screen,h-3,4,"Noch eine Runde? Tippe danach: neustart",3)
        screen.refresh()
        if screen.getch() in (10,13,curses.KEY_ENTER,27): return
        tick += 1


def maybe_show():
    if not sys.stdin.isatty() or not sys.stdout.isatty(): return
    state=request()["state"]
    if state["status"] not in ("won","lost"): return
    key=f"{state['started']}:{state['ended']}:{state['status']}"
    marker=Path("/tmp/frost-finish-seen")
    if marker.exists() and marker.read_text()==key: return
    marker.write_text(key)
    pane=os.environ.get("TMUX_PANE")
    zoomed=False
    if pane:
        flag=subprocess.run(["tmux","display-message","-p","-t",pane,"#{window_zoomed_flag}"],capture_output=True,text=True)
        if flag.stdout.strip()=="0":
            zoomed=subprocess.run(["tmux","resize-pane","-Z","-t",pane],stderr=subprocess.DEVNULL).returncode==0
    try:
        curses.wrapper(result_screen,state)
    except KeyboardInterrupt:
        pass
    finally:
        if zoomed:
            subprocess.run(["tmux","resize-pane","-Z","-t",pane],stderr=subprocess.DEVNULL)


if __name__=="__main__": maybe_show()
