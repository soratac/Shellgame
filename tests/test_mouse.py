import unittest
from frost.mouse import MouseInput
from frost.music import indicator, mixer_action


class MouseTests(unittest.TestCase):
    def test_fragmented_press_and_release_keep_readline_bytes(self):
        decoder=MouseInput()
        clicks=[]
        def click(x,y): clicks.append((x,y))
        payload=b"echo ab\x1b[<0;116;42M\x1b[<0;116;42m\x1b[D\rcd\x1b"
        forwarded=b"".join(decoder.feed(bytes([ch]),click) for ch in payload)+decoder.flush()
        self.assertEqual(forwarded,b"echo ab\x1b[D\rcd\x1b")
        self.assertEqual(clicks,[(115,41)])

    def test_hit_regions_follow_resize_and_mute_label(self):
        for width in (41,80,120):
            for muted in (False,True):
                state={"level":100,"muted":muted}
                text=indicator(state)
                start=width-3-len(text)
                for mark,action in [("♪","open"),("−","-"),("+","+"),("stumm" if muted else "100%","mute")]:
                    self.assertEqual(mixer_action(state,width,start+text.index(mark)),action)
                self.assertIsNone(mixer_action(state,width,start-1))
