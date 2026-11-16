"""Animated terminal HUD and a tiny depth-buffered 3D triangle renderer."""
import curses
import math
import textwrap
import time
import unicodedata

from .client import request
from .engine import AREAS

POSITIONS = {"dorf": (.18, .22), "wald": (.78, .22), "werkstatt": (.18, .76),
             "archiv": (.78, .76), "zitadelle": (.48, .48)}


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
    for i in range(max(1, w*h//90)):
        c.put((i*29+7) % w, (i*13+int(tick/4)) % h, "·", 3)
    nodes = {k: (int(x*(w-18))+8, int(y*(h-3))+1) for k, (x, y) in POSITIONS.items()}
    center = nodes["zitadelle"]
    for name, node in nodes.items():
        if name != "zitadelle":
            c.line(*node, *center, "·", 3)
    for name, (x, y) in nodes.items():
        color = 2 if name == s["area"] else 4 if name in s["visited"] else 1
        label = name + "/"
        c.put(x-len(label)//2-2, y, "[ " + label + " ]", color)
        if h >= 13:
            c.put(x-2, y-1, {"dorf": " /\\ ", "wald": "/▲\\", "werkstatt": "[⚙]", "archiv": "[≡]", "zitadelle": "♜ ♜"}[name], color)
    px, py = position
    c.put(round(px*(w-18))+8, int(py*(h-3)), "@", 5)
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
    palette = [252, 86, 60, 120, 221, 204]
    for i, color in enumerate(palette, 1):
        curses.init_pair(i, color if curses.COLORS >= 256 else [7,6,4,2,3,1][i-1], -1)


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


def hud(screen):
    colors()
    try: curses.curs_set(0)
    except curses.error: pass
    screen.nodelay(True)
    position = POSITIONS["dorf"]
    origin = position
    target = position
    travel_start = time.monotonic()
    last_fetch=0
    state=None
    while True:
        now = time.monotonic()
        key = screen.getch()
        if key in (ord("q"), 27): return
        if now-last_fetch > .35:
            try:
                state=request()["state"]
                new_target=POSITIONS.get(state["area"],POSITIONS["dorf"])
                if new_target != target:
                    origin, target, travel_start=position,new_target,now
            except (OSError,ValueError): pass
            last_fetch=now
        screen.erase()
        h,w=screen.getmaxyx()
        if not state:
            put(screen,1,2,"Verbinde mit dem Nordpol …",2)
        elif h < 10 or w < 50:
            put(screen,0,0,"FROSTBYTE · Terminal vergroessern (ideal 100×38)",2)
            put(screen,1,0,f"HP {state['hp']} | Boss {state['boss_hp']} | {state['score']} Punkte",5)
        else:
            elapsed=state["elapsed"]
            put(screen,0,2,"❄  F R O S T B Y T E",2,True)
            put(screen,0,max(27,w-44),f"{state['name'][:20]}  /  {state['mode'].upper()}",1)
            put(screen,1,2,f"DU     {bar(state['hp'],100)} {state['hp']:3}/100",4)
            put(screen,1,max(44,w-36),f"{state['score']:4} PTS  ·  {elapsed:07.2f}s",5)
            if state["area"]=="zitadelle":
                put(screen,2,2,f"BOSS   {bar(state['boss_hp'],240)} {state['boss_hp']:3}/240",6)
            else:
                put(screen,2,2,fit("RUCKSACK  "+(", ".join(state.get("bag",[])) or "leer"),max(25,w-44)),2)
            label={"playing":"SPIELT", "won":"GEWONNEN", "lost":"VERLOREN"}[state["status"]]
            put(screen,2,max(44,w-36),f"{len(state['visited'])}/5 ORTE  ·  {label}",3)
            progress=min(1,(now-travel_start)/1.25)
            position=tuple(origin[i]+(target[i]-origin[i])*progress for i in (0,1))
            scene_h=max(3,h-7)
            if state["status"] == "won":
                scene = Canvas(w-4,scene_h)
                scene.put(max(0,(w-28)//2), max(0,scene_h//2-1),"★ WEIHNACHTEN GERETTET ★",5)
                scene.put(max(0,(w-36)//2), max(1,scene_h//2+1),f"{state['score']} Punkte  /  {state['elapsed']:.2f}s  /  SIEG",4)
            elif state["area"] == "zitadelle":
                scene=boss_frame(w-4,scene_h,now,state["status"]=="won")
            else:
                scene=world_frame(w-4,scene_h,state,position,now)
            for y,row in enumerate(scene.cells):
                for x,(char,color) in enumerate(row):
                    if char != " ": put(screen,y+3,x+2,char,color)
            message=state["message"]
            lines=textwrap.wrap(message,max(20,w-6))[:2]
            for i,line in enumerate(lines): put(screen,h-3+i,2,line,5 if state["status"]=="won" else 1)
            put(screen,h-1,2,next_hint(state),2)
        screen.refresh()
        time.sleep(.08)


if __name__ == "__main__":
    try: curses.wrapper(hud)
    except KeyboardInterrupt: pass
