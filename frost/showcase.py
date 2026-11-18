"""Terminal artwork shared by the character studio and the Winterfest finale."""
import curses
import math
from functools import lru_cache
from itertools import groupby

from .avatar import HAIR, SHIRTS
from .geometry import Canvas, beast_segment, overlay, project_mesh
from .render import hero_mesh, put
from .spell_art import crystal, medal


# Seven-row carved capitals. Two vertical pixels share one terminal cell.
LETTERS = {
    "F": ("11111","11000","11000","11110","11000","11000","11000"),
    "R": ("11110","11011","11011","11110","11100","11010","11001"),
    "O": ("01110","11011","11011","11011","11011","11011","01110"),
    "S": ("01111","11000","11000","01110","00011","00011","11110"),
    "T": ("11111","11111","00100","00100","00100","00100","00100"),
    "B": ("11110","11011","11011","11110","11011","11011","11110"),
    "Y": ("10001","11011","01010","00100","00100","00100","00100"),
    "E": ("11111","11000","11000","11110","11000","11000","11111"),
}


def wordmark(screen,y,x,width,tick):
    if width<55:
        put(screen,y,x+(width-9)//2,"FROSTBYTE",2,True)
        return 1
    left=x+(width-53)//2
    glint=int(tick*9)%78-12
    for i,letter in enumerate("FROSTBYTE"):
        rows=LETTERS[letter]+("00000",)
        for row in range(4):
            for col in range(5):
                bits=int(rows[row*2][col])+2*int(rows[row*2+1][col])
                if bits:
                    at=i*6+col
                    tint=1 if abs(at+row-glint)<2 else (1,2,2,12)[row]
                    put(screen,y+row,left+at," ▀▄█"[bits],tint,True)
    return 4


def studio_frame(screen, top, left, height, width, tick):
    rows, cols = screen.getmaxyx()
    bottom, right = top+height-1, left+width-1
    for i in range(rows*cols//32):
        depth = i%3
        drift = int(tick*(.5+depth*.3))
        x = (i*37+drift+i//7) % cols
        y = (i*17+i//5+int(tick*(1+depth*.65))) % rows
        if not (left <= x <= right and top <= y <= bottom):
            put(screen, y, x, ("·","•","❄")[depth], (3,12,1)[depth])
    if width < 3 or height < 2:
        return
    put(screen, top, left, "╔"+"═"*(width-2)+"╗", 1, True)
    put(screen, bottom, left, "╚"+"═"*(width-2)+"╝", 12)
    for row in range(top+1,bottom):
        put(screen, row, left, "║", 1)
        put(screen, row, right, "║", 12)
    for x in (left+1, right-4):
        if width >= 12:
            put(screen, top, x, "═❄═", 2, True)
    glint = int(tick*7)%(width+14)
    if 5 <= glint < width-5:
        put(screen, top, left+glint, "✧", 20, True)


def blit(screen,canvas,y,x):
    for row,cells in enumerate(canvas.cells):
        offset=0
        for (ink,color),group in groupby(cells,lambda cell:(cell[0]!=" ",cell[1])):
            text="".join(char for char,_ in group)
            if ink: put(screen,y+row,x+offset,text,color)
            offset+=len(text)


def mouse_press():
    try:
        _,x,y,_,buttons=curses.getmouse()
        if buttons & (curses.BUTTON1_PRESSED|curses.BUTTON1_CLICKED): return x,y
    except curses.error: pass
    return None


def enable_buttons(screen):
    screen.keypad(True)
    try:
        curses.curs_set(0)
        curses.mouseinterval(0)
        curses.mousemask(curses.BUTTON1_PRESSED)
    except curses.error: pass


def button(screen,y,x,label,color=2):
    text="▐ "+label+" ▌"
    h,w=screen.getmaxyx()
    if 0<=x<w-1 and 0<=y<h:
        try:
            screen.addnstr(y,x,text,w-x-1,curses.color_pair(color)|curses.A_REVERSE|curses.A_BOLD)
        except curses.error:
            pass
    return range(x,min(w-1,x+len(text)))


@lru_cache(maxsize=1)
def pedestal():
    mesh=beast_segment((0,-1.66,0),(0,-1.48,0),(1.12,.82),(1.38,1.02),11)
    mesh+=beast_segment((0,-1.48,0),(0,-1.38,0),(1.38,1.02),(1.39,1.02),2)
    mesh+=beast_segment((0,-1.38,0),(0,-1.31,0),(1.39,1.02),(1.25,.91),12)
    return mesh


def studio(w,h,avatar,tick,changed):
    ca=math.cos(-.24+.61*math.sin(tick*.9))
    sa=math.sin(-.24+.61*math.sin(tick*.9))
    step=round(math.sin(tick*4.8))
    mesh=hero_mesh(HAIR[avatar["hair"]],SHIRTS[avatar["shirt"]],avatar["gender"],avatar["style"],step)
    scale=min(w*.18,h*.31)
    def camera(point):
        x,y,z=point
        x,z=x*ca+z*sa,-x*sa+z*ca
        d=5+z
        return w*.5+x*scale*8/d,h*.48-(y+.14*z)*scale*4.5/d,d
    c=project_mesh(w,h,0,pedestal()+mesh,project=camera)
    if h>=13:
        blink=tick%3.7>3.52
        for side in (-1,1):
            x,y,_=camera((side*.21,.72,-.47))
            c.put(round(x),round(y),"─" if blink else "•",8)
    for i in range(7):
        a=tick*.71+i*math.tau/7
        x=round(w*.5+math.cos(a)*w*.36)
        y=round(h*.68+math.sin(a)*h*.13)
        if 0<=x<w and 0<=y<h and (c.cells[y][x][0]==" " or math.sin(a)>.75):
            c.put(x,y,"✧" if i%3==0 else "·",2 if i%3 else 5)
    if 0<=changed<.65:
        for i in range(9):
            a=i*math.tau/9
            r=.18+.25*changed/.65
            c.put(round(w*(.5+r*math.cos(a))),round(h*(.46+r*math.sin(a))),"✦" if changed<.32 else "·",5)
    return c


@lru_cache(maxsize=2)
def relic(lit):
    outline=[]
    for i in range(10):
        a=math.pi/2+i*math.pi/5
        radius=1.23 if i%2==0 else .54
        outline.append((radius*math.cos(a),radius*math.sin(a)))
    mesh=medal(outline,5 if lit else 12,.28)
    # Distinct facets meet at the raised jewel. The back and rim are paler ice.
    for i,(x,y) in enumerate(outline):
        xx,yy=outline[(i+1)%10]
        mesh.append(((0,0,-.72),(x*.88,y*.88,-.37),(xx*.88,yy*.88,-.37),
                     (5,15,1,5,15)[i%5] if lit else 3))
    mesh+=crystal(0,0,-.69,.22,.58,1 if lit else 12)
    return mesh


@lru_cache(maxsize=48)
def star(w,h,phase,lit):
    angle=math.sin(phase*math.tau/24)*.50
    return project_mesh(w,h,angle,relic(lit),extent=2.28)


def festival(w,h,tick,won):
    c=Canvas(w,h)
    floor=h-1
    # A distant pine ridge sits behind the village. Lanterns face the viewer.
    for x in range(0,w,3):
        ridge=round(h*.10*(1+math.sin(x*.09)))
        for y in range(floor-ridge,floor):
            c.put(x,y,"▴" if y==floor-ridge else "▐",12)
    for i,x in enumerate(range(-2,w,10)):
        roof=floor-2-i%3
        c.put(x+2,roof-1,"╱▔╲",1)
        c.put(x,roof,"╱▔   ▔╲",12)
        for y in range(roof+1,floor+1):
            c.put(x+1,y,"▐     ▌",11)
            if y==roof+1:
                c.put(x+2,y,"▪  ▪",5 if won else 12)
        c.put(x+3,floor,"▐▌",7)
    for i in range(max(7,w//4)):
        x=(i*29+int(tick*.9))%w
        y=(i*17+int(tick*(.7+i%3)))%h
        if c.cells[y][x][0]==" ": c.put(x,y,"·",12)
    if won:
        for n,origin in enumerate((.16,.83,.30,.68)):
            t=(tick*.34+n*.31)%1
            peak=h*(.12+.12*(n%3))
            cx=w*origin
            if t<.38:
                progress=t/.38
                cy=floor-(floor-peak)*math.sin(progress*math.pi/2)
                for tail in range(3):
                    c.put(round(cx),round(cy)+tail,("♦","│","·")[tail],(1,5,15)[tail])
                continue
            t=(t-.38)/.62
            # Expanding shells of sparks projected at different depths.
            for i in range(36):
                z=1-2*(i+.5)/36
                a=i*2.39996+n
                radius=math.sqrt(1-z*z)
                spread=math.sin(t*math.pi/2)/(1+.32*z)
                def spark(fraction):
                    return (round(cx+math.cos(a)*radius*spread*w*.145*fraction),
                            round(peak+math.sin(a)*radius*spread*h*.37*fraction+t*t*h*.22))
                x,y=spark(1)
                if t<.72:
                    xx,yy=spark(.84)
                    c.line(xx,yy,x,y,"·",12 if z>0 else 15)
                c.put(x,y,"✧" if z<0 and t<.65 else "·",(5,2,9,6)[n] if t<.83 else 3)
    sw=min(w,max(9,round(h*2.65)))
    overlay(c,star(sw,h,int(tick*5)%24,won),(w-sw)//2,0)
    return c
