"""Decode xterm cell coordinates while forwarding ordinary PTY input unchanged."""
import re
import time

REPORT = re.compile(rb"\x1b\[<(\d{1,4});(\d{1,5});(\d{1,5})([Mm])")
PREFIX = b"\x1b[<"


class MouseInput:
    def __init__(self):
        self.pending = b""
        self.since = 0

    def feed(self, data, click):
        data = self.pending + data
        self.pending = b""
        out = bytearray()
        while data:
            pos = data.find(PREFIX)
            if pos < 0:
                tail = 2 if data.endswith(PREFIX[:2]) else int(data.endswith(PREFIX[:1]))
                out.extend(data[:len(data)-tail])
                self.pending = data[len(data)-tail:]
                break
            out.extend(data[:pos])
            data = data[pos:]
            match = REPORT.match(data)
            if match:
                if match[1]==b"0" and match[4]==b"M":
                    click(int(match[2])-1, int(match[3])-1)
                data=data[match.end():]
            elif len(data)<22 and re.fullmatch(rb"[0-9;]*", data[len(PREFIX):]):
                self.pending=data
                break
            else:
                out.extend(data[:1])
                data=data[1:]
        if self.pending: self.since=time.monotonic()
        return bytes(out)

    def flush(self):
        data,self.pending=self.pending,b""
        return data
