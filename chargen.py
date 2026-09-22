"""Character creation helpers."""
from .data import CLASSES, ORIGINS, STATS
from .entities import Player
from .items import gen_weapon, gen_armor, gen_shield, gen_potion, gen_food, gen_scroll


def roll_stats(rng):
    out = []
    for _ in range(6):
        d = sorted(rng.randint(1, 6) for _ in range(4))
        out.append(sum(d[1:]))
    return sorted(out, reverse=True)


def assign(cls, rolls):
    prio = CLASSES[cls]["prio"]
    return {s: rolls[i] for i, s in enumerate(prio)}


def create_player(rng, name, cls, origin, rolls, hardcore=False):
    c, o = CLASSES[cls], ORIGINS[origin]
    stats = assign(cls, rolls)
    stats[o["stat"]] += 1
    p = Player(name, cls, origin, stats, hardcore)
    p.gold = o["gold"]
    p.food = 3 + o.get("food", 0)
    kit = c["kit"]
    p.eq["weapon"] = gen_weapon(rng, 1, 0, kit["weapon"])
    p.eq["weapon"]["plus"] = 0
    p.eq["weapon"]["n"] = kit["weapon"]
    p.eq["armor"] = gen_armor(rng, 1, 0, kit["armor"])
    p.eq["armor"]["plus"] = 0
    p.eq["armor"]["n"] = kit["armor"]
    if kit.get("shield"):
        p.eq["shield"] = gen_shield(rng, 1, 0, kit["shield"])
        p.eq["shield"]["plus"] = 0
        p.eq["shield"]["n"] = kit["shield"]
    p.add_item(gen_potion(rng, 1, "heal1", 2))
    if origin == "soldier":
        p.add_item(gen_potion(rng, 1, "heal2", 1))
    if origin == "scholar":
        p.add_item(gen_scroll(rng, 1, "fireball", 1))
    if origin == "acolyte":
        p.add_item(gen_potion(rng, 1, "mana1", 1))
    if cls in ("wizard", "cleric"):
        p.add_item(gen_potion(rng, 1, "mana1", 1))
    p.hp, p.mp = p.max_hp, p.max_mp
    return p
