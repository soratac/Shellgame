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
    if event["hurt"]<0:
        t=min(1,age/1.32)
        apparition(c,"life",sx+math.sin(t*math.tau)*4,sy-t*height*.64,
                   height*(.62+.36*math.sin(t*math.pi)),age)
    elif spell=="schild" and age<1.1:
        apparition(c,"schild",sx+2,sy-1,height*(.72+.28*math.sin(age*3)),age)
    if event["damage"] and spell in ("funke","frost","stern","ping","staff") and age<.85:
        t=min(1,age/.54)
        # The falling star enters from above. Other projectiles arc across the court.
        x=sx+(ex-sx)*t
        y=sy+(ey-sy)*t-height*.28*math.sin(t*math.pi)
        if spell=="stern": x,y=ex-(1-t)*c.w*.25,ey-(1-t)*(ey+2)
        size=height*(.75+.25*math.sin(t*math.pi))
        if age>.54: size*=1+(age-.54)*1.35
        apparition(c,spell,x,y,size,age)
        if age>=.46:
            bloom=min(1,(age-.46)/.36)
            radius=height*(.25+.72*bloom)
            mark,color={"funke":("✹",15),"frost":("❄",1),"stern":("★",5),
                        "ping":("◦",2),"staff":("╱",20)}[spell]
            for i in range(10):
                a=i*math.tau/10
                dx,dy=math.cos(a)*radius*1.65,math.sin(a)*radius*.7
                tx,ty=round(ex+dx),round(ey+dy)
                if spell in ("frost","staff","funke"):
                    c.line(round(ex+dx*.59),round(ey+dy*.59),tx,ty,"╲" if dx*dy>0 else "╱",color)
                c.put(tx,ty,mark,color)
    if kind in ("disable","unload") and age<.78:
        symbol="⚙" if kind=="disable" else "◇"
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
    if event["hurt"]>0 and .55<age<1.35:
        t=min(1,(age-.55)/.52)
        counter=("gale" if "gale" in event["sounds"] else "claw") if "sounds" in event else ("gale" if event["hurt"]>=12 else "claw")
        apparition(c,counter,ex+(sx-ex)*t,ey+(sy-ey)*t,
                   height*(.57+.57*t),age)
