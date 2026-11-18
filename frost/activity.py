"""Bounded, session-local history of submitted Bash commands."""
from collections import deque

MAX_COMMAND = 16 * 1024
HISTORY_SIZE = 3
# Older player containers can still send five completed commands.
WIRE_HISTORY_SIZE = 5
# JSON can escape one Unicode character as a pair of six-byte surrogates.
MAX_PAYLOAD = 12 * MAX_COMMAND * (WIRE_HISTORY_SIZE + 1) + 64 * 1024


def bounded_command(text):
    if len(text) <= MAX_COMMAND:
        return text
    return text[:MAX_COMMAND-1]+"…"


class Activity:
    def __init__(self):
        self.current = ""
        self.completed = deque(maxlen=HISTORY_SIZE)

    def begin(self, command):
        self.finish()
        self.current = bounded_command(command)

    def finish(self):
        if self.current:
            self.completed.appendleft(self.current)
            self.current = ""

    def clear(self):
        self.current = ""
        self.completed.clear()

    def snapshot(self):
        return {"command_label": self.current, "command_active": bool(self.current),
                "command_history": list(self.completed)}


def screen_command(text, multiline=False):
    """Keep spacing and quotes. Make terminal controls visible as plain text."""
    return "".join(ch if ch.isprintable() or (multiline and ch=="\n")
                   else "\\n" if ch=="\n" else "\\t" if ch=="\t"
                   else ascii(ch)[1:-1] for ch in text)
