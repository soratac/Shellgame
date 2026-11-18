"""Deterministic game rules. No terminal, network or filesystem dependencies."""
import re
import time
import hashlib
from .avatar import DEFAULT, HAIR, SHIRTS
from .records import migrate, bests as merge_bests

AREAS = {
    "dorf": ("Sternendorf", "Warme Fenster, Zimtduft und ein gestohlener Weihnachtsstern."),
    "wald": ("Fluesterwald", "Frost zwischen den Tannen. Unter den Wurzeln leuchtet Magie."),
    "werkstatt": ("Elfenwerkstatt", "Das Geschenkband steht still. Die Elfen brauchen deine Hilfe."),
    "archiv": ("Nordlichtarchiv", "Alte Logdateien verraten die Schwaechen des Frostkoenigs."),
    "zitadelle": ("Eiszitadelle", "KRAMPUS.EXE bewacht den Weihnachtsstern. Dein Zug!"),
}
SPELL_FILES = {
    "funke.spell": ("dorf", "funke"), "frost.spell": ("wald", "frost"),
    "schild.spell": ("werkstatt", "schild"), "stern.spell": ("archiv", "stern"),
}
HELP = """ls / tree ~/welt       Umschauen
cp DATEI ~/rucksack/    Mitnehmen
cd ~/welt/wald         Weitergehen
~/rucksack/funke        Angreifen
~/rucksack/kakao        Heilen

Dorf → Wald → Werkstatt → Boss. Drei Orte oeffnen das Siegel.
Tab hilft beim Tippen. aussehen aendert deinen Charakter.
neustart | neustart alles (eigene Rekorde)
"""


def fresh(name="", now=None, bests=None):
    return dict(version=5, name=name, started=now if now is not None else time.time(),
                ended=None, hp=100, boss_hp=240, score=0, area="dorf", visited=[],
                spells={}, rewards=[], status="playing", method=None, shield=0, frozen=0,
                armor=True, blizzard=True, loop_hits=[], bests=merge_bests(bests), bag=[], deliveries={},
                boss_started=False, battle_items=[], avatar=dict(DEFAULT), avatar_set=False, events=[], event_seq=0,
                message="Nimm den Funken mit: cp funke ~/rucksack/")


def reward(s, key, points):
    if key not in s["rewards"]:
        s["rewards"].append(key)
        s["score"] += points
        return True
    return False


def public(s, now=None):
    now = time.time() if now is None else now
    return {**{k: v for k, v in s.items() if k != "loop_hits"},
            "elapsed": round(max(0, (s["ended"] if s["ended"] is not None else now) - s["started"]), 2)}


def win(s, method, now):
    s.update(boss_hp=0, status="won", ended=now, method=method)
    reward(s, "victory", 500)
    elapsed = max(0, now - s["started"])
    s["bests"]["best"] = min(elapsed, s["bests"].get("best", float("inf")))
    s["message"] = f"WEIHNACHTEN GERETTET! {elapsed:.2f}s / {s['score']} Punkte / {method}"


def counter(s, damage=7):
    if s["frozen"]:
        s["frozen"] -= 1
        return " Krampus ist eingefroren."
    if s["shield"]:
        s["shield"] -= 1
        return " Dein Schild faengt den Angriff ab."
    damage = damage if s["blizzard"] else max(1, damage // 3)
    s["hp"] = max(0, s["hp"] - damage)
    if s["hp"] == 0:
        s["status"] = "lost"
        return " DEIN LICHT ERLISCHT. Starte mit neustart erneut."
    return f" Eissturm: -{damage} HP."


def _act(s, action, args=(), *, now=None, cwd=None, code=0, command="", content=""):
    now = time.time() if now is None else now
    migrate(s)
    args = list(args)
    s.setdefault("bag", [])
    s.setdefault("deliveries", {})
    s.setdefault("boss_started", False)
    s.setdefault("battle_items", [])
    s.setdefault("avatar", dict(DEFAULT))
    s.setdefault("avatar_set", False)
    s.setdefault("events", [])
    s.setdefault("event_seq", 0)
    result = {"ok": True, "message": "", "stop": False}
    message = ""
    if action == "name":
        name = args[0].strip() if args else ""
        if not re.fullmatch(r"[\w -]{2,20}", name, flags=re.UNICODE):
            return {"ok": False, "message": "Name: 2–20 Buchstaben/Ziffern, Leerzeichen, _ oder -.", "stop": False}
        if s["name"]:
            return {"ok": False, "message": "Name bereits gesetzt. Dein Lauf wird fortgesetzt.", "stop": False}
        s.update(fresh(name, now=now))
        message = f"Willkommen, {name}! Weihnachten braucht dich."
    elif action == "avatar":
        if len(args)!=2 or args[0] not in HAIR or args[1] not in SHIRTS:
            return {"ok":False,"message":"Waehle Haar- und Shirtfarbe.","stop":False}
        s.update(avatar={"hair":args[0],"shirt":args[1]}, avatar_set=True)
        message="Dein Winterheld ist bereit."
    elif action == "reset":
        if args not in ([], ["normal"], ["alles"]):
            return {"ok": False, "message": "neustart | neustart alles", "stop": False}
        avatar, avatar_set = s["avatar"], s["avatar_set"]
        s.update(fresh(s["name"], now=now, bests={} if args == ["alles"] else s["bests"]))
        s.update(avatar=avatar, avatar_set=avatar_set)
        message = "Neuer Lauf. Auf ins Dorf!"
    elif action in ("status", "map", "inventory", "help", "modules"):
        if action == "help":
            message = HELP
        elif action == "inventory":
            message = "Zauber: " + (", ".join(f"{k} ({'unendlich' if v == -1 else v})" for k, v in s["spells"].items()) or "noch keine; lies HILFE.txt im Dorf")
        elif action == "modules":
            message = "Module          Status      Welt: simulierte Treiber\n" + "\n".join(
                f"{module:16}{'geladen' if s[key] else 'entfernt'}" for module, key in [("frost_armor", "armor"), ("blizzard", "blizzard")])
        else:
            message = f"{s['name']} | HP {s['hp']}/100 | Krampus {s['boss_hp']}/240 | {s['score']} Punkte | {s['status']}"
    elif s["status"] != "playing":
        message = "" if action in ("observe", "bag", "deliver") else "Lauf beendet. Neuer Versuch: neustart"
        result["stop"] = action in ("cast", "attack", "unload", "use")
    elif action == "enter_boss":
        if s["area"] != "zitadelle":
            return {"ok": False, "message": "Gehe zuerst zur Zitadelle.", "stop": False}
        if not s["boss_started"]:
            s["boss_started"] = True
            s["battle_items"] = list(s["bag"])
            message = "Das Tor ist zu. Kaempfen: ~/rucksack/funke. Kein Rueckweg bis Sieg oder Niederlage."
    elif s["boss_started"] and action in ("collect", "deliver", "submit"):
        if action != "deliver":
            message = "Das Tor ist geschlossen. Im Kampf gibt es keine neuen Funde oder Aufgaben."
        result["ok"] = False
    elif action == "bag":
        allowed = {"funke", "frost", "stern", "schild", "kakao", "beeren"}
        if s["boss_started"]:
            allowed &= set(s["battle_items"])
        s["bag"] = sorted(set(args) & allowed)
        new = []
        for item in s["bag"]:
            if item in {"funke", "frost", "stern", "schild"} and reward(s, "spell:"+item, 80):
                s["spells"][item] = {"funke": -1, "frost": 3, "stern": 2, "schild": 2}[item]
                new.append(item)
        if new:
            message = "Im Rucksack: " + ", ".join(new) + ". Benutzen: ~/rucksack/" + new[0]
    elif action == "use":
        item = args[0] if args else ""
        if item not in s["bag"]:
            return {"ok": False, "message": f"Zuerst mitnehmen: cp {item or 'DATEI'} ~/rucksack/", "stop": False}
        return _act(s, "heal" if item in ("kakao", "beeren") else "cast", [item], now=now)
    elif action == "deliver":
        place = args[0] if args else ""
        if place not in ("dorf", "werkstatt", "archiv"):
            return {"ok": False, "message": "Unbekannte Abgabe.", "stop": False}
        digest = hashlib.sha256(content.encode()).hexdigest()
        if s["deliveries"].get(place) == digest:
            return result
        s["deliveries"][place] = digest
        # A Linux copy into another location's inbox also counts there.
        return _act(s, "submit", now=now, cwd=place, content=content)
    elif action == "observe":
        if s["boss_started"]:
            cwd = "zitadelle"
        if cwd not in AREAS:
            s["area"] = "unterwegs"
        if cwd in AREAS and cwd != s["area"]:
            s["area"] = cwd
            message = AREAS[cwd][1]
        if cwd in AREAS and cwd not in s["visited"]:
            s["visited"].append(cwd)
            reward(s, "visit:" + cwd, 40)
            if cwd == "wald":
                s["hp"] = max(1, s["hp"] - 8)
                message += " Eisige Dornen: -8 HP."
        first = command.strip().split(" ", 1)[0]
        if code == 0 and first in {"ls", "cat", "pwd", "cp", "mkdir", "grep", "find", "sort", "uniq", "head", "tail", "wc", "sed", "awk", "tree"}:
            reward(s, "shell:" + first, 10)
        if code not in (0, 130) and s["boss_started"]:
            message = "Ein fehlgeschlagener Shell-Befehl weckt Krampus." + counter(s, 10)
    elif action == "collect":
        item = args[0].split("/")[-1] if args else ""
        found = SPELL_FILES.get(item)
        if not found or found[0] != s["area"]:
            result["ok"] = False
            message = "Hier liegt dieser Zauber nicht. Nutze ls oder find."
        elif reward(s, "spell:" + found[1], 80):
            s["spells"][found[1]] = {"funke": -1, "frost": 3, "stern": 2, "schild": 2}[found[1]]
            message = f"Zauber {found[1]} gelernt! +80 Punkte. Nutze zauber {found[1]}."
        else:
            message = "Diesen Zauber hast du bereits eingesammelt."
    elif action == "heal":
        item = args[0] if args else ""
        source = {"kakao": ("dorf", 35), "beeren": ("wald", 25)}.get(item)
        if not source or (s["area"] != source[0] and item not in s["bag"]):
            result["ok"] = False
            message = "Hier gibt es das nicht. Kakao im Dorf, Beeren im Wald."
        elif s["hp"] == 100:
            message = "Du bist gesund. Hebe die Heilung fuer spaeter auf."
        elif reward(s, "heal:" + item, 25):
            old = s["hp"]
            s["hp"] = min(100, s["hp"] + source[1])
            message = f"{item}: +{s['hp'] - old} HP."
        else:
            message = "Schon aufgebraucht."
    elif action == "submit":
        solutions = {"dorf": ("Mila: Stern\nNoah: Schlitten", "wunschzettel"),
                     "werkstatt": ("band=an\nlicht=an\nziel=weihnachten", "geschenkband"),
                     "archiv": ("AURORA", "passwort")}
        solution = solutions.get(cwd or s["area"])
        if solution and content.strip() == solution[0]:
            if reward(s, "quest:" + solution[1], 150):
                s["hp"] = min(100, s["hp"] + 20)
                message = "Aufgabe geloest! +150 Punkte und bis zu +20 HP."
            else:
                message = "Diese Aufgabe ist bereits geloest."
        else:
            result["ok"] = False
            s["hp"] = max(0, s["hp"] - 5)
            if s["hp"] == 0:
                s["status"] = "lost"
            message = "Das passt noch nicht. Ein Funken trifft dich: -5 HP. Lies AUFGABE.txt."
    elif action in ("attack", "cast", "unload"):
        if s["area"] != "zitadelle" or not s["boss_started"]:
            result["ok"] = False
            message = "Gehe zur Zitadelle und bestaetige den Bosskampf zuerst."
        else:
            spell = args[0] if args else ""
            damage = 0
            method = "spell" if action == "cast" else "staff"
            if action == "unload":
                key = {"frost_armor": "armor", "blizzard": "blizzard"}.get(spell)
                if key and s[key]:
                    s[key] = False
                    reward(s, "driver:" + spell, 120)
                    message = f"Spiel-Treiber {spell} entfernt! +120 Punkte."
                else:
                    result["ok"] = False
                    message = "Unbekannter oder bereits entfernter Spiel-Treiber."
            elif action == "attack":
                damage = 24
                message = "Zuckerstabschlag!"
            elif s["spells"].get(spell, 0) == 0:
                result["ok"] = False
                message = "Zauber unbekannt oder aufgebraucht. Nutze inventar."
            else:
                if s["spells"][spell] > 0:
                    s["spells"][spell] -= 1
                damage = {"funke": 30, "frost": 38, "stern": 75, "schild": 0}[spell]
                if spell == "frost":
                    s["frozen"] = 2
                if spell == "schild":
                    s["shield"] = 3
                if spell == "funke":
                    s["loop_hits"] = [t for t in s["loop_hits"] if now - t < 2.0] + [now]
                    if len(s["loop_hits"]) >= 6:
                        reward(s, "exploit:loop", 200)
                        win(s, "loop", now)
                        result.update(message=s["message"], stop=True)
                        return result
                message = f"{spell.upper()}!"
            if damage:
                damage = max(1, damage - (8 if s["armor"] else 0))
                # The loop bypass above remains available from the village. Ordinary
                # spells, staff and driver tactics need three explored non-boss places.
                floor = 0 if route_ready(s) else 1
                damage = min(damage, max(0, s["boss_hp"]-floor))
                s["boss_hp"] = max(floor, s["boss_hp"] - damage)
                if not route_ready(s):
                    message += " Frostsiegel: 3 Orte oder Funken-Loop."
                reward(s, "combat:" + (spell if action == "cast" else "staff"), 30)
                message += f" -{damage} Boss-HP."
            if s["boss_hp"] == 0:
                win(s, "driver" if not s["armor"] or not s["blizzard"] else method, now)
                result.update(message=s["message"], stop=True)
                return result
            message += counter(s, 7 if result["ok"] else 12)
    else:
        result["ok"] = False
        message = "Unbekannte Spielaktion. Nutze hilfe."
    if s["status"] == "lost" and s["ended"] is None:
        s["ended"] = now
        message += " VERLOREN. Mit neustart beginnt ein neuer Lauf."
    if message and action not in ("help", "status", "inventory", "map", "modules"):
        s["message"] = message
    result["message"] = message
    result["stop"] = result["stop"] or (s["status"] == "lost" and action in ("cast", "attack", "unload"))
    return result


def route_count(s):
    return len(set(s.get("visited",[])) & {"dorf","wald","werkstatt","archiv"})


def route_ready(s):
    return route_count(s)>=3


def act(s, action, args=(), **kwargs):
    """Record bounded combat events; rendering never delays the shell or loop."""
    before_hp, before_boss = s["hp"], s["boss_hp"]
    result = _act(s, action, args, **kwargs)
    if action not in ("reset","name") and (before_hp!=s["hp"] or before_boss!=s["boss_hp"] or action in ("cast","attack","unload","use")):
        s["event_seq"] += 1
        s["events"].append(dict(id=s["event_seq"], at=kwargs.get("now",time.time()),
            kind=action, spell=args[0] if args else "stab", hp_before=before_hp,
            boss_before=before_boss, hp=s["hp"], boss_hp=s["boss_hp"],
            damage=before_boss-s["boss_hp"], hurt=before_hp-s["hp"]))
        s["events"]=s["events"][-24:]
    return result
