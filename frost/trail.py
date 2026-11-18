"""Krampus uses a loopback address inside each player's own container."""
from hashlib import sha256
import time

BOSS_IP = "127.12.24.1"
HIDING_PLACES = ("wald", "werkstatt", "archiv")


def hiding_place(state, now=None):
    seed = f"{state['name']}:{state['started']}".encode()
    elapsed = max(0, (time.time() if now is None else now) - state["started"])
    leg = int(elapsed // 60)
    return HIDING_PLACES[(sha256(seed).digest()[0] + leg) % len(HIDING_PLACES)]


def discovered(state):
    return state.get("boss_started") or state.get("grinch_found", False)
