"""Unprivileged, forced-command terminal client; never exposes a gateway shell."""
import curses
import json
import os
import select
import shutil
import signal
import socket
import sys
import termios
import tty

from .dialogs import show
from .render import box,colors,put
from .wire import send,receive


def lobby(screen):
    colors()
    code=""
    resume=False
    while True:
        screen.erase()
        h,w=screen.getmaxyx()
        width=min(74,w-2)
        x=max(0,(w-width)//2)
        y=max(0,(h-11)//2)
        box(screen,y,x,11,width,2)
        put(screen,y+2,x+3,"FROSTBYTE / GEMEINSAMER EINSTIEG",5,True)
        put(screen,y+4,x+3,"Der Grinch hat den Weihnachtsstern gestohlen. Hol ihn zurück!",1)
        put(screen,y+6,x+3,"Enter   Neues Spiel     R   Fortsetzen",2,True)
        put(screen,y+8,x+3,"Fortsetzen-Code: "+code if resume else "",1)

        screen.refresh()
        try: key=screen.get_wch()
        except curses.error: continue
        if key in ("\n","\r",curses.KEY_ENTER):
            if not resume or code: return {"action":"resume","code":code} if resume else {"action":"new"}
        elif key in ("\x1b","\x03"): raise KeyboardInterrupt
        elif key in ("r","R") and not resume: resume=True
        elif key in ("n","N"): resume=False; code=""
        elif key in ("\x7f",curses.KEY_BACKSPACE,"\b"): code=code[:-1]
        elif resume and isinstance(key,str) and key.upper() in "0123456789ABCDEF-" and len(code)<24: code+=key.upper()


def main():
    if not sys.stdin.isatty():
        print("Bitte mit einem interaktiven SSH-Terminal verbinden."); return 1
    try:
        data=curses.wrapper(lobby) if os.getuid()==1000 else {"action":"score"}
        size=shutil.get_terminal_size((100,38))
        data.update(term=os.environ.get("TERM","xterm-256color"),width=size.columns,height=size.lines)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(300)
            sock.connect("/run/frost/gateway.sock")
            print("Dein Container wird vorbereitet …",flush=True)
            send(sock,b"J",data)
            kind,payload=receive(sock)
            metadata=json.loads(payload)
            if kind==b"E":
                show("VERBINDUNG NICHT MOEGLICH",[metadata["error"],"", "Verbinde dich erneut und waehle gegebenenfalls Fortsetzen."])
                return 1
            if kind!=b"M": return 1
            if metadata["role"]=="player":
                show("DEIN SPIELERPLATZ",[
                    "DEIN FORTSETZEN-CODE: "+metadata["code"],
                    "",
                    "Kopiere oder notiere diesen Code.",
                    "Spaeter: R waehlen und Code eingeben.",
                ])
            original=termios.tcgetattr(sys.stdin.fileno())
            pending=True
            def resized(*_):
                nonlocal pending
                pending=True
            previous=signal.signal(signal.SIGWINCH,resized)
            try:
                tty.setraw(sys.stdin.fileno())
                while True:
                    if pending:
                        size=shutil.get_terminal_size((100,38))
                        send(sock,b"R",[size.columns,size.lines])
                        pending=False
                    ready,_,_=select.select([sock,sys.stdin],[],[],.2)
                    if sock in ready:
                        kind,payload=receive(sock)
                        if kind==b"O":
                            view=memoryview(payload)
                            while view: view=view[os.write(sys.stdout.fileno(),view):]
                        elif kind in (b"D",b"E"): return 0 if kind==b"D" else 1
                    if sys.stdin in ready:
                        data=os.read(sys.stdin.fileno(),32768)
                        if not data: return 0
                        send(sock,b"I",data)
            finally:
                termios.tcsetattr(sys.stdin.fileno(),termios.TCSADRAIN,original)
                signal.signal(signal.SIGWINCH,previous)
    except KeyboardInterrupt:
        return 0
    except (OSError,EOFError,ValueError):
        print("Verbindung beendet. Mit deinem Code kannst du fortsetzen.")
        return 1


if __name__=="__main__": sys.exit(main())
