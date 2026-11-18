"""The ice courtyard and the winter trail map, rendered in terminal cells."""
from functools import lru_cache

from .geometry import Canvas, cube, cone, overlay, project_mesh

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


def atlas_point(w,h,pos):
    # Reserve room below each landmark for its name, including at small HUD sizes.
    return (round(4+pos[0]*max(0,w-9)),round(1+pos[1]*max(0,h-5)))


@lru_cache(maxsize=12)
def atlas(w,h):
    c=Canvas(w,h)
    centers={name:atlas_point(w,h,pos) for name,pos in POSITIONS.items()}
    for a,b in PATHS:
        x,y=centers[a]
        xx,yy=centers[b]
        c.line(x,y,xx,yy,"·",8)
    height=max(3,min(7,h//4))
    for name,(x,y) in centers.items():
        if h>=14 and w>=46:
            icon=project_mesh(height*3,height,-.38,landmark_mesh(name),extent=2.15)
            overlay(c,icon,x-icon.w//2,max(0,y-height//2))
        else:
            c.put(x,y,{"dorf":"⌂","wald":"▲","werkstatt":"⚙","archiv":"▤","zitadelle":"♜"}[name],20)
    return c.cells


def atlas_frame(w,h):
    return backdrop(atlas(w,h))
