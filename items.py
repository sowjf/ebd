"""Item generation and description."""
import random

from .data import (WEAPONS, ARMORS, SHIELDS, RING_NAMES, AMULET_NAMES, WEAPON_AFFIX, SUFFIXES, LEGEND_NAMES, POTIONS,
                   SCROLLS, GEMS, RELICS, RARITY_NAMES, ELEMENTS, STATS)
from .term import esc
from .util import weighted

RCOL = ["grey", "green", "blue", "purple", "amber"]
BONUS_LABEL = {"STR": "Strength", "DEX": "Dexterity", "CON": "Constitution", "INT": "Intelligence", "WIS": "Wisdom",
               "CHA": "Charisma", "hp": "Max HP", "mp": "Max resource", "ac": "Armor Class", "atk": "Attack",
               "dmg": "Damage", "regen": "HP regen"}
JEWEL_KINDS = [("STR", "Might"), ("DEX", "Grace"), ("CON", "Vigor"), ("INT", "Insight"), ("WIS", "Wisdom"),
               ("CHA", "Charm"), ("hp", "Life"), ("mp", "the Arcane"), ("ac", "Protection"), ("atk", "Accuracy"),
               ("dmg", "Ruin"), ("regen", "Renewal")]
METALS = ["Silver", "Gold", "Iron", "Jade", "Bone", "Copper", "Obsidian", "Moonstone", "Amber", "Onyx"]


def roll_rarity(rng, level=1, bonus=0.0, floor=0):
    w = [max(1, 60 - level - bonus * 20), 28, 9 + level * 0.15 + bonus * 6, 2.5 + level * 0.08 + bonus * 3,
         0.4 + level * 0.02 + bonus * 1.2]
    r = weighted(rng, list(zip(range(5), w)))
    return max(r, floor)


def _bonus_mag(key, level, r):
    if key in STATS:
        return 1 + (level + r * 2) // 9
    return {"hp": 4 + int(level * 1.6) + r * 3, "mp": 3 + level + r * 2, "ac": 1 + level // 14,
            "atk": 1 + level // 10, "dmg": 1 + level // 8, "regen": 1 + level // 10}[key]


def name_item(it):
    return f"<{RCOL[it['r']]}>{esc(it['n'])}</>"


def bonus_line(b):
    parts = []
    for k, v in b.items():
        parts.append(f"+{v} {BONUS_LABEL[k]}")
    return ", ".join(parts)


def gen_weapon(rng, level, rarity=None, base=None):
    r = roll_rarity(rng, level) if rarity is None else rarity
    base = base or rng.choice(list(WEAPONS))
    dice, stat, val, hands = WEAPONS[base]
    plus = max(0, (level + r * 2) // 4 + rng.choice([-1, 0, 0, 1]))
    if base in ("Quarterstaff", "Wand"):
        plus = max(0, plus)
    it = dict(k="weapon", base=base, dice=list(dice), stat=stat, plus=plus, ele=None, hands=hands, r=r, bonus={},
              lvl=level)
    name = base
    pre = ""
    if r >= 2 and rng.random() < 0.7:
        pre = rng.choice(list(WEAPON_AFFIX))
        it["ele"] = WEAPON_AFFIX[pre]
    if plus:
        name = f"{name} +{plus}"
    if pre:
        name = f"{pre} {name}"
    if r >= 3 or (r == 2 and rng.random() < 0.4):
        suf, b = rng.choice(SUFFIXES)
        it["bonus"] = {k: _bonus_mag(k, level, r) * v for k, v in b.items()}
        name = f"{name} {suf}"
    if r == 4:
        name = f"{rng.choice(LEGEND_NAMES)}, {name}"
    it["n"] = name
    it["v"] = int(val + plus * plus * 45 + r * r * 70 + (60 if it["ele"] else 0) + sum(it["bonus"].values()) * 25)
    return it


def gen_armor(rng, level, rarity=None, base=None):
    r = roll_rarity(rng, level) if rarity is None else rarity
    base = base or rng.choice(list(ARMORS))
    ac, cap, kind, val = ARMORS[base]
    plus = max(0, (level + r * 2) // 5 + rng.choice([-1, 0, 0, 1]))
    it = dict(k="armor", base=base, ac=ac, cap=cap, plus=plus, r=r, bonus={}, lvl=level, kind=kind)
    name = base + (f" +{plus}" if plus else "")
    if r >= 2 and rng.random() < 0.8:
        suf, b = rng.choice(SUFFIXES)
        it["bonus"] = {k: _bonus_mag(k, level, r) * v for k, v in b.items()}
        name += " " + suf
    if r == 4:
        name = f"{rng.choice(LEGEND_NAMES)}, {name}"
    it["n"] = name
    it["v"] = int(val + plus * plus * 55 + r * r * 80 + sum(it["bonus"].values()) * 25)
    return it


def gen_shield(rng, level, rarity=None, base=None):
    r = roll_rarity(rng, level) if rarity is None else rarity
    base = base or rng.choice(list(SHIELDS))
    ac, val = SHIELDS[base]
    plus = max(0, (level + r * 2) // 7 + rng.choice([-1, 0, 0, 1]))
    it = dict(k="shield", base=base, ac=ac, plus=plus, r=r, bonus={}, lvl=level)
    name = base + (f" +{plus}" if plus else "")
    if r >= 2 and rng.random() < 0.7:
        suf, b = rng.choice(SUFFIXES)
        it["bonus"] = {k: _bonus_mag(k, level, r) * v for k, v in b.items()}
        name += " " + suf
    if r == 4:
        name = f"{rng.choice(LEGEND_NAMES)}, {name}"
    it["n"] = name
    it["v"] = int(val + plus * plus * 50 + r * r * 70 + sum(it["bonus"].values()) * 25)
    return it


def gen_jewelry(rng, level, rarity=None, kind=None):
    r = roll_rarity(rng, level, floor=1) if rarity is None else rarity
    kind = kind or rng.choice(["ring", "amulet"])
    n = 1 + (1 if r >= 2 else 0) + (1 if r >= 4 else 0)
    keys = rng.sample(JEWEL_KINDS, n)
    bonus = {k: _bonus_mag(k, level, r) for k, _ in keys}
    base = rng.choice(RING_NAMES if kind == "ring" else AMULET_NAMES)
    name = f"{rng.choice(METALS)} {base} of {keys[0][1]}"
    if r == 4:
        name = f"{rng.choice(LEGEND_NAMES)}, {name}"
    it = dict(k=kind, n=name, r=r, bonus=bonus, lvl=level, v=int(40 + r * r * 90 + level * 25 * n))
    return it


def gen_potion(rng, level, pid=None, qty=1):
    if pid is None:
        if level < 6:
            pool = ["heal1", "heal2", "mana1", "antidote", "ironskin", "might", "oil", "smoke", "heal1", "heal2"]
        elif level < 14:
            pool = ["heal2", "heal3", "mana1", "mana2", "antidote", "ironskin", "might", "oil", "smoke", "heal2"]
        else:
            pool = ["heal3", "heal4", "mana2", "antidote", "ironskin", "might", "oil", "heal3", "smoke"]
        pid = rng.choice(pool)
    name, fx, mag, price = POTIONS[pid]
    return dict(k="potion", n=name, pid=pid, fx=fx, mag=mag, r=1 if "heal3" in pid or "heal4" in pid else 0,
                v=int(price * (1 + level * 0.09)), q=qty, lvl=level)


def gen_scroll(rng, level, sid=None, qty=1):
    sid = sid or rng.choice(list(SCROLLS))
    name, fx, price = SCROLLS[sid]
    return dict(k="scroll", n=name, sid=sid, fx=fx, r=2, v=int(price * (1 + level * 0.08)), q=qty, lvl=level)


def gen_food(qty=1):
    return dict(k="food", n="Travel Ration", r=0, v=6, q=qty, food=1)


def gen_gem(rng, level):
    g = rng.choice(GEMS)
    return dict(k="gem", n=g, r=2 if GEMS.index(g) > 4 else 1, v=int((30 + GEMS.index(g) * 45) * (1 + level * 0.15)), q=1)


def gen_relic(rng, level):
    return dict(k="relic", n=rng.choice(RELICS), r=3, v=int((150 + rng.randint(0, 200)) * (1 + level * 0.2)), q=1)


def gen_any(rng, level, rarity=None, kinds=None):
    kinds = kinds or [("weapon", 20), ("armor", 16), ("shield", 8), ("jewelry", 12), ("potion", 30), ("scroll", 8),
                      ("gem", 6)]
    k = weighted(rng, kinds)
    if k == "weapon": return gen_weapon(rng, level, rarity)
    if k == "armor": return gen_armor(rng, level, rarity)
    if k == "shield": return gen_shield(rng, level, rarity)
    if k == "jewelry": return gen_jewelry(rng, level, rarity)
    if k == "potion": return gen_potion(rng, level)
    if k == "scroll": return gen_scroll(rng, level)
    return gen_gem(rng, level)


def stack_key(it):
    return (it["k"], it["n"])


def is_stackable(it):
    return it["k"] in ("potion", "scroll", "food", "gem", "relic")


def describe(it):
    """Markup description lines for an item."""
    L = []
    k = it["k"]
    L.append(f"{name_item(it)}  <dim>{RARITY_NAMES[it['r']]} {k}</>")
    if k == "weapon":
        n, s = it["dice"]
        stat = {"FIN": "STR/DEX", "STR": "STR", "DEX": "DEX"}[it["stat"]]
        L.append(f"<white>{n}d{s}</> damage <dim>·</> uses <white>{stat}</>" + (" <dim>· two-handed</>" if it["hands"] == 2 else ""))
        if it["plus"]:
            L.append(f"<green>+{it['plus']}</> to hit and damage")
        if it.get("ele"):
            L.append(f"Deals bonus <{ELEMENTS[it['ele']][1]}>{ELEMENTS[it['ele']][0]}</> damage")
    elif k == "armor":
        cap = "no Dex bonus" if it["cap"] == 0 else ("any Dex bonus" if it["cap"] is None else f"Dex bonus max +{it['cap']}")
        L.append(f"AC <white>{it['ac'] + it['plus']}</> <dim>·</> {cap}")
    elif k == "shield":
        L.append(f"+<white>{it['ac'] + it['plus']}</> AC")
    if it.get("bonus"):
        L.append("<cyan>" + bonus_line(it["bonus"]) + "</>")
    if k == "potion":
        fx, mag = it["fx"], it["mag"]
        L.append({"heal": f"Restores {int(mag * 100)}% of max HP", "mana": f"Restores {int(mag * 100)}% of resource",
                  "cure": "Cures poison, burning and bleeding", "buff_ac": f"+{mag} AC for a battle",
                  "buff_dmg": f"+{mag} damage for a battle", "throw": "Hurl at a foe for heavy fire damage",
                  "escape": "Guaranteed escape from a fight"}[fx])
    if k == "scroll":
        L.append({"aoe_fire": "Burns every enemy", "aoe_frost": "Freezes and slows every enemy",
                  "reveal": "Reveals the map around you", "recall": "Teleports you to the last town you visited",
                  "mend": "Restores half your HP"}[it["fx"]])
    if k == "food":
        L.append("Feeds you for a day.")
    L.append(f"<gold>{it['v']}</> gold value")
    return L
