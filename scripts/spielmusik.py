#!/usr/bin/env python3
"""Play Frostbyte with local browser audio over a single OpenSSH connection."""
import os
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

PREFIX = b"\x1b]777;frost-volume="


def relay(stream, output, change):
    """Consume only complete volume messages; forward every other terminal byte."""
    pending = b""
    while chunk := stream.read1(65536):
        pending += chunk
        while pending:
            index = pending.find(PREFIX)
            if index < 0:
                keep = min(len(pending), len(PREFIX)-1)
                while keep and not PREFIX.startswith(pending[-keep:]):
                    keep -= 1
                end = len(pending)-keep
                output.write(pending[:end])
                pending = pending[end:]
                break
            output.write(pending[:index])
            pending = pending[index:]
            if len(pending) < len(PREFIX)+4:
                break
            value = pending[len(PREFIX):len(PREFIX)+3]
            if value.isdigit() and int(value)<=100 and pending[len(PREFIX)+3]==7:
                change(int(value))
                pending = pending[len(PREFIX)+4:]
            else:
                output.write(pending[:1])
                pending = pending[1:]
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
            first = True
            def change(volume):
                nonlocal first
                with board.lock:
                    board.music.update("local", {"key":key, "volume":volume})
                if first:
                    first = False
                    threading.Thread(target=webbrowser.open, args=(url,),daemon=True).start()
            url = f"http://127.0.0.1:{server.server_port}/#{key}"
            print("Musik im Browser: " + url, flush=True)
            env = {**os.environ, "TERM":f"frost-music-{server.server_port}-{key}"}
            try:
                with subprocess.Popen(["ssh","-tt",*sys.argv[1:]],env=env,stdout=subprocess.PIPE) as ssh:
                    try:
                        relay(ssh.stdout, sys.stdout.buffer, change)
                    except BaseException:
                        ssh.terminate()
                        raise
                    return ssh.wait()
            finally:
                server.shutdown()


if __name__ == "__main__":
    sys.exit(main())
