"""One fixed PTY + HUD. No tmux server, control prefix or extra windows."""
import codecs
import contextlib
import curses
import fcntl
from itertools import islice
import os
from pathlib import Path
import pty
import select
import signal
import socket
import struct
import termios
import time
import tty

from .client import request
from .music import indicator, mixer_action, music_link
from .mouse import MouseInput
from .music_http import recent_sounds
from .render import colors, paint, put, box, POSITIONS

CONTROL='/tmp/frost-terminal.sock'


@contextlib.contextmanager
def fullscreen(mouse=False):
    def resize(value):
        if not os.environ.get('FROST_TERMINAL'): return
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                sock.settimeout(2); sock.connect(CONTROL)
                sock.sendall((b'2' if mouse else b'1') if value else b'0'); sock.recv(1)
        except OSError: pass
    resize(True)
    try: yield
    finally: resize(False)


def frame(screen):
    import pyte
    colors()
    screen.nodelay(True)
    # We forward raw bytes to a real PTY, preserving Readline, Tab and Ctrl-C.
    tty.setraw(0)
    h,w=screen.getmaxyx()
    zoom=False
    dialog_mouse=False
    def dimensions():
        rows,cols=screen.getmaxyx()
        top=min(rows-7,max(10,round(rows*.62))) if rows>=18 else max(4,rows//2)
        return rows,cols,top,(rows if zoom else max(3,rows-top-2)),(cols if zoom else max(10,cols-4))
    rows,cols,top,sh,sw=dimensions()
    class TerminalScreen(pyte.Screen):
        alternate=None
        def set_mode(self,*modes,**kwargs):
            if kwargs.get('private') and any(m in (47,1047,1049) for m in modes) and self.alternate is None:
                import copy
                self.alternate=(copy.deepcopy(self.buffer),copy.deepcopy(self.cursor),self.margins)
                self.erase_in_display(2); self.cursor_position()
            super().set_mode(*modes,**kwargs)
        def reset_mode(self,*modes,**kwargs):
            super().reset_mode(*modes,**kwargs)
            if kwargs.get('private') and any(m in (47,1047,1049) for m in modes) and self.alternate is not None:
                self.buffer,self.cursor,self.margins=self.alternate
                self.alternate=None
                self.cursor.x=min(self.columns-1,self.cursor.x)
                self.cursor.y=min(self.lines-1,self.cursor.y)
    terminal=TerminalScreen(sw,sh)
    stream=pyte.Stream(terminal)
    decoder=codecs.getincrementaldecoder('utf-8')('replace')
    master,slave=pty.openpty()
    fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',sh,sw,0,0))
    child=os.fork()
    if child==0:
        os.close(master); os.setsid()
        fcntl.ioctl(slave,termios.TIOCSCTTY,0)
        for fd in (0,1,2): os.dup2(slave,fd)
        if slave>2: os.close(slave)
        os.environ.update(TERM='xterm-256color',FROST_TERMINAL='1')
        os.execv('/bin/bash',['bash','--rcfile','/etc/frost/bashrc','-i'])
    os.close(slave)
    terminal.write_process_input=lambda data: os.write(master,data.encode())
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    Path(CONTROL).unlink(missing_ok=True)
    listener.bind(CONTROL); os.chmod(CONTROL,0o600); listener.listen(4)
    music={"level":40,"muted":False}
    state=None; fetched=0; painted=0; previous_size=None
    local_music = bool(os.environ.get("FROST_LOCAL_MUSIC"))
    local_sfx = bool(os.environ.get("FROST_LOCAL_SFX"))
    last_sound = time.time()
    sent_level, last_signal = None, 0
    attrs={}
    position=origin=target=POSITIONS["dorf"]
    travel_start=time.monotonic()
    def style(char):
        key=(char.fg,char.bg,char.bold,char.italics,char.underscore,char.reverse)
        if key in attrs: return attrs[key]
        base={'black':0,'red':1,'green':2,'brown':3,'blue':4,'magenta':5,'cyan':6,'white':7,'default':-1}
        def color(value):
            if value in base: return base[value]
            try:
                r,g,b=(int(value[i:i+2],16) for i in (0,2,4))
                return 16+36*round(r/255*5)+6*round(g/255*5)+round(b/255*5) if curses.COLORS>=256 else 7
            except (ValueError,TypeError): return -1
        pair=16+len(attrs)
        if pair>=min(240,curses.COLOR_PAIRS): pair=0
        else:
            try: curses.init_pair(pair,color(char.fg),color(char.bg))
            except curses.error: pair=0
        result=curses.color_pair(pair)
        if char.bold: result|=curses.A_BOLD
        if char.underscore: result|=curses.A_UNDERLINE
        if char.reverse: result|=curses.A_REVERSE
        attrs[key]=result
        return result
    mouse=MouseInput()
    tracking=False
    notice=""
    notice_until=0
    def click(x,y):
        nonlocal music,notice,notice_until
        if y!=rows-1: return
        action=mixer_action(music,cols,x)
        if not action: return
        try:
            if action=="open":
                notice=music_link()
                notice_until=time.monotonic()+18
            else:
                music=request("music",[action])["music"]
        except (OSError,ValueError,KeyError):
            notice="Musik gerade nicht erreichbar."
            notice_until=time.monotonic()+4
    try:
        while True:
            physical=os.get_terminal_size(0)
            if screen.getmaxyx()!=(physical.lines,physical.columns):
                curses.resizeterm(physical.lines,physical.columns)
            rows,cols,top,sh,sw=dimensions()
            size=(sh,sw)
            if size!=previous_size:
                terminal.resize(lines=sh,columns=sw)
                fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',sh,sw,0,0))
                previous_size=size
            wanted=dialog_mouse or (not zoom and terminal.alternate is None and cols>=len(indicator(music))+4)
            if wanted!=tracking:
                os.write(1,b"\x1b[?1000h\x1b[?1006h" if wanted else b"\x1b[?1000l\x1b[?1006l")
                tracking=wanted
            ready,_,_=select.select([master,0,listener],[],[],.04)
            if listener in ready:
                with listener.accept()[0] as conn:
                    conn.settimeout(.2)
                    mode=conn.recv(1)
                    zoom=mode in (b'1',b'2')
                    dialog_mouse=mode==b'2'
                    rows,cols,top,sh,sw=dimensions()
                    terminal.resize(lines=sh,columns=sw)
                    terminal.erase_in_display(2)
                    fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',sh,sw,0,0))
                    previous_size=(sh,sw)
                    conn.sendall(b'K')
            if master in ready:
                try: data=os.read(master,65536)
                except OSError: break
                if not data: break
                stream.feed(decoder.decode(data))
            if 0 in ready:
                data=os.read(0,8192)
                if not data: break
                if tracking and not zoom: data=mouse.feed(data,click)
                elif mouse.pending: data=mouse.flush()+data
                if (1<<5) in terminal.mode:
                    for key in (b'A',b'B',b'C',b'D',b'H',b'F'):
                        data=data.replace(b'\x1b['+key,b'\x1bO'+key)
                os.write(master,data)
            now=time.monotonic()
            if mouse.pending and now-mouse.since>.12: os.write(master,mouse.flush())
            if (not zoom or local_sfx) and now-fetched>.15:
                try:
                    snapshot=request()
                    state=snapshot['state']
                    music=snapshot['music']
                    # Read as the player: show ordinary files as well as game items.
                    with os.scandir(Path.home()/"rucksack") as entries:
                        names = sorted("".join(c if c.isprintable() else "?" for c in e.name)[:40]
                                       for e in islice(entries, 65))
                    state["bag_display"] = names[:64] + (["…"] if len(names)>64 else [])
                    destination=POSITIONS.get(state['area'],POSITIONS['dorf'])
                    if destination!=target:
                        origin,target,travel_start=position,destination,now
                except (OSError,ValueError): pass
                fetched=now
            if local_music:
                level = 0 if music["muted"] else music["level"]
                if level != sent_level or now-last_signal >= 2:
                    os.write(1, f"\x1b]777;frost-volume={level:03}\x07".encode())
                    last_signal, sent_level = now, level
                if local_sfx and state:
                    for at, sounds in recent_sounds(state.get("events"), last_sound):
                        if level:
                            os.write(1, ("\x1b]777;frost-sound="+",".join(sounds)+"\x07").encode())
                        last_sound = at
            if now-painted<.075: continue
            screen.erase()
            if not zoom:
                hud=screen.derwin(top,cols,0,0)
                progress=min(1,(now-travel_start)/.9)
                position=tuple(origin[i]+(target[i]-origin[i])*progress for i in (0,1))
                paint(hud,state,now,position,walking=progress<1)
                if now<notice_until:
                    put(screen,top-1,1,notice,5,True)
                box(screen,top,0,rows-top,cols-1,2)
                label=indicator(music)
                if cols>=len(label)+4:
                    put(screen,rows-1,cols-3-len(label),label,2)

            sy,sx=(0,0) if zoom else (top+1,2)
            for y in range(min(sh,rows-sy)):
                line=terminal.buffer[y]
                for x in range(min(sw,cols-sx)):
                    char=line[x]
                    if not char.data: continue
                    try: screen.addstr(sy+y,sx+x,char.data,style(char))
                    except curses.error: pass
            try:
                curses.curs_set(0 if terminal.cursor.hidden else 1)
                screen.move(min(rows-1,sy+terminal.cursor.y),min(cols-1,sx+terminal.cursor.x))
            except curses.error: pass
            screen.refresh(); painted=now
    finally:
        if tracking:
            with contextlib.suppress(OSError): os.write(1,b"\x1b[?1000l\x1b[?1006l")
        with contextlib.suppress(OSError, ValueError):
            request("music", ["close"])
        listener.close(); Path(CONTROL).unlink(missing_ok=True); os.close(master)
        try: os.killpg(child,signal.SIGHUP)
        except ProcessLookupError: pass
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            if os.waitpid(child,os.WNOHANG)[0]: break
            time.sleep(.05)
        else:
            try: os.killpg(child,signal.SIGKILL)
            except ProcessLookupError: pass
            os.waitpid(child,0)


def main():
    try: curses.wrapper(frame)
    except (KeyboardInterrupt,EOFError): pass
