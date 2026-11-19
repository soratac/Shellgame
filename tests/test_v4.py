import unittest
from unittest.mock import patch
from frost.engine import fresh,act,route_count
from frost.render import combat_frame,world_frame,POSITIONS


class ProgressionTests(unittest.TestCase):
    def fight(self,places):
        s=fresh('Elf',now=0)
        for place in places: act(s,'observe',cwd=place,now=1)
        s["rewards"].append("quest:wunschzettel")
        if "werkstatt" in places: s["rewards"].append("quest:geschenkband")
        act(s,'bag',['funke','kakao','frost','schild'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        act(s,'unload',['blizzard']); act(s,'unload',['frost_armor'])
        for i in range(14):
            move='schild' if s['charging'] and 'schild' in s['bag'] else 'funke'
            act(s,'cast',[move],now=10+i*3)
        return s

    def test_boss_requires_discovered_address_and_ping_hits_four_times(self):
        from frost.trail import hiding_place, BOSS_IP
        s=fresh('Raoul', now=1)
        self.assertFalse(act(s,'connect',[BOSS_IP])['ok'])
        act(s,'observe',cwd='dorf')
        self.assertNotIn(hiding_place(s),act(s,'scan')['message'])
        self.assertFalse(act(s,'connect',[BOSS_IP])['ok'])
        act(s,'observe',cwd=hiding_place(s))
        self.assertIn(BOSS_IP,act(s,'scan')['message'])
        self.assertFalse(act(s,'ping',[BOSS_IP])['ok'])
        self.assertFalse(act(s,'connect',['127.0.0.1'])['ok'])
        s["rewards"].append("quest:wunschzettel")
        act(s,'bag',['ping'])
        self.assertTrue(act(s,'connect',[BOSS_IP])['ok'])
        hp=s['hp']
        self.assertTrue(act(s,'ping',[BOSS_IP])['ok'])
        self.assertEqual((s['area'],s['boss_hp'],s['hp']),('zitadelle',228,hp-15))
        self.assertEqual(s['events'][-1]['kind'],'ping')

    def test_mobile_trail_and_persistent_discovery(self):
        from frost.trail import BOSS_IP, hiding_place
        s=fresh("Elf",now=100)
        places=[hiding_place(s,now=t) for t in (101,161,221)]
        self.assertEqual(len(set(places)),3)
        act(s,"observe",cwd=places[1],now=161)
        self.assertIn(BOSS_IP,act(s,"scan",now=161)["message"])
        self.assertTrue(act(s,"connect",[BOSS_IP],now=381)["ok"])

    def test_storm_service_changes_counterattack_and_resets(self):
        for disabled,expected in [(False,42),(True,36)]:
            s=fresh("Elf")
            act(s,"observe",cwd="zitadelle")
            act(s,"enter_boss")
            if disabled:
                act(s,"disable",["eissturm"])
                self.assertIn("disabled",act(s,"services")["message"])
            for i in range(3): act(s,"attack")
            self.assertEqual(s["hp"],expected)
            act(s,"reset")
            self.assertTrue(s["storm_service"])

    def test_ignoring_the_charge_loses(self):
        s=self.fight(['dorf','wald'])
        self.assertGreater(s['boss_hp'],0)
        self.assertEqual(s['status'],'lost')
        self.assertEqual(route_count(s),2)

    def test_three_places_allow_normal_win(self):
        s=self.fight(['dorf','wald','werkstatt'])
        self.assertEqual(s['status'],'won')
        self.assertEqual(s['method'],'driver')

    def test_village_loop_remains_shortcut(self):
        s=fresh('Elf',now=0)
        s["rewards"].append("quest:wunschzettel")
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
        self.assertEqual(s['avatar'],{'hair':'blond','shirt':'lila','gender':'männlich','style':'kurz'})
        self.assertTrue(s['avatar_set'])

    def test_events_retain_actual_damage_and_bounded_history(self):
        s=fresh('Elf'); s["rewards"].append("quest:wunschzettel"); act(s,'bag',['funke'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        act(s,'use',['funke'],now=10)
        event=s['events'][-1]
        self.assertEqual((event['damage'],event['hurt']),(22,15))
        for i in range(60): act(s,'attack',now=100+i*3)
        self.assertLessEqual(len(s['events']),24)

    def test_hints_have_a_per_run_budget_and_expire(self):
        s=fresh("Elf",now=0)
        for left in (2,1,0):
            act(s,"hint",now=10)
            self.assertEqual(s["hints_left"],left)
        self.assertEqual(s["hint_until"],18)
        self.assertIn("verbraucht",act(s,"hint",now=20)["message"])
        self.assertEqual(s["hint_until"],18)
        act(s,"reset",now=22)
        self.assertEqual(s["hints_left"],3)
        del s["hints_left"]
        act(s,"hint",now=24)
        self.assertEqual(s["hints_left"],2)

    def test_animated_combat_has_both_bars_and_damage_numbers(self):
        s=fresh('Elf'); s["rewards"].append("quest:wunschzettel"); act(s,'bag',['funke'])
        act(s,'observe',cwd='zitadelle'); act(s,'enter_boss')
        act(s,'use',['funke'],now=10)
        with patch('frost.render.time.time',return_value=10.95):
            c=combat_frame(96,19,s,10.95)
        text='\n'.join(''.join(ch for ch,_ in row) for row in c.cells)
        for word in ['Elf','GRINCH','/100','/240','-22','-15']: self.assertIn(word,text)
        with patch('frost.render.time.time',return_value=10.1):
            self.assertNotEqual(c.cells,combat_frame(96,19,s,10.1).cells)


if __name__=='__main__': unittest.main()
