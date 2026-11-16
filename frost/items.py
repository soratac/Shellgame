"""The discoverable executable files: normal cp/mv and shell execution."""
ITEMS = {
    "funke": ("dorf/funke", "Feuer: unbegrenzt, 30 Schaden."),
    "kakao": ("dorf/kakao", "Heilt einmal bis zu 35 Leben."),
    "frost": ("wald/wurzeln/frost", "38 Schaden + zwei Runden Ruhe. 3 Ladungen."),
    "beeren": ("wald/beeren", "Heilen einmal bis zu 25 Leben."),
    "schild": ("werkstatt/schild", "Blockt drei Treffer. 2 Ladungen."),
    "stern": ("archiv/stern", "75 Schaden. 2 Ladungen."),
}
DELIVERIES = {"dorf": "gerettet.txt", "werkstatt": "maschine.conf", "archiv": "passwort.txt"}


def script(item):
    return f'#!/bin/sh\n# {ITEMS[item][1]}\n# Mitnehmen: cp {item} ~/rucksack/\n# Benutzen: ~/rucksack/{item}\nexec /usr/local/bin/frost use {item}\n'
