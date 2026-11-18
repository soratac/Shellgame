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
    # A single paved court extends right under both fighters. Raised borders and
    # smaller distant flagstones give the near and far sides a common vanishing point.
    for iz in range(11):
        z=-3.95+iz*1.1
        for ix in range(-6,6):
            x=ix*1.6+(iz%2)*.8
            color=(11,3,11,11)[(ix*3+iz)%4]
            mesh+=quad((x,0,z),(x+1.55,0,z),(x+1.55,0,z+1.06),(x,0,z+1.06),color)
    # A split double ring inlaid in the ice.
    for radius,color in ((2.65,14),(2.42,12)):
        for i in range(32):
            a,b=i*math.tau/32,(i+.88)*math.tau/32
            def ring(t,r): return (r*math.cos(t),.045,.4+r*math.sin(t))
            mesh+=quad(ring(a,radius),ring(b,radius),ring(b,radius+.095),ring(a,radius+.095),color)
    for side in (-1,1):
        mesh+=cube(side*5.1,.40,2,.45,.80,8,11)
        for z in (-1.8,1.7,5.1):
            x=side*(4.6+.2*z)
            mesh+=cube(x,.80,z,.55,1.6,.68,12)+cone(x,1.6,z,.52,1.0,13)
            mesh+=cube(x,1.16,z-.36,.20,.35,.08,5)
    mesh+=cube(0,1.02,6.6,15,2.04,.55,11)
    for x in range(-7,8):
        mesh+=cube(x,2.18,6.6,.52,.37,.58,12)
    for x in (-2.15,2.15):
        mesh+=cube(x,1.65,6.0,1.05,3.3,.98,13)+cone(x,3.30,6.0,.85,1.35,2)
        mesh+=cube(x,2.05,5.43,.24,.52,.09,5)
    mesh+=cube(0,1.04,6.2,1.75,2.08,.64,8)
    for x in (-1.02,1.02): mesh+=cube(x,1.16,5.82,.26,2.32,.34,12)
    mesh+=cone(0,2.23,5.97,1.44,.82,13)
    for x,height in ((-9,5.3),(-5,4),(1,4.7),(5,5.8),(10,4.3)):
        mesh+=cone(x,-.8,10,3.0,height,3)+cone(x,height*.71-.8,10,.94,height*.31,12)
    return mesh


@lru_cache(maxsize=12)
def courtyard(w,h):
    c=project_mesh(w,h,0,courtyard_mesh(),project=lambda p:courtyard_point(w,h,p))
    def carve(a,b,color):
        x,y,_=courtyard_point(w,h,a)
        xx,yy,_=courtyard_point(w,h,b)
        c.line(round(x),round(y),round(xx),round(yy),"╌",color)
    for i in range(6):
        angle=i*math.tau/6
        dx,dz=math.cos(angle),math.sin(angle)
        for reach in (1.1,1.55):
            center=(reach*dx,.07,.45+reach*dz)
            for side in (-1,1):
                carve(center,((reach+.30)*dx-side*.27*dz,.07,.45+(reach+.30)*dz+side*.27*dx),14)
        carve((0,.07,.45),(1.96*dx,.07,.45+1.96*dz),12)
    return c.cells


def backdrop(cells):
    c=Canvas(len(cells[0]),len(cells))
    c.cells=[row.copy() for row in cells]
    return c


def winter_arena(w,h,tick):
    c=backdrop(courtyard(w,h))
    for x in range(0,w,2):
        y=round(h*(.11+.055*math.sin(x*.075+tick*.49)))
        if 0<=y<h and c.cells[y][x][0]==" ":
            c.put(x,y,"∿",9 if (x//10)%3 else 14)
    for i in range(max(4,w//7)):
        x=(i*17+int(tick*(1+i%2)))%w
        y=(i*13+int(tick*(1+i%3)))%h
        c.put(x,y,"·" if i%5 else "✧",12 if i%5 else 1)
    # A glint travels around the inlay in floor coordinates.
    for i in range(3):
        angle=tick*.48+i*math.tau/3
        x,y,_=courtyard_point(w,h,(2.68*math.cos(angle),.07,.4+2.68*math.sin(angle)))
        c.put(round(x),round(y),"✧",2)
    # Braziers, and their reflections on the courtyard floor.
    for side in (-1,1):
        for z in (-.75,3.4):
            x=side*(3.0+.18*z)
            px,py,_=courtyard_point(w,h,(x,.57,z))
            cx,cy=round(px),round(py)
            c.put(cx,cy,"▴" if int(tick*5+z)%3 else "♨",5)
            c.put(cx-1,cy+1,"╲▂╱",15)
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
        mesh+=cube((x+xx)/2,-.74,(z+zz)/2,.33,1.05,.34,12)
        for t in (.32,.5,.68):
            px,pz=x+t*(xx-x),z+t*(zz-z)
            mesh+=cube(px+dx,.02,pz+dz,.09,.48,.09,7)
            mesh+=cube(px+dx,.29,pz+dz,.13,.16,.13,5)
    for name,pos in POSITIONS.items():
        x,z=island_center(pos)
        mesh+=beast_segment((x,-1.34,z),(x,-.28,z),(.79,.57),(1.47,1.13),11)
        mesh+=beast_segment((x,-.28,z),(x,0,z),(1.47,1.13),(1.36,1.04),12)
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
    for i in range(max(4,w//5)):
        x=(i*23+int(tick*.8))%w
        y=(i*7+int(math.sin(tick*.8+i)))%h
        if c.cells[y][x][0]==" ": c.put(x,y,"≈" if y>h//3 else "·",11 if y>h//3 else 12)
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
