"""The ice courtyard and the raised winter atlas, rendered in terminal cells."""
import math
from functools import lru_cache

from .geometry import Canvas, cube, cone, beast_segment, project_mesh

POSITIONS = {"zitadelle": (.50,.05), "wald": (.13,.39), "archiv": (.86,.39),
             "dorf": (.28,.90), "werkstatt": (.71,.90)}
PATHS = (("dorf","wald"), ("dorf","werkstatt"), ("werkstatt","archiv"),
         ("wald","zitadelle"), ("archiv","zitadelle"))


def landmark_mesh(place):
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
    return mesh



def quad(a,b,c,d,color):
    return [(a,b,c,color),(a,c,d,color)]


def translated(mesh,cx,cy,cz,scale=1):
    def move(p): return cx+p[0]*scale,cy+p[1]*scale,cz+p[2]*scale
    return [(move(a),move(b),move(c),color) for a,b,c,color in mesh]


def courtyard_point(w,h,p):
    x,y,z=p
    depth=z+6
    return (w*(.49+.69*x/depth), h*(.19+(2.25-y)*1.04/depth), depth)


@lru_cache(maxsize=1)
def courtyard_mesh():
    mesh=[]
    # Snowbanks and lanterns frame a quiet clearing. Leave the centre open for spells.
    for side in (-1,1):
        for x,z,height in ((4.2,4.9,2.9),(6.8,7.1,3.4)):
            mesh+=cone(side*x,0,z,1.1,height,17)
            mesh+=cone(side*x,height*.49,z,.64,height*.56,20)
        x=side*3.25
        mesh+=cube(x,.68,3.4,.12,1.36,.16,7)
        mesh+=cube(x,1.44,3.4,.35,.39,.31,5)
        mesh+=cone(x,1.62,3.4,.32,.26,20)
    return mesh


@lru_cache(maxsize=12)
def courtyard(w,h):
    c=project_mesh(w,h,0,courtyard_mesh(),project=lambda p:courtyard_point(w,h,p))
    for side in (-1,1):
        for z in (-2.6,-.7,1.8):
            x,y,_=courtyard_point(w,h,(side*2.8,0,z))
            c.put(round(x),round(y),"▁▁",8)
    return c.cells


def backdrop(cells):
    c=Canvas(len(cells[0]),len(cells))
    c.cells=[row.copy() for row in cells]
    return c


def winter_arena(w,h,tick):
    c=backdrop(courtyard(w,h))
    for i in range(max(3,w//18)):
        x=(i*19+int(tick*.65))%w
        y=(i*13+int(tick*(1+i%2)))%h
        if c.cells[y][x][0]==" ": c.put(x,y,"·",8 if i%3 else 20)
    return c


def island_center(pos):
    return ((pos[0]-.5)*10-(pos[1]-.5)*1.25, (pos[1]-.5)*8)


def atlas_projection(w,h,p):
    x,y,z=p
    return (w*(.5+.087*x+.0136*z),h*(.54+.091*z-.105*y),14-z-.40*y)


def atlas_point(w,h,pos):
    x,z=island_center(pos)
    sx,sy,_=atlas_projection(w,h,(x,.22,z))
    return round(sx),round(sy)


@lru_cache(maxsize=1)
def atlas_mesh():
    mesh=[]
    for a,b in PATHS:
        x,z=island_center(POSITIONS[a]); xx,zz=island_center(POSITIONS[b])
        length=math.hypot(xx-x,zz-z)
        dx,dz=(zz-z)*.16/length,(x-xx)*.16/length
        corners=[(x-dx,z-dz),(xx-dx,zz-dz),(xx+dx,zz+dz),(x+dx,z+dz)]
        top=[(px,-.19,pz) for px,pz in corners]
        mesh+=quad(*top,7)
        for i in (0,2):
            v,u=top[i:i+2]
            mesh+=quad(v,u,(u[0],-.43,u[2]),(v[0],-.43,v[2]),15)
        mesh+=cube((x+xx)/2,-.74,(z+zz)/2,.33,1.05,.34,18)
        px,pz=(x+xx)/2,(z+zz)/2
        mesh+=cube(px+dx,.02,pz+dz,.09,.48,.09,7)
        mesh+=cube(px+dx,.29,pz+dz,.13,.16,.13,5)
    for name,pos in POSITIONS.items():
        x,z=island_center(pos)
        mesh+=beast_segment((x,-1.34,z),(x,-.28,z),(.79,.57),(1.47,1.13),18)
        mesh+=beast_segment((x,-.28,z),(x,0,z),(1.47,1.13),(1.36,1.04),20)
        mesh+=translated(landmark_mesh(name),x,.56,z,.81)
        if name=="dorf":
            mesh+=translated(landmark_mesh(name),x-.85,.26,z+.18,.48)
        if name in ("wald","zitadelle"):
            for ox,oz in ((-.83,.35),(.80,.54)):
                mesh+=cone(x+ox,.02,z+oz,.26,.82,4)
        if name=="archiv": mesh+=cone(x,.91,z,.60,.62,9)
    return mesh


@lru_cache(maxsize=12)
def atlas(w,h):
    return project_mesh(w,h,0,atlas_mesh(),project=lambda p:atlas_projection(w,h,p)).cells


def atlas_frame(w,h,tick):
    c=backdrop(atlas(w,h))
    for i in range(max(3,w//22)):
        x=(i*23+int(tick*.8))%w
        y=(i*7+int(math.sin(tick*.8+i)))%h
        if c.cells[y][x][0]==" ": c.put(x,y,"·",8)
    x,y=atlas_point(w,h,POSITIONS["werkstatt"])
    for i in range(3):
        phase=(tick*.6+i/3)%1
        c.put(x+2+round(phase*3),y-1-round(phase*h*.16),"°" if phase<.7 else "·",12)
    if h>=12:
        # Icicles tumble from the forest shelf into the gorge below its bridge.
        x,y=atlas_point(w,h,POSITIONS["wald"])
        for i in range(3):
            fall=(tick*.7+i/3)%1
            c.put(x-3+i,y+2+round(fall*max(1,h*.14)),"╵" if fall<.67 else "·",14)
        x,y=atlas_point(w,h,POSITIONS["zitadelle"])
        c.put(x+2,max(0,y-round(h*.19)),"⚑" if int(tick*3)%2 else "⚐",6)
        x,y=atlas_point(w,h,POSITIONS["werkstatt"])
        c.put(x+2,y,("⊕","⊗")[int(tick*3)%2],5)
    x,y=atlas_point(w,h,POSITIONS["archiv"])
    c.put(x+round(3*math.cos(tick*2)),y-2+round(math.sin(tick*2)),"✧",9)
    return c
