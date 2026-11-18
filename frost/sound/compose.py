"""Render Schneefunken, an original 16-bar handheld waltz in D major, to PCM."""
import array
import functools
import math
import random
import sys
import wave

RATE = 22050
STEP = 60 / 132 / 2  # eighth notes in 3/4
# Each bar pairs chord tones (bass first) with six melody slots. A dash sustains.
SCORE = [
    ((50, 66, 69), "78 - 81 76 74 -"),
    ((47, 62, 66), "73 74 78 - 74 71"),
    ((43, 62, 67), "74 - 79 78 - 74"),
    ((45, 61, 64), "73 76 - 81 - 76"),
    ((50, 66, 69), "78 81 85 - 81 78"),
    ((42, 61, 69), "76 - 73 69 73 76"),
    ((43, 59, 66), "74 71 79 - 78 74"),
    ((45, 61, 67), "76 - - 73 69 -"),
    ((47, 62, 66), "83 - 81 78 - 74"),
    ((43, 59, 62), "79 78 74 71 74 -"),
    ((52, 64, 67), "76 79 83 - 86 83"),
    ((45, 61, 67), "85 - 81 76 - 73"),
    ((50, 66, 69), "81 78 74 - 78 81"),
    ((43, 62, 67), "83 - 79 74 71 74"),
    ((45, 61, 64), "76 73 69 73 76 81"),
    ((50, 66, 69), "78 - 74 - - ."),
]


@functools.lru_cache(maxsize=None)
def note(voice, pitch, steps):
    length = steps * STEP
    size = round(length * RATE)
    freq = 440 * 2 ** ((pitch - 69) / 12)
    noise = random.Random(pitch)
    samples = array.array("f")
    for i in range(size):
        t = i / RATE
        phase = math.tau * freq * t
        if voice == "bell":
            value = (.55 * math.sin(phase) + .20 * math.sin(2.01*phase)
                     + .11 * math.sin(3.98*phase) * math.exp(-12*t)) * math.exp(-5*t)
        elif voice == "pluck":
            value = (.24*math.sin(phase) + .09*math.sin(3*phase)) * math.exp(-13*t)
        elif voice == "bass":
            value = (.32*math.sin(phase) + .06*math.sin(2*phase)) * math.exp(-4*t)
        else:  # A short, high-passed noise jingle over two detuned metal partials
            value = (.05*(noise.random()-.5) + .035*math.sin(phase)
                     + .045*math.sin(1.47*phase)) * math.exp(-30*t)
        envelope = min(1, t/.006, (length-t)/.022)
        samples.append(value * envelope)
    return samples


def soundtrack():
    mix = array.array("f", [0]) * round(len(SCORE) * 6 * STEP * RATE)

    def place(at, voice, pitch, duration, gain=1):
        start = round(at * STEP * RATE)
        for i, value in enumerate(note(voice, pitch, duration)):
            # Fold the final bell tail into the pickup for a seamless loop.
            mix[(start + i) % len(mix)] += value * gain

    for bar, ((root, third, fifth), melody) in enumerate(SCORE):
        beat = bar * 6
        place(beat, "bass", root, 1.8)
        place(beat+3, "bass", root+7, 1.4, .75)
        for up, pitch in ((1, third), (2, fifth), (4, third), (5, fifth)):
            place(beat+up, "pluck", pitch, 1.1, .8 if up % 2 else .55)
        for up in (0, 2, 3, 5):
            place(beat+up, "jingle", 106 + up, .65, 1 if up == 0 else .58)
        slots = melody.split()
        for i, token in enumerate(slots):
            if token in ("-", "."):
                continue
            duration = 1
            while i+duration < len(slots) and slots[i+duration] == "-":
                duration += 1
            place(beat+i, "bell", int(token), duration * .93)
            place(beat+i+.75, "bell", int(token), 1.4, .13)
    scale = 28000 / max(map(abs, mix))
    return array.array("h", (round(v * scale) for v in mix))


def render(path):
    pcm = soundtrack()
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, RATE, len(pcm), "NONE", "not compressed"))
        out.writeframes(pcm.tobytes())


if __name__ == "__main__":
    render(sys.argv[1])
