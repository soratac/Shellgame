import json
import os
import socket
import sys
import signal
from pathlib import Path

SOCKET = os.environ.get("FROST_SOCKET", "/run/frost/game.sock")


def request(action="status", args=(), **kwargs):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.connect(SOCKET)
        sock.sendall(json.dumps({"action": action, "args": list(args), **kwargs}).encode() + b"\n")
        with sock.makefile("rb") as stream:
            return json.loads(stream.readline(65536))


def area():
    try:
        parts = Path.cwd().resolve().relative_to(Path.home() / "welt").parts
        return parts[0] if parts else None
    except (ValueError, OSError):
        return None


def sync_files():
    from .items import ITEMS, DELIVERIES, MOVE_ITEMS, script
    bag = Path.home() / "rucksack"
    found = []
    for name in ITEMS:
        try:
            with (bag/name).open("r", encoding="utf-8") as f:
                source = Path.home()/"welt"/ITEMS[name][0]
                if f.read(2048) == script(name) and (name not in MOVE_ITEMS or not source.exists()):
                    found.append(name)
        except (OSError, UnicodeError):
            pass
    request("bag", found)
    for place, filename in DELIVERIES.items():
        try:
            with (Path.home()/"welt"/place/"abgabe"/filename).open(encoding="utf-8", errors="replace") as f:
                content = f.read(8192)
        except OSError:
            continue
        request("deliver", [place], content=content)


def check_travel():
    state=request()["state"]
    if state["status"]!="playing": return 0
    location=area()
    if state.get("boss_started"):
        if location!="zitadelle":
            print("Das Tor ist zu. Kein Rueckweg im Bosskampf; neu anfangen: neustart")
            return 44
        return 0
    return 0


def main():
    args = sys.argv[1:]
    action = args.pop(0) if args else "status"
    if action == "music":
        from .music import controls
        return controls(args)
    if action == "activity":
        from .activity import bounded_command, MAX_COMMAND
        request("activity", [bounded_command(sys.stdin.read(MAX_COMMAND+1))])
        return 0
    if action == "boss-arrive":
        from .trail import BOSS_IP
        result = request("connect", [BOSS_IP])
        print("GRINCH" if result["ok"] else result["message"])
        return 0 if result["ok"] else 1
    if action == "boss-ssh":
        from .trail import BOSS_IP, discovered
        from .dialogs import confirm_boss
        import subprocess
        state = request()["state"]
        if state["status"] != "playing" or state["boss_started"]:
            print("Du bist bereits im Kampf oder die Runde ist beendet.")
            return 1
        if not discovered(state):
            print("Suche zuerst die Spur auf der Karte.")
            return 1
        if not confirm_boss(state):
            return 1
        sync_files()
        handshake = subprocess.run(["/usr/bin/ssh", "-F", "/etc/frost/boss_client", BOSS_IP],
                                   stdout=subprocess.PIPE, text=True)
        if handshake.returncode or handshake.stdout.strip() != "GRINCH":
            print("Grinch antwortet nicht.")
            return 1
        return 0
    if action == "travel": return check_travel()
    if action == "finish":
        from .finish import maybe_show
        maybe_show()
        return 0
    kwargs = {}
    quiet = action == "observe"
    if quiet:
        kwargs = dict(cwd=area(), code=int(args[0]) if args else 0, command=args[1][:500] if len(args) > 1 else "", prompt=args[2:]==["--prompt"])
        args = []
    if action in ("collect", "submit"):
        if len(args) != 1:
            print("Bitte eine Datei angeben.")
            return 1
        path = Path(args[0])
        if not path.is_file():
            print("Datei nicht gefunden. ls oder find helfen dir.")
            return 1
        if action == "submit":
            with path.open(encoding="utf-8", errors="replace") as source:
                kwargs["content"] = source.read(8192)
    if action in ("scan", "collect", "submit", "heal", "cast", "attack", "unload", "use"):
        travel=check_travel()
        if travel==43:
            if action=="use":
                signal.signal(signal.SIGINT,signal.SIG_DFL)
                os.kill(os.getpid(),signal.SIGINT)
            return 42
        # Also covers `builtin cd` and compound shell commands before the next prompt.
        request("observe", cwd=area())
        sync_files()
    result = request(action, args, **kwargs)
    if action == "use" and args:
        from .items import ITEMS
        item=args[0]
        state=result["state"]
        if item in ITEMS and (state["spells"].get(item)==0 or "heal:"+item in state["rewards"]):
            (Path.home()/"rucksack"/item).unlink(missing_ok=True)
    if quiet and result["state"]["status"] == "playing":
        sync_files()
    if action == "map":
        from .render import static_map
        print(static_map(result["state"]))
    elif not quiet and result["message"]:
        print(result["message"])
    # Bash wrapper interrupts the current loop when a run ends.
    if result.get("stop"):
        if action == "use":
            # Bash treats a foreground executable killed by SIGINT like Ctrl-C:
            # it stops a surrounding while loop, without signalling other jobs.
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGINT)
        return 42
    # Game errors already incur their own counterattack; do not double-charge in PROMPT_COMMAND.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as exc:
        print("Frostbyte ist gerade nicht erreichbar: " + str(exc), file=sys.stderr)
        sys.exit(1)
