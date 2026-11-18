"""Install/reset writable quest files strictly as the unprivileged player."""
import shutil
import sys
import json
import hashlib
from pathlib import Path


def sync_rewards(state):
    from .items import ITEMS, SPELL_QUEST, script, unlocked
    home=Path.home()
    receipts=home/".frost-rewards"
    receipts.mkdir(exist_ok=True)
    for item in SPELL_QUEST:
        location=home/"welt"/ITEMS[item][0]
        carried=home/"rucksack"/item
        receipt=receipts/item
        if receipt.exists() or not unlocked(state,item):
            continue
        already_carried = carried.is_file() and carried.stat().st_size<2048 and carried.read_bytes()==script(item).encode()
        if not state.get("boss_started") and item not in state["spells"] and not already_carried:
            location.parent.mkdir(parents=True,exist_ok=True)
            try:
                with location.open("x") as stream:
                    stream.write(script(item))
                location.chmod(0o755)
            except FileExistsError:
                pass
        receipt.touch()


def main():
    from .items import ITEMS, SPELL_QUEST, DELIVERIES, script
    home = Path.home()
    target = home/"welt"
    bag = home/"rucksack"
    marker = home/".frost-world-version"
    wipe = len(sys.argv)>1 and sys.argv[1]=="wipe"
    reset = wipe or (len(sys.argv)>1 and sys.argv[1]=="reset")
    if wipe:
        for path in home.iterdir():
            if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
            else: path.unlink()
    if reset:
        for path in (target, bag, home/".frost-rewards"):
            if path.is_symlink(): path.unlink()
            elif path.exists(): shutil.rmtree(path)
    target.mkdir(exist_ok=True)
    bag.mkdir(exist_ok=True)
    for place in DELIVERIES:
        inbox=target/place/"abgabe"
        inbox.mkdir(parents=True,exist_ok=True)
        placeholder=inbox/".gitkeep"
        if placeholder.is_file() and placeholder.stat().st_size==0: placeholder.unlink()
    previous_version=marker.read_text().strip() if marker.exists() else ""
    migrating = previous_version != "10"
    gated_paths={ITEMS[k][0] for k in SPELL_QUEST}
    if migrating or reset:
        source = Path("/opt/frost/world")
        legacy = json.loads(Path(__file__).with_name("legacy_world.json").read_text())
        if previous_version and not reset:
            from .client import request
            state=request()["state"]
            carried_ping=bag/"ping"
            if (previous_version=="8" and carried_ping.is_file() and not carried_ping.is_symlink()
                    and hashlib.sha256(carried_ping.read_bytes()).hexdigest() in legacy["dorf/ping"]):
                shutil.copy2(source/"dorf/ping",carried_ping)
            for item in SPELL_QUEST:
                path=target/ITEMS[item][0]
                if not path.is_symlink() and path.is_file() and item not in state["spells"] and (path.read_text(errors="replace") in (script(item),script(item,legacy=True)) or
                        (item=="ping" and hashlib.sha256(path.read_bytes()).hexdigest() in legacy["dorf/ping"])):
                    path.unlink()
        if previous_version in ("8","9") and not reset:
            # Only replace bundled text. Keep moved rewards and edited player files.
            for relative in ("wald/AUFGABE.txt","wald/.lichtung/rindenzeichen","dorf/AUFGABE.txt","dorf/HILFE.txt","wald/WEGWEISER.txt","zitadelle/BOSS.txt"):
                path=target/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                if not path.exists() or (not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() in legacy.get(relative,[])):
                    shutil.copy2(source/relative,path)
            sync_rewards(state)
            marker.write_text("10\n")
            return
        for relative, digest in legacy.items():
            path = target/relative
            if path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() in ([digest] if isinstance(digest,str) else digest):
                path.unlink()  # Only unmodified bundled v1 files; user edits survive.
        for path in source.rglob("*"):
            if str(path.relative_to(source)) in gated_paths: continue
            destination = target/path.relative_to(source)
            if path.is_dir(): destination.mkdir(parents=True, exist_ok=True)
            elif not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        if migrating and previous_version not in ("2","3","4","5","6","7","8") and not reset:
            from .client import request
            state = request()["state"]
            for name in state["spells"]:
                if name in ITEMS and not (bag/name).exists():
                    (bag/name).write_text(script(name))
                    (bag/name).chmod(0o755)
        if migrating and not reset and previous_version:
            # Old inventories were collected before items had transfer rules.
            from .client import request
            old_bag = request()["state"].get("bag", [])
            for name in old_bag:
                if name not in ITEMS: continue
                carried = bag/name
                if carried.is_file() and not carried.is_symlink() and (carried.read_bytes() in (script(name).encode(),script(name,legacy=True).encode()) or
                    (name=="ping" and hashlib.sha256(carried.read_bytes()).hexdigest() in legacy["dorf/ping"])):
                    carried.write_text(script(name))
                    if name in ("schild","stern"):
                        source_item=target/ITEMS[name][0]
                        if source_item.is_file() and source_item.read_bytes()==script(name).encode():
                            source_item.unlink()
        marker.write_text("10\n")


if __name__=="__main__": main()
