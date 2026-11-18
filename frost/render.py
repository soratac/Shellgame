"""Animated terminal HUD and a tiny depth-buffered 3D triangle renderer."""
import curses
from functools import lru_cache
import math
import textwrap
import time
import unicodedata

from .client import request
from .trail import BOSS_IP, hiding_place, discovered
from .engine import AREAS, route_count
from .avatar import HAIR, SHIRTS

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
            "  @ = du  |  cd ~/welt/ORT  |  " + trail_hint(s) + "\n")


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


@lru_cache(maxsize=96)
def landmark(place,w,h):
    snow,wood,pine,window=1,7,4,5
    if place=="wald":
        mesh=[]
        for x,z,height in [(-.65,0,1.4),(.55,.25,1.7),(0,-.5,1.1)]:
            mesh+=cube(x,-.5,z,.17,1,.17,wood)
            mesh+=cone(x,-.65,z,.60,height,pine)+cone(x,.12,z,.40,height*.62,snow)
    elif place=="zitadelle":
        mesh=cube(0,-.30,0,1.6,1,1.1,2)
        for x in (-.8,.8):
            mesh+=cube(x,0,0,.47,1.6,.65,2)+cone(x,.82,0,.44,.65,snow)
        mesh+=cube(0,-.54,-.57,.45,.68,.13,8)
    elif place=="archiv":
        mesh=cube(0,-.23,.1,1.9,1.05,1.0,9)+cube(0,.4,0,2.1,.22,1.35,snow)
        for x in (-.72,-.24,.24,.72): mesh+=cube(x,-.21,-.58,.16,1,.22,1)
    else:
        mesh=cube(0,-.25,0,1.65,1.0,1.15,wood)+cone(0,.24,0,1.27,.84,snow)
        for x in (-.52,.52): mesh+=cube(x,-.24,-.60,.28,.35,.08,window)
        if place=="werkstatt": mesh+=cube(.68,.62,.18,.34,1.36,.34,6)
        else: mesh+=cube(0,-.46,-.62,.26,.55,.1,6)
    return project_mesh(w,h,-.48,mesh)


def world_frame(w,h,s,position,tick):
    c=Canvas(w,h)
    def point(pos):
        return round(5+pos[0]*max(1,w-12)),round(1+pos[1]*max(1,h-5))
    coords={name:point(pos) for name,pos in POSITIONS.items()}
    for key,pos in coords.items():
        if key!="zitadelle": c.line(*pos,*coords["zitadelle"],"·",3)
    wh=max(3,min(8,h//3))
    for name,(x,y) in coords.items():
        overlay(c,landmark(name,14,wh),x-7,y-wh//2)
        label=name+(" ✧" if name==hiding_place(s) and not discovered(s) else "")
        c.put(x-len(name)//2,min(h-1,y+wh//2),label,2 if name==s["area"] else 1)
    x,y=point(position)
    hh=max(4,min(10,h//2))
    left=max(0,min(w-13,x-15 if x<w*.35 else x+3))
    top=max(0,min(h-hh-1,y-hh//2))
    overlay(c,hero_frame(13,hh,tick,s.get("avatar")),left,top)
    c.put(left+5,top+hh,"DU",5)
    event=(s.get("events") or [None])[-1]
    if event:
        age=time.time()-event["at"]
        if 0<=age<1.5:
            if event.get("kind")=="bag":
                c.put(left, max(0,top+2-int(age*2)), "+"+event.get("spell",""),5)
            else: attack_effect(c,event,age,(left+4,top+hh//2),(x,max(1,y-1)))
    return c


def smooth_life(value,before,progress):
    t=max(0,min(1,progress))
    return before+(value-before)*t*t*(3-2*t)


def life_meter(value,maximum,size):
    fill=round(max(0,min(1,value/maximum))*size*8)
    full,part=divmod(fill,8)
    track="█"*full+("▏▎▍▌▋▊▉"[part-1] if part else "")
    return "❨"+track+"░"*(size-len(track))+"❩ "+f"{round(value)}/{maximum}"


def combat_frame(w,h,s,tick):
    c=Canvas(w,h)
    event=(s.get("events") or [None])[-1]
    age=time.time()-event["at"] if event else 99
    active=event is not None and 0<=age<1.5
    hp,bhp=s["hp"],s["boss_hp"]
    if active:
        hp=smooth_life(hp,event["hp_before"],(age-(.12 if event["hurt"]<0 else .55))/.7)
        bhp=smooth_life(bhp,event["boss_before"],(age-.13)/.72)
    right=w//2+2
    meter=max(3,min(28,w//2-12))
    c.put(1,0,"GRINCH",4)
    c.put(1,1,life_meter(bhp,240,meter),6 if active and event["damage"] and age<.75 else 4)
    label=s["name"][:18]
    player_hp=life_meter(hp,100,meter)
    c.put(w-len(label),h-2,label,5)
    c.put(w-len(player_hp),h-1,player_hp,2 if active and event["hurt"]<0 else 6 if active and event["hurt"]>0 and age>.55 else 4)
    elapsed = max(0,time.time()-s.get("boss_entered_at",0))
    slide = max(0,1-elapsed/.65)
    bw,bheight = w//2-2,max(4,h-4)
    bx = right + round(slide*bw)
    hx = 1-round(slide*bw)
    b_hit = active and event["damage"]>0 and .28<age<.48
    p_hit = active and event["hurt"]>0 and .8<age<1.05
    overlay(c, boss_frame(bw,bheight,tick),bx+int(b_hit),0,6 if b_hit else None)
    overlay(c, hero_frame(bw,bheight,tick,s.get("avatar"),back=True),hx-int(p_hit),h-bheight,6 if p_hit else None)
    start,end = (w//4+3,h-3),(3*w//4-2,max(2,bheight//2))
    if active: attack_effect(c,event,age,start,end)
    return c


def attack_effect(c,event,age,start,end):
    def shot(progress,shape,color,dy=0):
        if 0<=progress<=1:
            x=round(start[0]+(end[0]-start[0])*progress)
            y=round(start[1]+(end[1]-start[1])*progress)
            c.put(x,y+dy,shape,color)
    if event and 0<=age<1.5:
        spell=event.get("spell","")
        kind=event.get("kind","")
        phase=min(1,age/.48)
        if age<.65:
            if spell=="schild":
                for dy in (-1,0,1): c.put(start[0]+round(phase*3),start[1]+dy,"❘",2)
            elif kind=="disable":
                c.put(end[0]-2,end[1]-1,("● ON","◐","○ OFF")[min(2,int(age*6))],6)
            elif kind=="unload":
                c.put(end[0]-3,end[1],("▣─▣","▣╱▣","·  ·")[min(2,int(age*6))],3)
            elif spell in ("kakao","beeren") and event["hurt"]<0:
                for i in range(3):
                    rise=round((age+i*.17)*4)
                    c.put(start[0]-2+i*2,max(0,start[1]-rise),"≈" if spell=="kakao" else "♥",5 if spell=="kakao" else 6)
            elif kind=="scan" or spell=="ping":
                radius=round(phase*4)
                c.put(start[0]-radius,start[1],"(",2)
                c.put(start[0]+radius,start[1],")",2)
        if event["damage"]>0:
            if kind=="ping" or spell=="ping":
                for i in range(4): shot((age-i*.13)/.38,"◉",2)
            elif spell=="frost":
                for dy in (-1,0,1): shot(age/.47,"❄",2,round(dy*math.sin(phase*math.pi)))
            elif spell=="stern":
                c.put(end[0],max(0,end[1]-round((1-phase)*6)),"★",5)
                if .3<age<.6: c.put(end[0]-2,end[1]+1,"· ✧ ·",1)
            elif kind=="attack":
                shot(age/.30,"╱━",1)
            else:
                shot(age/.44,"✦»",6,-round(2*math.sin(phase*math.pi)))
            if age>.25: c.put(end[0]+2,max(0,end[1]-2),f"-{event['damage']}",5)
        if event["hurt"]>0:
            strong=event["hurt"]>=12
            for dy in ((-1,0,1) if strong else (0,)):
                shot(1-(age-.6)/.35,"❄" if strong else "«✹",2 if strong else 6,dy)
            if age>.85: c.put(start[0]-4,max(2,start[1]-2),f"-{event['hurt']}",6)
        if event["hurt"]<0: c.put(start[0]-3,start[1]-1,f"+{-event['hurt']}",4)


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
    mesh = cube(0,-.57,0,1.36,.95,.85,6)  # red winter coat, fur cuff and belt
    mesh += cube(0,-.98,0,1.48,.18,.92,1)+cube(0,-.7,0,1.43,.15,.91,8)
    mesh += cube(0,-.69,-.48,.25,.17,.1,5)
    for side in (-1,1):
        mesh+=cube(side*.42,-1.29,0,.33,.51,.36,4)
        mesh+=cube(side*.44,-1.58,-.14,.43,.20,.65,7)
        mesh+=cube(side*.82,-.46,0,.28,.67,.48,6)+cube(side*.84,-.82,0,.32,.16,.50,1)
        mesh+=cube(side*.84,-.96,-.06,.27,.23,.36,4)
    mesh += cube(0,.25,-.05,1.2,1.1,1.0,4)  # green face
    # Upturned mouth and full cheeks make the Grinch grin in profile too.
    mesh += cube(0,.03,-.59,.55,.09,.12,8)
    for sign in (-1,1):
        mesh += cube(sign*.33,.12,-.60,.18,.12,.13,8)
        mesh += cube(sign*.52,.22,-.45,.27,.27,.32,4)
    mesh += cube(0,.26,-.65,.24,.19,.23,4)
    for x in (-.32,.32):
        mesh += cube(x,.42,-.59,.22,.13,.08,5)  # amber eyes
        mesh += cube(x,.56,-.58,.32,.09,.10,8)  # dark brows
    mesh += cone(0,.83,.03,.65,.85,6)  # Santa hat
    mesh += cube(0,.82,.03,1.25,.13,1.05,1)
    mesh += cube(0,1.68,.03,.18,.18,.18,1)
    mesh += cube(0,-.32,-.45,.15,.36,.1,1)
    return mesh


MESH = boss_mesh()


def overlay(canvas, layer, left, top, flash=None):
    for y,row in enumerate(layer.cells):
        for x,(char,color) in enumerate(row):
            if char != " ": canvas.put(left+x,top+y,char,flash or color)


@lru_cache(maxsize=32)
def hero_mesh(hair,shirt):
    # Boots, mitts, backpack and a pointed winter cap give the silhouette depth.
    mesh = cube(0,-.22,0,1.05,.93,.60,shirt)
    mesh += cube(0,.66,-.04,.81,.78,.72,10)
    mesh += cube(0,.98,0,.91,.27,.80,hair)
    mesh += cube(0,.67,.32,.85,.55,.24,hair)
    for x,y,z,size in [(-.33,1.10,-.04,.40),(-.12,1.24,-.12,.47),(.17,1.17,.04,.46),(.36,.96,-.17,.30)]:
        mesh+=cone(x,y-.18,z,size*.66,size,hair)
    mesh+=cube(-.22,.87,-.40,.41,.21,.18,hair)
    for side in (-1,1): mesh+=cube(side*.40,.76,-.09,.17,.42,.54,hair)
    mesh += cube(0,.20,-.04,1.06,.16,.73,5)
    mesh += cube(0,-.18,.43,.62,.73,.42,7)
    mesh += cube(0,-.04,.66,.55,.13,.07,5)
    for side in (-1,1):
        mesh += cube(side*.64,-.17,0,.25,.70,.40,shirt)
        mesh += cube(side*.64,-.56,-.06,.27,.23,.38,10)
        mesh += cube(side*.29,-.90,0,.39,.52,.44,8)
        mesh += cube(side*.29,-1.20,-.10,.43,.22,.66,7)
        mesh += cube(side*.21,.72,-.42,.11,.12,.07,8)
    return mesh


def hero_frame(w,h,tick,avatar,back=False):
    avatar=avatar or {}
    mesh=hero_mesh(HAIR.get(avatar.get("hair"),7), SHIRTS.get(avatar.get("shirt"),4))
    angle=(2.5 if back else -.38)+math.sin(tick*1.6)*.15
    return project_mesh(w,h,angle,mesh)


def boss_frame(w,h,tick,won=False):
    angle = .38+math.sin(tick*.8)*.38 if not won else tick*.5
    return project_mesh(w,h,angle,MESH,extent=3.9)


def project_mesh(w,h,angle,mesh,extent=3.1):
    c = Canvas(w,h)
    ca, sa = math.cos(angle), math.sin(angle)
    scale = max(2, min(h/extent, w/7.2))

    def project(v):
        x,y,z = v
        x,z = x*ca+z*sa, -x*sa+z*ca
        depth = z + 5
        return (w/2+x*scale*8/depth, h*.56-y*scale*4/depth, depth)

    for a,b,d,color in mesh:
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


def trail_hint(s):
    if discovered(s): return f"grinch · {BOSS_IP} · ssh grinch"
    if "ping" not in s["bag"]: return "Echo: mv ~/welt/dorf/ping ~/rucksack/"
    return f"Spur: {hiding_place(s)} · ping grinch"


def next_hint(s):
    if s["status"]!="playing": return "Neue Runde: restart"
    if s["boss_started"]: return ""
    if not s["bag"] and s["area"]=="dorf": return "mv funke ping ~/rucksack/"
    return trail_hint(s)


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
    score=f"{state['score']} PTS"
    timer=f"{state['elapsed']:.1f}s"
    put(screen,0,(w-len(score))//2,score,5,True)
    put(screen,0,w-len(timer)-2,timer,1)
    fight=state.get("boss_started")
    bag_w=min(19,max(11,w//6))
    # Keep the right edge free for the fighter's life meter.
    sx=bag_w+2
    scene_w=w-sx-1
    scene_h=h-3
    inventory=state.get("bag_display",state.get("bag",[]))
    put(screen,2,1,"Rucksack",5,True)
    visible=max(1,h-4)
    offset=int(tick//2)%len(inventory) if len(inventory)>visible else 0
    for i,item in enumerate((inventory[offset:]+inventory[:offset])[:visible] or ["leer"]):
        put(screen,3+i,1,fit(item,bag_w-1),1)
    if fight:
        scene=combat_frame(scene_w,scene_h,state,tick)
    else:
        scene=world_frame(scene_w,scene_h,state,position or POSITIONS.get(state["area"],POSITIONS["dorf"]),tick)
        hp=state["hp"]
        event=(state.get("events") or [None])[-1]
        age=time.time()-event["at"] if event else 9
        if 0<=age<1.4: hp=smooth_life(hp,event["hp_before"],age/.78)
        health=life_meter(hp,100,min(15,w//7))
        put(screen,1,w-len(health)-1,health,2 if event and age<1 and event["hurt"]<0 else 4)
        put(screen,1,1,fit(next_hint(state),w-len(health)-4),3)
    for y,row in enumerate(scene.cells):
        for x,(char,color) in enumerate(row):
            if char!=" ": put(screen,y+2,x+sx,char,color)


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
