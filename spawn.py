"""Monster group spawning."""
from .data import MONSTERS
from .entities import Monster


def candidates(level, where):
    c = [t for t in MONSTERS.values() if where in t["where"] and t["lo"] <= level <= t["hi"] and not t["id"].startswith("dragon")]
    if not c:
        c = [t for t in MONSTERS.values() if where in t["where"] and t["lo"] <= level and not t["id"].startswith("dragon")]
    if not c:
        c = [t for t in MONSTERS.values() if t["lo"] <= level and not t["id"].startswith("dragon")]
    return c


def spawn_group(rng, level, where, elite=None, ambush_size=False):
    cands = candidates(level, where)
    t = rng.choice(cands)
    n = rng.randint(*t["pack"])
    if level < 4:
        n = min(n, 2)
    elif level < 8:
        n = min(n, 3)
    if level >= 12 and n > 1 and rng.random() < 0.5:
        n -= 1
    lv = lambda: max(1, level + rng.choice([-1, 0, 0, 1]))
    if elite is None:
        elite = n == 1 and rng.random() < 0.10
    group = [Monster(t["id"], lv(), elite=elite and i == 0, rng=rng) for i in range(n)]
    if n == 1 and not elite and rng.random() < 0.25:
        t2 = rng.choice(cands)
        if t2["pack"][1] <= 2:
            group.append(Monster(t2["id"], lv(), rng=rng))
    return group
