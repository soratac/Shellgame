import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from frost.engine import fresh,act,public
from frost.records import migrate
from frost.board import Board,online,paint_board,ranking
from scripts.provision import credentials


class UnifiedTests(unittest.TestCase):
    def test_legacy_best_times_merge_without_resetting_progress(self):
        s=fresh('Old Elf',now=100)
        s.update(mode='speedrun',hp=61,score=340,bests={'normal:classic':80,'normal:loop':7,'speedrun:loop':4,'speedrun:classic':40})
        migrate(s)
        self.assertEqual(s['bests'],{'best':4})
        self.assertNotIn('mode',s)
        self.assertEqual((s['name'],s['hp'],s['score'],s['started']),('Old Elf',61,340,100))
        act(s,'reset')
        self.assertEqual(s['bests'],{'best':4})
        self.assertFalse(act(s,'reset',['speedrun'])['ok'])

    def test_password_length_and_regular_provision_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            first=credentials(p)
            self.assertEqual(len(first),12)
            self.assertTrue(first.isalnum())
            shadow=(p/'shadow').read_text()
            self.assertEqual(credentials(p),first)
            self.assertEqual((p/'shadow').read_text(),shadow)
            second=credentials(p,rotate=True)
            self.assertEqual(len(second),12)
            self.assertNotEqual(first,second)
            self.assertNotEqual((p/'shadow').read_text(),shadow)
            self.assertEqual((p/'password').stat().st_mode & 0o777,0o600)

    def test_exact_command_and_last_three_completed(self):
        from frost.activity import Activity, screen_command
        log=Activity()
        for cmd in ("ls", "pwd", "ls -la", "echo 'a  b' | cat", "pwd", "pwd"):
            log.begin(cmd)
            log.finish()
        log.begin("sleep 3 && printf 'done!'")
        self.assertEqual(log.snapshot()["command_label"],"sleep 3 && printf 'done!'")
        self.assertEqual(log.snapshot()["command_history"],["pwd","pwd","echo 'a  b' | cat"])
        self.assertNotIn(chr(27),screen_command("echo "+chr(27)+"[2J"))

    def test_live_activity_is_separate_from_persisted_scores(self):
        from frost.board import wrap_command
        with tempfile.TemporaryDirectory() as folder:
            b=Board(str(Path(folder)/'b.db'),{})
            data=dict(public(fresh("Elf")),connected=True,command_label="sleep 12", command_active=True,
                      command_history=["echo 'one  two' | wc -c"])
            b.update("a",data)
            self.assertEqual(b.rows(live=True)[0]["command_history"],data["command_history"])
            legacy=["pwd","pwd","ls -a","cd dorf","echo alt"]
            b.update("a",dict(data,command_history=legacy))
            self.assertEqual(b.rows(live=True)[0]["command_history"],legacy[:3])
            self.assertNotIn("command_history",b.rows()[0])
            b.update("a",dict(data,connected=False))
            self.assertEqual(b.rows(live=True),[])
            b.db.close()
        self.assertEqual("".join(wrap_command("echo 'one  two' | wc -c",6)),"echo 'one  two' | wc -c")

    def test_board_shows_active_command_and_three_completed_in_order(self):
        from frost.board import paint_history,paint_list
        row=dict(public(fresh("Elf")),slot="1",updated=100,connected=True,
                 command_active=True,command_label="sleep 5",
                 command_history=["ls -a","pwd","pwd","ignored older entry"])
        screen=type("Screen",(),{"getmaxyx":lambda self:(24,80),"erase":lambda self:None})()
        for painter,args in [(paint_board,([row],102)),(paint_list,([row],0)),(paint_history,(row,0))]:
            with self.subTest(view=painter.__name__), patch("frost.board.put") as put,patch("frost.board.box"):
                painter(screen,*args)
                text="\n".join(call.args[3] for call in put.call_args_list)
                self.assertEqual(text.count("pwd"),2)
                self.assertIn("sleep 5",text)
                self.assertIn("ls -a",text)
                self.assertNotIn("ignored older entry",text)
                self.assertLess(text.index("ls -a"),text.index("pwd"))

    def test_score_list_separates_players_and_keeps_selected_history_on_screen(self):
        from frost.board import paint_list
        rows=[dict(public(fresh(f"Elf{i:02}")),command_active=True,command_label="ls",
                   command_history=["pwd","ls","tree"]) for i in range(25)]
        for height,width in ((12,32),(24,80)):
            screen=type("Screen",(),{"getmaxyx":lambda self:(height,width),"erase":lambda self:None})()
            with patch("frost.board.put") as put:
                paint_list(screen,rows,18)
            lines={call.args[1]:call.args[3] for call in put.call_args_list}
            self.assertLess(max(lines),height)
            self.assertTrue(any("Elf18 · Rucksack" in text for text in lines.values()))
            for y,text in lines.items():
                if "Elf" in text and "Rucksack" not in text:
                    self.assertIn(lines[y+1][0],"─━")
            self.assertIn("tree",lines[max(lines)])

    def test_avatar_presence_events_and_old_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            board=Board(str(Path(folder)/'score.db'),{'player01':'t'})
            data=public(fresh('Elf'))
            data.update(avatar={'hair':'blond','shirt':'lila'},connected=True,
                        events=[{'at':100,'damage':22,'hurt':7}],bests={'normal:classic':40,'speedrun:loop':8})
            board.update('player01',data)
            row=board.rows()[0]
            self.assertEqual(row['avatar'],dict(data['avatar'],gender='männlich',style='kurz'))
            self.assertEqual(row['bests'],{'best':8})
            self.assertEqual(row['events'],data['events'])
            self.assertTrue(online(row,row['updated']+2))
            self.assertFalse(online(row,row['updated']+9))
            data['connected']=False
            board.update('player01',data)
            self.assertFalse(online(board.rows()[0],board.rows()[0]['updated']))
            for invalid in [dict(data,avatar={'hair':'evil','shirt':'lila'}),dict(data,connected='yes'),dict(data,events=[{'at':100,'damage':999,'hurt':0}])]:
                with self.assertRaises(ValueError): board.update('player01',invalid)
            board.db.close()

    def test_board_layout_all_players_small_and_large(self):
        rows=[dict(public(fresh(f'Elf{i:02}')),slot=f'player{i:02}',updated=100,connected=True,
                   score=i*10,bests={'best':30+i}) for i in range(1,24)]
        class Screen:
            def __init__(self,h,w): self.h,self.w=h,w
            def getmaxyx(self): return self.h,self.w
            def erase(self): pass
        for h,w in [(24,80),(42,120),(48,160),(12,35)]:
            drawn=[]
            with patch('frost.board.put',side_effect=lambda screen,y,x,text,*args: drawn.append((y,x,str(text)))),patch('frost.board.box'):
                pages=paint_board(Screen(h,w),rows,102)
            self.assertGreaterEqual(pages,1)
            if w>=44:
                text=' '.join(v[2] for v in drawn)
                self.assertIn('23 ONLINE',text)
                self.assertIn('ONLINE',text)
                self.assertNotIn('SPEEDRUN',text)
                self.assertNotIn('Bestzeit:',text)
                self.assertEqual(pages,1)
                self.assertTrue(all(r['name'] in text for r in rows))
            self.assertTrue(all(0<=y<h and 0<=x<w for y,x,_ in drawn))


if __name__=='__main__': unittest.main()
