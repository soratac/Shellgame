#!/usr/bin/env python3
"""Play Frostbyte with local browser audio over a single OpenSSH connection."""
import os
import time
from collections import deque
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frost import music_http
from frost.sound.compose import render

PREFIX = b"\x1b]777;frost-"


def relay(stream, output, change, play):
    """A packet can span SSH reads. Pass unrelated terminal bytes through verbatim."""
    pending = b""
    while chunk := stream.read1(65536):
        pending += chunk
        while pending:
            start = pending.find(PREFIX)
            if start < 0:
                keep = min(len(pending), len(PREFIX)-1)
                while keep and not PREFIX.startswith(pending[-keep:]):
                    keep -= 1
                end = len(pending)-keep
                output.write(pending[:end])
                pending = pending[end:]
                break
            output.write(pending[:start])
            pending = pending[start:]
            end = pending.find(b"\x07", len(PREFIX), 56)
            if end < 0 and len(pending)<56:
                break
            field, _, value = pending[len(PREFIX):end].partition(b"=")
            if end >= 0 and field == b"volume" and len(value)==3 and value.isdigit() and int(value)<=100:
                change(int(value))
            elif end >= 0 and field == b"sound":
                names = value.decode("ascii","replace").split(",")
                if 1<=len(names)<=2 and all(name in music_http.SOUNDS for name in names):
                    play(names)
                else:
                    output.write(pending[:end+1])
            else:
                output.write(pending[:1])
                pending = pending[1:]
                continue
            pending = pending[end+1:]
        output.flush()
    output.write(pending)
    output.flush()


def main():
    if not sys.argv[1:] or not sys.stdin.isatty():
        print("Auf deinem Rechner: python3 scripts/spielmusik.py [-J jump] spiel@HOST")
        return 1
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    key = secrets.token_urlsafe(12)
    board = SimpleNamespace(lock=threading.Lock(), music=music_http.Sessions())
    with tempfile.TemporaryDirectory() as temp:
        track = Path(temp)/"winter.wav"
        render(track)
        with ThreadingHTTPServer(("127.0.0.1",0), music_http.handler_for(board, track)) as server:
            threading.Thread(target=server.serve_forever,daemon=True).start()
            turns = deque(maxlen=24)
            level = 0
            first = True
            def change(volume):
                nonlocal first, level
                level = volume
                with board.lock:
                    board.music.update("local", {"key":key, "volume":volume}, list(turns))
                if first:
                    first = False
                    threading.Thread(target=webbrowser.open, args=(url,),daemon=True).start()
            def play(names):
                turns.append({"at":time.time(),"sounds":names})
                change(level)
            url = f"http://127.0.0.1:{server.server_port}/#{key}"
            print("Musik im Browser: " + url, flush=True)
            env = {**os.environ, "TERM":f"frost-music2-{server.server_port}-{key}"}
            try:
                with subprocess.Popen(["ssh","-tt",*sys.argv[1:]],env=env,stdout=subprocess.PIPE) as ssh:
                    try:
                        relay(ssh.stdout, sys.stdout.buffer, change, play)
                    except BaseException:
                        ssh.terminate()
                        raise
                    return ssh.wait()
            finally:
                server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
