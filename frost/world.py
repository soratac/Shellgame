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
    migrating = previous_version != "6"
    if migrating or reset:
        source = Path("/opt/frost/world")
        legacy = json.loads(Path(__file__).with_name("legacy_world.json").read_text())
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
        if migrating and previous_version not in ("2","3","4","5","6") and not reset:
            from .client import request
            state = request()["state"]
            for name in state["spells"]:
                if name in ITEMS and not (bag/name).exists():
                    (bag/name).write_text(script(name))
                    (bag/name).chmod(0o755)
        marker.write_text("6\n")


if __name__=="__main__": main()
