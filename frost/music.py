"""Per-login music controls. The browser receives only the effective volume."""
import os
import re
import secrets
import select
import sys
import termios
import tty
import urllib.request


class Mixer:
    def __init__(self):
        self.key = None
        self.level = 40
        self.muted = False

    def adjust(self, command):
        if command == "open":
            self.key = self.key or secrets.token_urlsafe(12)
        elif command == "close":
            self.__init__()
        elif command == "mute":
            self.muted = not self.muted
        elif command in ("+", "-"):
            self.level = max(0, min(100, self.level + (10 if command == "+" else -10)))
        elif re.fullmatch(r"\d{1,3}", command) and int(command) <= 100:
            self.level = int(command)
        else:
            raise ValueError("musik [mute | + | - | 0–100]")
        return self.display()

    def display(self):
        return {"level": self.level, "muted": self.muted}

    def broadcast(self):
        if self.key:
            return {"key": self.key, "volume": 0 if self.muted else self.level}


def mixer_buttons(mixer):
    label="stumm" if mixer["muted"] else f"{mixer['level']}%"
    return (("♪ Musik","open"), ("[−]","-"), (f"[{label}]","mute"), ("[+]","+"))


def indicator(mixer):
    return " ".join(label for label,_ in mixer_buttons(mixer))


def mixer_action(mixer, cols, x):
    start=cols-3-len(indicator(mixer))
    if start<1: return None
    for label,action in mixer_buttons(mixer):
        if start<=x<start+len(label): return action
        start+=len(label)+1


def music_link():
    from .client import request
    url = os.environ.get("FROST_LOCAL_MUSIC")
    if not url:
        base = os.environ.get("SCORE_URL", "http://scoreboard:8080")
        with urllib.request.urlopen(base + "/api/music-url", timeout=3) as response:
            address = response.read(2048).decode().strip()
        session = request("music", ["open"])
        url = f"{address}/#{session['key']}"
    return url


def controls(args):
    from .client import request
    native = bool(os.environ.get("FROST_NATIVE_AUDIO"))
    if args == ["link"] and native:
        print("Terminalton aktiv · musik mute / musik 0–100")
        return 0
    if args == ["link"]:
        print("Ton im Browser starten: "+music_link(),flush=True)
        return 0
    if args:
        result = request("music", args)
        print(indicator(result["music"]) if result["ok"] else result["message"])
        return 0 if result["ok"] else 1
    if native:
        print("Terminalton aktiv", flush=True)
    else:
        print(f"Im Browser öffnen und ▶ drücken:\n{music_link()}", flush=True)
    if not sys.stdin.isatty():
        return 0
    print("← → Lautstärke   M stumm   Enter zurück", flush=True)
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = os.read(fd, 1)
            if not key or key in (b"\r", b"\n", b"q"):
                break
            if key == b"\x1b":
                for _ in range(2):
                    if not select.select([fd], [], [], .15)[0]:
                        break
                    key += os.read(fd, 1)
                if key == b"\x1b":
                    break
            action = {b"\x1b[D": "-", b"\x1bOD": "-", b"-": "-", b"\x1b[C": "+",
                      b"\x1bOC": "+", b"+": "+", b"m": "mute", b"M": "mute"}.get(key)
            if action:
                request("music", [action])
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
    return 0
