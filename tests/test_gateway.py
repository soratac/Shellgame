import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from frost.gateway import Allocator
from frost.engine import act,fresh


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.slots=[f"player{i:02}" for i in range(1,24)]
        for slot in self.slots:
            (self.root/slot).mkdir()
            self.set_name(slot,"")
        self.allocator=Allocator(self.root/"joins.sqlite",self.slots,self.root)

    def set_name(self,slot,name): (self.root/slot/"state.json").write_text(json.dumps({"name":name}))

    def tearDown(self):
        self.allocator.db.close()
        self.temp.cleanup()

    def test_23_concurrent_joins_are_distinct_and_24th_rejected(self):
        with ThreadPoolExecutor(max_workers=23) as pool:
            reservations=list(pool.map(lambda _:self.allocator.reserve(),range(23)))
        self.assertEqual(len({slot for slot,_,_ in reservations}),23)
        self.assertEqual(len({code for _,code,_ in reservations}),23)
        with self.assertRaisesRegex(ValueError,"Alle Spielerplaetze"): self.allocator.reserve()

    def test_reconnect_is_private_and_rejects_double_login(self):
        slot,code,lease=self.allocator.reserve()
        self.set_name(slot,"Elf")
        with self.assertRaisesRegex(ValueError,"noch verbunden"): self.allocator.reserve(code)
        with self.assertRaises(ValueError): self.allocator.reserve("0000-0000-0000-0000")
        self.allocator.release(slot,lease)
        resumed,new_code,new_lease=self.allocator.reserve(code.lower())
        self.assertEqual((resumed,new_code),(slot,code))
        self.assertNotEqual(lease,new_lease)
        self.allocator.release(slot,lease)
        with self.assertRaisesRegex(ValueError,"noch verbunden"): self.allocator.reserve(code)

    def test_abandoned_unnamed_place_is_reclaimed(self):
        slot,code,lease=self.allocator.reserve()
        self.allocator.release(slot,lease)
        new_slot,new_code,_=self.allocator.reserve()
        self.assertEqual(slot,new_slot)
        self.assertNotEqual(code,new_code)

    def test_restart_keeps_codes_and_adopts_existing_players(self):
        slot,code,_=self.allocator.reserve()
        self.set_name(slot,"Existing")
        self.set_name("player02","Legacy")
        self.allocator.db.close()
        self.allocator=Allocator(self.root/"joins.sqlite",self.slots,self.root)
        self.assertEqual(self.allocator.reserve(code)[0],slot)
        self.assertEqual(self.allocator.reserve()[0],"player03")
        self.assertIn("player02",[r["slot"] for r in self.allocator.list_rows()])


class BossGateTests(unittest.TestCase):
    def test_no_attack_before_explicit_confirmation(self):
        s=fresh("Elf")
        act(s,"observe",cwd="zitadelle",code=127)
        self.assertEqual(s["hp"],100)
        self.assertFalse(act(s,"attack")["ok"])
        self.assertEqual(s["boss_hp"],240)
        act(s,"enter_boss")
        self.assertTrue(act(s,"attack")["ok"])

    def test_no_retreat_or_new_resources_after_acceptance(self):
        s=fresh("Elf")
        s["rewards"].append("quest:wunschzettel")
        act(s,"bag",["funke","kakao"])
        act(s,"observe",cwd="zitadelle")
        act(s,"enter_boss")
        act(s,"observe",cwd="dorf")
        self.assertEqual(s["area"],"zitadelle")
        act(s,"bag",["funke","kakao","stern","beeren"])
        self.assertEqual(s["bag"],["funke","kakao"])
        self.assertFalse(act(s,"deliver",["dorf"],content="Mila: Stern\nNoah: Schlitten")["ok"])
        self.assertFalse(act(s,"collect",["stern.spell"])["ok"])
        act(s,"enter_boss")
        self.assertEqual(s["battle_items"],["funke","kakao"])
        act(s,"reset",["normal"])
        self.assertFalse(s["boss_started"])
        act(s,"observe",cwd="wald")
        self.assertEqual(s["area"],"wald")


if __name__=="__main__": unittest.main()
