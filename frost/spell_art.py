"""Faceted spell models, healing spirits and impact choreography."""
import math
from functools import lru_cache
from .geometry import beast_segment, cube, cone, overlay, project_mesh


def crystal(x,y,z,r,height,color):
    middle=(x,y,z)
    return (beast_segment((x,y-height*.52,z),middle,(0,0),(r,r*.8),color)
            +beast_segment(middle,(x,y+height*.48,z),(r,r*.8),(0,0),color))


def medal(points,color,depth=.28):
    mesh=[]
    for i,(x,y) in enumerate(points):
        xx,yy=points[(i+1)%len(points)]
        a,b=(x,y,-depth),(xx,yy,-depth)
        c,d=(xx,yy,depth),(x,y,depth)
        mesh.extend((((0,0,-depth*2),a,b,color),((0,0,depth),c,d,color),
                     (a,b,c,1),(a,c,d,color)))
    return mesh


def halo(rx,ry,color):
    mesh=[]
    for i in range(16):
        a,b=i*math.tau/16,(i+1)*math.tau/16
        def vertex(t,r): return (rx*r*math.cos(t),ry*r*math.sin(t),.26*math.sin(t*2))
        v,u,s,t=vertex(a,.73),vertex(a,1),vertex(b,1),vertex(b,.73)
        mesh.extend(((v,u,s,color),(v,s,t,1 if i%4==0 else color)))
    return mesh


@lru_cache(maxsize=20)
def model(kind):
    if kind in ("life","shade"):
        glow,wing=(4,2) if kind=="life" else (9,13)
        mesh=crystal(0,-.30,0,.62,1.16,glow)
        mesh+=beast_segment((0,-.10,-.06),(0,.55,0),(.51,.42),(.58,.46),glow)
        mesh+=cone(0,.54,0,.57,.39,glow)
        for side in (-1,1):
            mesh+=beast_segment((side*.39,.05,.1),(side*1.09,.64,.25),(.26,.27),(0,0),wing)
            mesh+=cube(side*.23,.30,-.45,.19,.16,.13,5)
        return mesh
    if kind=="funke":
        mesh=crystal(0,0,0,.72,1.8,15)
        for x,z in ((-.45,0),(.37,-.15),(0,.36)):
            mesh+=beast_segment((x,-.36,z),(x+.34,1.10,z),(.39,.32),(0,0),6)
        return mesh+crystal(0,.04,-.50,.32,.95,5)
    if kind=="frost":
        mesh=crystal(0,0,0,.48,2.35,2)
        for side in (-1,1):
            mesh+=beast_segment((0,-.72,0),(side*.93,.72,.22),(.34,.36),(0,0),12)
        return mesh
    if kind=="stern":
        outline=[]
        for i in range(10):
            a=math.pi/2+i*math.pi/5
            r=1.14 if i%2==0 else .51
            outline.append((r*math.cos(a),r*math.sin(a)))
        return medal(outline,5)
    if kind=="schild":
        return medal([(-.86,.58),(0,1.06),(.86,.58),(.73,-.35),(0,-1.1),(-.73,-.35)],2)+crystal(0,0,-.63,.27,.75,5)
    if kind=="ping": return halo(1.05,.90,2)
    if kind=="staff":
        return (beast_segment((-.66,-1.05,0),(.51,.85,0),(.16,.15),(.19,.15),6)
                +beast_segment((-.07,-.15,0),(.12,.16,0),(.20,.16),(.20,.16),1)
                +crystal(.54,.80,0,.39,.64,5))
    if kind=="claw":
        mesh=[]
        for x in (-.55,0,.55):
            mesh+=beast_segment((x-.21,-1.14,0),(x+.26,.77,.18),(0,0),(.18,.18),1)
        return mesh
    return halo(1.11,.70,13)+crystal(0,0,0,.63,1.65,2)


@lru_cache(maxsize=180)
def glyph(kind,height,phase):
    angle=math.sin(phase*math.tau/12)*.66
    c=project_mesh(height*2+1,height,angle,model(kind),extent=2.45)
    if kind in ("life","shade"):
        middle=c.w//2
        if height>=5: c.put(middle-1,round(height*.42),"• •",5)
        else: c.put(middle,1,"✦",5)
    return c


def apparition(canvas,kind,x,y,size,tick):
    size=max(3,int(size))
    layer=glyph(kind,size,int(tick*10)%12)
    overlay(canvas,layer,round(x)-layer.w//2,round(y)-layer.h//2)


def spell_motion(c,event,age,start,end):
    """Launch, travel and impact, followed by the Grinch's answering motion."""
    kind=event.get("kind")
    spell=event.get("spell")
    if kind=="attack": spell="staff"
    if kind=="ping": spell="ping"
    height=max(5,min(19,c.h*.78,c.w*.31))
    sx,sy=start; ex,ey=end
    if event.get("healed") or event["hurt"]<0:
        t=min(1,age/1.32)
        apparition(c,"life",sx+math.sin(t*math.tau)*4,sy-t*height*.64,
                   height*(.62+.36*math.sin(t*math.pi)),age)
    elif spell=="schild" and age<1.1:
        apparition(c,"schild",sx+2,sy-1,height*(.72+.28*math.sin(age*3)),age)
    if event["damage"] and spell=="stern" and age<1.18:
        starfall(c,age,end)
    if event["damage"] and spell=="ping" and age<1.10:
        echo_train(c,age,start,end)
    if event["damage"] and spell in ("funke","frost","staff") and age<.85:
        t=min(1,age/.54)
        # Fire, frost and the staff arc across the court.
        x=sx+(ex-sx)*t
        y=sy+(ey-sy)*t-height*.28*math.sin(t*math.pi)
        size=height*(.75+.25*math.sin(t*math.pi))
        if age>.54: size*=1+(age-.54)*1.35
        # Each projectile leaves its own wake along the same curved flight path.
        for i in range(7,0,-1):
            trail=t-i*.036
            if trail<=0: continue
            tx=round(sx+(ex-sx)*trail)
            ty=round(sy+(ey-sy)*trail-height*.28*math.sin(trail*math.pi))
            if spell=="funke":
                flicker=round(math.sin(i*2-age*18)*height*.13)
                c.put(tx,ty+flicker,"✺" if i<4 else "·",15 if i%2 else 5)
            elif spell=="frost":
                branch=1+(i%3)
                for side in (-1,1):
                    c.line(tx,ty,tx-branch,ty+side*branch,"╱" if side>0 else "╲",12)
                    c.put(tx-branch,ty+side*branch,"❄",1)
            else:
                c.put(tx,ty+round(i*.22),"╱",20 if i<4 else 6)
        apparition(c,spell,x,y,size,age)
        if age>=.46:
            bloom=min(1,(age-.46)/.36)
            radius=height*(.25+.72*bloom)
            mark,color={"funke":("✹",15),"frost":("❄",1),"staff":("╱",20)}[spell]
            for i in range(10):
                a=i*math.tau/10
                dx,dy=math.cos(a)*radius*1.65,math.sin(a)*radius*.7
                tx,ty=round(ex+dx),round(ey+dy)
                if spell in ("frost","staff","funke"):
                    c.line(round(ex+dx*.59),round(ey+dy*.59),tx,ty,"╲" if dx*dy>0 else "╱",color)
                c.put(tx,ty,mark,color)
    if kind=="unload" and spell in event.get("sounds",[]) and age<1.38:
        t=age/1.38
        if spell=="frost_armor":
            # Two front plates split apart, sending facets tumbling out of the seam.
            spread=min(1,t*1.8)
            for side in (-1,1):
                x=ex+side*(2+height*spread)
                y=ey+height*t*t*.32
                apparition(c,"frost",x,y,height*(.92-.48*t),age+side*.2)
                for i in range(4):
                    c.put(round(x+side*(i+1)*spread),round(y+(i-1.4)*spread*height*.36),"◆" if t<.6 else "·",5 if i%2 else 20)
            if t<.48:
                c.line(ex-1,ey-round(height*.46),ex+1,ey+round(height*.40),"ϟ",5)
        elif spell=="blizzard":
            # A tall helix collapses into the Grinch and releases one last puff.
            for i in range(28):
                a=i*.58-age*8
                r=(1-t)*height*(.48+i/28)
                x=ex+r*math.cos(a)
                y=ey+(i/27-.5)*height*(1-t)+r*.19*math.sin(a)
                c.put(round(x),round(y),"❄" if i%5==0 else "·",1 if i%3 else 12)
            if t>.68: apparition(c,"ping",ex,ey,height*(t-.52)*1.5,age)
    if kind=="disable" and age<.78:
        symbol="⚙"
        r=height*(.22+age*.75)
        for i in range(8):
            angle=i*math.tau/8+age*2
            c.put(round(ex+r*1.65*math.cos(angle)),round(ey+r*.64*math.sin(angle)),symbol,5 if i%2 else 20)
    if "loop" in event.get("sounds",[]) and age<1.2:
        for i in range(15):
            t=age*5+i*math.tau/15
            c.put(round(ex+height*math.sin(t)),round(ey+.45*height*math.sin(2*t)),"✦",5 if i%3 else 20)
    if .55<age<1.15:
        sounds=event.get("sounds",[])
        if "parry" in sounds:
            apparition(c,"schild",sx+3,sy-2,height*.88,age)
        if "ice_lock" in sounds:
            for side in (-1,1):
                x=ex+side*round(height*.65)
                apparition(c,"frost",x,ey+1,height*.71,age)
    sounds=event.get("sounds",[])
    for sound in sounds:
        boss_magic(c,sound,age,start,end)
    if event["hurt"]>0 and .55<age<1.35 and (not sounds or "claw" in sounds):
        t=min(1,(age-.55)/.52)
        counter=("gale" if "gale" in event["sounds"] else "claw") if "sounds" in event else ("gale" if event["hurt"]>=12 else "claw")
        apparition(c,counter,ex+(sx-ex)*t,ey+(sy-ey)*t,
                   height*(.57+.57*t),age)


def shockwave(c,x,y,r,ink,mark,points=20):
    for i in range(points):
        angle=i*math.tau/points
        c.put(round(x+r*math.cos(angle)),round(y+r*.40*math.sin(angle)),mark,ink)


def starfall(c,age,end):
    x,y=end
    # A constellation contracts into the falling star, then breaks into gold rays.
    t=min(1,age/.52)
    cx=round(x-(1-t)*c.w*.52)
    cy=round(y-(1-t)*(y+2))
    radius=max(4,min(c.w*.30,c.h*1.7))
    if age<.64:
        for i in range(1,7):
            c.put(cx-i*2,cy-i//2,"✧" if i%2 else "·",20 if i%2 else 5)
        apparition(c,"stern",cx,cy,max(5,min(20,c.h*(.55+.43*t))),age)
    if age>=.45:
        bloom=min(1,(age-.45)/.72)
        reach=radius*math.sin(bloom*math.pi*.55)
        for i in range(12):
            a=i*math.tau/12
            dx,dy=math.cos(a)*reach,math.sin(a)*reach*.48
            c.line(round(x+dx*bloom*.62),round(y+dy*bloom*.62),round(x+dx),round(y+dy),
                   "━" if abs(dy)<.5 else "╲" if dx*dy>0 else "╱",20 if i%2 else 5)
            c.put(round(x+dx),round(y+dy),"★" if i%3==0 else "✧",5)
        shockwave(c,x,y,reach*.80,5,"✦")
        # Secondary stars burst in sequence around the central impact.
        for index in range(5):
            t=bloom-.10*index
            if not 0<t<.58: continue
            angle=index*math.tau/5-.3
            bx=round(x+radius*.68*math.cos(angle))
            by=round(y+radius*.30*math.sin(angle))
            shockwave(c,bx,by,1+t*radius*.46,20 if index%2 else 5,"✧",12)
            c.put(bx,by,"★",5)
        c.put(x-1,y,"✦★✦",20)


def echo_train(c,age,start,end):
    sx,sy=start
    ex,ey=end
    for pulse in range(4):
        t=(age-.12*pulse)/.52
        if 0<=t<=1:
            x,y=sx+(ex-sx)*t,sy+(ey-sy)*t
            shockwave(c,x,y,2+3*t,2 if pulse%2 else 20,"◦",12)
            c.put(round(x),round(y),"◉",2)
        elif 1<t<1.40:
            shockwave(c,ex,ey,2+(t-1)*14,5,"·")


def boss_magic(c,sound,age,start,end):
    sx,sy=start
    ex,ey=end
    if sound=="charge":
        shockwave(c,ex,ey,3+(1-(age%0.7)/.7)*min(c.w*.22,c.h),9,"◆")
    elif sound in ("eclipse","eclipse_guard"):
        for hit,delay in enumerate((.48,.90)):
            t=(age-delay)/.36
            if not 0<=t<=1.45: continue
            x=round(ex+(sx-ex)*min(1,t)); y=round(ey+(sy-ey)*min(1,t))
            slope=1 if hit else -1
            for n in range(-2,3):
                c.line(x+n-3,y-3*slope,x+n+3,y+3*slope,"╲" if slope==1 else "╱",9 if n%2 else 20)
            if t>=.85:
                shockwave(c,sx,sy,3+(t-.85)*17,2 if sound=="eclipse_guard" else 6,"✷")
            if sound=="eclipse_guard": apparition(c,"schild",sx+2,sy,max(5,min(12,c.h*.7)),age)
    elif sound=="claw" and .58<age<1.4:
        t=min(1,(age-.58)/.50)
        x,y=round(ex+(sx-ex)*t),round(ey+(sy-ey)*t)
        reach=max(2,min(6,c.h//4))
        for offset in (-3,0,3):
            c.line(x+offset-reach,y+reach,x+offset+reach,y-reach,"╱",6)
            c.put(x+offset-reach,y+reach,"✴",20)
    elif sound=="lance" and .52<age<1.27:
        t=min(1,(age-.52)/.48)
        x,y=round(ex+(sx-ex)*t),round(ey+(sy-ey)*t)
        c.line(x,y,x+max(3,c.w//7),y-2,"◆",12)
        for side in (-1,1):
            c.line(x,y,x+max(3,c.w//10),y+side*2,"╲" if side>0 else "╱",2)
        c.put(x-1,y,"◀",1)
        if t>.82: shockwave(c,sx,sy,3+(t-.82)*44,1,"❄")
    elif sound=="gale" and .52<age<1.3:
        t=min(1,(age-.52)/.60)
        x,y=ex+(sx-ex)*t,ey+(sy-ey)*t
        for ring in (0,1):
            shockwave(c,round(x),round(y-ring*2),3+(t+ring*.35)*min(10,c.h*.6),12,"◦",16)
        for i in range(26):
            a=i*.7+age*11
            c.put(round(x+math.cos(a)*(3+i*.24)),round(y+i*.24-3+math.sin(a)),"❄" if i%4==0 else "·",2)
