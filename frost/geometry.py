"""Terminal triangle rasterizer and shared mesh primitives."""
import math


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.cells = [[(" ", 1) for _ in range(w)] for _ in range(h)]
        self.depth = [[float("inf")] * w for _ in range(h)]

    def put(self, x, y, value, color=1):
        if 0 <= y < self.h:
            for i, char in enumerate(value):
                if 0 <= x+i < self.w:
                    self.cells[y][x+i] = (char, color)

    def line(self, x0, y0, x1, y1, char="·", color=3):
        steps = max(abs(x1-x0), abs(y1-y0), 1)
        for i in range(steps+1):
            self.put(round(x0+(x1-x0)*i/steps), round(y0+(y1-y0)*i/steps), char, color)


def cube(cx, cy, cz, sx, sy, sz, color):
    v = [(cx+dx*sx/2, cy+dy*sy/2, cz+dz*sz/2) for dx,dy,dz in
         [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    return [(v[a],v[b],v[c],color) for a,b,c in
            [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
             (3,7,6),(3,6,2),(0,4,7),(0,7,3),(1,2,6),(1,6,5)]]


def cone(cx, cy, cz, radius, height, color):
    bottom = [(cx+math.cos(i*math.pi/3)*radius, cy, cz+math.sin(i*math.pi/3)*radius) for i in range(6)]
    return [(bottom[i], bottom[(i+1)%6], (cx,cy+height,cz), color) for i in range(6)]


def beast_segment(base, tip, lower, upper, color):
    """Tapered elliptical rings form sloping shoulders, bent limbs and sharp tips."""
    rings = []
    for (cx,cy,cz),(rx,rz) in ((base,lower),(tip,upper)):
        rings.append([(cx+rx*math.cos(a*math.tau/8),cy,cz+rz*math.sin(a*math.tau/8))
                      for a in range(8)])
    lo,hi = rings
    mesh = []
    for a in range(8):
        b=(a+1)%8
        mesh.extend(((lo[a],lo[b],hi[a],color),(hi[a],lo[b],hi[b],color),
                     (tip,hi[a],hi[b],color),(base,lo[b],lo[a],color)))
    return mesh


def overlay(canvas, layer, left, top, flash=None):
    for y,row in enumerate(layer.cells):
        for x,(char,color) in enumerate(row):
            if char != " ": canvas.put(left+x,top+y,char,flash or color)


def projector(w,h,angle,extent):
    ca, sa = math.cos(angle), math.sin(angle)
    scale = max(2, min(h/extent, w/7.2))

    def project(v):
        x,y,z = v
        x,z = x*ca+z*sa, -x*sa+z*ca
        depth = z + 5
        return (w/2+x*scale*8/depth, h*.56-y*scale*4/depth, depth)

    return project


def project_mesh(w,h,angle,mesh,extent=3.1,project=None):
    c = Canvas(w,h)
    if project is None: project = projector(w,h,angle,extent)
    for a,b,d,color in mesh:
        p,q,r = project(a), project(b), project(d)
        denominator = (q[1]-r[1])*(p[0]-r[0])+(r[0]-q[0])*(p[1]-r[1])
        if abs(denominator) < 0.001:
            continue
        edge1 = tuple(b[i]-a[i] for i in range(3))
        edge2 = tuple(d[i]-a[i] for i in range(3))
        normal = (edge1[1]*edge2[2]-edge1[2]*edge2[1], edge1[2]*edge2[0]-edge1[0]*edge2[2], edge1[0]*edge2[1]-edge1[1]*edge2[0])
        norm = math.sqrt(sum(x*x for x in normal)) or 1
        shade = abs((normal[0]*.4+normal[1]*.6-normal[2]*.7)/norm)
        char = "░▒▓█"[min(3, int(shade*3.5))]
        for y in range(max(0,int(min(p[1],q[1],r[1]))), min(h,int(max(p[1],q[1],r[1]))+1)):
            for x in range(max(0,int(min(p[0],q[0],r[0]))), min(w,int(max(p[0],q[0],r[0]))+1)):
                u = ((q[1]-r[1])*(x-r[0])+(r[0]-q[0])*(y-r[1]))/denominator
                v = ((r[1]-p[1])*(x-r[0])+(p[0]-r[0])*(y-r[1]))/denominator
                t = 1-u-v
                if min(u,v,t) >= 0:
                    z = 1/(u/p[2]+v/q[2]+t/r[2])
                    if z < c.depth[y][x]:
                        c.depth[y][x] = z
                        c.cells[y][x] = (char, color)
    return c
