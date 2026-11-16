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

    def test_world_character_all_areas(self):
        for area,position in POSITIONS.items():
            state=fresh("Elf")
            state["area"]=area
            canvas=world_frame(96,14,state,position,0)
            self.assertEqual(sum(char=="@" for row in canvas.cells for char,_ in row),1)


if __name__=="__main__": unittest.main()
