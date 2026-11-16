import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

from frost.board import Board, handler_for
from frost.engine import fresh, public


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/"score.sqlite"
        self.tokens={f"player{i:02}":f"test-token-{i}" for i in range(1,24)}
        self.board=Board(self.path,self.tokens)

    def tearDown(self):
        self.board.db.close()
        self.folder.cleanup()

    def test_23_concurrent_updates_and_persistence(self):
        def update(i):
            data=public(fresh(f"Player {i}",now=100),now=110)
            data["score"]=i*10
            self.board.update(f"player{i:02}",data)
        with ThreadPoolExecutor(max_workers=23) as pool: list(pool.map(update,range(1,24)))
        self.assertEqual(len(self.board.rows()),23)
        self.assertEqual(self.board.rows()[0]["slot"],"player23")
        other=Board(self.path,self.tokens)
        self.assertEqual(len(other.rows()),23)
        other.db.close()

    def test_http_identity_and_authentication(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.board))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            url=f"http://127.0.0.1:{server.server_port}/api/score"
            data=public(fresh("Winterheld"))
            data["slot"]="player23"
            req=urllib.request.Request(url,json.dumps(data).encode(),headers={"Authorization":"Bearer test-token-1"})
            with urllib.request.urlopen(req) as response: self.assertEqual(response.status,200)
            self.assertEqual(self.board.rows()[0]["slot"],"player01")
            req=urllib.request.Request(url,b"{}",headers={"Authorization":"Bearer wrong"})
            with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(req)
            self.assertEqual(error.exception.code,401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_invalid_values_rejected(self):
        for key,value in [("name","\x1b[2J"),("score",float("nan")),("hp",200),("bests",{"bad":3})]:
            data=public(fresh("Winterheld"))
            data[key]=value
            with self.assertRaises(ValueError): self.board.update("player01",data)


if __name__=="__main__": unittest.main()
