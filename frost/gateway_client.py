"""Unprivileged, forced-command terminal client; never exposes a gateway shell."""
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
from .wire import send,receive


def main():
    if not sys.stdin.isatty():
        print("Bitte mit einem interaktiven SSH-Terminal verbinden."); return 1
    try:
        data={"action":"new"} if os.getuid()==1000 else {"action":"score"}
        size=shutil.get_terminal_size((100,38))
        data.update(term=os.environ.get("TERM","xterm-256color"),width=size.columns,height=size.lines)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(300)
            sock.connect("/run/frost/gateway.sock")
            send(sock,b"J",data)
            kind,payload=receive(sock)
            metadata=json.loads(payload)
            if kind==b"E":
                show("VERBINDUNG NICHT MOEGLICH",[metadata["error"],"Bitte später erneut verbinden."])
                return 1
            if kind!=b"M": return 1
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
        print("Verbindung beendet.")
        return 1


if __name__=="__main__": sys.exit(main())
