"""Play the lead of Schneefunken over the terminal's DECPS sound channel."""
import os

from .compose import SCORE, STEP


def melody():
    steps = [value for _, bar in SCORE for value in bar.split()]
    notes = []
    for i, value in enumerate(steps):
        if value in ("-", "."):
            notes.append(None)
            continue
        pitch = int(value)
        while pitch < 72:
            pitch += 12
        length = 1
        while i+length < len(steps) and steps[i+length] == "-":
            length += 1
        notes.append((pitch-71, round(length*STEP*29)))
    return notes


LEAD = melody()
EFFECT = {"funke": (8,17), "frost": (20,15), "stern": (13,25), "schild": (5,12),
          "ping": (18,18), "staff": (4,1), "kakao": (6,10), "beeren": (5,9),
          "disable": (11,3), "frost_armor": (23,7), "blizzard": (21,4), "loop": (1,25),
          "ice_lock": (16,16), "parry": (10,15), "gale": (13,3), "claw": (6,2)}


class TerminalTune:
    def __init__(self, start):
        self.start = start
        self.last_step = -1

    def packet(self, now, level, sounds=()):
        step = int((now-self.start)/STEP)
        changed = step != self.last_step
        self.last_step = step
        if not level:
            return b""
        volume = max(1, round(level*7/100))
        if sounds:
            return b"".join(f"\x1b[{volume};2;{a};{b},~".encode()
                            for sound in sounds for a,b in (EFFECT[sound],))
        note = LEAD[step % len(LEAD)]
        if changed and note:
            pitch, duration = note
            return f"\x1b[{volume};{duration};{pitch},~".encode()
        return b""

    def play(self, now, level, sounds=()):
        packet = self.packet(now, level, sounds)
        if packet:
            os.write(1, packet)
