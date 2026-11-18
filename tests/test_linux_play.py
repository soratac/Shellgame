import unittest
from frost.engine import act, fresh
from frost.board import ranking, columns, table_line
from frost.render import cell_width, fit


class LinuxPlayTests(unittest.TestCase):
    def test_inventory_removal_and_no_charge_farming(self):
        s=fresh("Elf",now=0)
        s["rewards"].extend(("quest:wunschzettel","quest:waldzeichen"))
        act(s,"bag",["frost","funke"])
        act(s,"observe",cwd="zitadelle")
        act(s,"enter_boss")
        act(s,"use",["frost"])
        self.assertEqual(s["spells"]["frost"],2)
        act(s,"bag",[])
        self.assertFalse(act(s,"use",["frost"])["ok"])
        act(s,"bag",["frost"])
        self.assertEqual(s["spells"]["frost"],2)
        self.assertEqual(s["rewards"].count("spell:frost"),1)

    def test_carried_healing_works_at_boss_once(self):
        s=fresh("Elf")
        act(s,"bag",["kakao"])
        act(s,"observe",cwd="zitadelle")
        act(s,"enter_boss")
        s["hp"]=30
        act(s,"use",["kakao"])
        self.assertEqual(s["hp"],65)
        act(s,"use",["kakao"])
        self.assertEqual(s["hp"],65)

    def test_file_delivery_deduplicates_wrong_attempts_and_rewards(self):
        s=fresh("Elf")
        act(s,"deliver",["werkstatt"],content="wrong")
        self.assertEqual(s["hp"],95)
        for _ in range(4): act(s,"deliver",["werkstatt"],content="wrong")
        self.assertEqual(s["hp"],95)
        act(s,"deliver",["werkstatt"],content="band=an\nlicht=an\nziel=weihnachten\n")
        self.assertIn("quest:geschenkband",s["rewards"])
        self.assertEqual(s["hp"],100)
        self.assertEqual(s["area"],"dorf")
        act(s,"deliver",["werkstatt"],content="band=an\nlicht=an\nziel=weihnachten\n")
        self.assertEqual(s["score"],150)

    def test_full_personal_reset_clears_records(self):
        s=fresh("Elf")
        s["bests"]={"speedrun:loop":3.5}
        act(s,"bag",["funke"])
        act(s,"reset",["alles"])
        self.assertEqual(s["name"],"Elf")
        self.assertEqual(s["bests"],{})
        self.assertEqual(s["bag"],[])
        self.assertEqual(s["score"],0)

    def test_v1_state_preserves_player_and_records(self):
        s=fresh("Existing Elf")
        s.pop("bag")
        s.pop("deliveries")
        s["version"]=1
        s["bests"]={"normal:classic":72}
        act(s,"bag",["funke"])
        self.assertEqual(s["name"],"Existing Elf")
        self.assertEqual(s["bests"]["best"],72)


class RankingTests(unittest.TestCase):
    def rows(self):
        return [dict(fresh("Elf A"),slot="player01",score=500,elapsed=30,status="won",bests={"normal:classic":30}),
                dict(fresh("Elf B"),slot="player02",score=700,elapsed=20,bests={"normal:classic":15}),
                dict(fresh("Elf C"),slot="player03",score=900,elapsed=5,bests={"speedrun:loop":5})]

    def test_points_and_unified_best_time_sort_independently(self):
        self.assertEqual([r["slot"] for r in ranking(self.rows())],["player03","player02","player01"])
        self.assertEqual([r["slot"] for r in ranking(self.rows(),1)],["player03","player02","player01"])

    def test_columns_align_with_wide_names_and_long_values(self):
        for width in (50,74,110):
            layout=columns(width)
            expected=sum(size for _,size in layout)+3*(len(layout)-1)
            for name in ["Winterheld", "雪の妖精", "a"*50, "Élf"]:
                line=table_line({"rank":23,"name":name,"score":9999,"hp":100,"boss":240,"time":"123:45:12.00","status":"GEWONNEN","area":"werkstatt"},layout)
                self.assertEqual(cell_width(line),expected)
                self.assertLessEqual(expected,width)
        self.assertEqual(cell_width(fit("雪雪雪",5)),5)


if __name__=="__main__": unittest.main()
