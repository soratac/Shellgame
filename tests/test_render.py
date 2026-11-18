import unittest
from frost.engine import fresh
from frost.render import boss_frame, world_frame, POSITIONS


class RenderTests(unittest.TestCase):
    def test_small_and_large_3d_projection(self):
        for w,h in [(46,3),(96,12),(140,35)]:
            first=boss_frame(w,h,0)
            second=boss_frame(w,h,1.2)
            self.assertEqual(len(first.cells),h)
            self.assertTrue(any(char in "░▒▓█" for row in first.cells for char,_ in row))
            self.assertNotEqual(first.cells,second.cells)

    def test_life_gauge_loses_health_with_warm_trail_and_no_brackets(self):
        from frost.render import health_gauge
        hit=health_gauge(35,100,18,95,.42,2)
        settled=health_gauge(35,100,18,95,2,2)
        text="".join(ch for ch,_ in hit.cells[0])
        self.assertIn("35/100",text)
        self.assertIn("▓",text)
        self.assertNotIn("❨",text)
        self.assertNotIn("▓",[ch for ch,_ in settled.cells[0]])
        self.assertTrue(all(color not in (2,11,12,14) for row in hit.cells for ch,color in row if ch!=" "))

    def test_successful_module_removals_have_distinct_animations(self):
        from frost.engine import act
        from frost.geometry import Canvas
        from frost.spell_art import spell_motion
        for module,marker in (("frost_armor","ϟ"),("blizzard","❄")):
            state=fresh("Elf")
            act(state,"observe",cwd="zitadelle")
            act(state,"enter_boss")
            for expected in (True,False):
                self.assertEqual(act(state,"unload",[module])["ok"],expected)
                event=state["events"][-1]
                canvas=Canvas(70,18)
                spell_motion(canvas,event,.24,(10,12),(48,7))
                text="".join(ch for row in canvas.cells for ch,_ in row)
                self.assertEqual(module in event["sounds"],expected)
                self.assertEqual(marker in text,expected)

    def test_all_map_labels_remain_legible_on_small_terminals(self):
        for w,h in ((34,7),(46,9),(96,14)):
            for area,pos in POSITIONS.items():
                state=fresh("Elf")
                state["area"]=area
                canvas=world_frame(w,h,state,pos,.5)
                lines=["".join(ch for ch,_ in row) for row in canvas.cells]
                for name in POSITIONS:
                    self.assertTrue(any(name in line for line in lines),(w,h,area,name))
                self.assertTrue(any("▸ "+area in line for line in lines))

    def test_world_character_all_areas(self):
        for area,position in POSITIONS.items():
            state=fresh("Elf")
            state["area"]=area
            canvas=world_frame(96,14,state,position,0)
            self.assertTrue(any(char=="█" for row in canvas.cells for char,_ in row))
            self.assertIn("DU", "".join(char for row in canvas.cells for char,_ in row))


if __name__=="__main__": unittest.main()
