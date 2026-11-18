"""Public command labels for spectators. Only game vocabulary is shared."""
from .items import ITEMS
from .trail import BOSS_IP

COMMANDS = frozenset("ls pwd cd tree cp mv cat grep find sort head tail wc nano vim sleep ssh ping systemctl modprobe lsmod inventar karte hilfe restart neustart aussehen angreifen zauber heilen while".split())
PUBLIC_ARGS = set(ITEMS) | {"-a","-la","-al","-c","4","disable","status","list-unit-files",
    "grinch","eissturm.service",BOSS_IP,"~/rucksack/","~/rucksack","-r","frost_armor","blizzard",
    "wurzeln/frost",".lichtung/beeren",".depot/stern","game"} | {
    prefix+place for prefix in ("../","~/welt/") for place in ("dorf","wald","archiv","werkstatt","zitadelle")}


def public_command(line):
    words = line.strip().split()
    if not words:
        return ""
    first = words[0]
    if first.startswith("~/rucksack/") and first.removeprefix("~/rucksack/") in ITEMS:
        return first
    if first not in COMMANDS:
        return "Shell"
    args = []
    for word in words[1:5]:
        if word not in PUBLIC_ARGS: break
        args.append(word)
    return " ".join([first, *args])
