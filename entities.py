"""Player and Monster."""
import random

from .data import (CLASSES, ORIGINS, MONSTERS, SKILLS, STATS, ADJECTIVES, ELITE_TITLES, title_for, xp_needed)
from .items import is_stackable, stack_key
from .util import mod, parse_dice, seeded

SLOTS = ["weapon", "armor", "shield", "ring", "amulet"]
INV_LIMIT = 32
HP_SCALE = 0.30


class Player:
    def __init__(self, name="Hero", cls="knight", origin="soldier", stats=None, hardcore=False):
        self.name = name
        self.cls = cls
        self.origin = origin
        self.level = 1
        self.xp = 0
        self.stats = dict(stats or {s: 10 for s in STATS})
        self.stat_points = 0
        self.gold = 0
        self.food = 3
        self.fed_until = 8 * 60 + 1440        # a ration feeds you for 24 hours
        self.inv = []
        self.eq = {s: None for s in SLOTS}
        self.pos = [0, 0]
        self.minutes = 8 * 60
        self.hp = 1
        self.mp = 1
        self.kills = {}
        self.deeds = []
        self.quests = []
        self.flags = {}
        self.last_town = None
        self.hardcore = hardcore
        self.deaths = 0
        self.dragons = 0
        self.steps = 0
        self.since_enc = 0
        self.blessed_until = 0
        self.rep = 0
        self.rest_debt = 0

    # -- persistence -----------------------------------------------------
    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, d):
        p = cls()
        p.__dict__.update(d)
        return p

    # -- static data -----------------------------------------------------
    @property
    def c(self):
        return CLASSES[self.cls]

    @property
    def title(self):
        return title_for(self.level)

    @property
    def hungry(self):
        return bool(self.flags.get("hungry"))

    @property
    def prof(self):
        return 2 + (self.level - 1) // 4

    # -- stats -----------------------------------------------------------
    def bonus(self, key):
        return sum(it["bonus"].get(key, 0) for it in self.eq.values() if it and it.get("bonus"))

    def stat(self, s):
        return self.stats[s] + self.bonus(s)

    def m(self, s):
        return mod(self.stat(s))

    @property
    def max_hp(self):
        cm = self.m("CON")
        hit = self.c["hit"]
        per = max(1, hit // 2 + 1 + cm)
        return max(1, hit + cm + 4 + (self.level - 1) * per + self.bonus("hp"))

    @property
    def max_mp(self):
        c = self.c
        return int(c["mp_base"] + self.level * (c["mp_per"] + max(0, self.m(c["mp_stat"]))) + self.bonus("mp"))

    @property
    def weapon(self):
        return self.eq["weapon"]

    def weapon_mod(self):
        w = self.weapon
        st = w["stat"] if w else "STR"
        if st == "FIN":
            return max(self.m("STR"), self.m("DEX"))
        return self.m(st)

    @property
    def atk_bonus(self):
        w = self.weapon
        return self.prof + self.weapon_mod() + (w["plus"] if w else 0) + self.bonus("atk") - (2 if self.hungry else 0)

    @property
    def dmg_flat(self):
        w = self.weapon
        return self.weapon_mod() + (w["plus"] if w else 0) + self.bonus("dmg") + self.level // 5

    @property
    def dice(self):
        w = self.weapon
        return tuple(w["dice"]) if w else (1, 2)

    @property
    def ac(self):
        a = self.eq["armor"]
        dex = self.m("DEX")
        if a:
            cap = a["cap"]
            base = a["ac"] + a["plus"] + (dex if cap is None else min(dex, cap))
        else:
            base = 10 + dex
        s = self.eq["shield"]
        if s:
            base += s["ac"] + s["plus"]
        return base + self.bonus("ac")

    @property
    def attacks(self):
        n = 1
        for lv, k in self.c["extra"].items():
            if self.level >= lv:
                n = max(n, k)
        w = self.weapon
        return n

    @property
    def sneak_dice(self):
        return (self.level + 1) // 2 if self.c.get("sneak") else 0

    @property
    def spell_mod(self):
        return self.m(self.c["mp_stat"]) + self.level // 5 + self.bonus("dmg")

    def skill_bonus(self, skill):
        prof = skill in self.c["skills"] or skill == ORIGINS[self.origin]["skill"]
        return self.m(SKILLS[skill]) + (self.prof if prof else 0) - (2 if self.hungry else 0)

    @property
    def abilities(self):
        return [a for a in self.c["abilities"] if a["lv"] <= self.level]

    @property
    def regen(self):
        return self.bonus("regen")

    # -- resources ---------------------------------------------------------
    def heal(self, n):
        before = self.hp
        self.hp = min(self.max_hp, self.hp + int(n))
        return self.hp - before

    def restore_mp(self, n):
        before = self.mp
        self.mp = min(self.max_mp, self.mp + int(n))
        return self.mp - before

    def clamp(self):
        self.hp = min(self.hp, self.max_hp)
        self.mp = min(self.mp, self.max_mp)

    def gain_xp(self, n):
        self.xp += int(n)
        gained = 0
        while self.xp >= xp_needed(self.level):
            self.xp -= xp_needed(self.level)
            old = self.max_hp
            self.level += 1
            if self.level % 2 == 0:
                self.stat_points += 1
            self.hp += self.max_hp - old
            self.mp = self.max_mp
            gained += 1
        return gained

    # -- inventory ---------------------------------------------------------
    def add_item(self, it):
        if is_stackable(it):
            for o in self.inv:
                if stack_key(o) == stack_key(it):
                    o["q"] = o.get("q", 1) + it.get("q", 1)
                    return True
        if len(self.inv) >= INV_LIMIT:
            return False
        self.inv.append(it)
        return True

    def remove_one(self, it):
        if is_stackable(it) and it.get("q", 1) > 1:
            it["q"] -= 1
        else:
            self.inv.remove(it)

    def count(self, name):
        return sum(it.get("q", 1) for it in self.inv if it["n"] == name)

    def slot_of(self, it):
        k = it["k"]
        return k if k in SLOTS else None

    def equip(self, it):
        """Equip item from inventory; returns list of notes."""
        slot = self.slot_of(it)
        notes = []
        if slot is None:
            return ["You can't equip that."]
        self.inv.remove(it)
        if slot == "weapon" and it["hands"] == 2 and self.eq["shield"]:
            self.inv.append(self.eq["shield"])
            notes.append(f"You stow your shield to wield {it['n']} with both hands.")
            self.eq["shield"] = None
        if slot == "shield" and self.eq["weapon"] and self.eq["weapon"]["hands"] == 2:
            self.inv.append(self.eq["weapon"])
            notes.append(f"You put away your two-handed {self.eq['weapon']['n']}.")
            self.eq["weapon"] = None
        old = self.eq[slot]
        self.eq[slot] = it
        if old:
            self.inv.append(old)
        self.clamp()
        return notes

    def unequip(self, slot):
        it = self.eq[slot]
        if it and len(self.inv) < INV_LIMIT:
            self.inv.append(it)
            self.eq[slot] = None
            self.clamp()
            return True
        return False


class Monster:
    def __init__(self, tid="goblin", level=1, elite=False, boss=False, name=None, hp_mult=1.0, rng=random):
        t = MONSTERS[tid]
        self.tid = tid
        self.level = level
        self.elite = elite
        self.boss = boss or tid.startswith("dragon")
        L = level
        self.name = name or t["name"]
        if not name and not elite and not self.boss and rng.random() < 0.35:
            self.name = f"{rng.choice(ADJECTIVES)} {t['name']}"
        if elite and not name:
            self.name = f"{t['name']} {rng.choice(ELITE_TITLES)}"
        lo = t["lo"]
        d = L - lo
        hp = 1.2 * t["hp"] * (12 + 8.4 * L) / (12 + 8.4 * lo)
        if elite:
            hp *= 2.0
        self.max_hp = self.hp = max(1, int(hp * hp_mult * rng.uniform(0.92, 1.08)))
        self.ac = t["ac"] + d // 3 + (1 if elite else 0)
        self.atk = t["atk"] + int(d * 0.95) + (1 if elite else 0)
        n, s, b = parse_dice(t["dmg"])
        self.dice = [n + max(0, d) // 9, s]
        self.flat = b + int(max(0, d) * 0.95) + (2 if elite else 0)
        self.sp = list(t["sp"])
        if elite and "rage" not in self.sp and not self.boss:
            self.sp.append("rage")
        self.weak = list(t["weak"])
        self.res = list(t["res"])
        self.tags = list(t["tags"])
        self.art = t["art"]
        self.color = t["color"]
        self.glyph = t["glyph"]
        mult = 3.0 if elite else (1.0)
        self.xp = int(t["xp"] * (18 + 10 * L) * mult)
        self.gold = int(t["xp"] * rng.randint(1, 3) * (3 + 2 * L) * (2.5 if elite else 1) * (3 if self.boss else 1))
        self.st = {}
        self.cd = {}
        self.flags = {}
        self.awake = True
        self.pos = None

    def to_dict(self):
        d = dict(self.__dict__)
        d["pos"] = list(self.pos) if self.pos else None
        return d

    @classmethod
    def from_dict(cls, d):
        m = cls.__new__(cls)
        m.__dict__.update(d)
        m.pos = tuple(d["pos"]) if d.get("pos") else None
        return m

    @property
    def alive(self):
        return self.hp > 0

    @property
    def multi(self):
        for s in self.sp:
            if s.startswith("multi"):
                return int(s[5:])
        return 1

    @property
    def breath(self):
        for s in self.sp:
            if s.startswith("breath:"):
                return s[7:]
        return None
