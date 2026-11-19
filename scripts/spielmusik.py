#!/usr/bin/env python3
"""Play Frostbyte with local terminal audio over one OpenSSH connection."""
from contextlib import ExitStack
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from frost.music_http import SOUNDS
from frost.sound.native import Output

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
                if 1<=len(names)<=2 and all(name in SOUNDS for name in names):
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
    try:
        with ExitStack() as stack:
            ssh_command = ["ssh","-tt",*sys.argv[1:]]
            try:
                mixer = stack.enter_context(Output())
            except OSError:
                os.execvp("ssh", ssh_command)
            env = {**os.environ, "TERM":"frost-audio"}
            with subprocess.Popen(ssh_command,env=env,stdout=subprocess.PIPE) as ssh:
                try:
                    relay(ssh.stdout,sys.stdout.buffer,mixer.change,mixer.play)
                    return ssh.wait()
                except BaseException:
                    ssh.terminate()
                    try: ssh.wait(timeout=2)
                    except subprocess.TimeoutExpired: ssh.kill()
                    raise
    except OSError as exc:
        print(str(exc),file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
