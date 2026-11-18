import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from frost.gateway import Allocator
from frost.board import Board
from frost.spawner import Manager
from types import SimpleNamespace
from unittest.mock import Mock
from scripts.env_config import read_env,write_env


class Provider:
    def __init__(self): self.names={}; self.stopped=[];self.lock=threading.Lock();self.sequence=0
    def call(self,action): return list(self.names)
    def create(self):
        with self.lock:
            self.sequence+=1;slot=f'elf-{self.sequence:016x}';self.names[slot]='';return slot
    def player_name(self,slot): return self.names.get(slot)
    def idle(self,slot):
        self.stopped.append(slot)
        if self.names.get(slot)=='': self.names.pop(slot)


class DynamicTests(unittest.TestCase):
    def test_service_lookup_ignores_inherited_compose_image_labels(self):
        docker=Mock()
        docker.containers.return_value=[
            {'Id':'real-board','State':'running','Labels':{}},
            {'Id':'player','State':'running','Labels':{'frost.managed':'shell-game'}}]
        manager=SimpleNamespace(project='shell-game',docker=docker)
        self.assertEqual(Manager.service(manager,'scoreboard'),'real-board')

    def test_60_concurrent_players_no_fixed_slot_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            provider=Provider();allocator=Allocator(Path(temp)/'join.db',[],Path(temp),provider)
            with ThreadPoolExecutor(max_workers=12) as pool: results=list(pool.map(lambda _:allocator.reserve(),range(60)))
            self.assertEqual(len({r[0] for r in results}),60)
            self.assertEqual(len({r[1] for r in results}),60)
            self.assertEqual(len(provider.names),60)
            allocator.db.close()

    def test_resume_stops_same_container_and_orphan_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            provider=Provider();path=Path(temp)/'join.db';allocator=Allocator(path,[],Path(temp),provider)
            slot,code,lease=allocator.reserve();provider.names[slot]='Elf'
            allocator.release(slot,lease)
            self.assertEqual(provider.stopped,[slot])
            resumed,new_code,new_lease=allocator.reserve(code)
            self.assertEqual((resumed,new_code),(slot,code))
            allocator.release(slot,lease)
            self.assertEqual(provider.stopped,[slot])
            orphan=provider.create()
            allocator.db.close();allocator=Allocator(path,[],Path(temp),provider)
            self.assertNotIn(orphan,provider.names)
            self.assertEqual(allocator.reserve(code)[0],slot)
            allocator.db.close()

    def test_failed_creation_does_not_allocate_code(self):
        with tempfile.TemporaryDirectory() as temp:
            provider=Provider();allocator=Allocator(Path(temp)/'join.db',[],Path(temp),provider)
            with patch.object(provider,'create',side_effect=ValueError('Docker unavailable')):
                with self.assertRaises(ValueError): allocator.reserve()
            self.assertEqual(allocator.list_rows(),[])
            allocator.db.close()

    def test_dynamic_score_token_is_reloaded(self):
        with tempfile.TemporaryDirectory() as temp:
            board=Board(str(Path(temp)/'board.db'),{'player01':'old'})
            registry=Path(temp)/'registry.json';registry.write_text('{}')
            with patch('frost.board.Path',return_value=registry):
                self.assertIsNone(board.authenticate('new-token'))
                registry.write_text(json.dumps({'elf-123':'new-token'}))
                self.assertEqual(board.authenticate('new-token'),'elf-123')
                self.assertEqual(board.authenticate('old'),'player01')
            board.db.close()

    def test_fresh_install_has_only_three_services_no_player_pool(self):
        import sys
        from scripts import provision
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(provision,'ROOT',Path(temp)),patch.object(sys,'argv',['provision.py','--host','example.test']),patch('builtins.print'):
                provision.main()
            config=json.loads((Path(temp)/'compose.yaml').read_text())
            self.assertEqual(set(config['services']),{'gateway','scoreboard','spawner'})
            self.assertEqual(config['services']['gateway']['environment']['FROST_DYNAMIC'],'1')
            env=read_env(Path(temp)/'.env')
            self.assertEqual(len(env['PLAYER_PASSWORD']),12)
            self.assertEqual(len(env['DASHBOARD_PASSWORD']),12)
            self.assertFalse(any('docker.sock' in v for k in ('gateway','scoreboard') for v in config['services'][k]['volumes']))

    def test_env_values_are_literal_and_private(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'.env'
            values={'PLAYER_PASSWORD':'AbcDef123456','DASHBOARD_PASSWORD':'Another12345','LITERAL':'$(no-execution)'}
            write_env(path,values)
            self.assertEqual(read_env(path),values)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            with self.assertRaises(ValueError): write_env(path,{'BAD':'line\nbreak'})


if __name__=='__main__':unittest.main()
