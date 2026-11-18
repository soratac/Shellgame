import unittest

from frost.music_http import SOUNDS
from frost.sound.native import Mix


class NativeAudioTests(unittest.TestCase):
    def test_every_wire_effect_has_distinct_audio_and_mute_discards_queued_turns(self):
        mix = Mix()
        self.assertEqual(set(mix.effects), SOUNDS)
        self.assertEqual(len({a.tobytes() for a in mix.effects.values()}), len(SOUNDS))
        mix.play(["frost_armor", "gale"])
        mix.change(0)
        mix.play(["claw"])
        self.assertEqual(mix.block(441), bytes(882))
        self.assertFalse(mix.voices)

    def test_music_wraps_mid_block(self):
        mix = Mix()
        size = 100
        mix.position = len(mix.track) - size
        last = mix.block(size)
        first = mix.block(size)
        mix.position = len(mix.track) - size
        self.assertEqual(mix.block(2*size), last+first)
