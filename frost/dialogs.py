"""Small, keyboard-friendly floating hints; no function keys needed."""
import curses
from .render import colors, put, box


def floating(screen, title, lines):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.keypad(True)
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
        put(screen,y+height-2,x+3,"[ ENTER - WEITER ]",2,True)
        screen.refresh()
        key=screen.getch()
        if key in (10,13,curses.KEY_ENTER): return True
        if key==27: return False


def show(title,lines):
    from .terminal import fullscreen
    with fullscreen():
        try: return curses.wrapper(floating,title,lines)
        except KeyboardInterrupt: return False
