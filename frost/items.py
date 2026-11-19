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
    if "heal:"+item in state.get("rewards", []): return "×0"
    return "×1" if item in ITEMS else ""


DELIVERIES = {"dorf": "gerettet.txt", "wald": "zeichen.txt", "werkstatt": "maschine.conf", "archiv": "passwort.txt"}


SPELL_QUEST = {"funke":"wunschzettel", "ping":"wunschzettel", "frost":"waldzeichen",
               "schild":"geschenkband", "stern":"passwort"}


def unlocked(state, item):
    # Already earned spells stay playable in saves from before quest rewards.
    return (item not in SPELL_QUEST or "quest:"+SPELL_QUEST[item] in state["rewards"]
            or item in state["spells"] or (item=="ping" and item in state.get("bag", [])))


def pickup(item):
    return "mv"


def script(item, legacy=False):
    verb = 'cp' if legacy else pickup(item)
    return f'#!/bin/sh\n# {ITEMS[item][1]}\n# Mitnehmen: {verb} {item} ~/rucksack/\n# Benutzen: ~/rucksack/{item}\nexec /usr/local/bin/frost use {item}\n'

def is_item_script(item, content):
    # Released wrappers differ in their instructions. Match the executable part.
    lines = content.splitlines()
    return (len(content) <= 2048 and lines[:1] == ["#!/bin/sh"]
            and [line for line in lines[1:] if line and not line.startswith("#")] ==
                [f"exec /usr/local/bin/frost use {item}"])
