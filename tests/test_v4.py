import unittest
from unittest.mock import patch
from frost.engine import fresh,act,route_count
from frost.render import combat_frame,world_frame,POSITIONS


class ProgressionTests(unittest.TestCase):
    def fight(self,places):
        s=fresh('Elf',now=0)
        for place in places: act(s,'observe',cwd=place,now=1)
        act(s,'bag',['funke','kakao','frost','schild'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        act(s,'unload',['blizzard']); act(s,'unload',['frost_armor'])
        for i in range(12): act(s,'cast',['funke'],now=10+i*3)
        return s

    def test_two_places_cannot_win_even_without_drivers(self):
        s=self.fight(['dorf','wald'])
        self.assertEqual(s['boss_hp'],1)
        self.assertEqual(s['status'],'playing')
        self.assertEqual(route_count(s),2)

    def test_three_places_allow_normal_win(self):
        s=self.fight(['dorf','wald','werkstatt'])
        self.assertEqual(s['status'],'won')
        self.assertEqual(s['method'],'driver')

    def test_village_loop_remains_shortcut(self):
        s=fresh('Elf',now=0)
        act(s,'observe',cwd='dorf'); act(s,'bag',['funke'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        for i in range(6): act(s,'use',['funke'],now=10+i*.1)
        self.assertEqual(s['method'],'loop')
        self.assertEqual(route_count(s),1)

    def test_avatar_validation_persistence_and_old_save(self):
        s=fresh('Elf'); s.pop('avatar'); s.pop('avatar_set')
        self.assertFalse(act(s,'avatar',['bad','red'])['ok'])
        self.assertTrue(act(s,'avatar',['blond','lila'])['ok'])
        act(s,'reset',['normal'])
        self.assertEqual(s['avatar'],{'hair':'blond','shirt':'lila'})
        self.assertTrue(s['avatar_set'])

    def test_events_retain_actual_damage_and_bounded_history(self):
        s=fresh('Elf'); act(s,'bag',['funke'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        act(s,'use',['funke'],now=10)
        event=s['events'][-1]
        self.assertEqual((event['damage'],event['hurt']),(22,7))
        for i in range(60): act(s,'attack',now=100+i*3)
        self.assertLessEqual(len(s['events']),24)

    def test_animated_combat_has_both_bars_and_damage_numbers(self):
        s=fresh('Elf'); act(s,'bag',['funke'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        act(s,'use',['funke'],now=10)
        with patch('frost.render.time.time',return_value=10.95):
            c=combat_frame(96,19,s,10.95)
        text='\n'.join(''.join(ch for ch,_ in row) for row in c.cells)
        for word in ['Elf','KRAMPUS','/100','/240','-22','-7']: self.assertIn(word,text)
        with patch('frost.render.time.time',return_value=10.1):
            self.assertNotEqual(c.cells,combat_frame(96,19,s,10.1).cells)


if __name__=='__main__': unittest.main()
