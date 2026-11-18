"""Root-only, narrow controller RPC. No Docker access in gateway or player shells."""
import json
import socket

SOCKET='/run/controller/control.sock'


class Client:
    def call(self,action,slot=None,**kwargs):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(300); sock.connect(SOCKET)
            sock.sendall(json.dumps({'action':action,'slot':slot,**kwargs}).encode()+b'\n')
            with sock.makefile('rb') as stream: result=json.loads(stream.readline(65536))
        if not result['ok']: raise ValueError(result['error'])
        return result.get('result')
    def create(self): return self.call('create')['slot']
    def destination(self,slot): return self.call('start',slot)
    def player_name(self,slot): return self.call('name',slot)
    def idle(self,slot): return self.call('idle',slot)
