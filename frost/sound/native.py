"""Mix the local terminal soundtrack and game events into a mono PCM stream."""
import array
from collections import deque
import math
import random
import shutil
import subprocess
import sys
import threading
import time

from .compose import RATE, soundtrack

# Pitch contours in Hz. Separate notes give each item its own attack and rhythm.
PATCHES = {
    "ping": ("bell", .09, (880,880,880,1175)),
    "stern": ("bell", .085, (523,659,784,1047,1568)),
    "frost": ("ice", .075, (2217,1865,2489,1245)),
    "funke": ("crash", .12, (620,310,155)),
    "staff": ("crash", .09, (270,80)),
    "schild": ("hum", .22, (184,493)),
    "kakao": ("hum", .10, (180,226,285)),
    "beeren": ("bell", .10, (587,880,740)),
    "disable": ("pulse", .08, (440,330,220)),
    "frost_armor": ("ice", .09, (155,2600,1900,950)),
    "blizzard": ("wind", .13, (2100,1300,690,320,95)),
    "loop": ("pulse", .055, (262,392,523,784,1047,1568)),
    "ice_lock": ("ice", .065, (2800,1700,700)),
    "parry": ("bell", .07, (940,1413)),
    "claw": ("crash", .075, (380,210,106)),
    "gale": ("wind", .13, (220,520,980,260,82)),
}


def effect(name):
    voice, step, pitches = PATCHES[name]
    noise = random.Random(name)
    samples = array.array("h")
    count = round(step*RATE)
    for hz in pitches:
        phase = 0
        for i in range(count):
            t = i/count
            phase += math.tau*hz*(1-.55*t if voice in ("wind","crash") else 1)/RATE
            sine = math.sin(phase)
            if voice == "bell": value = .7*sine + .3*math.sin(2.01*phase)
            elif voice == "ice": value = .4*sine + .33*math.sin(3.97*phase) + .27*noise.uniform(-1,1)
            elif voice == "crash": value = .48*sine + .52*noise.uniform(-1,1)
            elif voice == "wind": value = (.45*sine+.55*noise.uniform(-1,1))*(.7+.3*math.sin(phase*.13))
            elif voice == "pulse": value = .75 if sine>0 else -.75
            else: value = .8*sine + .2*math.sin(2*phase)
            envelope = min(1,i/(RATE*.005),(count-i)/(RATE*.014))*math.exp(-1.5*t)
            samples.append(round(21000*value*envelope))
    return samples


class Mix:
    def __init__(self):
        self.track = soundtrack()
        self.effects = {name:effect(name) for name in PATCHES}
        self.position = 0
        self.level = 40
        self.voices = deque(maxlen=12)
        self.lock = threading.Lock()

    def change(self, level):
        with self.lock:
            self.level = level
            if not level: self.voices.clear()

    def play(self, names):
        with self.lock:
            if self.level:
                for i,name in enumerate(names):
                    self.voices.append((self.effects[name], -round(i*.55*RATE)))

    def block(self, size):
        with self.lock:
            start = self.position
            n = len(self.track)
            self.position = (start+size)%n
            if not self.level: return bytes(size*2)
            values = [self.track[(start+i)%n]*.43 for i in range(size)]
            for _ in range(len(self.voices)):
                sound, offset = self.voices.popleft()
                for i in range(max(0,-offset),min(size,len(sound)-offset)):
                    values[i] += sound[offset+i]
                if offset+size<len(sound):
                    self.voices.append((sound, offset+size))
            gain = self.level/100
        pcm = array.array("h",(max(-32768,min(32767,round(v*gain))) for v in values))
        if sys.byteorder!="little": pcm.byteswap()
        return pcm.tobytes()


def output_commands():
    for name,args in (
        ("aplay", ["-q","-t","raw","-f","S16_LE","-c","1","-r",str(RATE),"--buffer-time=60000"]),
        ("paplay", ["--raw","--format=s16le","--channels=1","--rate="+str(RATE),"--latency-msec=60"]),
        ("play", ["-q","-t","raw","-e","signed-integer","-b","16","-L","-c","1","-r",str(RATE),"-"]),
        ("ffplay", ["-nodisp","-autoexit","-loglevel","error","-fflags","nobuffer","-probesize","32",
                    "-analyzeduration","0","-f","s16le","-sample_rate",str(RATE),"-i","pipe:0"]),
    ):
        path = shutil.which(name)
        if path: yield [path,*args]


class Output:
    def __enter__(self):
        commands = list(output_commands())
        if not commands:
            raise OSError("Für Ton auf deinem Rechner wird aplay (alsa-utils), paplay, SoX (play) oder ffplay benötigt.")
        self.mix = Mix()
        self.stop = threading.Event()
        self.starting = True
        for command in commands:
            try:
                self.proc = subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,bufsize=0)
            except OSError:
                continue
            self.worker = threading.Thread(target=self.write,daemon=True)
            self.worker.start()
            try:
                self.proc.wait(timeout=.25)
            except subprocess.TimeoutExpired:
                self.starting = False
                return self.mix
            except BaseException:
                self.__exit__(None,None,None)
                raise
            self.worker.join()
            self.proc.stdin.close()
        raise OSError("Keine lokale Audioausgabe verfügbar. Prüfe dein Standard-Audiogerät.")

    def write(self):
        size = 441  # 20 ms blocks keep volume changes and actions responsive.
        due = time.monotonic()
        try:
            while not self.stop.is_set():
                data = memoryview(self.mix.block(size))
                while data:
                    data = data[self.proc.stdin.write(data):]
                due = max(time.monotonic(),due+size/RATE)
                self.stop.wait(max(0,due-time.monotonic()))
        except (BrokenPipeError,OSError):
            if not self.stop.is_set() and not self.starting:
                print("Audiogerät nicht erreichbar. Bitte die lokale Tonausgabe prüfen.",file=sys.stderr,flush=True)

    def __exit__(self,*exc):
        self.stop.set()
        self.proc.terminate()
        try: self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.worker.join()
        self.proc.stdin.close()
