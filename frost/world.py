"""Install/reset writable quest files strictly as the unprivileged player."""
import shutil
import sys
import json
import hashlib
from pathlib import Path


def main():
    from .items import ITEMS, script
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
        for path in (target, bag):
            if path.is_symlink(): path.unlink()
            elif path.exists(): shutil.rmtree(path)
    target.mkdir(exist_ok=True)
    bag.mkdir(exist_ok=True)
    previous_version=marker.read_text().strip() if marker.exists() else ""
    migrating = previous_version != "9"
    if migrating or reset:
        source = Path("/opt/frost/world")
        legacy = json.loads(Path(__file__).with_name("legacy_world.json").read_text())
        if previous_version == "8" and not reset:
            # Update just bundled hints in place, including the carried echo.
            # A player may already have moved or edited any of these files.
            for relative in ("dorf/ping", "dorf/HILFE.txt", "zitadelle/BOSS.txt"):
                paths = [target/relative]
                if relative == "dorf/ping": paths.append(bag/"ping")
                for path in paths:
                    if path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() in legacy[relative]:
                        shutil.copy2(source/relative,path)
            marker.write_text("9\n")
            return
        for relative, digest in legacy.items():
            path = target/relative
            if path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() in ([digest] if isinstance(digest,str) else digest):
                path.unlink()  # Only unmodified bundled v1 files; user edits survive.
        for path in source.rglob("*"):
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
        marker.write_text("9\n")


if __name__=="__main__": main()
