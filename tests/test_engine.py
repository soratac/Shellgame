import unittest

from frost.engine import act, fresh, public


class GameTests(unittest.TestCase):
    def setUp(self):
        self.s=fresh("Winterheld",now=100)

    def action(self,action,args=(),now=110,**kw):
        return act(self.s,action,args,now=now,**kw)

    def visit(self,area):
        result=self.action("observe",cwd=area)
        if area=="zitadelle": self.action("enter_boss")
        return result

    def test_basic_spell_route_is_winnable(self):
        self.action("collect",["funke.spell"])
        self.visit("zitadelle")
        for i in range(11): self.action("cast",["funke"],now=115+i*3)
        self.assertEqual(self.s["status"],"won")
        self.assertGreater(self.s["hp"],0)
        self.assertEqual(self.s["method"],"spell")
        self.assertIn("normal:classic",self.s["bests"])

    def test_loop_wins_and_stops(self):
        self.action("collect",["funke.spell"])
        self.visit("zitadelle")
        for i in range(6): result=self.action("cast",["funke"],now=111+i*.1)
        self.assertEqual(self.s["method"],"loop")
        self.assertTrue(result["stop"])
        self.assertEqual(self.s["boss_hp"],0)
        self.assertIn("normal:loop",self.s["bests"])

    def test_driver_route(self):
        self.visit("zitadelle")
        self.action("unload",["frost_armor"])
        self.action("unload",["blizzard"])
        for _ in range(10): self.action("attack")
        self.assertEqual(self.s["status"],"won")
        self.assertEqual(self.s["method"],"driver")

    def test_all_spells_and_classic_fight(self):
        for area,file in [("dorf","funke.spell"),("wald","frost.spell"),("werkstatt","schild.spell"),("archiv","stern.spell")]:
            self.visit(area)
            self.action("collect",[file])
        self.visit("zitadelle")
        for i,spell in enumerate(["schild","frost","stern","stern","frost","funke","funke","funke"]):
            self.action("cast",[spell],now=120+i*4)
        self.assertEqual(self.s["status"],"won")
        self.assertGreater(self.s["hp"],70)

    def test_no_farming(self):
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
        self.assertEqual(self.s["ended"],129)
        self.assertEqual(public(self.s,200)["elapsed"],29)
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
        self.assertEqual(self.s["hp"],90)
        self.assertEqual(self.s["area"],"zitadelle")
        self.assertTrue(self.s["boss_started"])

    def test_reset_keeps_records_not_inventory(self):
        self.test_loop_wins_and_stops()
        bests=self.s["bests"].copy()
        self.action("reset",["speedrun"],now=200)
        self.assertEqual(self.s["bests"],bests)
        self.assertEqual(self.s["score"],0)
        self.assertEqual(self.s["hp"],100)
        self.assertEqual(self.s["spells"],{})
        self.assertEqual(self.s["mode"],"speedrun")

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

    def test_quests_reward_once_and_mistake_hurts(self):
        self.action("submit",content="wrong")
        self.assertEqual(self.s["hp"],95)
        self.action("submit",content="Mila: Stern\nNoah: Schlitten\n")
        self.assertEqual(self.s["score"],150)
        self.assertEqual(self.s["hp"],100)
        self.action("submit",content="Mila: Stern\nNoah: Schlitten")
        self.assertEqual(self.s["score"],150)

    def test_spell_charges_and_invalid_spell_counter(self):
        self.visit("wald")
        self.action("collect",["frost.spell"])
        self.visit("zitadelle")
        for _ in range(3): self.action("cast",["frost"])
        self.assertEqual(self.s["spells"]["frost"],0)
        self.action("cast",["frost"])
        hp=self.s["hp"]
        self.assertFalse(self.action("cast",["not-a-spell"])["ok"])
        self.assertEqual(self.s["hp"],hp-12)


if __name__=="__main__": unittest.main()
