"""The discoverable executable files: normal cp/mv and shell execution."""
ITEMS = {
    "ping": ("dorf/ping", "Echo: im Kampf vier kleine Treffer mit ping -c 4 IP."),
    "funke": ("dorf/funke", "Feuer: unbegrenzt, 30 Schaden."),
    "kakao": ("dorf/kakao", "Heilt einmal bis zu 35 Leben."),
    "frost": ("wald/wurzeln/frost", "38 Schaden + zwei Runden Ruhe. 3 Ladungen."),
    "beeren": ("wald/.lichtung/beeren", "Heilen einmal bis zu 25 Leben."),
    "schild": ("werkstatt/schild", "Blockt drei Treffer. 2 Ladungen."),
    "stern": ("archiv/.depot/stern", "75 Schaden. 2 Ladungen."),
}
BAG_ICONS = {"funke":("✦",6), "frost":("❄",2), "stern":("★",5),
             "schild":("◇",9), "kakao":("♥",7), "beeren":("♥",6), "ping":("◉",2)}


def bag_count(item,state):
    charges=state.get("spells",{}).get(item)
    if item in ("funke","ping") or charges==-1: return "∞"
    if charges is not None: return f"×{charges}"
    return "×1" if item in ITEMS else ""


DELIVERIES = {"dorf": "gerettet.txt", "werkstatt": "maschine.conf", "archiv": "passwort.txt"}


MOVE_ITEMS = {"schild", "stern"}


def pickup(item):
    return "mv"


def script(item, legacy=False):
    verb = 'cp' if legacy else pickup(item)
    return f'#!/bin/sh\n# {ITEMS[item][1]}\n# Mitnehmen: {verb} {item} ~/rucksack/\n# Benutzen: ~/rucksack/{item}\nexec /usr/local/bin/frost use {item}\n'
