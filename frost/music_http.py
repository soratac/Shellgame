"""Read-only companion for audio on the player's own device."""
import json
import re
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ASSETS = Path(__file__).with_name("sound")
FILES = {"/": ("player.html", "text/html; charset=utf-8"),
         "/player.js": ("player.js", "application/javascript"),
         "/effects.js": ("effects.js", "application/javascript"),
         "/winter.wav": ("winter.wav", "audio/wav")}
KEY = re.compile(r"[a-zA-Z0-9_-]{16}")


SOUNDS = frozenset(("funke", "frost", "stern", "schild", "ping", "staff", "kakao", "beeren",
                    "disable", "frost_armor", "blizzard", "loop", "ice_lock", "parry", "gale", "claw", "lance", "charge", "eclipse", "eclipse_guard"))


def recent_sounds(events, after):
    """Heartbeat snapshots repeat. Only emit new, recent turns from this player."""
    now = time.time()
    if not isinstance(events,list): return
    for event in events[-24:]:
        if not isinstance(event,dict): continue
        at, sounds = event.get("at"), event.get("sounds")
        if (isinstance(at,(float,int)) and max(after, now-2) < at <= now
                and isinstance(sounds,list) and 1 <= len(sounds) <= 2
                and all(isinstance(name,str) and name in SOUNDS for name in sounds)):
            yield at, sounds


class Sessions:
    """Called under the board lock. Keys are distinct from game credentials."""
    def __init__(self):
        self.slots = {}

    def update(self, slot, music, events=None):
        if (isinstance(music, dict) and isinstance(music.get("key"), str)
                and KEY.fullmatch(music["key"]) and type(music.get("volume")) is int
                and 0 <= music["volume"] <= 100):
            self.slots[slot] = (music["key"], music["volume"], time.monotonic(), list(recent_sounds(events, 0)))
        else:
            self.slots.pop(slot, None)

    def session(self, key):
        now = time.monotonic()
        for slot, (saved, volume, updated, turns) in list(self.slots.items()):
            if now - updated >= 8:
                del self.slots[slot]
            elif saved == key:
                return volume, turns


def handler_for(board, track=ASSETS / "winter.wav"):
    class MusicHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path in FILES:
                name, kind = FILES[self.path]
                body = (track if name == "winter.wav" else ASSETS / name).read_bytes()
            elif self.path.startswith("/stream/") and KEY.fullmatch(self.path[8:]):
                return self.stream_volume(self.path[8:])
            else:
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def stream_volume(self, key):
            self.connection.settimeout(4)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last_sound = time.time()
            previous = -1
            heartbeat = time.monotonic()
            try:
                while True:
                    with board.lock:
                        session = board.music.session(key)
                    if session is None:
                        self.wfile.write(b"data: null\n\n")
                        return
                    volume, turns = session
                    if volume != previous:
                        self.wfile.write(f"data: {volume}\n\n".encode())
                        previous = volume
                    elif time.monotonic() >= heartbeat:
                        self.wfile.write(b": heartbeat\n\n")
                        heartbeat = time.monotonic() + 3
                    for at, sounds in turns:
                        if at > last_sound:
                            if volume:
                                self.wfile.write(b"event: attack\ndata: "+json.dumps(sounds).encode()+b"\n\n")
                            last_sound = at
                    time.sleep(.10)
            except OSError:
                pass
    return MusicHandler
