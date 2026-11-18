"""Authenticated score ingestion, SQLite persistence and live spectator terminal."""
import argparse
import curses
import hmac
import json
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
from .activity import public_command
from .items import ITEMS
from .render import combat_frame, world_frame, POSITIONS, attack_effect
from .avatar import DEFAULT, HAIR, SHIRTS, sprite
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
        if not isinstance(avatar,dict) or avatar.get("hair") not in HAIR or avatar.get("shirt") not in SHIRTS:
            raise ValueError("invalid avatar")
        selected["avatar"]={"hair":avatar["hair"],"shirt":avatar["shirt"]}
        if not isinstance(data.get("connected",False),bool): raise ValueError("invalid presence")
        selected["connected"]=data.get("connected",False)
        bag = data.get("bag", [])
        label = data.get("command_label","")
        if not isinstance(bag,list) or not isinstance(label,str):
            raise ValueError("invalid spectator data")
        selected["bag"] = [item for item in ITEMS if item in bag]
        selected["command_label"] = public_command(label[:100])
        selected["command_active"] = data.get("command_active") is True
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
            self.db.execute("INSERT INTO scores VALUES (?,?,?) ON CONFLICT(slot) DO UPDATE SET payload=excluded.payload, updated=excluded.updated",
                            (slot,json.dumps(selected),time.time()))
            self.db.commit()

    def rows(self):
        with self.lock:
            records=self.db.execute("SELECT slot,payload,updated FROM scores").fetchall()
        rows=[dict(json.loads(payload),slot=slot,updated=updated) for slot,payload,updated in records]
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
            elif self.path=="/api/scores": self.reply(200,{"players":board.rows(),"server_time":time.time()})
            else: self.reply(404,{"error":"not found"})

        def do_POST(self):
            if self.path!="/api/score": return self.reply(404,{"error":"not found"})
            slot=board.authenticate(self.headers.get("Authorization","").removeprefix("Bearer "))
            if not slot: return self.reply(401,{"error":"unauthorized"})
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 1<=size<=16384: return self.reply(413,{"error":"payload size"})
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
                overlay(canvas,boss_frame(canvas.w//2,canvas.h,tick),canvas.w//2,0)
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
    label=row.get("command_label") or "bereit"
    line(last,("▶ " if live and row.get("command_active") else "$ ")+label,2)


def paint_board(screen,rows,now,page=0):
    screen.erase()
    h,w=screen.getmaxyx()
    if h<8 or w<18:
        put(screen,0,0,"LIVE-SCOREBOARD",2)
        return 1
    ordered=ranking(rows)
    live=[r for r in ordered if online(r,now)]
    offline=[r for r in ordered if not online(r,now)]
    groups=[g for g in (live,offline) if g]
    pages=[]
    for group in groups:
        cols,lines=grid_shape(len(group),w-1,h-2)
        step=cols*lines
        pages.extend(group[i:i+step] for i in range(0,len(group),step))
    page%=max(1,len(pages))
    marker=f"  ← {page+1}/{len(pages)} →" if len(pages)>1 else ""
    put(screen,0,1,fit(f"LIVE-SCOREBOARD   {len(live)} ONLINE"+marker,w-2),2,True)
    if not pages:
        put(screen,3,2,"Warte auf Spieler …",3)
        return 1
    visible=pages[page]
    if not online(visible[0],now): put(screen,1,1,"Zuletzt gespielt",3)
    cols,lines=grid_shape(len(visible),w-1,h-2)
    for i,row in enumerate(visible):
        gy,gx=divmod(i,cols)
        y=2+gy*(h-2)//lines; x=gx*(w-1)//cols
        tile(screen,row,y,x,2+(gy+1)*(h-2)//lines-y,(gx+1)*(w-1)//cols-x,now)
    return len(pages)


def board_hud(screen,url):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.keypad(True); screen.timeout(130)
    page=0; rows=[]; fetched=0; error=False
    while True:
        now=time.time()
        if now-fetched>=.4:
            try:
                with urllib.request.urlopen(url+"/api/scores",timeout=2) as response: rows=json.load(response)["players"]
                error=False
            except (OSError,ValueError,KeyError): error=True
            fetched=now
        pages=paint_board(screen,rows,now,page)
        if error: put(screen,1,1,"Verbinde …",6)
        screen.refresh()
        key=screen.getch()
        if key in (ord("q"),ord("Q"),27): return
        if key in (curses.KEY_RIGHT,ord("n")): page=(page+1)%pages
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
    server.serve_forever()


if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: pass
