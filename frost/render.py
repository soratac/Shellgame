"""Animated terminal HUD, character models and combat choreography."""
import curses
from functools import lru_cache
import math
import time
import unicodedata

from .geometry import Canvas, cube, cone, beast_segment, overlay, projector, project_mesh
from .client import request
from .trail import hiding_place, discovered
from .engine import HINT_LIMIT
from .avatar import HAIR, SHIRTS
from .items import BAG_ICONS, bag_count

from .spell_art import apparition, spell_motion
from .scenery import POSITIONS, atlas_frame, atlas_point, winter_arena


def static_map(s):
    def tag(name):
        marker=" ✧" if not discovered(s) and name==hiding_place(s) else ""
        return ("@ " if s["area"] == name else "") + name + "/" + marker
    return ("\n"+tag("zitadelle").center(44)+"\n"
            + "           ╱                   ╲\n"
            + f"  {tag('wald'):<23} {tag('archiv')}\n"
            + "        ╲                     ╱\n"
            + f"       {tag('dorf')} ───── {tag('werkstatt')}\n\n"
            + "  @ = du   ✧ = Grinch-Spur\n")


def world_frame(w,h,s,position,tick,walking=False):
    c=atlas_frame(w,h)
    marked=None if discovered(s) else hiding_place(s)
    x,y=atlas_point(w,h,position)
    hh=max(4,min(8,h//2))
    left=max(0,min(w-13,x+5 if x<w*.5 else x-17))
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
    offset=max(3,min(7,h//4))//2+1 if h>=14 and w>=46 else 1
    for name,pos in POSITIONS.items():
        lx,ly=atlas_point(w,h,pos)
        label=("▸ " if name==s["area"] else "")+name+(" ✧" if name==marked else "")
        lx=max(0,min(w-len(label)-2,lx-len(label)//2-1))
        c.put(lx,min(h-1,ly+offset)," "+label+" ",5 if name==marked else 4 if name==s["area"] else 1)
    return c


def smooth_life(value,before,progress):
    t=max(0,min(1,progress))
    return before+(value-before)*t*t*(3-2*t)


def health_gauge(value, maximum, size, previous, age, tick):
    """A continuous enamel face with a darker lower edge and a fading damage trail."""
    label=f" {round(value)}/{maximum}"
    c=Canvas(size+len(label),2)
    amount=max(0,min(size*8,round(value/maximum*size*8)))
    healing=previous<value and 0<=age<1.45
    trailing=smooth_life(value,previous,(age-.66)/.70) if 0<=age<1.5 else value
    shine=int(tick*8)%(size+5)
    for x in range(size):
        units=max(0,min(8,amount-x*8))
        color=4 if value>maximum*.45 else 5 if value>maximum*.23 else 16
        if units:
            shadow=19 if color==4 else 7 if color==5 else 16
            ch="▏▎▍▌▋▊▉█"[units-1]
            if healing and abs(x-shine)<3: color=20
            elif color==16 and math.sin(tick*5)>.55: color=6
            if units==8 and x==0: ch="▐"
            elif units==8 and x==size-1: ch="▌"
            c.put(x,0,ch,color)
            c.put(x,1,"▝" if x==0 else "▘" if x==size-1 else "▀",shadow)
        else:
            c.put(x,0,"▓" if x<trailing/maximum*size else "▁",15 if x<trailing/maximum*size else 8)
    c.put(size,0,label,20)
    return c


def combat_frame(w,h,s,tick):
    c=winter_arena(w,h,tick)
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
    # Flattened contact shadows anchor the sprites to the same paved surface.
    for cx,cy,r in ((w//4,h-2,max(2,w//12)),(3*w//4,monster_h-1,max(3,w//10))):
        c.put(cx-r,cy,"╶"+"▄"*(r*2-1)+"╴",18)
    overlay(c,boss_frame(monster_w,monster_h,tick,event=event,age=age),
            monster_x+int(b_hit),0,6 if b_hit else None)
    overlay(c, hero_frame(bw,bheight,tick,s.get("avatar"),back=True),hx-int(p_hit),h-bheight,6 if p_hit else None)
    start,end = (w//4+3,h-3),(3*w//4-2,max(2,bheight//2))
    if w>=37 and h>=7:
        size=max(3,min(7,h//4))
        apparition(c,"shade",min(w//2-1,meter+10),2+.7*math.sin(tick*2),size,tick)
        apparition(c,"life",w-(meter+8)-3,h-3+.6*math.sin(tick*2.3),size,tick+.5)
    if active: attack_effect(c,event,age,start,end)
    boss_bar=health_gauge(bhp,240,meter,event["boss_before"] if active else bhp,age,tick)
    player_bar=health_gauge(hp,100,meter,event["hp_before"] if active else hp,age,tick)
    label=s["name"][:18]
    c.put(1,0,"♥ GRINCH",4)
    overlay(c,boss_bar,1,1)
    c.put(w-len(label)-2,h-3,"♥ "+label,5)
    overlay(c,player_bar,w-player_bar.w,h-2)
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
        if event["hurt"]>0:
            burst(start,(age-.84)/.62,"❄" if event["hurt"]>=12 else "✴",6)
            strong=event["hurt"]>=12
            for dy in ((-1,0,1) if strong else (0,)):
                shot(1-(age-.6)/.35,"❄" if strong else "«✹",2 if strong else 6,dy)
        spell_motion(c,event,age,start,end)
        if event["damage"]>0 and age>.25: c.put(end[0]+2,max(0,end[1]-2),f"-{event['damage']}",5)
        if event["hurt"]>0 and age>.85: c.put(start[0]-4,max(2,start[1]-2),f"-{event['hurt']}",6)
        if event["hurt"]<0: c.put(start[0]-3,start[1]-1,f"+{-event['hurt']}",4)


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
    mesh+=beast_segment((0,-.94,.15),(cx,neck,-.04),(.77,.51),(1.28,.62),16)
    mesh+=beast_segment((0,-.83,.15),(0,-.64,.15),(.82,.54),(.86,.54),8)
    for side in (-1,1):
        shoulder=cx+side*1.00
        wrist=cx+side*(1.40+reach*.28)
        wy=-.44+lift+(reach*.46 if side<0 else -reach*.12)
        wz=-.47-(reach*.90 if side<0 else 0)
        mesh+=beast_segment((wrist,wy,wz),(shoulder,neck,.02),(.29,.32),(.54,.53),4)
        mesh+=beast_segment((shoulder,neck-.29,.02),(shoulder,neck+.12,.04),(.56,.54),(.46,.47),16)
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
    # Fur-trimmed coat, brass buckle and a bent stocking cap with a pompom.
    mesh+=beast_segment((0,-.99,.15),(0,-.82,.15),(.82,.56),(.85,.56),20)
    mesh+=cube(0,-.72,-.43,.36,.20,.13,5)
    mesh+=beast_segment((cx,neck-.20,-.05),(cx,neck-.05,-.05),(1.07,.62),(1.15,.62),20)
    mesh+=beast_segment((hx,hy+.22,-.17),(hx,hy+.40,-.16),(.82,.62),(.78,.59),20)
    mesh+=beast_segment((hx,hy+.39,-.16),(hx-.33,hy+.87,-.14),(.78,.59),(.32,.27),16)
    mesh+=beast_segment((hx-.33,hy+.87,-.14),(hx-.91,hy+.54,-.26),(.32,.27),(.10,.10),16)
    mesh+=beast_segment((hx-.91,hy+.38,-.26),(hx-.91,hy+.62,-.26),(.20,.17),(.15,.15),20)
    return mesh



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
        if h>=12:
            x,y,_=project((cx-1.04,neck+.94+lift,-.30))
            canvas.put(round(x),round(y),"✹",20)
        for side in (-1,1):
            x,y,_=project((cx-.13+side*.39,neck+.56+lift,-.86))
            eye_row=round(y)
            canvas.put(round(x),eye_row,"◥" if side<0 else "◤",5)
            if h>=10:
                x,y,_=project((cx-.13+side*.39,neck+.15+lift,-.98))
                canvas.put(round(x),max(round(y),eye_row+1),"▾",1)
    return canvas


def colors():
    curses.start_color()
    curses.use_default_colors()
    palette = [252, 86, 60, 120, 221, 204, 130, 240, 141, 223, 24, 67, 103, 37, 173, 160, 22, 237, 28, 230]
    for i, color in enumerate(palette, 1):
        curses.init_pair(i, color if curses.COLORS >= 256 else [7,6,4,2,3,1,3,0,5,3,4,6,4,6,3,1,2,0,2,7][i-1], -1)


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


def hud_hint(state):
    if time.time()<state.get("hint_until",0):
        return state.get("hint_text","")
    return f"tipp · {state.get('hints_left',HINT_LIMIT)}/{HINT_LIMIT}"


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
        hint=hud_hint(state)
        color=5
        if 0<=age<1.5:
            spell=event.get("spell","")
            titles={"funke":"FUNKENSTURM", "frost":"FROSTWELLE", "stern":"STERNENREGEN",
                    "schild":"EISSCHILD", "beeren":"BEERENHEILUNG", "kakao":"WÄRMEZAUBER"}
            kind=event.get("kind")
            if kind=="unload" and spell in ("frost_armor","blizzard") and spell in event.get("sounds",[]):
                hint={"frost_armor":"❖  EISPANZER ZERBROCHEN","blizzard":"❄  SCHNEESTURM ERLOSCHEN"}[spell]
                color=5
            elif event["hurt"]>0 and age>.66:
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
        health=health_gauge(hp,100,min(15,w//7),event["hp_before"] if event else hp,age,tick)
        put(screen,1,1,fit(hud_hint(state),w-health.w-4),5,True)
    for y,row in enumerate(scene.cells):
        for x,(char,color) in enumerate(row):
            if char!=" ": put(screen,y+2,x+sx,char,color)
    if not fight:
        for y,row in enumerate(health.cells):
            for x,(ch,color) in enumerate(row):
                if ch!=" ": put(screen,y+1,w-health.w-1+x,ch,color)


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
