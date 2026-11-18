"""Sparse, independently drifting flakes shared by the outdoor terminal scenes."""
from functools import lru_cache
import math
import random


@lru_cache(maxsize=24)
def particles(width, height, studio):
    rng = random.Random(11917*width+463*height+int(studio))
    count = min(300, width*height//(36 if studio else 62))
    return tuple((rng.random()*width, rng.random()*height, rng.uniform(.6,2),
                  rng.uniform(-.35,.45), rng.random()*math.tau, rng.uniform(.18,.55),
                  rng.choices(("·","∙","❄"), (7,3,1))[0]) for _ in range(count))


def flakes(width, height, tick, studio=False):
    for x,y,speed,wind,phase,sway,glyph in particles(width,height,studio):
        yield (int(x+wind*tick+1.4*math.sin(phase+sway*tick))%width,
               int(y+speed*tick)%height,glyph,1 if glyph=="❄" else 12 if glyph=="∙" else 3)
