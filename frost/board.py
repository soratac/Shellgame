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

from .render import colors, put, box, fit

VIEWS = [(None, "PUNKTE"), ("normal:classic", "ABENTEUER"), ("normal:loop", "ABENTEUER / LOOP"),
         ("speedrun:classic", "SPEEDRUN"), ("speedrun:loop", "SPEEDRUN / LOOP")]


def ranking(rows, view=0):
    category = VIEWS[view][0]
    if category:
        return sorted((row for row in rows if category in row["bests"]),
                      key=lambda r:(r["bests"][category], -r["score"], r["slot"]))
    return sorted(rows,key=lambda r:(-r["score"], 0 if r["status"]=="won" else 1,
                                    r["elapsed"] if r["status"]=="won" else float("inf"), r["slot"]))


def duration(seconds):
    minutes, seconds = divmod(max(0, seconds),60)
    hours, minutes = divmod(int(minutes),60)
    return f"{hours:d}:{minutes:02d}:{seconds:05.2f}" if hours else f"{minutes:02d}:{seconds:05.2f}"


def columns(width):
    # Each column has an exact terminal-cell width, including wide player names.
    if width >= 96:
        return [("rank",4),("name",20),("score",7),("hp",5),("boss",6),("time",11),("status",10),("area",12)]
    if width >= 74:
        return [("rank",3),("name",18),("score",6),("hp",4),("time",10),("status",10)]
    return [("rank",3),("name",max(8,min(14,width-37))),("score",6),("time",9)]


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
        return next((slot for slot,value in self.tokens.items() if hmac.compare_digest(value,token)),None)

    def update(self, slot, data):
        if not isinstance(data,dict) or not re.fullmatch(r"[\w -]{2,20}",data.get("name","")):
            raise ValueError("invalid name")
        for field in ("hp","boss_hp","score","elapsed","started"):
            value=data.get(field)
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:
                raise ValueError("invalid numeric field")
        if data["hp"]>100 or data["boss_hp"]>240 or data["score"]>10000:
            raise ValueError("out of bounds")
        if data.get("status") not in ("playing","won","lost") or data.get("mode") not in ("normal","speedrun"):
            raise ValueError("invalid status")
        bests=data.get("bests",{})
        if not isinstance(bests,dict) or len(bests)>4:
            raise ValueError("invalid records")
        for key,value in bests.items():
            if key not in {"normal:classic","normal:loop","speedrun:classic","speedrun:loop"} or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError("invalid record")
        selected={k:data.get(k) for k in ("name","hp","boss_hp","score","elapsed","started","status","mode","bests","method")}
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


def board_hud(screen,url):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.timeout(800)
    page=0
    view=0
    while True:
        screen.erase()
        h,w=screen.getmaxyx()
        box(screen,0,1,h-1,w-2,3)
        put(screen,1,3,"❄  FROSTBYTE  /  LIVE-SCOREBOARD",2,True)
        put(screen,2,3,"1 Punkte   2 Abenteuer   3 Abenteuer/Loop   4 Speedrun   5 Speedrun/Loop",3)
        try:
            with urllib.request.urlopen(url+"/api/scores",timeout=2) as response: payload=json.load(response)
            all_rows=payload["players"]
            rows=ranking(all_rows,view)
            now=payload["server_time"]
            criterion="Punkte absteigend" if view==0 else "Beste Zeit aufsteigend"
            put(screen,4,3,f"{VIEWS[view][1]}  ·  {criterion}",5,True)
            layout=columns(w-8) if view==0 else [("rank",4),("name",min(24,max(10,w-40))),("time",11),("status",10)]
            header=table_line(dict(rank="#",name="SPIELER",score="PUNKTE",hp="HP",boss="BOSS",time="ZEIT",status="STATUS",area="ORT"),layout)
            put(screen,6,3,header,2,True)
            put(screen,7,3,"─"*min(w-7,len(header)),3)
            per_page=max(1,h-13)
            pages=max(1,math.ceil(len(rows)/per_page))
            page%=pages
            for index,row in enumerate(rows[page*per_page:(page+1)*per_page],page*per_page+1):
                y=8+(index-1)%per_page
                category=VIEWS[view][0]
                elapsed=row["bests"][category] if category else max(0,now-row["started"]) if row["status"]=="playing" else row["elapsed"]
                online=now-row["updated"]<15
                status="REKORD" if category else {"won":"GEWONNEN","lost":"VERLOREN","playing":"SPIELT" if online else "OFFLINE"}[row["status"]]
                line=table_line(dict(rank=index,name=row["name"],score=row["score"],hp=row["hp"],boss=row["boss_hp"],time=duration(elapsed),status=status,area=row["area"]),layout)
                put(screen,y,3,line,4 if row["status"]=="won" else 1 if online else 3)
            if not rows: put(screen,9,3,"Noch keine Spieler." if view==0 else "Noch keine Bestzeit in dieser Kategorie.",1)
            put(screen,h-4,3,f"{len(all_rows)} Spieler  ·  {sum(r['status']=='won' for r in all_rows)} Siege  ·  Seite {page+1}/{pages}",3)
            put(screen,h-3,3,"1–5 Ansicht wechseln   ·   ←/→ Blaettern   ·   Q Schliessen",2)
        except (OSError,ValueError,KeyError):
            put(screen,6,3,"Verbindung zum Scoreboard wird wiederhergestellt …",6)
        screen.refresh()
        key=screen.getch()
        if key in (ord("q"),ord("Q"),27): return
        if key in (curses.KEY_RIGHT,ord("n")): page+=1
        if key in (curses.KEY_LEFT,ord("p")): page=max(0,page-1)
        if key in range(ord("1"),ord("6")):
            view=key-ord("1")
            page=0


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
