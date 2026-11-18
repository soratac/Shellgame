"""Authenticated score ingestion, SQLite persistence and live spectator terminal."""
import argparse
import curses
import hmac
import json
import ipaddress
import math
import os
import re
import sqlite3
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .render import colors, put, box, fit, Canvas, bar, boss_frame, hero_frame, overlay
from .activity import HISTORY_SIZE, MAX_PAYLOAD, bounded_command, screen_command
from . import music_http
from .items import ITEMS
from .render import combat_frame, world_frame, POSITIONS, attack_effect
from .avatar import DEFAULT, appearance
from .records import bests as merge_bests, LEGACY_KEYS


def ranking(rows, view=0):
    if view==1:
        return sorted((r for r in rows if merge_bests(r.get("bests"))),
                      key=lambda r:(merge_bests(r["bests"])["best"],-r["score"],r["slot"]))
    return sorted(rows,key=lambda r:(-r["score"],0 if r["status"]=="won" else 1,
                                    r["elapsed"] if r["status"]=="won" else float("inf"),r["slot"]))


def online(row,now):
    return row.get("connected",False) and 0<=now-row["updated"]<8


def duration(seconds):
    minutes, seconds = divmod(max(0, seconds),60)
    hours, minutes = divmod(int(minutes),60)
    return f"{hours:d}:{minutes:02d}:{seconds:05.2f}" if hours else f"{minutes:02d}:{seconds:05.2f}"


def columns(width):
    if width>=77:
        return [("rank",3),("avatar",3),("name",19),("score",6),("time",10),("status",10),("area",8)]
    if width>=61:
        return [("rank",3),("avatar",3),("name",16),("score",6),("time",10),("status",8)]
    return [("rank",2),("avatar",2),("name",max(6,min(15,width-32))),("score",5),("time",10)]


def table_line(values, layout):
    return " │ ".join(fit(values.get(key,""),width,right=key in {"rank","score","hp","boss","time"}) for key,width in layout)


class Board:
    def __init__(self, db, tokens):
        self.db=sqlite3.connect(db,check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS scores (slot TEXT PRIMARY KEY, payload TEXT NOT NULL, updated REAL NOT NULL)")
        self.db.commit()
        self.lock=threading.Lock()
        self.tokens=tokens
        self.activity={}
        self.music=music_http.Sessions()

    def authenticate(self, token):
        tokens=dict(self.tokens)
        try: tokens.update(json.loads(Path("/run/controller/registry.json").read_text()))
        except (OSError,ValueError): pass
        return next((slot for slot,value in tokens.items() if hmac.compare_digest(value,token)),None)

    def update(self, slot, data):
        if not isinstance(data,dict) or not re.fullmatch(r"[\w -]{2,20}",data.get("name","")):
            raise ValueError("invalid name")
        for field in ("hp","boss_hp","score","elapsed","started"):
            value=data.get(field)
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:
                raise ValueError("invalid numeric field")
        if data["hp"]>100 or data["boss_hp"]>240 or data["score"]>10000:
            raise ValueError("out of bounds")
        if data.get("status") not in ("playing","won","lost"):
            raise ValueError("invalid status")
        bests=data.get("bests",{})
        if not isinstance(bests,dict) or len(bests)>5:
            raise ValueError("invalid records")
        for key,value in bests.items():
            if key not in LEGACY_KEYS or not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:
                raise ValueError("invalid record")
        selected={k:data.get(k) for k in ("name","hp","boss_hp","score","elapsed","started","status","method")}
        selected["bests"]=merge_bests(bests)
        avatar=data.get("avatar",DEFAULT)
        selected["avatar"]=appearance(avatar)
        if not isinstance(data.get("connected",False),bool): raise ValueError("invalid presence")
        selected["connected"]=data.get("connected",False)
        bag = data.get("bag", [])
        label = data.get("command_label","")
        if not isinstance(bag,list) or not isinstance(label,str):
            raise ValueError("invalid spectator data")
        selected["bag"] = [item for item in ITEMS if item in bag]
        history=data.get("command_history", [])
        if not isinstance(history,list) or len(history)>HISTORY_SIZE or not all(isinstance(cmd,str) for cmd in history):
            raise ValueError("invalid command history")
        activity={"command_label":bounded_command(label),"command_active":data.get("command_active") is True,
                  "command_history":[bounded_command(cmd) for cmd in history]}
        selected["grinch_found"] = data.get("grinch_found") is True
        selected["boss_started"] = data.get("boss_started") is True
        selected["visited"] = [p for p in POSITIONS if p in data.get("visited",[])] if isinstance(data.get("visited",[]),list) else []
        selected["events"]=[]
        events=data.get("events",[])
        if not isinstance(events,list): raise ValueError("invalid events")
        if events:
            event=events[-1]
            if not isinstance(event,dict): raise ValueError("invalid event")
            values={key:event.get(key,0) for key in ("at","damage","hurt")}
            if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in values.values()):
                raise ValueError("invalid animation")
            if not 0<=values["damage"]<=240 or not -100<=values["hurt"]<=100 or values["at"]<0: raise ValueError("invalid damage")
            for key,allowed in [("kind",("use","cast","attack","disable","unload","heal","observe","ping","bag","scan")),
                                ("spell",(*ITEMS,"stab","eissturm","frost_armor","blizzard"))]:
                if event.get(key) in allowed: values[key]=event[key]
            for key,limit in [("boss_before",240),("hp_before",100)]:
                if isinstance(event.get(key),int) and 0<=event[key]<=limit: values[key]=event[key]
            selected["events"]=[values]
        selected["area"]=data.get("area") if data.get("area") in {"dorf","wald","werkstatt","archiv","zitadelle"} else "unterwegs"
        selected["method"]=selected["method"] if selected["method"] in {"loop","staff","spell","driver"} else None
        with self.lock:
            self.music.update(slot, data.get("music") if selected["connected"] else None, events)
            if selected["connected"]: self.activity[slot]=activity
            else: self.activity.pop(slot,None)
            self.db.execute("INSERT INTO scores VALUES (?,?,?) ON CONFLICT(slot) DO UPDATE SET payload=excluded.payload, updated=excluded.updated",
                            (slot,json.dumps(selected),time.time()))
            self.db.commit()

    def rows(self,live=False):
        with self.lock:
            records=self.db.execute("SELECT slot,payload,updated FROM scores").fetchall()
            now=time.time()
            rows=[]
            for slot,payload,updated in records:
                row=dict(json.loads(payload),slot=slot,updated=updated)
                if not online(row,now): self.activity.pop(slot,None)
                if live:
                    if not online(row,now): continue
                    row.update(self.activity.get(slot,{}))
                rows.append(row)
        for row in rows:
            row.pop("mode",None)
            row["bests"]=merge_bests(row.get("bests"))
            row.setdefault("avatar",dict(DEFAULT))
            row.setdefault("connected",False)
            row.setdefault("events",[])
        return ranking(rows)


def handler_for(board):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self,*args): pass

        def reply(self,status,payload):
            body=json.dumps(payload,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path=="/health": self.reply(200,{"ok":True})
            elif self.path=="/api/music-url":
                body=os.environ.get("MUSIC_URL","http://localhost:8094").rstrip("/").encode()
                self.send_response(200)
                self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path=="/api/live":
                if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                    return self.reply(403, {"error":"spectator access only"})
                self.reply(200,{"players":board.rows(live=True),"server_time":time.time()})
            elif self.path=="/api/scores": self.reply(200,{"players":board.rows(),"server_time":time.time()})
            else: self.reply(404,{"error":"not found"})

        def do_POST(self):
            if self.path!="/api/score": return self.reply(404,{"error":"not found"})
            slot=board.authenticate(self.headers.get("Authorization","").removeprefix("Bearer "))
            if not slot: return self.reply(401,{"error":"unauthorized"})
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 1<=size<=MAX_PAYLOAD: return self.reply(413,{"error":"payload size"})
                data=json.loads(self.rfile.read(size))
                board.update(slot,data)
            except (ValueError,TypeError,OverflowError):
                return self.reply(400,{"error":"invalid score"})
            self.reply(200,{"ok":True})
    return Handler


def grid_shape(count,w,h):
    # Prefer a wide terminal viewport per player. Tight grids pack down to 16x6.
    max_cols, max_rows = max(1,w//16), max(1,h//6)
    if count>max_cols*max_rows:
        max_cols, max_rows = max(1,w//12), max(1,h//4)
    shown = min(max(count,1),max_cols*max_rows)
    choices = []
    for cols in range(1,max_cols+1):
        rows = math.ceil(shown/cols)
        if rows>max_rows: continue
        aspect = (w/cols)/(h/rows)
        cost = abs(math.log(aspect/2.8)) + (rows*cols-shown)/shown
        choices.append((cost,cols,rows))
    _, cols, rows = min(choices)
    return cols,rows


def tile(screen,row,y,x,h,w,now):
    live=online(row,now)
    edge=4 if live else 3
    compact=h<7 or w<16
    if not compact: box(screen,y,x,h,w,edge)
    inner=w-2
    score=str(row["score"])+"p"
    def line(at,text,color=1,bold=False):
        put(screen,y+at,x+1,fit(text,inner),color,bold)
    name=fit(row["name"],max(1,inner-len(score)-1))
    first=0 if compact else 1
    line(first,name+" "+score,5,True)
    fighting=row.get("boss_started",False)
    place="Grinch" if fighting else row["area"]
    if row["status"]=="won": place="SIEG"
    elif row["status"]=="lost": place="Niederlage"
    line(first+1,f"{place}  ♥{row['hp']}" + (f"  ◆{row['boss_hp']}" if fighting else ""),edge)
    scene_h=h-(4 if compact else 6)
    if scene_h>0:
        # Render the same scene and moves as the player's HUD using public game state.
        state=dict(row,visited=row.get("visited",[]))
        tick=now if live else row["updated"]
        if fighting and scene_h>=6 and inner>=25:
            events=state.get("events",[])
            if events and not {"kind","hp_before","boss_before"}<=events[-1].keys():
                state["events"]=[]
            canvas=combat_frame(min(inner,90),min(scene_h,24),state,tick)
        elif not fighting and scene_h>=9 and inner>=48:
            canvas=world_frame(min(inner,96),min(scene_h,25),state,
                               POSITIONS.get(row["area"],POSITIONS["dorf"]),tick)
        else:
            canvas=Canvas(min(inner,70),min(scene_h,14))
            if fighting:
                overlay(canvas,hero_frame(canvas.w//2,canvas.h,tick,row.get("avatar"),True),0,0)
                event=next(iter(row.get("events",[])),None)
                age=now-event["at"] if event else 99
                overlay(canvas,boss_frame(canvas.w//2,canvas.h,tick,event=event,age=age),canvas.w//2,0)
                if live and row.get("events"):
                    event=row["events"][-1]
                    attack_effect(canvas,event,now-event["at"],(canvas.w//4,canvas.h-1),(3*canvas.w//4,0))
            else:
                overlay(canvas,hero_frame(canvas.w,canvas.h,tick,row.get("avatar")),0,0)
        top=y+first+2+(scene_h-canvas.h)//2
        left=x+1+(inner-canvas.w)//2
        for cy,cells in enumerate(canvas.cells):
            for cx,(ch,color) in enumerate(cells):
                if ch!=" ": put(screen,top+cy,left+cx,ch,color)
    bag=", ".join(row.get("bag",[])) or "leer"
    prefix="Rucksack " if inner>=30 else "Bag "
    # A long bag scrolls even on compact cards.
    room=max(1,inner-len(prefix))
    if len(bag)>room:
        loop=bag+"   "; offset=int(now*2)%len(loop)
        bag=(loop+loop)[offset:offset+room]
    last=h-1 if compact else h-2
    line(last-1,prefix+bag,5)
    history=row.get("command_history") or []
    label=screen_command(row.get("command_label") or (history[0] if history else "bereit"))
    line(last,("▶ " if live and row.get("command_active") else "$ ")+label,2)


def paint_board(screen,rows,now,page=0):
    screen.erase()
    h,w=screen.getmaxyx()
    if h<8 or w<18:
        put(screen,0,0,"LIVE-SCOREBOARD",2)
        return 1
    ordered=ranking(rows)
    live=[r for r in ordered if online(r,now)]
    cols,lines=grid_shape(len(live),w-1,h-2)
    step=cols*lines
    pages=[live[i:i+step] for i in range(0,len(live),step)]
    page%=max(1,len(pages))
    marker=f"  ← {page+1}/{len(pages)} →" if len(pages)>1 else ""
    put(screen,0,1,fit(f"LIVE-SCOREBOARD   {len(live)} ONLINE"+marker,w-2),2,True)
    if not pages:
        put(screen,1,1,"Tab · Liste",3)
        put(screen,3,2,"Warte auf Spieler …",3)
        return 1
    visible=pages[page]
    put(screen,1,1,"Tab · Liste",3)
    cols,lines=grid_shape(len(visible),w-1,h-2)
    for i,row in enumerate(visible):
        gy,gx=divmod(i,cols)
        y=2+gy*(h-2)//lines; x=gx*(w-1)//cols
        tile(screen,row,y,x,2+(gy+1)*(h-2)//lines-y,(gx+1)*(w-1)//cols-x,now)
    return len(pages)


def history_entries(row):
    entries=[("Jetzt",row.get("command_label") or "bereit")]
    entries.extend((str(i),cmd) for i,cmd in enumerate(row.get("command_history",[]),1))
    return entries


def wrap_command(command,width):
    """Hard wrap at terminal cell boundaries, including whitespace in quoted arguments."""
    from .render import cell_width
    lines=[]; segment=[]; used=0
    for ch in screen_command(command,multiline=True):
        if ch=="\n":
            lines.append("".join(segment)); segment=[]; used=0
            continue
        size=cell_width(ch)
        if used+size>width:
            lines.append("".join(segment)); segment=[]; used=0
        segment.append(ch); used+=size
    lines.append("".join(segment))
    return lines


def paint_list(screen,live,focus):
    screen.erase()
    h,w=screen.getmaxyx()
    put(screen,0,1,f"LIVE-LISTE   {len(live)} ONLINE",2,True)
    put(screen,1,1,"Tab Raster · ↑↓ Spieler · Enter Verlauf",3)
    if not live:
        put(screen,3,1,"Warte auf Spieler …",3)
        return
    if w<30 or h<12:
        put(screen,3,1,"Terminal vergrößern",3)
        return
    # Leave six command lines below the roster. Keep selection visible on resize.
    capacity=max(1,h-12)
    start=focus//capacity*capacity
    name_w=min(22,max(9,w//4))
    head=fit("Spieler",name_w)+" Punkte   Ort         Befehl"
    put(screen,3,1,head,3)
    for y,row in enumerate(live[start:start+capacity],4):
        cmd=row.get("command_label") or next(iter(row.get("command_history",[])),"bereit")
        line=fit(row["name"],name_w)+f" {row['score']:6}   "+fit(row["area"],12)+screen_command(cmd)
        chosen=row["slot"]==live[focus]["slot"]
        put(screen,y,1,line,5 if chosen else 1,chosen)
    y=4+min(len(live),capacity)
    row=live[focus]
    put(screen,y,1,row["name"]+" · Befehle",2,True)
    for i,(label,cmd) in enumerate(history_entries(row),1):
        put(screen,y+i,1,f"{label:>5}  "+screen_command(cmd),2 if i==1 else 1)


def paint_history(screen,row,offset):
    screen.erase()
    h,w=screen.getmaxyx()
    put(screen,0,1,row["name"]+" · Befehlsverlauf",2,True)
    lines=[]
    for label,cmd in history_entries(row):
        prefix=f"{label:>5}  "
        for i,line in enumerate(wrap_command(cmd,max(1,w-len(prefix)-3))):
            lines.append((prefix if i==0 else " "*len(prefix))+line)
    height=max(1,h-3)
    offset=max(0,min(offset,len(lines)-height))
    put(screen,1,1,"↑↓ scrollen · Enter zurück",3)
    for y,line in enumerate(lines[offset:offset+height],3):
        put(screen,y,1,line)
    return offset


def board_hud(screen,url):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.keypad(True); screen.timeout(130)
    page=0; rows=[]; fetched=0; error=False
    mode="grid"; selected=None; offset=0
    while True:
        now=time.time()
        if now-fetched>=.4:
            try:
                with urllib.request.urlopen(url+"/api/live",timeout=2) as response: rows=json.load(response)["players"]
                error=False
            except (OSError,ValueError,KeyError): error=True
            fetched=now
        live=[r for r in rows if online(r,now)]
        slots=[r["slot"] for r in live]
        if selected not in slots:
            selected=slots[0] if slots else None
            offset=0
            if mode=="history": mode="list"
        focus=slots.index(selected) if live else 0
        pages=1
        if mode=="grid": pages=paint_board(screen,live,now,page)
        elif mode=="list": paint_list(screen,live,focus)
        else: offset=paint_history(screen,live[focus],offset)
        if error: put(screen,1,1,"Verbinde …",6)
        screen.refresh()
        key=screen.getch()
        if key in (ord("q"),ord("Q"),27): return
        if key in (9,ord("l"),ord("L")):
            mode="list" if mode=="grid" else "grid"; offset=0
        elif key in (10,13,curses.KEY_ENTER) and live:
            mode="list" if mode=="history" else "history"; offset=0
        elif mode=="list" and live and key in (curses.KEY_UP,curses.KEY_DOWN):
            selected=slots[(focus+(1 if key==curses.KEY_DOWN else -1))%len(slots)]
        elif mode=="history":
            step=max(1,screen.getmaxyx()[0]-3)
            offset+= {curses.KEY_DOWN:1,curses.KEY_UP:-1,curses.KEY_NPAGE:step,curses.KEY_PPAGE:-step}.get(key,0)
        elif key in (curses.KEY_RIGHT,ord("n")): page=(page+1)%pages
        if key in (curses.KEY_LEFT,ord("p")): page=(page-1)%pages


def watch():
    curses.wrapper(board_hud,os.environ.get("SCORE_URL","http://127.0.0.1:8080"))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--watch",action="store_true")
    args=parser.parse_args()
    if args.watch: return watch()
    db=os.environ.get("SCORE_DB","/var/lib/frost/scoreboard.sqlite")
    tokens=json.loads(Path("/run/bootstrap/score_tokens").read_text())
    board=Board(db,tokens)
    server=ThreadingHTTPServer(("0.0.0.0",8080),handler_for(board))
    audio=ThreadingHTTPServer(("0.0.0.0",8094),music_http.handler_for(board))
    threading.Thread(target=audio.serve_forever,daemon=True).start()
    server.serve_forever()


if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: pass
