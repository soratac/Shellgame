"""One shared best time, including records saved by older game versions."""
import math
from .avatar import appearance

LEGACY_KEYS={'normal:classic','normal:loop','speedrun:classic','speedrun:loop','best'}


def bests(records):
    values=[v for k,v in (records or {}).items() if k in LEGACY_KEYS and
            isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0]
    return {'best':min(values)} if values else {}


def migrate(state):
    state["avatar"] = appearance(state.get("avatar", {}))
    state.pop('mode',None)
    state['bests']=bests(state.get('bests'))
    state['version']=5
    return state
