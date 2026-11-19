"""Deterministic game rules. No terminal, network or filesystem dependencies."""
import re
import time
import hashlib
from .trail import BOSS_IP, discovered, hiding_place
from .items import pickup, ITEMS, bag_count, DELIVERIES, SPELL_QUEST, unlocked
from .avatar import DEFAULT, OPTIONS, appearance
from .records import migrate, bests as merge_bests

AREAS = {
    "dorf": ("Sternendorf", "Warme Fenster, Zimtduft und ein gestohlener Weihnachtsstern."),
    "wald": ("Fluesterwald", "Frost zwischen den Tannen. Unter den Wurzeln leuchtet Magie."),
    "werkstatt": ("Elfenwerkstatt", "Das Geschenkband steht still. Die Elfen brauchen deine Hilfe."),
    "archiv": ("Nordlichtarchiv", "Alte Logdateien verraten die Schwaechen des Frostkoenigs."),
    "zitadelle": ("Eiszitadelle", "Der Grinch bewacht den Weihnachtsstern. Dein Zug!"),
}
SPELL_FILES = {
    "funke.spell": ("dorf", "funke"), "frost.spell": ("wald", "frost"),
    "schild.spell": ("werkstatt", "schild"), "stern.spell": ("archiv", "stern"),
}
HELP = """ls / tree ~/welt       Umschauen
cat AUFGABE.txt         Zauber freischalten
mv DATEI ~/rucksack/    Mitnehmen
cd ~/welt/wald         Weitergehen
~/rucksack/funke        Angreifen
~/rucksack/kakao        Heilen

Folge der Spur auf der Karte. Am Fundort zeigt nmap grinch seine IP.

ls -a zeigt Verstecke. Mit cp oder mv kommt jeder Fund in den Rucksack.
systemctl status zeigt Bossdienste. restart beginnt eine neue Runde.
tipp gibt einen von drei Hinweisen pro Runde. Tab hilft beim Tippen. aussehen aendert deinen Charakter.
restart | restart alles (eigene Rekorde)
"""


HINT_LIMIT = 3
ECLIPSE_THRESHOLDS = (190, 95)
ECLIPSE_HIT = 46


def fresh(name="", now=None, bests=None):
    return dict(version=5, name=name, started=now if now is not None else time.time(),
                ended=None, hp=100, boss_hp=240, score=0, time_bonus=None, area="dorf", visited=[],
                spells={}, rewards=[], status="playing", method=None, shield=0, frozen=0,
                storm_service=True, combat_turn=0, eclipse_casts=0, charging=False, last_attack=None, armor=True, blizzard=True, loop_hits=[], bests=merge_bests(bests), bag=[], deliveries={},
                hints_left=HINT_LIMIT, hint_until=0, hint_text="", grinch_found=False, boss_started=False, battle_items=[], avatar=dict(DEFAULT), avatar_set=False, events=[], event_seq=0,
                message="Rette den Wunschzettel: cat AUFGABE.txt")


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


def victory_time_bonus(elapsed):
    seconds = max(0, int(elapsed))
    # The first five minutes are worth 12 points per second saved.
    if seconds < 300:
        return 4800 - 12 * seconds
    return max(0, 1200 - 2 * (seconds - 300))


def win(s, method, now):
    elapsed = max(0, now - s["started"])
    bonus = victory_time_bonus(elapsed)
    if not reward(s, "victory", 500 + bonus):
        return
    s.update(boss_hp=0, status="won", ended=now, method=method, charging=False)
    s["time_bonus"] = bonus
    s["bests"]["best"] = min(elapsed, s["bests"].get("best", float("inf")))
    s["message"] = f"WEIHNACHTEN GERETTET! {elapsed:.2f}s / {s['score']} Punkte (inkl. {bonus} Zeitbonus)"


def boss_lock(s):
    if s["armor"]:
        return "Eispanzer lösen: modprobe -r frost_armor"
    if s["storm_service"]:
        return "Sturmsiegel lösen: systemctl disable eissturm.service"
    return ""


def counter(s, penalty=0):
    s["combat_turn"] += 1
    if s["charging"]:
        s["charging"] = False
        if s["shield"]:
            s["shield"] = 0
            return " Dein Schild fängt beide Schläge der Polarnacht ab!", "eclipse_guard"
        damage = 2*ECLIPSE_HIT
        sound, title = "eclipse", "Polarnacht · 2 × 46"
    elif s["eclipse_casts"] < len(ECLIPSE_THRESHOLDS) and s["boss_hp"] <= ECLIPSE_THRESHOLDS[s["eclipse_casts"]]:
        s["charging"] = True
        s["eclipse_casts"] += 1
        return " Grinch lädt POLARNACHT! Nächster Zug: ~/rucksack/schild", "charge"
    else:
        if s["frozen"]:
            s["frozen"] -= 1
            return " Grinch ist eingefroren.", "ice_lock"
        if s["shield"]:
            s["shield"] -= 1
            return " Dein Schild fängt den Angriff ab.", "parry"
        attacks = (("claw","Krallenschlag",15), ("lance","Eislanze",19),
                   ("gale","Sturmböe",24))
        sound,title,damage = attacks[(s["combat_turn"]-1)%3]
        if sound=="gale" and not s["storm_service"]:
            sound,title,damage = attacks[0]
        damage += penalty + (4 if s["boss_hp"]<=120 else 0)
        if not s["blizzard"]:
            damage = max(1,damage//3)
    s["hp"] = max(0,s["hp"]-damage)
    if not s["hp"]: s["status"] = "lost"
    return f" {title}: −{damage} LP.", sound


def _act(s, action, args=(), *, now=None, cwd=None, code=0, command="", content=""):
    now = time.time() if now is None else now
    migrate(s)
    args = list(args)
    s.setdefault("storm_service", True)
    s.setdefault("combat_turn", 0)
    if "eclipse_casts" not in s:
        s["eclipse_casts"] = sum(s["boss_hp"]<=hp for hp in ECLIPSE_THRESHOLDS)
    s.setdefault("charging", False)
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
        try:
            if len(args) not in (2, 4):
                raise ValueError("Wähle deinen Charakter.")
            avatar = appearance({**s["avatar"], **dict(zip(OPTIONS, args))})
        except ValueError as error:
            return {"ok":False, "message":str(error), "stop":False}
        s.update(avatar=avatar, avatar_set=True)
        message="Dein Winterheld ist bereit."
    elif action == "reset":
        if args not in ([], ["normal"], ["alles"]):
            return {"ok": False, "message": "restart | restart alles", "stop": False}
        avatar, avatar_set = s["avatar"], s["avatar_set"]
        s.update(fresh(s["name"], now=now, bests={} if args == ["alles"] else s["bests"]))
        s.update(avatar=avatar, avatar_set=avatar_set)
        message = "Neuer Lauf. Auf ins Dorf!"
    elif action == "hint":
        left=s.get("hints_left",HINT_LIMIT)
        if left==0:
            message="Alle drei Tipps dieser Runde sind verbraucht."
        else:
            place=hiding_place(s,now)
            if s["status"]!="playing": hint="Mit restart beginnt die nächste Runde."
            elif s["boss_started"] and s["charging"]: hint="Polarnacht abwehren: ~/rucksack/schild"
            elif s["boss_started"] and boss_lock(s): hint=boss_lock(s)
            elif s["boss_started"]: hint="Angreifen: angreifen" if s["hp"]>40 or "kakao" not in s["bag"] else "Heilen: ~/rucksack/kakao"
            elif discovered(s): hint=f"Verbinden: ssh {BOSS_IP}"
            elif s["area"]=="dorf" and not unlocked(s,"funke"): hint="Dorfaufgabe: cat AUFGABE.txt"
            elif not s["bag"] and s["area"]=="dorf": hint="Funken holen: mv funke ~/rucksack/"
            elif s["area"]==place: hint="Grinch orten: nmap grinch"
            else: hint=f"Spur: cd ~/welt/{place}"
            s.update(hints_left=left-1,hint_until=now+8,hint_text=hint)
            message=f"{hint}  ({left-1} Tipps übrig)"
    elif action == "services":
        message = "eissturm.service   " + ("enabled" if s["storm_service"] else "disabled")
    elif action in ("status", "map", "inventory", "help", "modules"):
        if action == "help":
            message = HELP
        elif action == "inventory":
            message = "Rucksack\n" + ("\n".join(f"  {k:10} {bag_count(k,s)}" for k in s["bag"]) or "  leer")
        elif action == "modules":
            message = "Module          Status      Welt: simulierte Treiber\n" + "\n".join(
                f"{module:16}{'geladen' if s[key] else 'entfernt'}" for module, key in [("frost_armor", "armor"), ("blizzard", "blizzard")])
        else:
            message = f"{s['name']} | HP {s['hp']}/100 | Grinch {s['boss_hp']}/240 | {s['score']} Punkte | {s['status']}"
    elif s["status"] != "playing":
        message = "" if action in ("observe", "bag", "deliver") else "Lauf beendet. Neuer Versuch: restart"
        result["stop"] = action in ("cast", "attack", "unload", "use", "ping")
    elif action == "scan":
        place = hiding_place(s, now)
        if s["area"] == place or discovered(s):
            s["grinch_found"] = True
            reward(s,"echo:gefunden",40)
            message = f"Grinch gefunden · {BOSS_IP}  →  ssh {BOSS_IP} · Schild und Kakao einpacken!"
        else:
            message = "Kein Grinch-Signal an diesem Ort."
    elif action == "connect":
        if args != [BOSS_IP] or not discovered(s):
            return {"ok": False, "message": "Suche zuerst die Spur auf der Karte.", "stop": False}
        _act(s, "observe", cwd="zitadelle", now=now)
        return _act(s, "enter_boss", now=now)
    elif action == "enter_boss":
        if s["area"] != "zitadelle":
            return {"ok": False, "message": "Gehe zuerst zur Zitadelle.", "stop": False}
        if not s["boss_started"]:
            s["boss_started"] = True
            s["boss_entered_at"] = now
            s["battle_items"] = list(s["bag"])
            message = "Grinchs Schutz brechen: modprobe -r frost_armor und systemctl disable eissturm.service."
    elif s["boss_started"] and action in ("collect", "deliver", "submit"):
        if action != "deliver":
            message = "Das Tor ist geschlossen. Im Kampf gibt es keine neuen Funde oder Aufgaben."
        result["ok"] = False
    elif action == "bag":
        allowed = {item for item in ITEMS if unlocked(s,item)}
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
            return {"ok": False, "message": f"Mit {pickup(item)} mitnehmen: {ITEMS.get(item, ('DATEI',))[0]} → ~/rucksack/", "stop": False}
        if item=="ping":
            if s["boss_started"]: return _act(s,"ping",[BOSS_IP],now=now)
            return dict(result, message="Echo bereit. Suche die Grinch-Spur mit nmap grinch.")
        return _act(s, "heal" if item in ("kakao", "beeren") else "cast", [item], now=now)
    elif action == "deliver":
        place = args[0] if args else ""
        if place not in DELIVERIES:
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
            reply, result["counter_sound"] = counter(s, 3)
            message = "Ein fehlgeschlagener Shell-Befehl weckt Grinch." + reply
    elif action == "collect":
        item = args[0].split("/")[-1] if args else ""
        found = SPELL_FILES.get(item)
        if not found or found[0] != s["area"]:
            result["ok"] = False
            message = "Hier liegt dieser Zauber nicht. Nutze ls oder find."
        elif not unlocked(s,found[1]):
            result["ok"] = False
            message = "Löse zuerst die Ortsaufgabe in AUFGABE.txt."
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
            result["sound"] = item
            result["healed"] = s["hp"]-old
            message = f"{item}: +{result['healed']} HP."
            if s["boss_started"]:
                reply,result["counter_sound"] = counter(s)
                message += reply
        else:
            message = "Schon aufgebraucht."
    elif action == "submit":
        solutions = {"wald": ("TANNENGRUEN", "waldzeichen"), "dorf": ("Mila: Stern\nNoah: Schlitten", "wunschzettel"),
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
    elif action in ("attack", "cast", "unload", "ping", "disable"):
        if s["area"] != "zitadelle" or not s["boss_started"]:
            result["ok"] = False
            message = "Entdecke die Spur und verbinde dich per ssh mit Grinch."
        else:
            spell = args[0] if args else ""
            damage = 0
            lock = boss_lock(s)
            rapid_cast = False
            method = "spell" if action in ("cast", "ping") else "staff"
            if action == "disable":
                if spell != "eissturm":
                    result["ok"] = False
                    message = "Unbekannter Spieldienst. Liste: systemctl status"
                elif not s["storm_service"]:
                    return {"ok":True, "message":"eissturm.service ist bereits deaktiviert.", "stop":False}
                else:
                    result["sound"] = "disable"
                    s["storm_service"] = False
                    reward(s, "service:eissturm", 100)
                    message = "Sturmböe deaktiviert. +100 Punkte."
            elif action == "unload":
                key = {"frost_armor": "armor", "blizzard": "blizzard"}.get(spell)
                if key and s[key]:
                    result["sound"] = spell
                    s[key] = False
                    reward(s, "driver:" + spell, 120)
                    message = f"Spiel-Treiber {spell} entfernt! +120 Punkte."
                else:
                    result["ok"] = False
                    message = "Unbekannter oder bereits entfernter Spiel-Treiber."
            elif action == "ping":
                if args != [BOSS_IP] or "ping" not in s["bag"]:
                    return {"ok": False, "message": "Dafür brauchst du das Echo und die Boss-IP.", "stop": False}
                result["sound"] = "ping"
                damage = 12
                message = "Echo-Zauber: 4 Treffer mit je 3 Schaden."
            elif action == "attack":
                result["sound"] = "staff"
                damage = 24
                message = "Zuckerstabschlag!"
            elif s["spells"].get(spell, 0) == 0:
                result["ok"] = False
                message = "Zauber unbekannt oder aufgebraucht. Nutze inventar."
            else:
                result["sound"] = spell
                if s["spells"][spell] > 0:
                    s["spells"][spell] -= 1
                damage = {"funke": 30, "frost": 38, "stern": 75, "schild": 0}[spell]
                if spell == "frost":
                    s["frozen"] = 2
                if spell == "schild":
                    s["shield"] = 3
                if spell == "funke":
                    s["loop_hits"] = [t for t in s["loop_hits"] if now - t < 2.0] + [now]
                    # During the speedrun burst the boss cannot answer at shell-loop speed.
                    hits = s["loop_hits"]
                    rapid_cast = (not lock and len(hits)>=2 and s.get("last_attack")=="funke"
                                  and now-hits[0] < .4*(len(hits)-1))
                    if not lock and len(s["loop_hits"]) >= 6:
                        reward(s, "exploit:loop", 200)
                        result["sound"] = "loop"
                        win(s, "loop", now)
                        result.update(message=s["message"], stop=True)
                        return result
                message = f"{spell.upper()}!"
            if damage:
                damage = max(1, damage - (8 if s["armor"] and action != "ping" else 0))
                attack_name = {"cast": spell, "ping": "ping"}.get(action, "staff")
                if s["armor"] and attack_name != "ping" and attack_name == s.get("last_attack"):
                    damage = max(1, damage // 4)
                    message += " Der Eispanzer wehrt Wiederholungen ab. Wechsle den Angriff!"
                s["last_attack"] = attack_name
                damage = min(damage, s["boss_hp"])
                if lock and damage == s["boss_hp"]:
                    damage = max(0, damage-1)
                    message += " Letzter LP geschützt! " + lock
                s["boss_hp"] -= damage
                if 0 < s["boss_hp"] <= 120 < s["boss_hp"] + damage:
                    s["shield"] = s["frozen"] = 0
                    message += " Der Grinch gerät in Wut und sprengt deinen Schutz!"
                reward(s, "combat:" + attack_name, 30)
                message += f" -{damage} Boss-HP."
            # A released double strike lands even if this attack also fells the boss.
            if s["charging"] or (s["boss_hp"] and not rapid_cast):
                reply, result["counter_sound"] = counter(s, 0 if result["ok"] else 5)
                message += reply
            if s["boss_hp"] == 0 and s["hp"] > 0:
                win(s, "driver" if not s["armor"] or not s["blizzard"] else method, now)
                result.update(message=s["message"], stop=True)
                return result
    else:
        result["ok"] = False
        message = "Unbekannte Spielaktion. Nutze hilfe."
    if s["status"] == "lost" and s["ended"] is None:
        s["ended"] = now
        message += " VERLOREN. Mit restart beginnt ein neuer Lauf."
    if message and action not in ("help", "status", "inventory", "map", "modules"):
        s["message"] = message
    result["message"] = message
    result["stop"] = result["stop"] or (s["status"] == "lost" and action in ("cast", "attack", "unload", "ping", "disable"))
    return result


def route_count(s):
    return len(set(s.get("visited",[])) & {"dorf","wald","werkstatt","archiv"})


def act(s, action, args=(), **kwargs):
    """Record bounded combat events; rendering never delays the shell or loop."""
    before_bag=set(s.get("bag",[]))
    before_hp, before_boss = s["hp"], s["boss_hp"]
    result = _act(s, action, args, **kwargs)
    sounds = [result.pop(key) for key in ("sound", "counter_sound") if key in result]
    if action not in ("reset","name") and (sounds or before_hp!=s["hp"] or before_boss!=s["boss_hp"] or action in ("cast","attack","unload","use","disable","ping","scan") or (action=="bag" and set(s["bag"])-before_bag)):
        s["event_seq"] += 1
        s["events"].append(dict(id=s["event_seq"], at=kwargs.get("now",time.time()),
            sounds=sounds, healed=result.get("healed",0), kind=action, spell=(sorted(set(s["bag"])-before_bag)[0] if action=="bag" else args[0] if args else "stab"), hp_before=before_hp,
            boss_before=before_boss, hp=s["hp"], boss_hp=s["boss_hp"],
            damage=before_boss-s["boss_hp"], hurt=before_hp-s["hp"]))
        s["events"]=s["events"][-24:]
    return result
