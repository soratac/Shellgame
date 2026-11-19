import unittest

from frost.engine import act, fresh, public


class GameTests(unittest.TestCase):
    def setUp(self):
        self.s=fresh("Winterheld",now=100)

    def solved(self,*quests):
        self.s["rewards"].extend("quest:"+name for name in quests)

    def action(self,action,args=(),now=110,**kw):
        return act(self.s,action,args,now=now,**kw)

    def visit(self,area):
        result=self.action("observe",cwd=area)
        if area=="zitadelle": self.action("enter_boss")
        return result

    def test_repeating_only_the_starter_spell_loses(self):
        self.solved("wunschzettel")
        self.action("bag",["funke"])
        self.visit("zitadelle")
        for i in range(25):
            result=self.action("use",["funke"],now=120+i*3)
            if i==1:
                self.assertIn("Wechsle",result["message"])
                self.assertEqual(self.s["boss_hp"],240-22-5)
            if result["stop"]: break
        self.assertEqual(self.s["status"],"lost")
        self.assertGreater(self.s["boss_hp"],0)

    def test_shield_and_cocoa_cannot_finish_through_boss_lock(self):
        self.solved("wunschzettel","waldzeichen","geschenkband")
        self.visit("wald")
        self.action("bag",["funke","frost","schild","kakao"])
        self.visit("zitadelle")
        moves=["funke","stab","frost","schild","funke","stab","kakao","frost","funke","schild","stab","frost","funke","stab"]
        for i,move in enumerate(moves):
            if move=="stab":
                self.action("attack",now=120+i*3)
            else:
                self.action("use",[move],now=120+i*3)
        self.assertNotEqual(self.s["status"],"won")
        self.assertEqual(self.s["boss_hp"],1)

    def test_switching_attacks_breaks_guard_but_healing_does_not(self):
        self.solved("wunschzettel")
        self.action("bag",["funke","kakao"])
        self.visit("zitadelle")
        del self.s["last_attack"]  # A fight saved before the balance update.
        for i,(action,item,damage) in enumerate([("use","funke",22),("use","kakao",0),
                                                ("cast","funke",5),("attack",None,16),("use","funke",22)]):
            before=self.s["boss_hp"]
            self.action(action,[item] if item else [],now=120+i*3)
            self.assertEqual(before-self.s["boss_hp"],damage)
        self.action("reset")
        self.assertIsNone(self.s["last_attack"])

    def test_half_health_breaks_protection_only_once(self):
        self.solved("wunschzettel","waldzeichen","geschenkband")
        self.action("bag",["funke","frost","schild"])
        self.visit("zitadelle")
        self.s.update(boss_hp=142,shield=2,frozen=1,eclipse_casts=1)
        self.action("use",["funke"])
        self.assertEqual((self.s["boss_hp"],self.s["shield"],self.s["frozen"],self.s["hp"]),(120,0,0,81))
        self.action("use",["schild"])
        self.action("use",["frost"])
        self.assertEqual(self.s["hp"],81)

    def test_loop_wins_and_stops(self):
        self.solved("wunschzettel")
        self.action("collect",["funke.spell"])
        self.visit("zitadelle")
        self.action("unload",["frost_armor"])
        self.action("disable",["eissturm"])
        for i in range(6): result=self.action("cast",["funke"],now=111+i*.1)
        self.assertEqual(self.s["method"],"loop")
        self.assertTrue(result["stop"])
        self.assertEqual(self.s["boss_hp"],0)
        self.assertIn("best",self.s["bests"])

    def test_charged_strikes_persist_until_a_combat_turn_and_only_happen_twice(self):
        import json
        self.solved("geschenkband","waldzeichen")
        self.action("bag",["schild","frost"])
        self.visit("zitadelle")
        self.s["boss_hp"]=190
        self.action("attack")
        self.s=json.loads(json.dumps(self.s))
        for cmd in ("inventory","status","hint","observe"):
            self.action(cmd,cwd="zitadelle")
        self.assertTrue(self.s["charging"])
        self.action("use",["frost"])
        self.assertEqual((self.s["hp"],self.s["charging"]), (8,False))
        self.assertIn("eclipse",self.s["events"][-1]["sounds"])
        self.s["boss_hp"]=95
        self.action("attack")
        self.assertTrue(self.s["charging"])
        self.action("use",["schild"])
        self.assertIn("eclipse_guard",self.s["events"][-1]["sounds"])
        self.assertEqual(self.s["hp"],8)
        self.action("attack")
        self.assertEqual((self.s["eclipse_casts"],self.s["charging"]),(2,False))
        self.action("reset")
        self.assertEqual((self.s["eclipse_casts"],self.s["charging"]),(0,False))

    def test_unshielded_charge_lands_on_a_finishing_blow(self):
        self.visit("zitadelle")
        self.s.update(charging=True,eclipse_casts=2,boss_hp=1,hp=80,armor=False,storm_service=False)
        self.action("attack")
        self.assertEqual((self.s["boss_hp"],self.s["hp"],self.s["status"]),(0,0,"lost"))

    def test_either_seal_blocks_lethal_attacks_and_rapid_casts(self):
        for armor, service in ((True,True),(True,False),(False,True)):
            with self.subTest(armor=armor,service=service):
                self.s=fresh("Elf")
                self.visit("zitadelle")
                self.s.update(armor=armor,storm_service=service,boss_hp=1,eclipse_casts=2,
                              spells={"funke":-1},frozen=10)
                for i in range(7):
                    self.action("cast",["funke"],now=120+i*.1)
                self.assertEqual((self.s["status"],self.s["boss_hp"]),("playing",1))
                self.assertNotIn("victory",self.s["rewards"])

    def test_driver_route(self):
        for area in ("dorf","wald","werkstatt"): self.visit(area)
        self.solved("geschenkband")
        self.action("bag",["schild"])
        self.visit("zitadelle")
        self.action("unload",["frost_armor"])
        self.action("unload",["blizzard"])
        self.action("disable",["eissturm"])
        for _ in range(14):
            if self.s["charging"]: self.action("use",["schild"])
            else: self.action("attack")
        self.assertEqual(self.s["status"],"won")
        self.assertEqual(self.s["method"],"driver")

    def test_all_spells_and_classic_fight(self):
        self.solved("wunschzettel","waldzeichen","geschenkband","passwort")
        for area,file in [("dorf","funke.spell"),("wald","frost.spell"),("werkstatt","schild.spell"),("archiv","stern.spell")]:
            self.visit(area)
            self.action("collect",[file])
        self.visit("zitadelle")
        self.action("unload",["blizzard"])
        self.action("unload",["frost_armor"])
        self.action("disable",["eissturm"])
        spells=iter(["funke","frost","stern","funke","frost","stern"])
        for i in range(8):
            spell="schild" if self.s["charging"] else next(spells)
            self.action("cast",[spell],now=120+i*4)
            if self.s["status"]!="playing": break
        self.assertEqual(self.s["status"],"won")
        self.assertGreater(self.s["hp"],0)
        self.assertEqual(self.s["method"],"driver")

    def test_no_farming(self):
        self.solved("waldzeichen")
        self.visit("wald")
        self.action("heal",["beeren"])
        self.action("collect",["frost.spell"])
        score=self.s["score"]
        for _ in range(20):
            self.visit("wald")
            self.action("heal",["beeren"])
            self.action("collect",["frost.spell"])
        self.assertEqual(self.s["score"],score)
        self.assertEqual(self.s["spells"]["frost"],3)

    def test_failed_command_and_loss(self):
        self.visit("zitadelle")
        for i in range(10): self.action("observe",cwd="zitadelle",code=127,command="typo",now=120+i)
        self.assertEqual(self.s["status"],"lost")
        self.assertEqual(self.s["hp"],0)
        self.assertEqual(self.s["ended"],124)
        self.assertEqual(public(self.s,200)["elapsed"],24)
        self.assertTrue(self.action("attack")["stop"])

    def test_reading_and_ctrl_c_are_safe(self):
        self.visit("zitadelle")
        self.action("observe",cwd="zitadelle",code=0,command="cat BOSS.txt")
        self.action("observe",cwd="zitadelle",code=130)
        self.assertEqual(self.s["hp"],100)
        self.assertIn("shell:cat",self.s["rewards"])

    def test_leaving_world_does_not_escape_combat(self):
        self.visit("zitadelle")
        self.action("observe",cwd=None,code=127)
        self.assertEqual(self.s["hp"],82)
        self.assertEqual(self.s["area"],"zitadelle")
        self.assertTrue(self.s["boss_started"])

    def test_reset_keeps_records_not_inventory(self):
        self.test_loop_wins_and_stops()
        bests=self.s["bests"].copy()
        self.action("reset",[],now=200)
        self.assertEqual(self.s["bests"],bests)
        self.assertEqual(self.s["score"],0)
        self.assertEqual(self.s["hp"],100)
        self.assertEqual(self.s["spells"],{})
        self.assertNotIn("mode",self.s)

    def test_victory_message_survives_prompt(self):
        self.test_loop_wins_and_stops()
        message=self.s["message"]
        self.action("observe",cwd="zitadelle")
        self.assertEqual(self.s["message"],message)

    def test_name_validation(self):
        for name in ("x","\x1b[2Jtest","a"*21,"<script>"):
            state=fresh(now=100)
            self.assertFalse(act(state,"name",[name])["ok"])
        self.assertTrue(act(fresh(),"name",["Schnee-Elf_23"])["ok"])

    def test_quests_unlock_only_their_own_loot(self):
        all_items=["funke","ping","frost","schild","stern","beeren"]
        self.action("bag",all_items)
        self.assertEqual(self.s["bag"],["beeren"])
        self.assertFalse(self.action("collect",["funke.spell"])["ok"])
        self.action("deliver",["dorf"],content="falsch")
        self.action("bag",all_items)
        self.assertEqual(self.s["bag"],["beeren"])
        self.action("deliver",["dorf"],content="Mila: Stern\nNoah: Schlitten")
        self.action("bag",all_items)
        self.assertEqual(self.s["bag"],["beeren","funke","ping"])
        self.action("reset")
        self.action("bag",all_items)
        self.assertEqual(self.s["bag"],["beeren"])

    def test_quests_reward_once_and_mistake_hurts(self):
        self.action("submit",content="wrong")
        self.assertEqual(self.s["hp"],95)
        self.action("submit",content="Mila: Stern\nNoah: Schlitten\n")
        self.assertEqual(self.s["score"],150)
        self.assertEqual(self.s["hp"],100)
        self.action("submit",content="Mila: Stern\nNoah: Schlitten")
        self.assertEqual(self.s["score"],150)

    def test_spell_charges_and_invalid_spell_counter(self):
        self.solved("waldzeichen")
        self.visit("wald")
        self.action("collect",["frost.spell"])
        self.visit("zitadelle")
        for _ in range(3): self.action("cast",["frost"])
        self.assertEqual(self.s["spells"]["frost"],0)
        self.action("cast",["frost"])
        hp=self.s["hp"]
        self.assertFalse(self.action("cast",["not-a-spell"])["ok"])
        self.assertEqual(self.s["hp"],hp-24)


if __name__=="__main__": unittest.main()
