"""A real full-screen result view, shown once per completed run."""
import curses
import sys
import time
from pathlib import Path

from .client import request
from .render import colors, put, fit
from .showcase import blit, button, enable_buttons, festival, mouse_press


def result_screen(screen, state):
    colors()
    enable_buttons(screen)
    screen.timeout(100)
    won=state["status"]=="won"
    started=time.monotonic()
    while True:
        h,w=screen.getmaxyx()
        screen.erase()
        title="WEIHNACHTEN GERETTET!" if won else "DEIN LICHT ERLISCHT"
        y=1 if h>=12 else 0
        put(screen,y,max(0,(w-len(title))//2),title,5 if won else 12,True)
        footer=max(y+1,h-5)
        sky_h=footer-y-1
        if sky_h>=3 and w>=12:
            blit(screen,festival(w-2,sky_h,time.monotonic()-started,won),y+1,1)
        method={"loop":"Loop","staff":"Zuckerstab","spell":"Zauber","driver":"Treiber-Trick"}.get(state.get("method"))
        name=state["name"]+(f"  ·  {method}" if won and method else "")
        stats=f"{state['score']} PUNKTE   {state['elapsed']:.2f} s   {state['hp']} LP"
        put(screen,footer,1,fit(name,w-2,center=True),1,True)
        put(screen,footer+1,1,fit(stats,w-2,center=True),5 if won else 3)
        action="↵  Zur Shell"
        row=min(h-1,footer+3)
        target=button(screen,row,max(0,(w-len(action)-4)//2),action)
        if footer+4<h:
            put(screen,footer+4,1,fit("Neue Runde mit restart",w-2,center=True),3)
        screen.refresh()
        key=screen.getch()
        if key in (10,13,curses.KEY_ENTER,27): return
        if key==curses.KEY_MOUSE:
            click=mouse_press()
            if click and click[1]==row and click[0] in target: return


def maybe_show():
    if not sys.stdin.isatty() or not sys.stdout.isatty(): return
    state=request()["state"]
    if state["status"] not in ("won","lost"): return
    key=f"{state['started']}:{state['ended']}:{state['status']}"
    marker=Path("/tmp/frost-finish-seen")
    if marker.exists() and marker.read_text()==key: return
    marker.write_text(key)
    # Let the final hit and falling health bars finish before the win window.
    event=(state.get("events") or [{}])[-1]
    time.sleep(max(0,min(1.4,event.get("at",0)+1.4-time.time())))
    from .terminal import fullscreen
    with fullscreen(mouse=True):
        try: curses.wrapper(result_screen,state)
        except KeyboardInterrupt: pass


if __name__=="__main__": maybe_show()
