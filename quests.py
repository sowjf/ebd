"""Procedural quests tied to real world locations."""
import math

from .data import MONSTERS, MOB_TAG_NAMES
from .items import gen_weapon, gen_armor, gen_jewelry, gen_any, gen_relic
from .util import seeded, person_name, dragon_name, weighted, town_name
from .world import DUNGEONS, SETTLEMENTS, FEATURES, BIOMES

ARTIFACTS = ["Sunstone Amulet", "Lost Signet of the Old King", "Chalice of the Nine Bells", "Runed Skull",
             "Heart of Frost", "Book of Seven Oaths", "Gilded Warhorn", "Moonlit Mirror", "Shard of the Star-Forge"]
HUNT_TARGETS = [("wolf", "wolves"), ("goblin", "goblins"), ("bandit", "bandits"), ("skeleton", "skeletons"),
                ("orc", "orcs"), ("spider", "giant spiders"), ("gnoll", "gnolls"), ("zombie", "zombies"),
                ("harpy", "harpies"), ("ogre", "ogres"), ("troll", "trolls"), ("cultist", "cultists"),
                ("imp", "imps"), ("bat", "vampire bats"), ("viper", "vipers"), ("boar", "wild boars")]
DRAGON_BY_GROUP = {"ash": "dragon_red", "tundra": "dragon_white", "swamp": "dragon_green", "desert": "dragon_black",
                   "mountain": "dragon_blue", "hills": "dragon_red", "forest": "dragon_green", "plains": "dragon_blue"}
DRAGON_NAMES = {"dragon_red": "Red Dragon", "dragon_white": "White Dragon", "dragon_green": "Green Dragon",
                "dragon_black": "Black Dragon", "dragon_blue": "Blue Dragon", "dragon_bone": "Bone Dragon"}
DIRS = ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]
ARROWS = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"]


def direction(dx, dy):
    ang = math.atan2(dy, dx)                 # screen coords: +y is south
    i = int(round(ang / (math.pi / 4))) % 8
    return i


def dir_name(dx, dy):
    return DIRS[direction(dx, dy)]


def arrow(dx, dy):
    return ARROWS[direction(dx, dy)]


def dragon_of(feature):
    """Deterministic dragon for a lair."""
    rng = seeded("dragon", feature.seed)
    from .world import BIOMES
    group = BIOMES[feature.biome][1]
    tid = DRAGON_BY_GROUP.get(group, rng.choice(list(DRAGON_NAMES)))
    if rng.random() < 0.2:
        tid = rng.choice(list(DRAGON_NAMES))
    return tid, dragon_name(rng)


def boss_of(feature, kind="slay"):
    """Named boss for camp / dungeon quests. Returns (template id, name)."""
    rng = seeded("boss", feature.seed)
    from .spawn import candidates
    where = feature.kind if feature.kind in ("camp", "cave", "ruins", "crypt", "tower") else "cave"
    c = [t for t in candidates(feature.level, where)]
    c = [t for t in c if t["pack"][1] <= 2] or c
    t = rng.choice(c)
    return t["id"], f"{person_name(rng, True)}"


def quest_level(q):
    return q.get("level", 1)


def _reward(rng, level, mult=1.0):
    gold = int((35 + level * 32) * mult * rng.uniform(0.85, 1.25))
    xp = int((40 + level * 38) * mult)
    item = None
    if rng.random() < 0.55 * min(1.6, mult):
        rar = 2 if mult >= 1.5 else (1 if rng.random() < 0.6 else 2)
        item = gen_any(rng, level + 1, rarity=rar, kinds=[("weapon", 3), ("armor", 3), ("shield", 1), ("jewelry", 3)])
    return dict(gold=gold, xp=xp, item=item)


def gen_board(world, town, week, taken=()):
    """Deterministic notice-board quests for a settlement."""
    rng = seeded("board", town.seed, week)
    out = []
    tries = 0
    want = 3 if town.kind == "village" else 4
    kinds = ["slay", "clear", "retrieve", "deliver", "hunt", "hunt", "dragon"]
    while len(out) < want and tries < 30:
        tries += 1
        t = rng.choice(kinds)
        q = make_quest(world, town, rng, t, week, len(out))
        if q and q["id"] not in taken and all(o["type"] != q["type"] or o["target_key"] != q["target_key"] for o in out):
            out.append(q)
    return out


def make_quest(world, town, rng, t, week, idx):
    lvl = max(1, world.level_at(town.x, town.y))
    qid = f"{town.key}:{week}:{idx}"
    base = dict(id=qid, type=t, giver=town.name, giver_key=town.key, state="active", progress=0, goal=1, level=lvl,
                target_key=None, target_name=None, tx=None, ty=None)
    giver = person_name(rng)
    base["npc"] = giver
    if t in ("slay", "clear", "retrieve"):
        kinds = {"slay": ("camp", "cave", "ruins", "crypt"), "clear": ("ruins", "cave", "crypt", "tower"),
                 "retrieve": ("ruins", "crypt", "cave", "tower")}[t]
        c = [f for f in world.features_near(town.x, town.y, 60, kinds) if f.key != town.key and math.hypot(f.x - town.x, f.y - town.y) > 10]
        if not c:
            return None
        f = rng.choice(c)
        base.update(target_key=f.key, target_name=f.name, tx=f.x, ty=f.y, level=max(lvl, f.level))
        if t == "slay":
            tid, bname = boss_of(f)
            base.update(boss_tid=tid, boss_name=bname, title=f"Slay {bname}",
                        desc=f"{giver} of {town.name} begs you to end the terror of {bname}, who holds {f.name}.")
        elif t == "clear":
            base.update(title=f"Clear {f.name}", desc=f"Something foul has moved into {f.name}. {giver} will pay well for its removal.")
        else:
            art = rng.choice(ARTIFACTS)
            base.update(artifact=art, title=f"Recover the {art}",
                        desc=f"The {art} was lost in {f.name}. {giver} offers a fine reward for its return.")
        base["reward"] = _reward(rng, base["level"], 1.15)
    elif t == "deliver":
        c = [f for f in world.features_near(town.x, town.y, 70, SETTLEMENTS) if f.key != town.key and math.hypot(f.x - town.x, f.y - town.y) > 14]
        if not c:
            return None
        f = rng.choice(c)
        base.update(target_key=f.key, target_name=f.name, tx=f.x, ty=f.y, level=max(lvl, f.level),
                    title=f"Sealed letter for {f.name}",
                    desc=f"{giver} needs a sealed letter carried to {f.name}. Do not open it. Do not lose it.")
        base["reward"] = _reward(rng, base["level"], 0.8)
    elif t == "hunt":
        cands = [(tid, pl) for tid, pl in HUNT_TARGETS if MONSTERS[tid]["lo"] <= lvl + 2 and MONSTERS[tid]["hi"] >= lvl - 2]
        if not cands:
            return None
        tid, pl = rng.choice(cands)
        n = rng.randint(4, 7)
        base.update(tid=tid, goal=n, title=f"Cull the {pl}", plural=pl,
                    desc=f"{giver} is paying a bounty on {pl}. Bring proof of {n} kills; anywhere in the wild will do.")
        base["reward"] = _reward(rng, lvl, 0.7)
    elif t == "dragon":
        c = [f for f in world.features_near(town.x, town.y, 90, ("lair",)) if f.key != town.key]
        if not c:
            return None
        f = rng.choice(c)
        tid, dname = dragon_of(f)
        base.update(target_key=f.key, target_name=f.name, tx=f.x, ty=f.y, level=max(lvl, f.level, 8), boss_tid=tid,
                    boss_name=dname, title=f"Slay {dname}",
                    desc=f"{dname} lairs at {f.name}. {giver} speaks of it in a whisper: the whole region will sing of whoever ends it.")
        base["reward"] = _reward(rng, base["level"], 2.6)
        base["reward"]["item"] = gen_any(rng, base["level"] + 2, rarity=3, kinds=[("weapon", 3), ("armor", 3), ("jewelry", 2)])
    else:
        return None
    return base


def describe_quest(q, ppos=None):
    """Markup lines for the journal."""
    L = [f"<b><gold>{q['title']}</></>  <dim>(recommended level {q['level']})</>", "", q["desc"], ""]
    if q.get("target_name"):
        loc = f"<white>{q['target_name']}</>"
        if ppos and q.get("tx") is not None:
            dx, dy = q["tx"] - ppos[0], q["ty"] - ppos[1]
            dist = int(math.hypot(dx, dy))
            loc += f"  <dim>—</> <cyan>{dist} leagues {dir_name(dx, dy)} {arrow(dx, dy)}</>"
        L.append(f"<grey>Where:</> {loc}")
    if q["type"] == "hunt":
        L.append(f"<grey>Progress:</> <white>{q['progress']}/{q['goal']}</> {q.get('plural', '')}")
    elif q["type"] == "retrieve":
        L.append(f"<grey>Objective:</> find the <white>{q['artifact']}</> at the site")
    r = q["reward"]
    L.append(f"<grey>Reward:</> <gold>{r['gold']}</> gold, <cyan>{r['xp']}</> XP" +
             (f", {_iname(r['item'])}" if r.get("item") else ""))
    L.append(f"<grey>Return to:</> <white>{q['giver']}</>" if q["type"] != "deliver" else
             f"<grey>Deliver to:</> <white>{q['target_name']}</>")
    st = {"active": "<amber>In progress</>", "ready": "<green>Ready to turn in!</>", "done": "<dim>Completed</>"}[q["state"]]
    L.append(f"<grey>Status:</> {st}")
    return L


def _iname(it):
    from .items import name_item
    return name_item(it)
