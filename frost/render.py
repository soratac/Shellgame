"""Animated terminal HUD and a tiny depth-buffered 3D triangle renderer."""
import curses
import math
import textwrap
import time
import unicodedata

from .client import request
from .engine import AREAS, route_count
from .avatar import sprite, HAIR, SHIRTS

POSITIONS = {"dorf": (.18, .18), "wald": (.80, .18), "werkstatt": (.18, .76),
             "archiv": (.80, .76), "zitadelle": (.49, .47)}


def static_map(s):
    def tag(name):
        return ("@ " if s["area"] == name else "  ") + name + "/"
    return ("\n   *  N O R D P O L  *\n\n"
            f"  [{tag('dorf'):20}]----------[{tag('wald'):20}]\n"
            "             \\                      /\n"
            f"                 [{tag('zitadelle')}]\n"
            "             /                      \\\n"
            f"  [{tag('werkstatt'):20}]----------[{tag('archiv'):20}]\n\n"
            "  @ = du  |  cd ~/welt/ORT  |  karte  |  hilfe\n")


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[(" ", 1) for _ in range(w)] for _ in range(h)]
        self.depth = [[float("inf")] * w for _ in range(h)]

    def put(self, x, y, value, color=1):
        if 0 <= y < self.h:
            for i, char in enumerate(value):
                if 0 <= x+i < self.w:
                    self.cells[y][x+i] = (char, color)

    def line(self, x0, y0, x1, y1, char="·", color=3):
        steps = max(abs(x1-x0), abs(y1-y0), 1)
        for i in range(steps+1):
            self.put(round(x0+(x1-x0)*i/steps), round(y0+(y1-y0)*i/steps), char, color)


def world_frame(w, h, s, position, tick):
    c = Canvas(w, h)
    sprite(c, 2, max(1,h//2-2), s.get("avatar"), pose=int(tick*3)%2)
    c.put(1, max(0,h-2), s["name"][:12], 5)
    left=17
    mw=max(20,w-left)
    nodes={"dorf":(.18,.18), "wald":(.80,.18), "werkstatt":(.18,.76),
           "archiv":(.80,.76), "zitadelle":(.49,.47)}
    coords={k:(left+int(x*(mw-13))+6, 2+int(y*max(1,h-6))) for k,(x,y) in nodes.items()}
    for k,point in coords.items():
        if k!="zitadelle": c.line(*point,*coords["zitadelle"], char="·",color=3)
    art={"dorf":["  /╲  /╲", " /__╲/__╲", " |▣ |▣ |"],
         "wald":["  ▲  ▲", " ▲▲▲▲▲▲", "  │  │"],
         "werkstatt":[" __┌┐__", "| ⚙  ⚙ |", "|__▣___|"],
         "archiv":[" ╭────╮", " │≡ ≡ │", " ╰─▣──╯"],
         "zitadelle":["╥  ╥  ╥", "╠══╩══╣", "╚══▣══╝"]}
    for name,(x,y) in coords.items():
        color=2 if name==s["area"] else 4 if name in s["visited"] else 1
        if h>=15:
            for i,line in enumerate(art[name]): c.put(x-4,y-2+i,line,color)
        c.put(x-len(name)//2-1,y+1,"["+name+"]",color)
        if name==s["area"]: c.put(x-1,y+2,"▼ DU",5)
    px=left+int(position[0]*(mw-13))+6
    py=2+int(position[1]*max(1,h-6))+3
    avatar=s.get("avatar",{})
    c.put(px,py,"●",HAIR.get(avatar.get("hair"),7))
    c.put(px-1,py+1,"╱█╲",SHIRTS.get(avatar.get("shirt"),4))
    return c


def combat_frame(w,h,s,tick):
    c=Canvas(w,h)
    event=(s.get("events") or [None])[-1]
    age=time.time()-event["at"] if event else 99
    active=event is not None and 0<=age<1.5
    hp,bhp=s["hp"],s["boss_hp"]
    if active:
        hp=round(event["hp_before"]+(hp-event["hp_before"])*max(0,min(1,(age-.65)/.5)))
        bhp=round(event["boss_before"]+(bhp-event["boss_before"])*max(0,min(1,(age-.15)/.5)))
    c.put(2,0,s["name"][:18],4)
    c.put(2,1,f"{bar(hp,100,14)} {hp}/100",6 if active and event["hurt"]>0 and age>.65 else 4)
    right=max(w//2+3,w-29)
    c.put(right,0,"KRAMPUS",6)
    c.put(right,1,f"{bar(bhp,240,14)} {bhp}/240",6)
    py=max(4,h//2-1)
    sprite(c, max(4,w//6),py,s.get("avatar"),pose=1 if active and age<.6 else int(tick*2)%2,
           hit=active and event["hurt"]>0 and .7<age<1.05)
    bw=max(12,w//3)
    boss=boss_frame(bw,max(5,h-4),tick)
    bx=w-bw-2
    for y,row in enumerate(boss.cells):
        for x,(char,color) in enumerate(row):
            if char!=" ": c.put(bx+x,y+3,char,6 if active and event["damage"]>0 and .25<age<.5 else color)
    c.line(2,h-1,w-3,h-1,"─",3)
    c.line(max(2,w//6-2),min(h-2,py+5),w//6+10,min(h-2,py+5),"▔",3)
    if active:
        start,end=w//6+8,bx+bw//2
        lane=max(5,h//2+1)
        if event["damage"]>0:
            x=round(start+(end-start)*min(1,age/.4))
            c.put(x,lane,"*»»" if age<.4 else "✦",2 if event["spell"]=="frost" else 5)
            if age>.25: c.put(end-2,max(3,lane-3-int(age*2)),f"-{event['damage']}",5)
        if event["hurt"]>0 and age>.6:
            x=round(end-(end-start)*min(1,(age-.6)/.35))
            c.put(x,lane,"«*",6)
            if age>.85: c.put(start-5,max(3,lane-3-int((age-.6)*2)),f"-{event['hurt']}",6)
        if event["hurt"]<0: c.put(start-5,max(3,py-2),f"+{-event['hurt']}",4)
        if event["spell"]=="schild": c.put(start-1,py,"◖",2)
    return c


def cube(cx, cy, cz, sx, sy, sz, color):
    v = [(cx+dx*sx/2, cy+dy*sy/2, cz+dz*sz/2) for dx,dy,dz in
         [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    return [(v[a],v[b],v[c],color) for a,b,c in
            [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
             (3,7,6),(3,6,2),(0,4,7),(0,7,3),(1,2,6),(1,6,5)]]


def cone(cx, cy, cz, radius, height, color):
    bottom = [(cx+math.cos(i*math.pi/3)*radius, cy, cz+math.sin(i*math.pi/3)*radius) for i in range(6)]
    return [(bottom[i], bottom[(i+1)%6], (cx,cy+height,cz), color) for i in range(6)]


def boss_mesh():
    mesh = cube(0,-.65,0,1.7,1.2,.9,6)  # red coat
    mesh += cube(0,.25,-.05,1.2,1.1,1.0,2)  # ice face
    mesh += cube(0,-.2,-.62,.65,.35,.16,1)  # silver beard
    for x in (-.32,.32):
        mesh += cube(x,.42,-.59,.22,.13,.08,5)  # amber eyes
        mesh += cone(x*2,.65,0,.23,.85,1)  # crystalline horns
    mesh += cone(0,.83,.03,.65,.85,6)  # Santa hat
    mesh += cube(0,.82,.03,1.25,.13,1.05,1)
    mesh += cube(0,1.68,.03,.18,.18,.18,1)
    mesh += cube(0,-.7,-.5,.15,1.0,.1,5)
    return mesh


MESH = boss_mesh()


def boss_frame(w, h, tick, won=False):
    c = Canvas(w,h)
    angle = math.sin(tick*.8)*.5 if not won else tick*.5
    ca, sa = math.cos(angle), math.sin(angle)
    scale = max(2, min(h/3.1, w/7.2))

    def project(v):
        x,y,z = v
        x,z = x*ca+z*sa, -x*sa+z*ca
        depth = z + 5
        return (w/2+x*scale*8/depth, h*.56-y*scale*4/depth, depth)

    for a,b,d,color in MESH:
        p,q,r = project(a), project(b), project(d)
        denominator = (q[1]-r[1])*(p[0]-r[0])+(r[0]-q[0])*(p[1]-r[1])
        if abs(denominator) < 0.001:
            continue
        edge1 = tuple(b[i]-a[i] for i in range(3))
        edge2 = tuple(d[i]-a[i] for i in range(3))
        normal = (edge1[1]*edge2[2]-edge1[2]*edge2[1], edge1[2]*edge2[0]-edge1[0]*edge2[2], edge1[0]*edge2[1]-edge1[1]*edge2[0])
        norm = math.sqrt(sum(x*x for x in normal)) or 1
        shade = abs((normal[0]*.4+normal[1]*.6-normal[2]*.7)/norm)
        char = "░▒▓█"[min(3, int(shade*3.5))]
        for y in range(max(0,int(min(p[1],q[1],r[1]))), min(h,int(max(p[1],q[1],r[1]))+1)):
            for x in range(max(0,int(min(p[0],q[0],r[0]))), min(w,int(max(p[0],q[0],r[0]))+1)):
                u = ((q[1]-r[1])*(x-r[0])+(r[0]-q[0])*(y-r[1]))/denominator
                v = ((r[1]-p[1])*(x-r[0])+(p[0]-r[0])*(y-r[1]))/denominator
                t = 1-u-v
                if min(u,v,t) >= 0:
                    z = 1/(u/p[2]+v/q[2]+t/r[2])
                    if z < c.depth[y][x]:
                        c.depth[y][x] = z
                        c.cells[y][x] = (char, color)
    # Snow and a perspective floor surround the depth-tested rotating model.
    for i in range(w//5):
        x=(i*31+3)%w
        y=(i*7+int(tick*2))%h
        if c.cells[y][x][0] == " ": c.put(x,y,"·",3)
    if w > 75:
        c.put(3, max(1,h//2-2), "KRAMPUS.EXE", 6)
        c.put(3, h//2, "FROST / DAEMON", 3)
        c.put(w-25,max(1,h//2-2),"WEIHNACHTSSTERN",5)
        c.put(w-25,h//2,"BEFREIT" if won else "STATUS: GEFANGEN",4 if won else 3)
    return c


def colors():
    curses.start_color()
    curses.use_default_colors()
    palette = [252, 86, 60, 120, 221, 204, 130, 240, 141, 223]
    for i, color in enumerate(palette, 1):
        curses.init_pair(i, color if curses.COLORS >= 256 else [7,6,4,2,3,1,3,0,5,3][i-1], -1)


def put(screen, y, x, text, color=1, bold=False):
    h,w = screen.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        try:
            screen.addnstr(y,x,text,max(0,w-x-1),curses.color_pair(color) | (curses.A_BOLD if bold else 0))
        except curses.error:
            pass


def cell_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def fit(text, width, right=False, center=False):
    text=str(text)
    result=""
    for char in text:
        if cell_width(result+char)>width: break
        result+=char
    gap=max(0,width-cell_width(result))
    if center: return " "*(gap//2)+result+" "*(gap-gap//2)
    return " "*gap+result if right else result+" "*gap


def box(screen, y, x, height, width, color=3):
    if height<2 or width<2: return
    put(screen,y,x,"╭"+"─"*(width-2)+"╮",color)
    put(screen,y+height-1,x,"╰"+"─"*(width-2)+"╯",color)
    for row in range(y+1,y+height-1):
        put(screen,row,x,"│",color)
        put(screen,row,x+width-1,"│",color)


def next_hint(s):
    if s["status"]=="won": return "Gewonnen! Noch eine Runde: neustart"
    if s["status"]=="lost": return "Neuer Versuch: neustart"
    if not s.get("bag") and not s["spells"]: return "MITNEHMEN  cp ~/welt/dorf/funke ~/rucksack/"
    if s["area"]=="zitadelle": return "ANGRIFF  ~/rucksack/funke    |    Heilung: ~/rucksack/kakao"
    next_area={"dorf":"wald", "wald":"werkstatt", "werkstatt":"archiv", "archiv":"zitadelle"}.get(s["area"],"dorf")
    return f"MITNEHMEN  cp DATEI ~/rucksack/    |    WEITER  cd ~/welt/{next_area}"


def bar(value, maximum, size=16):
    n = round(size*value/maximum)
    return "━"*n + "·"*(size-n)


def paint(screen,state,tick,position=None):
    h,w=screen.getmaxyx()
    screen.erase()
    if not state:
        put(screen,1,2,"Verbinde …",2); return
    if h<10 or w<50:
        put(screen,0,1,"FROSTBYTE · Terminal vergroessern",2)
        put(screen,2,1,f"Du {state['hp']}/100   Boss {state['boss_hp']}/240",4); return
    put(screen,0,2,"❄ FROSTBYTE",2,True)
    put(screen,0,max(20,w-31),f"{state['score']} PTS  ·  {state['elapsed']:.1f}s",5)
    scene_h=h-4
    if state.get("boss_started"):
        scene=combat_frame(w-4,scene_h,state,tick)
    else:
        scene=world_frame(w-4,scene_h,state,position or POSITIONS.get(state["area"],POSITIONS["dorf"]),tick)
        put(screen,1,2,f"{bar(state['hp'],100,12)} {state['hp']}/100   ·   Orte {min(3,route_count(state))}/3",4)
    for y,row in enumerate(scene.cells):
        for x,(char,color) in enumerate(row):
            if char!=" ": put(screen,y+2,x+2,char,color)
    put(screen,h-1,2,next_hint(state),2)


def hud(screen):
    colors()
    screen.nodelay(True)
    while True:
        paint(screen,request()["state"],time.monotonic())
        screen.refresh()
        if screen.getch() in (ord("q"),27): return
        time.sleep(.1)


if __name__ == "__main__":
    try: curses.wrapper(hud)
    except KeyboardInterrupt: pass
