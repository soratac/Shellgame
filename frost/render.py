"""Animated terminal HUD and a tiny depth-buffered 3D triangle renderer."""
import curses
from functools import lru_cache
import math
import textwrap
import time
import unicodedata

from .client import request
from .trail import BOSS_IP, hiding_place, discovered
from .engine import AREAS
from .avatar import HAIR, SHIRTS
from .items import BAG_ICONS, bag_count

POSITIONS = {"zitadelle": (.50,.05), "wald": (.13,.39), "archiv": (.86,.39),
             "dorf": (.28,.90), "werkstatt": (.71,.90)}
PATHS = (("dorf","wald"), ("dorf","werkstatt"), ("werkstatt","archiv"),
         ("wald","zitadelle"), ("archiv","zitadelle"))


def static_map(s):
    def tag(name):
        return ("@ " if s["area"] == name else "") + name + "/"
    return ("\n"+tag("zitadelle").center(44)+"\n"
            + "           ╱                   ╲\n"
            + f"  {tag('wald'):<23} {tag('archiv')}\n"
            + "        ╲                     ╱\n"
            + f"       {tag('dorf')} ───── {tag('werkstatt')}\n\n"
            + "  @ = du   ✧ " + trail_hint(s) + "\n")


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


def world_frame(w,h,s,position,tick,walking=False):
    c=Canvas(w,h)
    def point(pos):
        return round(5+pos[0]*max(1,w-12)),round(1+pos[1]*max(1,h-5))
    coords={name:point(pos) for name,pos in POSITIONS.items()}
    for a,b in PATHS:
        c.line(*coords[a],*coords[b],"·",3)
    wh=max(3,min(7,h//4))
    marked=None if discovered(s) else hiding_place(s)
    for name,(x,y) in coords.items():
        if h<12:
            roof,front,tint={"dorf":("⌂ ⌂","▥ ▥",7), "werkstatt":("▥╱▔╲","▥▦▥",6),
                "archiv":("╱▔▔╲","╫╫╫╫",9), "wald":("▲ ▲","╱▲╲",4),
                "zitadelle":("╥╤╥","▥╫▥",2)}[name]
            c.put(x-2,y-1,roof,tint)
            c.put(x-2,y,front,tint)
        else:
            overlay(c,landmark(name,14,wh),x-7,y-wh//2)
        if name==marked:
            # A moving pair of golden footprints leads to the current search area.
            c.put(x+3,y-1,"✧" if int(tick*3)%2 else "✦",5)
        label=name+(" ✧" if name==marked else "")
        c.put(max(0,min(w-len(label)-2,x-len(label)//2-1)),min(h-1,y+wh//2)," "+label+" ",
              5 if name==marked else 2 if name==s["area"] else 1)
    x,y=point(position)
    hh=max(4,min(9,h//2))
    left=max(0,min(w-13,x+3 if x<w*.5 else x-15))
    top=max(0,min(h-hh-1,y-hh//2))
    overlay(c,hero_frame(13,hh,tick,s.get("avatar"),walking=walking),left,top)
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


def life_meter(value,maximum,size,trail=None):
    fill=round(max(0,min(1,value/maximum))*size*8)
    full,part=divmod(fill,8)
    track="█"*full+("▏▎▍▌▋▊▉"[part-1] if part else "")
    ghost=max(0,min(size,round((trail or 0)*size/maximum))-len(track))
    return "❨"+track+"▒"*ghost+"░"*(size-len(track)-ghost)+"❩ "+f"{round(value)}/{maximum}"


def winter_arena(c,tick):
    w,h=c.w,c.h
    horizon=max(2,h//2)
    # Aurora over a distant crenellated wall and two floating ice platforms.
    for x in range(1,w-1,2):
        y=round(h*.21+math.sin(x*.10+tick*.5)*h*.08)
        c.put(x,y,"╌",9 if (x//10)%3==0 else 3)
    if h>=10 and w>=40:
        # Ice watchtowers and their lit arrow slits behind the duelling floor.
        for x in (w//12, w//2-3, w-8):
            c.put(x,horizon-2,"╥╤╥",3)
            c.put(x,horizon-1,"│▯│",3)
            c.put(x+1,horizon-1,"▯",5)
            c.put(x,horizon,"╵ ╵",3)
    for x in range(0,w,5):
        c.put(x,horizon+int(abs(math.sin(x*.17))*2),"╱╲",3)
    for i in range(max(4,w//6)):
        x=(i*17+int(tick*(1+i%2)))%w
        y=(i*13+int(tick*(1+i%3)))%max(1,h-2)
        c.put(x,y,"·" if i%4 else "✧",3)
    for cx,cy,r in ((w//4,h-2,w//6),(3*w//4,max(3,h*2//3),w//7)):
        c.put(cx-r,cy,"╭"+"─"*(2*r-1)+"╮",2)
        c.put(cx-r+2,cy+1,"╲"+"▔"*max(0,2*r-5)+"╱",3)


def combat_frame(w,h,s,tick):
    c=Canvas(w,h)
    winter_arena(c,tick)
    event=(s.get("events") or [None])[-1]
    age=time.time()-event["at"] if event else 99
    active=event is not None and 0<=age<1.5
    hp,bhp=s["hp"],s["boss_hp"]
    if active:
        hp=smooth_life(hp,event["hp_before"],(age-(.12 if event["hurt"]<0 else .55))/.7)
        bhp=smooth_life(bhp,event["boss_before"],(age-.13)/.72)
    right=w//2+2
    meter=max(3,min(28,w//2-12))
    elapsed = max(0,time.time()-s.get("boss_entered_at",0))
    slide = max(0,1-elapsed/.65)
    bw,bheight = w//2-2,max(4,h-4)
    bx = right + round(slide*bw)
    hx = 1-round(slide*bw)
    b_hit = active and event["damage"]>0 and .28<age<.48
    p_hit = active and event["hurt"]>0 and .8<age<1.05
    monster_w=max(6,w*3//5)
    monster_h=max(5,h-2)
    monster_x=bx-(monster_w-bw)//2
    overlay(c,boss_frame(monster_w,monster_h,tick,event=event,age=age),
            monster_x+int(b_hit),0,6 if b_hit else None)
    overlay(c, hero_frame(bw,bheight,tick,s.get("avatar"),back=True),hx-int(p_hit),h-bheight,6 if p_hit else None)
    start,end = (w//4+3,h-3),(3*w//4-2,max(2,bheight//2))
    if active: attack_effect(c,event,age,start,end)
    boss_bar=life_meter(bhp,240,meter,event["boss_before"] if active else None)
    player_bar=life_meter(hp,100,meter,event["hp_before"] if active else None)
    label=s["name"][:18]
    c.put(1,0,"♥ GRINCH",4)
    c.put(1,1,boss_bar,6 if b_hit else 4)
    c.put(w-len(label)-2,h-2,"♥ "+label,5)
    c.put(w-len(player_bar),h-1,player_bar,2 if active and event["hurt"]<0 else 6 if p_hit or hp<25 else 4)
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
        # A widening impact ring keeps hits readable at small terminal sizes.
        def burst(center, progress, mark, color):
            if not 0 <= progress < 1: return
            rx=2+round(progress*min(8,c.w/7))
            ry=1+round(progress*min(3,c.h/6))
            for i in range(8):
                angle=i*math.pi/4
                c.put(center[0]+round(math.cos(angle)*rx),
                      center[1]+round(math.sin(angle)*ry),mark,color)
        if spell=="schild":
            burst(start,min(.97,age/.65),"◇",2)
        if event["hurt"]<0:
            for i in range(5):
                t=(age*.8+i*.18)%1
                c.put(start[0]+round(math.sin(t*5+i)*5),start[1]-round(t*5),"♥",4 if i%2 else 5)
        if event["damage"]>0:
            mark,color={"frost":("❄",2),"stern":("★",5),"ping":("◉",2)}.get(spell,("✦",6))
            burst(end,(age-.32)/.68,mark,color)
            if spell=="funke":
                for i in range(4): shot((age-i*.055)/.44,"━✦",5 if i%2 else 6,-round(2*math.sin(phase*math.pi)))
            if spell=="stern" and age<.50:
                for i in range(4): c.put(end[0]-5+i*3,round(phase*(end[1]+2))-i%2,"╲★",5)
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
            burst(start,(age-.84)/.62,"❄" if event["hurt"]>=12 else "✴",6)
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


def beast_segment(base, tip, lower, upper, color):
    """Tapered elliptical rings form sloping shoulders, bent limbs and sharp tips."""
    rings = []
    for (cx,cy,cz),(rx,rz) in ((base,lower),(tip,upper)):
        rings.append([(cx+rx*math.cos(a*math.tau/8),cy,cz+rz*math.sin(a*math.tau/8))
                      for a in range(8)])
    lo,hi = rings
    mesh = []
    for a in range(8):
        b=(a+1)%8
        mesh.extend(((lo[a],lo[b],hi[a],color),(hi[a],lo[b],hi[b],color),
                     (tip,hi[a],hi[b],color),(base,lo[b],lo[a],color)))
    return mesh


def beast_posture(breath,lunge,recoil):
    lift=breath*.048
    reach=lunge*.20
    return lift, reach, -.16-reach*.65+recoil*.14, .47+lift-reach*.20


@lru_cache(maxsize=96)
def boss_mesh(breath, lunge, recoil):
    lift,reach,cx,neck=beast_posture(breath,lunge,recoil)
    mesh=[]
    # Planted hind legs, heavy paws and a ripped winter coat over a deep chest.
    for side in (-1,1):
        mesh+=beast_segment((side*.86,-1.34,.19),(side*.57,-.64,.17),(.31,.34),(.47,.46),4)
        mesh+=cube(side*.88,-1.44,-.12,.65,.30,.83,8)
        for toe in (-.17,.07,.27):
            mesh+=beast_segment((side*.88+toe,-1.38,-.46),(side*.88+toe,-1.57,-.75),(.09,.13),(0,0),1)
    mesh+=beast_segment((0,-.94,.15),(cx,neck,-.04),(.77,.51),(1.28,.62),6)
    mesh+=beast_segment((0,-.83,.15),(0,-.64,.15),(.82,.54),(.86,.54),8)
    for side in (-1,1):
        shoulder=cx+side*1.00
        wrist=cx+side*(1.40+reach*.28)
        wy=-.44+lift+(reach*.46 if side<0 else -reach*.12)
        wz=-.47-(reach*.90 if side<0 else 0)
        mesh+=beast_segment((wrist,wy,wz),(shoulder,neck,.02),(.29,.32),(.54,.53),4)
        mesh+=beast_segment((shoulder,neck-.29,.02),(shoulder,neck+.12,.04),(.56,.54),(.46,.47),6)
        mesh+=cube(wrist,wy-.15,wz,.61,.45,.56,4)
        for finger in (-.22,0,.22):
            mesh+=beast_segment((wrist+finger,wy-.24,wz-.20),(wrist+finger-.13,wy-.69,wz-.49),
                                (.105,.13),(0,0),1)
    hx=cx-.13; hy=neck+.44+lift
    def face(x,y,z,w,h,d,color):
        return cube(hx+x,hy+y,z,w,h,d,color)
    mesh+=beast_segment((hx,hy-.42,-.24),(hx,hy+.27,-.17),(.62,.48),(.84,.60),4)
    mesh+=face(0,-.20,-.81,1.00,.38,.21,8)  # dark maw with a projecting jaw
    mesh+=face(0,-.43,-.69,.78,.15,.36,4)
    mesh+=face(0,-.01,-.81,.51,.20,.39,4)
    for side in (-1,1):
        mesh+=face(side*.39,.12,-.74,.42,.16,.21,5)
        mesh+=face(side*.35,.12,-.86,.08,.16,.04,8)
        mesh+=face(side*.30,.24,-.76,.42,.10,.19,8)
        mesh+=beast_segment((hx+side*.39,hy-.08,-.96),(hx+side*.34,hy-.39,-1.0),(.12,.07),(0,0),1)
        mesh+=beast_segment((hx+side*.66,hy+.22,-.15),(hx+side*1.15,hy+.63,.04),
                            (.33,.31),(0,0),4)
        mesh+=beast_segment((hx+side*.46,hy+.30,.14),(hx+side*.75,hy+.94,.26),
                            (.20,.21),(0,0),7)
    mesh+=beast_segment((hx,hy+.28,-.14),(hx-.48,hy+.79,.12),(.49,.38),(0,0),6)
    return mesh



def overlay(canvas, layer, left, top, flash=None):
    for y,row in enumerate(layer.cells):
        for x,(char,color) in enumerate(row):
            if char != " ": canvas.put(left+x,top+y,char,flash or color)


@lru_cache(maxsize=96)
def hero_mesh(hair,shirt,gender,style,step):
    # Boots, mitts, backpack and a pointed winter cap give the silhouette depth.
    shoulder=.95 if gender=="weiblich" else 1.12
    mesh = cube(0,-.22,0,shoulder,.93,.60,shirt)
    if gender=="weiblich":
        mesh+=cube(0,-.61,0,1.15,.22,.70,shirt)+cube(.36,.08,-.31,.27,.56,.14,5)
    mesh += cube(0,.66,-.04,.81,.78,.72,10)
    mesh += cube(0,.98,0,.91,.27,.80,hair)
    mesh += cube(0,.67,.32,.85,.55,.24,hair)
    if style=="Zopf":
        for i in range(4):
            mesh+=cube(.28,.84-.22*i,.44+.07*i,.36-.03*i,.34,.36,hair)
        mesh+=cube(.28,.24,.68,.30,.12,.32,5)
    elif style=="Locken":
        for i in range(9):
            angle=i*math.tau/9
            mesh+=cube(.44*math.cos(angle),.95+.08*(i%2),.39*math.sin(angle),.42,.42,.40,hair)
        mesh+=cube(0,1.23,0,.66,.28,.60,hair)
    elif style=="Irokese":
        for i in range(4): mesh+=cone(0,1.06,-.33+i*.22,.23,.59-.06*i,hair)
    else:
        mesh+=cone(-.21,1.04,-.13,.34,.31,hair)+cube(.23,.90,-.37,.35,.23,.20,hair)
    mesh += cube(0,.20,-.04,1.06,.16,.73,5)
    mesh += cube(0,-.18,.43,.62,.73,.42,7)
    mesh += cube(0,-.04,.66,.55,.13,.07,5)
    for side in (-1,1):
        swing=side*step*.25
        mesh += cube(side*.61,-.17,swing,.25,.70,.40,shirt)
        mesh += cube(side*.61,-.56,swing-.06,.27,.23,.38,10)
        mesh += cube(side*.29,-.90,-swing,.39,.52,.44,8)
        mesh += cube(side*.29,-1.20+max(0,swing*.4),-swing-.10,.43,.22,.66,7)
        mesh += cube(side*.21,.72,-.42,.11,.12,.07,8)
    return mesh


def hero_frame(w,h,tick,avatar,back=False,walking=False):
    avatar=avatar or {}
    mesh=hero_mesh(HAIR.get(avatar.get("hair"),7), SHIRTS.get(avatar.get("shirt"),4),
                   avatar.get("gender","männlich"),avatar.get("style","kurz"),
                   round(math.sin(tick*7)) if walking else 0)
    angle=(2.5 if back else -.38)+math.sin(tick*1.6)*.15
    return project_mesh(w,h,angle,mesh)


def boss_frame(w,h,tick,won=False,event=None,age=99):
    def pulse(start,duration):
        phase=(age-start)/duration
        return math.sin(phase*math.pi) if 0<phase<1 else 0
    lunging=event and any(s in ("claw","gale") for s in event.get("sounds",[]))
    if event and "sounds" not in event: lunging=event.get("hurt",0)>0
    lunge=round(5*pulse(.48,.54)) if lunging else 0
    recoil=round(3*pulse(.20,.36)) if event and event.get("damage",0)>0 else 0
    breath=round(2*math.sin(tick*1.8))
    return monster_pose(w,h,breath,lunge,recoil)


@lru_cache(maxsize=32)
def monster_pose(w,h,breath,lunge,recoil):
    angle, extent=.32,3.35
    canvas=project_mesh(w,h,angle,boss_mesh(breath,lunge,recoil),extent)
    if h>=7:
        # Reserve one cell for each glint even when a fang is smaller than a terminal cell.
        project=projector(w,h,angle,extent)
        lift,_,cx,neck=beast_posture(breath,lunge,recoil)
        for side in (-1,1):
            x,y,_=project((cx-.13+side*.39,neck+.56+lift,-.86))
            eye_row=round(y)
            canvas.put(round(x),eye_row,"◥" if side<0 else "◤",5)
            if h>=10:
                x,y,_=project((cx-.13+side*.39,neck+.15+lift,-.98))
                canvas.put(round(x),max(round(y),eye_row+1),"▾",1)
    return canvas


def projector(w,h,angle,extent):
    ca, sa = math.cos(angle), math.sin(angle)
    scale = max(2, min(h/extent, w/7.2))

    def project(v):
        x,y,z = v
        x,z = x*ca+z*sa, -x*sa+z*ca
        depth = z + 5
        return (w/2+x*scale*8/depth, h*.56-y*scale*4/depth, depth)

    return project


def project_mesh(w,h,angle,mesh,extent=3.1):
    c = Canvas(w,h)
    project = projector(w,h,angle,extent)
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
    place=hiding_place(s)
    if s["area"]==place: return "Hier ist die Spur!  nmap grinch"
    return f"Grinch-Spur → cd ~/welt/{place}"


def next_hint(s):
    if s["status"]!="playing": return "Neue Runde: restart"
    if s["boss_started"]: return ""
    if not s["bag"] and s["area"]=="dorf": return "Funken holen → mv funke ~/rucksack/"
    return trail_hint(s)


def bar(value, maximum, size=16):
    n = round(size*value/maximum)
    return "━"*n + "·"*(size-n)


def paint(screen,state,tick,position=None,walking=False):
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
    bag_w=min(22,max(13,w//5))
    # Keep the right edge free for the fighter's life meter.
    sx=bag_w+2
    scene_w=w-sx-1
    scene_h=h-3
    inventory=state.get("bag_display",state.get("bag",[]))
    put(screen,2,1,fit("Rucksack",bag_w-4)+f"{len(inventory):2}",5,True)
    visible=max(1,h-5)
    pages=max(1,math.ceil(len(inventory)/visible))
    page=int(tick//4)%pages
    for y in range(2,h): put(screen,y,bag_w+1,"│",3)
    if not inventory: put(screen,4,2,"leer",3)
    for i,item in enumerate(inventory[page*visible:(page+1)*visible]):
        icon,color=BAG_ICONS.get(item,("·",1))
        count=bag_count(item,state)
        put(screen,4+i,1,icon,color,True)
        put(screen,4+i,3,fit(item,bag_w-len(count)-3),1)
        put(screen,4+i,bag_w-len(count),count,color)
    if pages>1: put(screen,h-1,2,f"{page+1}/{pages}",3)
    if fight:
        event=(state.get("events") or [None])[-1]
        age=time.time()-event["at"] if event else 9
        hint="✦ DEIN ZUG   angreifen"
        color=5
        if 0<=age<1.5:
            spell=event.get("spell","")
            titles={"funke":"FUNKENSTURM", "frost":"FROSTWELLE", "stern":"STERNENREGEN",
                    "schild":"EISSCHILD", "beeren":"BEERENHEILUNG", "kakao":"WÄRMEZAUBER"}
            kind=event.get("kind")
            if event["hurt"]>0 and age>.66:
                hint=f"❄ GEGENANGRIFF   −{event['hurt']} LP"; color=6
            elif event["hurt"]<0:
                hint=f"♥ {titles.get(spell,'HEILUNG')}   +{-event['hurt']} LP"; color=4
            elif event["damage"] or spell in titles:
                title=titles.get(spell,"ECHOWELLE" if kind=="ping" else "ZUCKERSTABSCHLAG")
                hint="✦ "+title+(f"   −{event['damage']} LP" if event["damage"] else ""); color=2
        put(screen,1,sx,hint,color,True)
        scene=combat_frame(scene_w,scene_h,state,tick)
    else:
        scene=world_frame(scene_w,scene_h,state,position or POSITIONS.get(state["area"],POSITIONS["dorf"]),tick,walking)
        hp=state["hp"]
        event=(state.get("events") or [None])[-1]
        age=time.time()-event["at"] if event else 9
        if 0<=age<1.4: hp=smooth_life(hp,event["hp_before"],age/.78)
        health=life_meter(hp,100,min(15,w//7))
        put(screen,1,w-len(health)-1,health,2 if event and age<1 and event["hurt"]<0 else 4)
        hint=next_hint(state)
        space=w-len(health)-4
        if len(hint)+2>space:
            if discovered(state): hint=f"ssh {BOSS_IP}"
            elif not state["bag"] and state["area"]=="dorf": hint="mv funke ~/rucksack/"
            else: hint="nmap grinch" if state["area"]==hiding_place(state) else f"cd ~/welt/{hiding_place(state)}"
        put(screen,1,1,fit("✦ "+hint,space),5,True)
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
