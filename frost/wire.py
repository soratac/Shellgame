"""Bounded binary frames for the local SSH gateway relay."""
import json
import struct


def send(sock, kind, data=b""):
    if not isinstance(data,bytes): data=json.dumps(data).encode()
    if len(data)>65536: raise ValueError("frame too large")
    sock.sendall(struct.pack("!cI",kind,len(data))+data)


def receive(sock):
    def exact(n):
        chunks=[]
        while n:
            chunk=sock.recv(n)
            if not chunk: raise EOFError
            chunks.append(chunk)
            n-=len(chunk)
        return b"".join(chunks)
    kind,size=struct.unpack("!cI",exact(5))
    if size>65536: raise ValueError("frame too large")
    return kind,exact(size)
