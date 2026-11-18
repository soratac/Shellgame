"""Winter trail map with five landmarks."""
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
        # Leave some air around the landmarks and between the trail markers.
        steps=max(abs(xx-x),abs(yy-y))
        for step in range(3,steps-2,3):
            c.put(round(x+(xx-x)*step/steps),round(y+(yy-y)*step/steps),"·",8)
    height=max(3,min(7,h//4))
    for name,(x,y) in centers.items():
        if h>=14 and w>=46:
            icon=project_mesh(height*3,height,-.38,landmark_mesh(name),extent=2.15)
            overlay(c,icon,x-icon.w//2,max(0,y-height//2))
        else:
            c.put(x,y,{"dorf":"⌂","wald":"▲","werkstatt":"⚙","archiv":"▤","zitadelle":"♜"}[name],20)
    return c.cells


def atlas_frame(w,h):
    c=Canvas(w,h)
    c.cells=[row.copy() for row in atlas(w,h)]
    return c
