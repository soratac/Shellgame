"""One authoritative state owner per player container; socket for the shell UI."""
import json
import os
import signal
import socket
import socketserver
import struct
import threading
import time
import urllib.request
from pathlib import Path

from .engine import act, fresh, public

STATE_DIR = Path(os.environ.get("FROST_STATE", "/var/lib/frost"))
SOCKET = os.environ.get("FROST_SOCKET", "/run/frost/game.sock")
LOCK = threading.RLock()
DIRTY = threading.Event()
STATE = None


def save():
    path = STATE_DIR / "state.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def publish_forever():
    token_file = Path("/run/bootstrap/score_token")
    token = token_file.read_text().strip() if token_file.exists() else ""
    url = os.environ.get("SCORE_URL", "http://scoreboard:8080") + "/api/score"
    while True:
        DIRTY.wait(5)
        DIRTY.clear()
        with LOCK:
            snapshot = public(STATE)
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


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(2)
        try:
            raw = self.rfile.readline(16385)
            if len(raw) > 16384 or not raw.endswith(b"\n"):
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
            with LOCK:
                if action == "admin-reset":
                    peer = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                    uid = struct.unpack("3i", peer)[1]
                    if uid != 0 or args != [STATE["name"]]:
                        result = {"ok": False, "message": "Administrator identity/name check failed.", "stop": False}
                    else:
                        STATE.clear()
                        STATE.update(fresh())
                        result = {"ok": True, "message": "Slot cleared.", "stop": False}
                else:
                    result = act(STATE, action, args, cwd=data.get("cwd"), code=data.get("code", 0),
                                 command=data.get("command", "")[:500], content=data.get("content", "")[:8192])
                if action not in ("status", "map", "inventory", "help", "modules"):
                    save()
                    DIRTY.set()
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
