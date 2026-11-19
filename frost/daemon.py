"""One authoritative state owner per player container; socket for the shell UI."""
import fcntl
import json
import os
import signal
import socket
import socketserver
import struct
import threading
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

from .activity import Activity, MAX_COMMAND
from .engine import act, fresh, public
from .records import migrate
from .music import Mixer

STATE_DIR = Path(os.environ.get("FROST_STATE", "/var/lib/frost"))
SOCKET = os.environ.get("FROST_SOCKET", "/run/frost/game.sock")
LOCK = threading.RLock()
DIRTY = threading.Event()
STATE = None
ACTIVITY = Activity()
MIXER = Mixer()


def save():
    path = STATE_DIR / "state.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def connected():
    try:
        with open("/run/frost/login.lock","r") as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return True
    except OSError: pass
    return False


def publish_forever():
    token_file = Path("/run/bootstrap/score_token")
    token = token_file.read_text().strip() if token_file.exists() else ""
    url = os.environ.get("SCORE_URL", "http://scoreboard:8080") + "/api/score"
    while True:
        DIRTY.wait(2)
        DIRTY.clear()
        with LOCK:
            snapshot = public(STATE)
            snapshot["connected"] = connected()
            if not snapshot["connected"]:
                ACTIVITY.clear()
                MIXER.adjust("close")
            snapshot["music"] = MIXER.broadcast()
            snapshot.update(ACTIVITY.snapshot())
        if not token or not snapshot["name"]:
            continue
        try:
            request = urllib.request.Request(url, json.dumps(snapshot).encode(),
                                             headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=2) as response:
                response.read(1024)
        except (OSError, ValueError) as exc:
            print("Scoreboard temporarily unavailable:", type(exc).__name__, flush=True)
        # Coalesce rapid spell-loop events. Gameplay never waits for the board.
        time.sleep(0.15)


@lru_cache(maxsize=1)
def music_url():
    url = os.environ.get("SCORE_URL", "http://scoreboard:8080") + "/api/music-url"
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.read(2048).decode().strip()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        try:
            raw = self.rfile.readline(12*MAX_COMMAND+1025)
            if len(raw) > 12*MAX_COMMAND+1024 or not raw.endswith(b"\n"):
                return
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            action = data.get("action", "status")
            args = data.get("args", [])
            if not isinstance(action, str) or not isinstance(args, list) or len(args) > 8 or any(not isinstance(x, str) for x in args):
                return
            if not isinstance(data.get("content", ""), str) or not isinstance(data.get("command", ""), str):
                return
            if action == "music-url":
                self.wfile.write(json.dumps({"url": music_url()}).encode()+b"\n")
                return
            if action != "activity" and any(len(arg)>128 for arg in args):
                return
            with LOCK:
                peer = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                uid = struct.unpack("3i", peer)[1]
                if action == "music":
                    try:
                        if len(args) != 1:
                            raise ValueError("musik [mute | + | - | 0–100]")
                        result = {"ok": True, "music": MIXER.adjust(args[0]), "key": MIXER.key}
                        DIRTY.set()
                    except ValueError as exc:
                        result = {"ok": False, "message": str(exc)}
                    self.wfile.write(json.dumps(result).encode() + b"\n")
                    return
                if action == "activity":
                    if args: ACTIVITY.begin(args[0])
                    DIRTY.set()
                    self.wfile.write(b'{"ok":true}\n')
                    return
                if action == "observe" and data.get("prompt") is True:
                    ACTIVITY.finish()
                if action == "admin-reset":
                    if uid != 0 or args != [STATE["name"]]:
                        result = {"ok": False, "message": "Administrator identity/name check failed.", "stop": False}
                    else:
                        STATE.clear()
                        STATE.update(fresh())
                        result = {"ok": True, "message": "Slot cleared.", "stop": False}
                elif action == "enter_boss" or (action == "connect" and uid != 1002):
                    result = {"ok":False, "stop":False, "message":"Nutze den SSH-Zugang auf der Karte."}
                else:
                    result = act(STATE, action, args, cwd=data.get("cwd"), code=data.get("code", 0),
                                 command=data.get("command", "")[:500], content=data.get("content", "")[:8192])
                if action not in ("status", "map", "inventory", "help", "modules"):
                    save()
                    DIRTY.set()
                if action == "status":
                    result["music"] = MIXER.display()
                    result["music_link_open"] = MIXER.key is not None
                result["state"] = public(STATE)
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode() + b"\n")
        except (OSError, ValueError, TypeError, KeyError):
            return


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    request_queue_size = 64


def main():
    global STATE
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / "state.json"
    STATE = json.loads(path.read_text()) if path.exists() else fresh()
    migrate(STATE)
    save()
    Path(SOCKET).parent.mkdir(parents=True, exist_ok=True)
    Path(SOCKET).unlink(missing_ok=True)
    with Server(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o666)
        threading.Thread(target=publish_forever, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
        server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
