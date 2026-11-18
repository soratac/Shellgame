"""Winter trail map with five landmarks."""
from functools import lru_cache

from .geometry import Canvas, cube, cone, overlay, project_mesh

POSITIONS = {"zitadelle": (.50,.05), "wald": (.13,.39), "archiv": (.86,.39),
             "dorf": (.28,.90), "werkstatt": (.71,.90)}
PATHS = (("dorf","wald"), ("dorf","werkstatt"), ("werkstatt","archiv"),
         ("wald","zitadelle"), ("archiv","zitadelle"))


def snowy_roof(width, depth, eave, ridge):
    mesh=[]
    for side in (-1,1):
        a,b=(side*width,eave,-depth),(side*width,eave,depth)
        c,d=(0,ridge,depth),(0,ridge,-depth)
        mesh.extend(((a,b,c,1),(a,c,d,20)))
    for side in (-1,1):
        z=-depth-.04
        a,b=(side*width,eave,z),(0,ridge,z)
        c,d=(0,ridge-.18,z),(side*width,eave-.16,z)
        mesh.extend(((a,b,c,20),(a,c,d,1)))
    for z in (-depth,depth):
        mesh.append(((-width,eave,z),(width,eave,z),(0,ridge,z),7))
    return mesh


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
        for x in (-.8,.8):
            mesh+=cube(x,.20,-.37,.19,.36,.09,5)
        mesh+=cube(0,.29,-.55,1.25,.14,.22,20)
    elif place=="archiv":
        mesh=cube(0,-.23,.1,1.9,1.05,1.0,9)+snowy_roof(1.13,.66,.36,.96)
        mesh+=cube(0,-.50,-.43,.38,.55,.20,5)
        for x in (-.72,-.24,.24,.72): mesh+=cube(x,-.21,-.58,.16,1,.22,1)
    else:
        mesh=cube(0,-.25,0,1.65,1.0,1.15,wood)+snowy_roof(1.02,.72,.25,1.04)
        for x in (-.52,.52): mesh+=cube(x,-.24,-.60,.28,.35,.08,window)
        if place=="werkstatt": mesh+=cube(.68,.62,.18,.34,1.36,.34,6)
        else:
            mesh+=cube(0,-.46,-.62,.32,.55,.1,6)
            mesh+=cube(-.94,-.48,.30,.65,.62,.83,wood)+cube(-.94,-.12,.30,.81,.14,.99,20)
        mesh+=cube(0,.48,-.74,.25,.23,.07,5)
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
    height=max(3,min(8,h//4+1))
    # At small scales rasterized windows disappear. Keep recognizable silhouettes.
    icons={"dorf":(("◢◣◢◣",20),("▐▪▥▌",5)), "wald":((" ▲▲ ",4),("▲┴▲┴",19)),
           "archiv":(("◢▀▀◣",20),("╫▥▥╫",9)), "werkstatt":(("╻◢▀◣",20),("▐▥⚙▌",5)),
           "zitadelle":(("♜▔▔♜",20),("▐█∩▌",9))}
    for name,(x,y) in centers.items():
        if h>=14 and w>=46:
            icon=project_mesh(height*3,height,-.35,landmark_mesh(name),extent=1.85)
            overlay(c,icon,x-icon.w//2,max(0,y-height//2))
        else:
            for line,(art,tint) in enumerate(icons[name]):
                c.put(x-2,max(0,y-1)+line,art,tint)
    return c.cells


def atlas_frame(w,h):
    c=Canvas(w,h)
    c.cells=[row.copy() for row in atlas(w,h)]
    return c
