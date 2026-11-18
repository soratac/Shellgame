import curses
import fcntl
import os
import re
import subprocess
import time
import sys
from pathlib import Path

from .client import request
from .render import colors, put


FIELDS = (("Name", None), ("Geschlecht", "gender"), ("Haartyp", "style"),
          ("Haarfarbe", "hair"), ("Shirtfarbe", "shirt"))


def draw_editor(screen, name, avatar, field, existing, tick, changed, error):
    from .render import box, cell_width, fit
    from .showcase import blit, button, studio, wordmark
    screen.erase()
    rows, cols = screen.getmaxyx()
    width, height = min(92, cols-1), min(31, rows)
    left, top = (cols-width)//2, (rows-height)//2
    box(screen, top, left, height, width, 12)
    logo_width = width-2 if height >= 18 else min(54, width-2)
    logo_height = wordmark(screen, top+1, left+(width-logo_width)//2, logo_width, tick)
    heading = top+logo_height+2
    put(screen, heading, left+3, "❄ CHARAKTER", 2, True)
    footer = top+height-3
    base = heading+2
    space = max(1, footer-base-1)
    spacing = min(3, max(1, space//len(FIELDS)))
    visible = min(len(FIELDS), (space-1)//spacing+1)
    first = max(0, field-visible+1)
    preview = width >= 56 and height >= 14
    panel = min(43, width//2) if preview else width-2
    if preview:
        divider = left+panel+1
        pw, ph = width-panel-4, footer-heading
        for y in range(heading, footer):
            put(screen, y, divider, "│", 3)
        blit(screen, studio(pw, ph, avatar, tick, changed), heading, divider+1)
    hits = {}
    x = left+3
    for i in range(first, first+visible):
        label, part = FIELDS[i]
        row = base+(i-first)*spacing
        focus = i == field
        tint = 5 if focus else 1
        put(screen, row, x, ("› " if focus else "  ")+label, tint, focus)
        value_x = x+13
        right = left+panel-1
        if part:
            value = fit(avatar[part], max(1, right-value_x-3), center=True)
            put(screen, row, value_x, "‹", 2, True)
            put(screen, row, value_x+2, value, tint, focus)
            put(screen, row, right, "›", 2, True)
        else:
            value = name+("▏" if focus and int(tick*2)%2 == 0 else "")
            available = max(1, right-value_x+1)
            while cell_width(value) > available:
                value = value[1:]
            put(screen, row, value_x, value, tint, focus)
        hits[row] = (i, x, right, value_x)
    action = "↵  Übernehmen" if existing else "↵  Spielen"
    target = button(screen, footer, left+max(1,(width-len(action)-4)//2), action)
    if error:
        put(screen, footer+1, left+2, fit(error, width-4, center=True), 6)
    screen.refresh()
    return hits, footer, target


def name_dialog(screen):
    from .avatar import OPTIONS, appearance
    from .showcase import enable_buttons, mouse_press
    colors()
    enable_buttons(screen)
    state = request()["state"]
    name = state["name"]
    existing = bool(name)
    avatar = appearance(state.get("avatar", {}))
    field = 1 if existing else 0
    started = time.monotonic()
    last_change = started-1
    error = ""
    screen.timeout(130)
    while True:
        now = time.monotonic()
        hits, footer, target = draw_editor(screen, name, avatar, field, existing,
                                            now-started, now-last_change, error)
        try:
            key = screen.get_wch()
        except curses.error:
            continue
        if key == curses.KEY_MOUSE:
            pos = mouse_press()
            if not pos:
                continue
            x, y = pos
            if y == footer and x in target:
                key = curses.KEY_ENTER
            elif y in hits:
                index, start, end, arrows = hits[y]
                if start <= x <= end and (index or not existing):
                    field = index
                    if index and x >= arrows:
                        key = curses.KEY_LEFT if x < arrows+2 else curses.KEY_RIGHT
        if key in ("\n", "\r", curses.KEY_ENTER):
            if not existing:
                if not request("name", [name])["ok"]:
                    error = "Name braucht 2–20 Zeichen."
                    field = 0
                    continue
                existing = True
            result = request("avatar", [avatar[k] for k in OPTIONS])
            if result["ok"]:
                return
            error = "Speichern fehlgeschlagen. Erneut bestätigen."
        elif key in ("\t", curses.KEY_DOWN, curses.KEY_UP, curses.KEY_BTAB):
            first = 1 if existing else 0
            step = -1 if key in (curses.KEY_UP, curses.KEY_BTAB) else 1
            field = first+(field-first+step)%(len(FIELDS)-first)
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT) and field:
            part = FIELDS[field][1]
            options = list(OPTIONS[part])
            step = 1 if key == curses.KEY_RIGHT else -1
            avatar[part] = options[(options.index(avatar[part])+step)%len(options)]
            last_change = now
        elif key in ("\x03", "\x1b"):
            raise KeyboardInterrupt
        elif field == 0 and not existing:
            if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
                name = name[:-1]
                error = ""
            elif isinstance(key, str) and (key.isalnum() or key in " _-") and len(name)<20:
                name += key
                error = ""


def edit_avatar():
    from .terminal import fullscreen
    with fullscreen(mouse=True):
        curses.wrapper(name_dialog)


def main():
    if not sys.stdin.isatty():
        print("Bitte ein Terminal anfordern: ssh -t -p PORT player@HOST")
        return 1
    role=Path("/run/frost/role").read_text().strip()
    if role=="gateway":
        from .gateway_client import main as join
        return join()
    audio = re.fullmatch(r"frost-music(2?)-(\d{1,5})-([A-Za-z0-9_-]{16})", os.environ.get("TERM",""))
    if audio and 0 < int(audio[2]) <= 65535:
        os.environ["TERM"] = "xterm-256color"
        if audio[1]: os.environ["FROST_LOCAL_SFX"] = "1"
        os.environ["FROST_LOCAL_MUSIC"] = f"http://127.0.0.1:{audio[2]}/#{audio[3]}"
    if role=="scoreboard":
        from .board import watch
        watch()
        return 0
    lock=open("/tmp/frost-login.lock","w")
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print("Dieser Spielerplatz hat bereits eine aktive SSH-Verbindung.")
        return 1
    state=request()["state"]
    if not state["name"] or not state.get("avatar_set"):
        curses.wrapper(name_dialog)
    subprocess.run([sys.executable,"-m","frost.world","init"],check=True)
    from .terminal import main as terminal
    terminal()
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: pass
