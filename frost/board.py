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
from .avatar import DEFAULT, HAIR, SHIRTS, sprite
from .records import bests as merge_bests, LEGACY_KEYS

VIEWS = ["PUNKTE", "BESTZEIT"]


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


def spotlight(screen,y,x,width,height,row,now):
    box(screen,y,x,height,width,3)
    put(screen,y+1,x+2,fit(row["name"],width-4),5,True)
    live=online(row,now)
    put(screen,y+2,x+2,"● ONLINE" if live else "○ OFFLINE",4 if live else 3)
    canvas=Canvas(width-4,7)
    event=(row.get("events") or [{}])[-1]
    impact=live and 0<=now-event.get("at",0)<1.5
    overlay(canvas,hero_frame(14,7,now if live else 0,row.get("avatar")),0,0,
            6 if impact and event.get("hurt",0)>0 else None)
    if row["area"]=="zitadelle":
        boss=boss_frame(12,7,now)
        for cy,line in enumerate(boss.cells):
            for cx,(char,color) in enumerate(line):
                if char!=" ": canvas.put(width-18+cx,cy,char,color)
        if impact:
            canvas.put(12,2,"*→" if event.get("damage",0) else "←*",5)
            canvas.put(12,0,f"-{event.get('damage',0)}",5)
    else:
        canvas.put(13,2,{"dorf":"⌂", "wald":"▲ ▲", "werkstatt":"⚙", "archiv":"≡"}.get(row["area"],"·"),2)
    for cy,line in enumerate(canvas.cells):
        for cx,(char,color) in enumerate(line):
            if char!=" ": put(screen,y+3+cy,x+2+cx,char,color)
    put(screen,y+11,x+2,f"DU    {bar(row['hp'],100,10)} {row['hp']}",4)
    put(screen,y+13,x+2,f"BOSS  {bar(row['boss_hp'],240,10)} {row['boss_hp']}",6)
    put(screen,y+15,x+2,row["area"].upper(),2)
    status={"playing":"Unterwegs", "won":"Weihnachten gerettet!", "lost":"Neuer Versuch?"}[row["status"]]
    put(screen,y+16,x+2,status,4 if row["status"]=="won" else 1)
    record=merge_bests(row.get("bests"))
    put(screen,y+18,x+2,"Bestzeit: "+(duration(record["best"]) if record else "—"),5)


def paint_board(screen,rows,now,view=0,page=0,selected=None):
    screen.erase()
    h,w=screen.getmaxyx()
    if w<44 or h<15:
        put(screen,1,1,"LIVE-SCOREBOARD · Terminal vergroessern",2)
        return 1
    box(screen,0,1,h-1,w-2,3)
    put(screen,1,3,"❄ FROSTBYTE / LIVE-SCOREBOARD",2,True)
    put(screen,2,3,f"{len(rows)} HELDEN   ·   {sum(online(r,now) for r in rows)} ONLINE   ·   {sum(r['status']=='won' for r in rows)} SIEGE",3)
    ordered=ranking(rows,view)
    details=w>=110 and h>=28
    available=w-45 if details else w-8
    layout=columns(available)
    put(screen,4,3,"[ PUNKTE ]   Bestzeit" if view==0 else "Punkte   [ BESTZEIT ]",5,True)
    header=table_line(dict(rank="#",avatar="",name="SPIELER",score="PUNKTE",time="ZEIT" if view==0 else "BESTZEIT",status="STATUS",area="ORT"),layout)
    put(screen,6,3,header,2,True)
    put(screen,7,3,"─"*min(available,w-7),3)
    per_page=max(1,h-12)
    pages=max(1,math.ceil(len(ordered)/per_page)); page%=pages
    for index,row in enumerate(ordered[page*per_page:(page+1)*per_page],page*per_page+1):
        y=8+(index-1)%per_page
        elapsed=merge_bests(row.get("bests"))["best"] if view else max(0,now-row["started"]) if row["status"]=="playing" else row["elapsed"]
        live=online(row,now)
        status={"won":"SIEG", "lost":"VERLOREN", "playing":"SPIELT" if live else "OFFLINE"}[row["status"]]
        values=dict(rank=index,avatar="●▰",name=row["name"],score=row["score"],time=duration(elapsed),status=status,area=row["area"])
        put(screen,y,3,table_line(values,layout),4 if row["status"]=="won" else 1 if live else 3,row["slot"]==selected)
        avatar=row.get("avatar",DEFAULT)
        ax=3+layout[0][1]+3
        put(screen,y,ax,"●",HAIR.get(avatar.get("hair"),7))
        put(screen,y,ax+1,"▰",SHIRTS.get(avatar.get("shirt"),4))
    if not ordered: put(screen,9,3,"Noch keine Bestzeit." if view else "Warte auf die ersten Helden …",1)
    if details and ordered:
        focus=next((r for r in ordered if r["slot"]==selected),ordered[page*per_page])
        spotlight(screen,4,w-37,34,h-8,focus,now)
    put(screen,h-3,3,f"1 Punkte · 2 Bestzeit · ↑↓ Charakter · ←→ Seite {page+1}/{pages} · Q Ende",2)
    return pages


def board_hud(screen,url):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.keypad(True); screen.timeout(120)
    page=view=0; selected=None; rows=[]; fetched=0; error=False
    while True:
        now=time.time()
        if now-fetched>=.8:
            try:
                with urllib.request.urlopen(url+"/api/scores",timeout=2) as response: payload=json.load(response)
                rows=payload["players"]; error=False
            except (OSError,ValueError,KeyError): error=True
            fetched=now
        ordered=ranking(rows,view)
        if ordered and selected not in [r["slot"] for r in ordered]: selected=ordered[0]["slot"]
        pages=paint_board(screen,rows,now,view,page,selected)
        if error: put(screen,3,3,"Verbindung wird wiederhergestellt …",6)
        screen.refresh()
        key=screen.getch()
        if key in (ord("q"),ord("Q"),27): return
        if key in (curses.KEY_RIGHT,ord("n")): page=(page+1)%pages
        if key in (curses.KEY_LEFT,ord("p")): page=(page-1)%pages
        if key in (curses.KEY_DOWN,curses.KEY_UP) and ordered:
            index=next((i for i,r in enumerate(ordered) if r["slot"]==selected),0)
            index=(index+(1 if key==curses.KEY_DOWN else -1))%len(ordered)
            selected=ordered[index]["slot"]; page=index//max(1,screen.getmaxyx()[0]-12)
        if key in (ord("1"),ord("2"),9):
            view=(1-view) if key==9 else key-ord("1"); page=0
        if key in (curses.KEY_RIGHT,curses.KEY_LEFT,ord("n"),ord("p")) and ordered:
            selected=ordered[min(len(ordered)-1,page*max(1,screen.getmaxyx()[0]-12))]["slot"]


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
