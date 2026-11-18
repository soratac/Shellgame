"""Small Docker Engine client; only the controller receives the Docker socket."""
import http.client
import json
import os
import socket
import urllib.parse


class DockerError(RuntimeError): pass


class Connection(http.client.HTTPConnection):
    def __init__(self,path): super().__init__('localhost',timeout=60); self.path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout); self.sock.connect(self.path)


class Docker:
    def __init__(self,path=None): self.path=path or os.environ.get('DOCKER_SOCKET','/var/run/docker.sock')
    def call(self,method,path,data=None,raw=False):
        conn=Connection(self.path)
        body=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
        headers={'Content-Type':'application/x-tar' if isinstance(data,bytes) else 'application/json'}
        try:
            conn.request(method,'/v1.48'+path,body,headers)
            response=conn.getresponse(); content=response.read()
            if response.status>=400:
                try: message=json.loads(content).get('message','Docker error')
                except ValueError: message='Docker error'
                raise DockerError(f'{response.status}: {message}')
            return content if raw else json.loads(content) if content else None
        finally: conn.close()
    def containers(self,labels):
        filters=urllib.parse.quote(json.dumps({'label':labels}))
        return self.call('GET','/containers/json?all=1&filters='+filters)
