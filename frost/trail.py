"""Krampus uses a loopback address inside each player's own container."""
from hashlib import sha256

BOSS_IP = "127.12.24.1"
HIDING_PLACES = ("wald", "werkstatt", "archiv")


def hiding_place(state):
    seed = f"{state['name']}:{state['started']}".encode()
    return HIDING_PLACES[sha256(seed).digest()[0] % len(HIDING_PLACES)]


def discovered(state):
    return state.get("boss_started") or hiding_place(state) in state["visited"]
