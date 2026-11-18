"""Read-only companion for audio on the player's own device."""
import re
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ASSETS = Path(__file__).with_name("sound")
FILES = {"/": ("player.html", "text/html; charset=utf-8"),
         "/player.js": ("player.js", "application/javascript"),
         "/winter.wav": ("winter.wav", "audio/wav")}
KEY = re.compile(r"[a-zA-Z0-9_-]{16}")


class Sessions:
    """Called under the board lock. Keys are distinct from game credentials."""
    def __init__(self):
        self.slots = {}

    def update(self, slot, music):
        if (isinstance(music, dict) and isinstance(music.get("key"), str)
                and KEY.fullmatch(music["key"]) and type(music.get("volume")) is int
                and 0 <= music["volume"] <= 100):
            self.slots[slot] = (music["key"], music["volume"], time.monotonic())
        else:
            self.slots.pop(slot, None)

    def volume(self, key):
        now = time.monotonic()
        for slot, (saved, volume, updated) in list(self.slots.items()):
            if now - updated >= 8:
                del self.slots[slot]
            elif saved == key:
                return volume


def handler_for(board):
    class MusicHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path in FILES:
                name, kind = FILES[self.path]
                body = (ASSETS / name).read_bytes()
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
            previous = -1
            heartbeat = time.monotonic()
            try:
                while True:
                    with board.lock:
                        volume = board.music.volume(key)
                    if volume is None:
                        self.wfile.write(b"data: null\n\n")
                        return
                    if volume != previous:
                        self.wfile.write(f"data: {volume}\n\n".encode())
                        previous = volume
                    elif time.monotonic() >= heartbeat:
                        self.wfile.write(b": heartbeat\n\n")
                        heartbeat = time.monotonic() + 3
                    time.sleep(.25)
            except OSError:
                pass
    return MusicHandler
