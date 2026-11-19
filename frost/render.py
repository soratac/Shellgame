"""Animated terminal HUD, character models and combat choreography."""
import curses
from functools import lru_cache
import math
import time
import unicodedata

from .geometry import Canvas, cube, cone, beast_segment, overlay, projector, project_mesh
from .client import request
from .trail import hiding_place, discovered
from .engine import HINT_LIMIT, ECLIPSE_HIT, boss_lock
from .avatar import HAIR, SHIRTS
from .items import BAG_ICONS, bag_count

from .snow import flakes
from .spell_art import apparition, spell_motion, shockwave
from .scenery import POSITIONS, atlas_frame, atlas_point


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
    for fx,fy,glyph,tint in flakes(w,h,tick):
        if c.cells[fy][fx][0]==" ": c.put(fx,fy,glyph,tint)
    marked=None if discovered(s) else hiding_place(s)
    x,y=atlas_point(w,h,position)
    hh=max(4,min(8,h//2))
    left=max(0,min(w-13,round(x+5-22*x/max(1,w-1))))
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
    offset=max(3,min(8,h//4+1))//2+1 if h>=14 and w>=46 else 1
    for name,pos in POSITIONS.items():
        lx,ly=atlas_point(w,h,pos)
        label=("▸ " if name==s["area"] else "")+name+(" ✧" if name==marked else "")
        lx=max(0,min(w-len(label)-2,lx-len(label)//2-1))
        row=min(h-1,ly+offset)
        if any(ink==22 for _,ink in c.cells[row][lx:lx+len(label)+2]):
            row = row+1 if row<h-1 else row-1
        c.put(lx,row," "+label+" ",5 if name==marked else 4 if name==s["area"] else 1)
    return c


def smooth_life(value,before,progress):
    t=max(0,min(1,progress))
    return before+(value-before)*t*t*(3-2*t)


def health_gauge(value, maximum, size, previous, age, tick, current=None):
    """A continuous enamel face with a darker lower edge and a fading damage trail."""
    label=f" {round(value) if current is None else current}/{maximum}"
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
    c.put(size,0,label,21)
    return c


def combat_frame(w,h,s,tick):
    c=Canvas(w,h)
    for fx,fy,glyph,tint in flakes(w,h,tick): c.put(fx,fy,glyph,tint)
    event=(s.get("events") or [None])[-1]
    age=time.time()-event["at"] if event else 99
    active=event is not None and 0<=age<1.5
    hp,bhp=s["hp"],s["boss_hp"]
    if active:
        hp=smooth_life(hp,event["hp_before"],(age-(.12 if event["hurt"]<0 else .55))/.7)
        healed=event.get("healed",0)
        peak=event["hp_before"]+healed
        if healed:
            hp=smooth_life(peak,event["hp_before"],age/.38)
            if age>=.52: hp=smooth_life(s["hp"],peak,(age-.52)/.58)
        if "eclipse" in event.get("sounds",[]):
            mid=max(0,peak-ECLIPSE_HIT)
            if age>=.55: hp=smooth_life(mid,peak,(age-.55)/.22)
            if age>=.99: hp=smooth_life(s["hp"],mid,(age-.99)/.22)
        bhp=smooth_life(bhp,event["boss_before"],(age-.13)/.72)
    right=w//2+2
    meter=max(3,min(28,w//2-12))
    elapsed = max(0,time.time()-s.get("boss_entered_at",0))
    slide = max(0,1-elapsed/.65)
    bw,bheight = w//2-2,max(4,h-4)
    bx = right + round(slide*bw)
    hx = 1-round(slide*bw)
    b_hit = active and event["damage"]>0 and .28<age<.48
    p_hit = active and event["hurt"]>0 and (.8<age<1.05 or ("eclipse" in event.get("sounds",[]) and 1.18<age<1.36))
    monster_w=max(6,w*3//5)
    monster_h=max(5,h-2)
    monster_x=bx-(monster_w-bw)//2
    overlay(c,boss_frame(monster_w,monster_h,tick,event=event,age=age),
            monster_x+int(b_hit),0,6 if b_hit else None)
    overlay(c, hero_frame(bw,bheight,tick,s.get("avatar"),back=True),hx-int(p_hit),h-bheight,6 if p_hit else None,preserve=(22,))
    start,end = (w//4+3,h-3),(3*w//4-2,max(2,bheight//2))
    if w>=37 and h>=7:
        size=max(3,min(7,h//4))
        apparition(c,"shade",min(w//2-1,meter+10),2+.7*math.sin(tick*2),size,tick)
        apparition(c,"life",w-(meter+8)-3,h-3+.6*math.sin(tick*2.3),size,tick+.5)
    if s.get("charging") and s.get("status")=="playing":
        radius=3+(1-(tick%1.3)/1.3)*min(w*.16,h*.8)
        shockwave(c,end[0],end[1],radius,9,"✧")
    if active: attack_effect(c,event,age,start,end)
    boss_bar=health_gauge(bhp,240,meter,event["boss_before"] if active else bhp,age,tick,s["boss_hp"])
    player_bar=health_gauge(hp,100,meter,event["hp_before"] if active else hp,age,tick,s["hp"])
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
            elif spell=="frost":
                for dy in (-1,0,1): shot(age/.47,"❄",2,round(dy*math.sin(phase*math.pi)))
            elif kind=="attack":
                shot(age/.30,"╱━",1)
            elif spell not in ("stern","ping") and kind!="ping":
                shot(age/.44,"✦»",6,-round(2*math.sin(phase*math.pi)))
        if event["hurt"]>0 and not set(event.get("sounds",[])).intersection(("lance","eclipse","gale")):
            burst(start,(age-.84)/.62,"❄" if event["hurt"]>=12 else "✴",6)
            strong=event["hurt"]>=12
            for dy in ((-1,0,1) if strong else (0,)):
                shot(1-(age-.6)/.35,"❄" if strong else "«✹",2 if strong else 6,dy)
        spell_motion(c,event,age,start,end)
        if event["damage"]>0 and age>.25: c.put(end[0]+2,max(0,end[1]-2),f"-{event['damage']}",5)
        healed=event.get("healed",0)
        hit=max(0,event["hurt"]+healed)
        if hit and age>.85:
            label="2 × 46" if "eclipse" in event.get("sounds",[]) else f"-{hit}"
            c.put(start[0]-4,max(2,start[1]-2),label,6)
        recovery=healed or max(0,-event["hurt"])
        if recovery and age<.65: c.put(start[0]-3,start[1]-1,f"+{recovery}",4)


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
                            (.12,.14),(0,0),4)
    # Fur-trimmed coat, brass buckle and a bent stocking cap with a pompom.
    mesh+=beast_segment((0,-.99,.15),(0,-.82,.15),(.82,.56),(.85,.56),20)
    mesh+=cube(0,-.72,-.46,.40,.23,.14,5)
    # White cuffs, a scarlet lapel and gold buttons across the front of the coat.
    for side in (-1,1):
        wrist=cx+side*(1.40+reach*.28)
        wy=-.44+lift+(reach*.46 if side<0 else -reach*.12)
        wz=-.47-(reach*.90 if side<0 else 0)
        mesh+=beast_segment((wrist,wy+.10,wz),(shoulder,neck-.15,.02),(.33,.36),(.50,.49),6)
        mesh+=cube(wrist,wy+.10,wz,.68,.25,.65,20)
    mesh+=beast_segment((-.03,-.58,-.44),(cx,neck-.12,-.66),(.14,.08),(.24,.09),6)
    for i in range(3):
        mesh+=cube(-.07,-.46+i*.27,-.57-i*.06,.13,.13,.09,5)
    mesh+=beast_segment((cx,neck-.20,-.05),(cx,neck-.05,-.05),(1.07,.62),(1.15,.62),20)
    mesh+=beast_segment((hx,hy+.22,-.17),(hx,hy+.40,-.16),(.82,.62),(.78,.59),20)
    mesh+=beast_segment((hx,hy+.39,-.16),(hx-.33,hy+.87,-.14),(.78,.59),(.32,.27),6)
    mesh+=beast_segment((hx-.33,hy+.87,-.14),(hx-.91,hy+.54,-.26),(.32,.27),(.10,.10),6)
    mesh+=beast_segment((hx-.91,hy+.38,-.26),(hx-.91,hy+.62,-.26),(.27,.24),(.22,.19),20)
    return mesh



@lru_cache(maxsize=96)
def hero_mesh(hair,shirt,gender,style,step):
    # Boots, mitts, backpack and a pointed winter cap give the silhouette depth.
    shoulder=.95 if gender=="weiblich" else 1.12
    mesh = cube(0,-.22,0,shoulder,.93,.60,shirt)
    if gender=="weiblich":
        mesh+=beast_segment((0,-.73,0),(0,-.30,0),(.69,.39),(.40,.33),shirt)
        mesh+=cube(.31,.02,-.32,.22,.51,.14,6)
    mesh += cube(0,.66,-.04,.81,.78,.72,25)
    mesh += cube(0,1.00,-.055,.92,.32,.85,hair)
    mesh += cube(0,.67,.32,.85,.55,.24,hair)
    if style=="Dutt":
        mesh+=beast_segment((.16,1.06,.20),(.23,1.40,.20),(.31,.27),(.38,.32),hair)
        mesh+=cube(.23,1.43,.2,.49,.16,.42,hair)
        mesh+=cube(.16,1.11,.19,.56,.09,.50,5)
    elif style in ("Zopf","Flechtkranz"):
        for side in ((-1,1) if style=="Flechtkranz" else (1,)):
            for i in range(4):
                mesh+=cube(side*(.43+.065*(i%2)),.89-i*.21,-.11-i*.06,.28,.31,.32,hair)
            mesh+=cube(side*.49,.18,-.30,.27,.13,.29,6)
        if style=="Flechtkranz":
            for i in range(5):
                mesh+=cube((i-2)*.18,1.02+.06*(i%2),-.38,.23,.20,.19,hair)
    elif style=="Wellen":
        mesh+=beast_segment((-.19,.91,-.39),(.09,1.14,-.24),(.25,.14),(.43,.26),hair)
        for side in (-1,1):
            for i in range(4):
                mesh+=cube(side*(.42+.07*math.sin(i*2)),.92-i*.23,.02,.29,.38,.55,hair)
    elif style=="Locken":
        for i in range(9):
            angle=i*math.tau/9
            mesh+=cube(.44*math.cos(angle),.95+.08*(i%2),.39*math.sin(angle),.42,.42,.40,hair)
        mesh+=cube(0,1.23,0,.66,.28,.60,hair)
    elif style=="Irokese":
        for i in range(4): mesh+=cone(0,1.06,-.33+i*.22,.23,.59-.06*i,hair)
    else:
        mesh+=cone(-.21,1.04,-.13,.34,.31,hair)+cube(.23,.90,-.37,.35,.23,.20,hair)
    if gender=="weiblich" and style in ("kurz","Locken"):
        for side in (-1,1):
            mesh+=beast_segment((side*.42,.34,-.02),(side*.40,.90,.02),
                                (.13,.21),(.22,.32),hair)
        mesh+=cube(-.20,.91,-.39,.48,.17,.16,hair)
    mesh += cube(0,.20,-.04,1.06,.16,.73,5)
    mesh += cube(0,-.18,.43,.62,.73,.42,7)
    mesh += cube(0,-.04,.66,.55,.13,.07,5)
    for side in (-1,1):
        swing=side*step*.25
        mesh += cube(side*.61,-.17,swing,.25,.70,.40,shirt)
        mesh += cube(side*.61,-.56,swing-.06,.27,.23,.38,10)
        mesh += cube(side*.29,-.90,-swing,.39,.52,.44,8)
        mesh += cube(side*.29,-1.20+max(0,swing*.4),-swing-.10,.43,.22,.66,7)
    return mesh


def face_details(canvas, camera, profile=False):
    # Paint inside the visible face. Hair, scarf and silhouette keep their depth.
    skin = {(x,y) for y,row in enumerate(canvas.cells) for x,(_,ink) in enumerate(row) if ink==25}
    if not skin and canvas.h>8:
        return
    eyes = [camera((side*.19,.68,-.40)) for side in (-1,1)]
    gap = abs(eyes[1][0]-eyes[0][0])
    if profile and gap<3:
        eyes = [min(eyes,key=lambda eye:eye[2])]
    eye_row = round(sum(eye[1] for eye in eyes)/len(eyes))
    painted = []
    for ex,ey,_ in eyes:
        x,y = round(ex),eye_row
        if canvas.h>8:
            x,y = min(skin,key=lambda cell: ((cell[0]-ex)**2 + 2*(cell[1]-ey)**2,cell))
        canvas.put(x,y,"•",22)
        painted.append((x,y))
    if canvas.h>=12:
        mx,my,_=camera((0,.43,-.46))
        canvas.put(round(mx),max(round(my),max(y for _,y in painted)+1),"─",26)


def hero_frame(w,h,tick,avatar,back=False,walking=False):
    avatar=avatar or {}
    mesh=hero_mesh(HAIR.get(avatar.get("hair"),7), SHIRTS.get(avatar.get("shirt"),4),
                   avatar.get("gender","männlich"),avatar.get("style","kurz"),
                   round(math.sin(tick*7)) if walking else 0)
    angle=(-.94 if back else -.30)+math.sin(tick*1.6)*.12
    if h<=8 and not back:
        angle=-.30  # Keep the small face on the same cells throughout the walking cycle.
    camera=projector(w,h,angle,2.85)
    canvas=project_mesh(w,h,angle,mesh,project=camera)
    face_details(canvas,camera,profile=back)
    return canvas


def boss_frame(w,h,tick,won=False,event=None,age=99):
    def pulse(start,duration):
        phase=(age-start)/duration
        return math.sin(phase*math.pi) if 0<phase<1 else 0
    lunging=event and any(s in ("claw","gale","lance","eclipse","eclipse_guard") for s in event.get("sounds",[]))
    if event and "sounds" not in event: lunging=event.get("hurt",0)>0
    lunge=round(5*pulse(.48,.54)) if lunging else 0
    if event and any(sound in ("eclipse","eclipse_guard") for sound in event.get("sounds",[])):
        lunge=round(5*(pulse(.45,.32)+pulse(.88,.32)))
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
        if h>=13:
            x,y,_=project((cx,neck-.30,-.70))
            canvas.put(round(x),round(y),"❄",20)
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
    if not curses.has_colors(): return
    curses.use_default_colors()
    palette = [252, 86, 103, 120, 221, 203, 173, 245, 141, 223, 24, 67, 103, 37, 173, 160, 22, 237, 28, 230]
    for i, color in enumerate(palette, 1):
        curses.init_pair(i, color if curses.COLORS >= 256 else [7,6,4,2,3,1,3,7,5,7,4,6,4,6,3,1,2,7,2,7][i-1], -1)

    for pair,fg,bg,small_fg,small_bg in ((21,231,22,7,2),(22,16,223,0,7),
                                        (23,195,23,7,4),(24,122,-1,6,-1),
                                        (25,223,-1,7,-1),(26,16,224,0,7)):
        curses.init_pair(pair,fg if curses.COLORS>=256 else small_fg,bg if curses.COLORS>=256 else small_bg)


def put(screen, y, x, text, color=1, bold=False):
    h,w = screen.getmaxyx()
    if 0 <= y < h and 0 <= x < w:
        try:
            screen.addnstr(y,x,text,max(0,w-x-1),curses.color_pair(color) | (curses.A_BOLD if bold or color==21 else 0))
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
        put(screen,0,1,"POLARNACHT → ~/rucksack/schild" if state.get("charging") else "FROSTBYTE · Terminal vergroessern",2)
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
        hint=(boss_lock(state) if time.time()>=state.get("hint_until",0) else "") or hud_hint(state)
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
        if state.get("charging") and state.get("status")=="playing":
            hint="POLARNACHT → ~/rucksack/schild"
            color=6
        elif event and .52<age<1.48:
            moves={"claw":"KRALLENSCHLAG","lance":"EISLANZE","gale":"STURMBÖE",
                   "eclipse":"POLARNACHT · 2 × 46 LP","eclipse_guard":"POLARNACHT · BEIDE BLOCKIERT"}
            for sound in event.get("sounds",[]):
                if sound in moves: hint,color=moves[sound],6 if sound!="eclipse_guard" else 4
        put(screen,1,sx,hint,color,True)
        scene=combat_frame(scene_w,scene_h,state,tick)
    else:
        scene=world_frame(scene_w,scene_h,state,position or POSITIONS.get(state["area"],POSITIONS["dorf"]),tick,walking)
        hp=state["hp"]
        event=(state.get("events") or [None])[-1]
        age=time.time()-event["at"] if event else 9
        if 0<=age<1.4: hp=smooth_life(hp,event["hp_before"],age/.78)
        health=health_gauge(hp,100,min(15,w//7),event["hp_before"] if event else hp,age,tick,state["hp"])
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
