"""Small shared character sprites for the editor, map and combat."""
HAIR = {'braun': 7, 'blond': 5, 'schwarz': 8, 'rot': 6, 'blau': 2}
SHIRTS = {'rot': 6, 'gruen': 4, 'blau': 2, 'lila': 9, 'weiss': 1}
STYLES = ("kurz", "Locken", "Zopf", "Irokese")
GENDERS = ("männlich", "weiblich")
OPTIONS = {"hair": HAIR, "shirt": SHIRTS, "gender": GENDERS, "style": STYLES}
DEFAULT = {"hair":"braun", "shirt":"gruen", "gender":GENDERS[0], "style":STYLES[0]}


def appearance(values):
    if not isinstance(values, dict):
        raise ValueError("Ungültiger Charakter")
    merged = {key: values.get(key, DEFAULT[key]) for key in OPTIONS}
    if any(value not in OPTIONS[key] for key, value in merged.items()):
        raise ValueError("Ungültige Charakterauswahl")
    return merged


def sprite(canvas, x, y, avatar=None, facing=1, pose=0, hit=False):
    avatar = avatar or DEFAULT
    hair = HAIR.get(avatar.get('hair'), 7)
    shirt = SHIRTS.get(avatar.get('shirt'), 4)
    skin = 6 if hit else 10
    canvas.put(x+2, y, '███', hair)
    canvas.put(x+2, y+1, '• )' if facing==1 else '( •', skin)
    canvas.put(x, y+2, '╱███╲' if not pose else '╱███──*', shirt)
    canvas.put(x+1, y+3, '███', shirt)
    canvas.put(x+1, y+4, '╱ ╲' if pose%2 else '│ │', 1)
