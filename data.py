"""Static game data: classes, abilities, statuses, monsters, item tables, flavour text."""

STATS = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
STAT_NAMES = {"STR": "Strength", "DEX": "Dexterity", "CON": "Constitution", "INT": "Intelligence",
              "WIS": "Wisdom", "CHA": "Charisma"}
SKILLS = {"Athletics": "STR", "Acrobatics": "DEX", "Stealth": "DEX", "Survival": "WIS", "Perception": "WIS",
          "Medicine": "WIS", "Insight": "WIS", "Arcana": "INT", "Lore": "INT", "Investigation": "INT",
          "Persuasion": "CHA", "Intimidation": "CHA", "Deception": "CHA", "Religion": "WIS"}

ELEMENTS = {
    "fire": ("fire", "ember"), "frost": ("frost", "ice"), "lightning": ("lightning", "gold"),
    "poison": ("poison", "lime"), "holy": ("radiant", "white"), "dark": ("necrotic", "purple"),
    "force": ("force", "cyan"), "acid": ("acid", "green"), "phys": ("", "white"),
}

LEVEL_TITLES = [(1, "Wanderer"), (3, "Sellsword"), (5, "Wayfarer"), (8, "Veteran"), (11, "Champion"),
                (15, "Hero of the Road"), (20, "Dragonbane"), (26, "Legend"), (33, "Mythic Warden"),
                (40, "Ageless One"), (50, "Myth Incarnate")]


def title_for(level):
    t = LEVEL_TITLES[0][1]
    for lv, name in LEVEL_TITLES:
        if level >= lv:
            t = name
    return t


def xp_needed(level):
    return int(70 * level + 14 * level * level)


# ───────────────────────── statuses ─────────────────────────
# name: (glyph, color, label, kind)  kind: dot | skip | debuff | buff
STATUS = {
    "poison": ("≈", "lime", "Poisoned", "dot"), "burn": ("*", "ember", "Burning", "dot"),
    "bleed": ("♦", "red", "Bleeding", "dot"), "stun": ("✦", "gold", "Stunned", "skip"),
    "slow": ("▾", "ice", "Slowed", "debuff"), "weak": ("▿", "grey", "Weakened", "debuff"),
    "fear": ("!", "purple", "Terrified", "debuff"), "exposed": ("◌", "red", "Exposed", "debuff"),
    "shield": ("◈", "cyan", "Shielded", "buff"), "bless": ("✚", "white", "Blessed", "buff"),
    "rage": ("▲", "red", "Raging", "buff"), "mark": ("◎", "amber", "Marked", "debuff"),
    "guard": ("◘", "silver", "On Guard", "buff"),
}

# ───────────────────────── classes ─────────────────────────
# Ability kinds: weapon | spell | heal | buff | debuff | execute
CLASSES = {
    "knight": dict(
        name="Knight", tag="Oath-sworn shield of the realm", color="silver", hit=10,
        prio=["STR", "CON", "WIS", "DEX", "CHA", "INT"], skills=["Athletics", "Persuasion", "Intimidation", "Insight"],
        resource="Valor", mp_base=6, mp_per=2, mp_stat="WIS", regen=2, extra={5: 2, 11: 3, 20: 4},
        kit=dict(weapon="Longsword", armor="Chain Mail", shield="Round Shield"),
        blurb="Heavy armour, a sharp sword and an unbreakable oath. Tough, reliable, and hard to put down.",
        abilities=[
            dict(id="power_strike", name="Power Strike", lv=1, cost=3, kind="weapon", mult=1.7, hit=1,
                 desc="A crushing blow: 170% weapon damage."),
            dict(id="shield_bash", name="Shield Bash", lv=2, cost=3, kind="weapon", mult=0.8, status=("stun", 1, 0.75),
                 desc="Batter the foe; likely to stun for a turn."),
            dict(id="second_wind", name="Second Wind", lv=3, cost=4, kind="heal", pct=0.22, dice=(1, 10),
                 desc="Catch your breath: heal 22% of max HP + 1d10."),
            dict(id="rally", name="Rallying Cry", lv=5, cost=5, kind="buff", buffs=[("bless", 4, 0), ("shield", 4, 2)],
                 desc="+2 AC and a blessing (+d4 to hit) for 4 turns."),
            dict(id="cleave", name="Cleave", lv=7, cost=6, kind="weapon", mult=0.9, aoe=True,
                 desc="Sweep your blade through every enemy."),
            dict(id="judgement", name="Judgement", lv=10, cost=9, kind="spell", dice=(4, 8), per=4, ele="holy",
                 desc="Call down radiant wrath on one foe."),
            dict(id="bulwark", name="Bulwark", lv=13, cost=8, kind="buff", buffs=[("shield", 3, 6)], heal=0.15,
                 desc="+6 AC for 3 turns and heal 15% HP."),
            dict(id="titan", name="Titan's Wrath", lv=16, cost=13, kind="weapon", mult=2.4, aoe=True, hit=2,
                 desc="A devastating sweep: 240% damage to all enemies."),
        ]),
    "ranger": dict(
        name="Ranger", tag="Hunter of the wild roads", color="green", hit=10,
        prio=["DEX", "WIS", "CON", "STR", "INT", "CHA"], skills=["Survival", "Perception", "Stealth", "Athletics"],
        resource="Focus", mp_base=6, mp_per=2, mp_stat="WIS", regen=2, extra={4: 2, 9: 3, 16: 4},
        kit=dict(weapon="Longbow", armor="Studded Leather", shield=None),
        blurb="A bow, a keen eye and the patience of a wolf. Strikes from afar, tracks anything, forages anywhere.",
        abilities=[
            dict(id="aimed", name="Aimed Shot", lv=1, cost=3, kind="weapon", mult=1.6, hit=4,
                 desc="Take your time: +4 to hit, 160% damage."),
            dict(id="mark", name="Hunter's Mark", lv=1, cost=2, kind="debuff", status=("mark", 5, 0),
                 desc="Mark a foe: all your hits deal +1d6 extra for 5 turns."),
            dict(id="poison_arrow", name="Poison Arrow", lv=3, cost=4, kind="weapon", mult=0.9, status=("poison", 4, 1.0),
                 desc="A tainted shaft; the target is poisoned."),
            dict(id="volley", name="Volley", lv=5, cost=6, kind="weapon", mult=0.8, aoe=True, hit=-1,
                 desc="Loose arrows at every enemy."),
            dict(id="snare", name="Snare Trap", lv=7, cost=5, kind="debuff", status=("stun", 2, 0), dmg=(2, 6),
                 desc="A hidden snare: the foe is held for 2 turns."),
            dict(id="heartseeker", name="Heartseeker", lv=10, cost=10, kind="weapon", mult=3.0, hit=10, crit=True,
                 desc="A perfect shot. Always a critical hit."),
            dict(id="rain", name="Rain of Arrows", lv=14, cost=13, kind="weapon", mult=1.6, aoe=True, hit=2,
                 desc="The sky darkens with arrows: 160% to all."),
        ]),
    "rogue": dict(
        name="Rogue", tag="Blade in the shadows", color="purple", hit=8,
        prio=["DEX", "CON", "CHA", "INT", "WIS", "STR"], skills=["Stealth", "Acrobatics", "Deception", "Perception"],
        resource="Guile", mp_base=6, mp_per=2, mp_stat="CHA", regen=2, extra={6: 2, 13: 3, 22: 4}, sneak=True,
        kit=dict(weapon="Rapier", armor="Leather Armor", shield=None),
        blurb="Quick, cunning and never fair. Sneak Attack adds bonus dice to your first hit each round.",
        abilities=[
            dict(id="backstab", name="Backstab", lv=1, cost=3, kind="weapon", mult=2.0, hit=2,
                 desc="Strike from the shadows: 200% damage."),
            dict(id="venom", name="Poison Blade", lv=2, cost=3, kind="weapon", mult=1.0, status=("poison", 4, 1.0),
                 desc="Coat your blade: the target is poisoned."),
            dict(id="smoke", name="Smoke Bomb", lv=3, cost=4, kind="buff", buffs=[("shield", 3, 5)],
                 desc="Vanish in smoke: +5 AC for 3 turns."),
            dict(id="cripple", name="Hamstring", lv=5, cost=4, kind="weapon", mult=0.8, status=("slow", 3, 1.0),
                 desc="Cut the tendons: the foe is slowed."),
            dict(id="flurry", name="Blade Flurry", lv=7, cost=7, kind="weapon", mult=0.65, n=3,
                 desc="Three lightning-fast strikes at 65% each."),
            dict(id="assassinate", name="Assassinate", lv=10, cost=10, kind="execute",
                 desc="Slay a wounded foe (<40% HP) outright; otherwise deal 300%. Bosses resist the execute."),
            dict(id="blossom", name="Death Blossom", lv=14, cost=13, kind="weapon", mult=0.9, n=3, aoe=True,
                 desc="A whirl of blades: three strikes against every enemy."),
        ]),
    "wizard": dict(
        name="Wizard", tag="Scholar of the arcane", color="cyan", hit=6,
        prio=["INT", "CON", "DEX", "WIS", "CHA", "STR"], skills=["Arcana", "Lore", "Investigation", "Insight"],
        resource="Mana", mp_base=10, mp_per=4, mp_stat="INT", regen=2, extra={},
        kit=dict(weapon="Quarterstaff", armor="Mage Robes", shield=None),
        blurb="Fragile, brilliant, terrifying. A deep pool of mana and spells that never miss.",
        abilities=[
            dict(id="firebolt", name="Firebolt", lv=1, cost=2, kind="spell", dice=(1, 10), per=5, ele="fire",
                 desc="A bolt of flame. Scales with level."),
            dict(id="missile", name="Magic Missile", lv=1, cost=3, kind="spell", dice=(1, 4), flat=1, hits=3, hper=4,
                 ele="force", desc="Unerring darts of force."),
            dict(id="frost_ray", name="Frost Ray", lv=3, cost=4, kind="spell", dice=(2, 8), per=4, ele="frost",
                 status=("slow", 3, 0.85), desc="Freezing ray that slows the target."),
            dict(id="arcane_shield", name="Arcane Shield", lv=3, cost=4, kind="buff", buffs=[("shield", 4, 4)],
                 desc="+4 AC for 4 turns."),
            dict(id="lightning", name="Lightning Bolt", lv=5, cost=7, kind="spell", dice=(4, 6), per=3, ele="lightning",
                 aoe=True, desc="Chain lightning strikes every enemy."),
            dict(id="fireball", name="Fireball", lv=8, cost=10, kind="spell", dice=(6, 6), per=2, ele="fire", aoe=True,
                 status=("burn", 3, 0.6), desc="An exploding sphere of flame."),
            dict(id="meteor", name="Meteor Swarm", lv=13, cost=16, kind="spell", dice=(10, 6), per=2, ele="fire",
                 aoe=True, status=("stun", 1, 0.5), desc="Rocks from the heavens."),
            dict(id="disintegrate", name="Disintegrate", lv=16, cost=15, kind="spell", dice=(12, 8), per=2, ele="force",
                 desc="Unravel a single foe."),
        ]),
    "cleric": dict(
        name="Cleric", tag="Voice of a bright god", color="gold", hit=8,
        prio=["WIS", "CON", "STR", "CHA", "DEX", "INT"], skills=["Medicine", "Insight", "Religion", "Persuasion"],
        resource="Faith", mp_base=8, mp_per=3, mp_stat="WIS", regen=2, extra={},
        kit=dict(weapon="Mace", armor="Scale Mail", shield="Round Shield"),
        blurb="Armoured and blessed. Heals wounds, smites evil and burns the undead.",
        abilities=[
            dict(id="flame", name="Sacred Flame", lv=1, cost=2, kind="spell", dice=(1, 8), per=4, ele="holy",
                 desc="Radiant fire from above. Undead take extra."),
            dict(id="cure", name="Cure Wounds", lv=1, cost=3, kind="heal", pct=0.18, dice=(2, 8),
                 desc="Heal 18% of max HP + 2d8."),
            dict(id="bless", name="Bless", lv=3, cost=4, kind="buff", buffs=[("bless", 5, 0)],
                 desc="+1d4 to your attack rolls for 5 turns."),
            dict(id="smite", name="Smite", lv=5, cost=5, kind="weapon", mult=1.2, ele="holy", edice=(2, 8),
                 desc="Weapon strike wreathed in radiance."),
            dict(id="turn", name="Turn Undead", lv=7, cost=6, kind="spell", dice=(3, 8), per=3, ele="holy", aoe=True,
                 only=("undead", "demon"), status=("fear", 3, 1.0), desc="Blast undead and fiends; they flee in terror."),
            dict(id="wrath", name="Divine Wrath", lv=10, cost=11, kind="spell", dice=(5, 8), per=3, ele="holy", aoe=True,
                 heal=0.2, desc="Holy light scours your enemies and mends you."),
            dict(id="revive", name="Miracle", lv=14, cost=14, kind="heal", pct=0.6, dice=(4, 8),
                 buffs=[("shield", 3, 3)], desc="Heal 60% max HP and gain +3 AC."),
        ]),
    "barbarian": dict(
        name="Barbarian", tag="Fury of the frozen north", color="red", hit=12,
        prio=["STR", "CON", "DEX", "WIS", "CHA", "INT"], skills=["Athletics", "Survival", "Intimidation", "Perception"],
        resource="Fury", mp_base=5, mp_per=2, mp_stat="CON", regen=3, extra={5: 2, 11: 3, 20: 4},
        kit=dict(weapon="Greataxe", armor="Hide Armor", shield=None),
        blurb="Rage incarnate. Enormous health, crushing blows and a temper that heals wounds.",
        abilities=[
            dict(id="rage", name="Rage", lv=1, cost=3, kind="buff", buffs=[("rage", 5, 0)],
                 desc="+damage on every hit and 25% less damage taken for 5 turns."),
            dict(id="reckless", name="Reckless Strike", lv=1, cost=2, kind="weapon", mult=1.8, hit=4,
                 selfstatus=("exposed", 1), desc="Wild swing: +4 to hit, 180% damage, but you are exposed."),
            dict(id="frenzy", name="Frenzy", lv=3, cost=5, kind="weapon", mult=0.8, n=2,
                 desc="Two furious blows at 80% each."),
            dict(id="whirl", name="Whirlwind", lv=5, cost=6, kind="weapon", mult=1.0, aoe=True,
                 desc="Spin with your axe out, hitting all."),
            dict(id="roar", name="Intimidating Roar", lv=7, cost=4, kind="debuff", aoe=True, status=("fear", 3, 0.85),
                 desc="Terrify all foes."),
            dict(id="bloodfury", name="Blood Fury", lv=10, cost=9, kind="weapon", mult=2.4, lifesteal=0.5,
                 desc="240% damage; heal for half of what you deal."),
            dict(id="quake", name="Earthshatter", lv=14, cost=13, kind="weapon", mult=1.8, aoe=True,
                 status=("stun", 1, 0.6), desc="Split the ground: 180% to all, may stun."),
        ]),
}

ORIGINS = {
    "noble": dict(name="Disgraced Noble", stat="CHA", gold=90, skill="Persuasion",
                  intro="Your family's banner was struck from the rolls of the realm, and your inheritance with it. "
                        "All that is left is a signet ring, a good name (soon to be a better one) and the road.",
                  perk="+1 CHA · 90 gold · Persuasion"),
    "outlander": dict(name="Forest Outlander", stat="CON", gold=25, skill="Survival", food=4,
                      intro="You grew up far from any wall, listening to the wind and the wolves. When the last "
                            "village on your trapline burned, you followed the smoke and never stopped walking.",
                      perk="+1 CON · 4 extra rations · Survival"),
    "scholar": dict(name="Runaway Scholar", stat="INT", gold=40, skill="Lore",
                    intro="The Archive at Vael Sorrow has a rule: no reader leaves with a book. You broke it, and the "
                          "book you took whispers at night about a dragon that has been asleep for a thousand years.",
                    perk="+1 INT · Lore · a stolen scroll"),
    "urchin": dict(name="Gutter Urchin", stat="DEX", gold=15, skill="Stealth",
                   intro="Cities are just big forests with more predators. You learned every alley, every lock, every "
                         "guardsman's habits. Now you want to see what's beyond the last gate.",
                   perk="+1 DEX · Stealth · a lucky charm"),
    "soldier": dict(name="Veteran Soldier", stat="STR", gold=40, skill="Athletics",
                    intro="Twelve winters in the King's levy, and the king never came home. The pay stopped, the "
                          "orders stopped, and one morning you simply kept marching in a different direction.",
                    perk="+1 STR · Athletics · a field potion"),
    "acolyte": dict(name="Wandering Acolyte", stat="WIS", gold=30, skill="Religion",
                    intro="The temple bells fell silent the night the sky turned red. You took the last candle from the "
                          "altar and swore to carry its light until you found out why.",
                    perk="+1 WIS · Religion · a blessed candle"),
}

# ───────────────────────── monsters ─────────────────────────
# id: name, glyph, art, color, hp, ac, atk, dmg, xp, lv_min, lv_max, where, tags, specials, weak, resist, pack
MONSTERS = {}


def _m(id, name, glyph, art, color, hp, ac, atk, dmg, xp, lo, hi, where, tags, sp=(), weak=(), res=(), pack=(1, 1)):
    MONSTERS[id] = dict(id=id, name=name, glyph=glyph, art=art, color=color, hp=hp, ac=ac, atk=atk, dmg=dmg, xp=xp,
                        lo=lo, hi=hi, where=list(where), tags=list(tags), sp=list(sp), weak=list(weak),
                        res=list(res), pack=pack)


_m("rat", "Giant Rat", "r", "rat", "brown", 6, 10, 1, "1d4", 0.5, 1, 5, ["plains", "forest", "cave", "ruins", "swamp"], ["beast"], pack=(1, 3))
_m("wolf", "Wolf", "w", "wolf", "grey", 11, 12, 3, "1d6+1", 1.0, 1, 10, ["plains", "forest", "hills", "tundra"], ["beast"], pack=(1, 3))
_m("boar", "Wild Boar", "b", "boar", "brown", 16, 11, 3, "1d8", 1.0, 1, 9, ["plains", "forest", "swamp"], ["beast"], ["stun"])
_m("bear", "Cave Bear", "B", "bear", "brown", 30, 12, 5, "1d10+2", 2.0, 4, 16, ["forest", "hills", "mountain", "cave", "tundra"], ["beast"], ["multi2"])
_m("spider", "Giant Spider", "s", "spider", "violet", 16, 13, 4, "1d6+1", 1.4, 2, 15, ["forest", "cave", "ruins", "swamp", "crypt"], ["beast"], ["poison", "slow"], ["fire"])
_m("bat", "Vampire Bat", "v", "bat", "purple", 8, 13, 3, "1d4", 0.6, 1, 8, ["cave", "crypt", "mountain", "ruins"], ["beast"], ["drain"], pack=(2, 3))
_m("viper", "Viper", "~", "snake", "green", 8, 13, 4, "1d4", 0.8, 1, 10, ["desert", "swamp", "plains", "ruins"], ["beast"], ["poison"], pack=(1, 2))
_m("scorpion", "Giant Scorpion", "x", "scorpion", "amber", 24, 14, 4, "1d8", 1.6, 3, 14, ["desert", "cave"], ["beast"], ["poison"])
_m("harpy", "Harpy", "h", "harpy", "rose", 17, 12, 4, "1d6", 1.3, 3, 15, ["mountain", "hills", "ruins", "ash"], ["beast"], ["fear"])
_m("goblin", "Goblin", "g", "goblin", "green", 9, 12, 3, "1d6", 1.0, 1, 8, ["plains", "forest", "hills", "cave", "camp", "ruins"], ["humanoid"], pack=(2, 4))
_m("hobgoblin", "Hobgoblin", "G", "goblin", "amber", 22, 15, 4, "1d8+1", 1.7, 3, 14, ["plains", "hills", "cave", "camp", "ruins", "mountain"], ["humanoid"], pack=(1, 3))
_m("bandit", "Bandit", "p", "human", "silver", 14, 13, 3, "1d6+1", 1.2, 1, 12, ["plains", "forest", "hills", "desert", "camp", "ruins", "tundra"], ["humanoid"], ["steal"], pack=(1, 3))
_m("orc", "Orc Marauder", "o", "orc", "forest", 28, 13, 5, "1d12+2", 2.0, 3, 15, ["plains", "hills", "mountain", "camp", "cave", "ash"], ["humanoid"], ["rage"], pack=(1, 3))
_m("ogre", "Ogre", "O", "ogre", "brown", 48, 11, 6, "2d8+2", 2.6, 5, 18, ["hills", "mountain", "cave", "forest", "swamp"], ["giant"], ["stun"])
_m("troll", "Cave Troll", "T", "troll", "teal", 58, 13, 6, "2d6+3", 3.2, 8, 26, ["swamp", "mountain", "cave", "forest", "tundra", "ruins"], ["giant"], ["regen"], ["fire", "acid"])
_m("gnoll", "Gnoll Raider", "n", "gnoll", "sand", 22, 13, 4, "1d8+1", 1.6, 4, 14, ["desert", "plains", "hills", "camp", "ruins"], ["humanoid"], ["bleed"], pack=(2, 3))
_m("cultist", "Cultist", "c", "mage", "blood", 13, 11, 3, "1d6", 1.1, 2, 12, ["ruins", "crypt", "tower", "camp"], ["humanoid"], ["burn"], pack=(2, 3))
_m("warlock", "Dark Warlock", "W", "mage", "purple", 30, 12, 6, "2d6", 3.0, 8, 30, ["tower", "ruins", "crypt"], ["humanoid"], ["drain", "curse"], ["holy"])
_m("fknight", "Fallen Knight", "K", "knight", "silver", 42, 17, 7, "1d10+3", 3.2, 7, 30, ["ruins", "crypt", "camp", "plains"], ["humanoid", "undead"], ["multi2"], ["holy"])
_m("skeleton", "Skeleton", "S", "skeleton", "bone", 13, 12, 3, "1d6+1", 1.0, 1, 12, ["crypt", "ruins", "cave"], ["undead"], [], ["holy", "fire"], ["poison", "dark"], pack=(2, 3))
_m("zombie", "Rotting Zombie", "z", "zombie", "lime", 26, 8, 3, "1d8+1", 1.1, 2, 10, ["crypt", "ruins", "swamp"], ["undead"], ["poison"], ["holy", "fire"], ["poison", "dark"], pack=(1, 3))
_m("ghoul", "Ghoul", "u", "ghoul", "teal", 32, 12, 5, "1d8+2", 2.0, 5, 16, ["crypt", "ruins", "swamp"], ["undead"], ["stun"], ["holy"], ["poison", "dark"], pack=(1, 2))
_m("wraith", "Wraith", "w", "ghost", "ice", 36, 14, 6, "2d6", 3.0, 9, 28, ["crypt", "ruins", "swamp"], ["undead"], ["drain"], ["holy"], ["phys", "dark", "poison", "frost"])
_m("dknight", "Death Knight", "D", "knight", "blood", 96, 19, 9, "2d8+4", 6.0, 15, 45, ["crypt", "ruins", "tower"], ["undead", "humanoid"], ["multi2", "drain"], ["holy"], ["dark", "poison"])
_m("lich", "Lich", "L", "lich", "purple", 118, 16, 10, "3d8", 8.0, 24, 60, ["tower", "crypt"], ["undead"], ["drain", "breath:frost", "summon:skeleton"], ["holy"], ["dark", "poison", "frost"])
_m("ooze", "Gelatinous Ooze", "j", "slime", "lime", 28, 8, 3, "1d8", 1.2, 2, 12, ["cave", "swamp", "ruins", "crypt"], ["ooze"], ["corrode"], ["fire", "lightning"], ["acid", "phys"])
_m("golem", "Stone Golem", "M", "golem", "grey", 72, 17, 7, "2d10+2", 4.0, 10, 32, ["tower", "ruins", "mountain"], ["construct"], ["stun"], ["lightning"], ["poison", "dark", "frost"])
_m("gargoyle", "Gargoyle", "Y", "gargoyle", "silver", 42, 15, 6, "1d10+2", 2.6, 6, 22, ["ruins", "tower", "crypt", "mountain"], ["construct"], [], ["lightning"], ["phys", "poison"])
_m("imp", "Imp", "i", "imp", "red", 15, 14, 5, "1d6+1", 1.5, 4, 16, ["tower", "crypt", "ash", "ruins"], ["demon"], ["burn"], ["frost", "holy"], ["fire", "poison"])
_m("firelem", "Fire Elemental", "E", "elemental", "ember", 46, 14, 7, "2d8", 3.0, 8, 30, ["ash", "lair", "tower"], ["elemental"], ["burn"], ["frost"], ["fire", "poison"])
_m("frostwolf", "Frost Wolf", "w", "wolf", "ice", 19, 13, 4, "1d8+1", 1.5, 3, 14, ["tundra", "mountain"], ["beast"], ["slow"], ["fire"], ["frost"], pack=(2, 3))
_m("yeti", "Yeti", "Y", "yeti", "ice", 54, 12, 7, "2d8+3", 3.2, 8, 24, ["tundra", "mountain"], ["beast"], ["multi2"], ["fire"], ["frost"])
_m("treant", "Ancient Treant", "A", "treant", "forest", 84, 15, 7, "3d8", 4.2, 10, 32, ["forest"], ["plant"], ["stun"], ["fire"], ["poison"])
_m("basilisk", "Basilisk", "b", "basilisk", "sand", 62, 15, 7, "2d8+2", 4.0, 12, 32, ["desert", "cave", "mountain"], ["beast"], ["stun", "poison"], [], ["poison"])
_m("hydra", "Hydra", "H", "hydra", "teal", 96, 15, 8, "1d10+3", 5.5, 14, 40, ["swamp", "cave", "lair"], ["beast"], ["multi3", "regen"], ["fire"])
_m("wyvern", "Wyvern", "V", "wyvern", "amber", 72, 15, 8, "2d8+3", 4.6, 10, 32, ["mountain", "hills", "lair", "ash"], ["beast", "dragon"], ["multi2", "poison"], ["lightning"])
_m("giant", "Hill Giant", "N", "ogre", "sand", 104, 14, 8, "3d10", 5.0, 12, 38, ["hills", "mountain", "tundra"], ["giant"], ["stun"])
_m("demon", "Abyssal Demon", "&", "demon", "blood", 150, 18, 11, "3d10+5", 9.0, 22, 60, ["ash", "lair", "crypt", "tower"], ["demon"], ["burn", "multi2", "fear"], ["holy", "frost"], ["fire", "poison"])
_m("wyrmling", "Young Wyrm", "d", "wyrm", "ember", 64, 15, 7, "2d8+2", 4.5, 6, 30, ["lair"], ["dragon"], ["breath:fire"], ["frost"], ["fire"])
# dragons: hp/atk high, always bosses
for _id, _name, _ele, _col, _weak in [("dragon_red", "Red Dragon", "fire", "ember", "frost"),
                                      ("dragon_white", "White Dragon", "frost", "ice", "fire"),
                                      ("dragon_green", "Green Dragon", "poison", "lime", "lightning"),
                                      ("dragon_black", "Black Dragon", "acid", "purple", "holy"),
                                      ("dragon_blue", "Blue Dragon", "lightning", "cyan", "frost"),
                                      ("dragon_bone", "Bone Dragon", "dark", "bone", "holy")]:
    _m(_id, _name, "D", "dragon", _col, 300, 17, 9, "1d10+4", 12.0, 10, 200, ["lair"], ["dragon"],
       ["multi2", f"breath:{_ele}", "rage"], [_weak], [_ele])

MOB_TAG_NAMES = {"beast": "beasts", "humanoid": "humanoids", "undead": "undead", "giant": "giants",
                 "demon": "fiends", "construct": "constructs", "dragon": "dragonkin", "ooze": "oozes"}

ADJECTIVES = ["Feral", "Gaunt", "Scarred", "Ravenous", "Bloodied", "Grim", "Lean", "Wretched", "Snarling", "Savage",
              "Mangy", "Hardened", "Cunning", "Vile"]
ELITE_TITLES = ["the Cruel", "the Ravager", "Skullsplitter", "the Undying", "Bonegnaw", "the Merciless",
                "Blackfang", "the Hungering", "Gorefist", "Ironhide", "the Scarred", "Doomcaller"]

# ───────────────────────── items ─────────────────────────
# name: dice, stat, value, hands
WEAPONS = {
    "Dagger": ((1, 4), "FIN", 20, 1), "Shortsword": ((1, 6), "FIN", 35, 1), "Rapier": ((1, 8), "FIN", 60, 1),
    "Mace": ((1, 6), "STR", 30, 1), "Longsword": ((1, 8), "STR", 55, 1), "Warhammer": ((1, 10), "STR", 70, 1),
    "Battleaxe": ((1, 10), "STR", 65, 1), "Spear": ((1, 8), "STR", 40, 1), "Greatsword": ((2, 6), "STR", 100, 2),
    "Greataxe": ((1, 12), "STR", 95, 2), "Quarterstaff": ((1, 6), "STR", 15, 2), "Wand": ((1, 6), "STR", 45, 1),
    "Shortbow": ((1, 6), "DEX", 45, 2), "Longbow": ((1, 8), "DEX", 80, 2), "Crossbow": ((1, 10), "DEX", 85, 2),
}
WEAPON_RANGED = {"Shortbow", "Longbow", "Crossbow"}
# name: ac, dex cap (None = no cap), kind
ARMORS = {
    "Mage Robes": (10, None, "cloth", 30), "Padded Armor": (11, None, "light", 25), "Leather Armor": (11, None, "light", 40),
    "Studded Leather": (12, None, "light", 70), "Hide Armor": (12, 2, "medium", 45), "Chain Shirt": (13, 2, "medium", 85),
    "Scale Mail": (14, 2, "medium", 110), "Breastplate": (14, 2, "medium", 160), "Chain Mail": (16, 0, "heavy", 140),
    "Splint Armor": (17, 0, "heavy", 210), "Plate Armor": (18, 0, "heavy", 350),
}
SHIELDS = {"Buckler": (1, 15), "Round Shield": (2, 30), "Kite Shield": (2, 50), "Tower Shield": (3, 90)}
RING_NAMES = ["Ring", "Band", "Signet", "Loop"]
AMULET_NAMES = ["Amulet", "Talisman", "Pendant", "Charm", "Medallion"]

WEAPON_AFFIX = {  # prefix: (element, extra dice)
    "Flaming": "fire", "Frozen": "frost", "Shocking": "lightning", "Venomous": "poison", "Radiant": "holy",
    "Gloomforged": "dark",
}
SUFFIXES = [  # (text, bonus dict)
    ("of the Wolf", {"DEX": 1}), ("of the Bear", {"CON": 1}), ("of the Bull", {"STR": 1}),
    ("of the Owl", {"WIS": 1}), ("of the Fox", {"CHA": 1}), ("of the Sage", {"INT": 1}),
    ("of Vigor", {"hp": 1}), ("of the Mystic", {"mp": 1}), ("of Precision", {"atk": 1}), ("of Ruin", {"dmg": 1}),
    ("of Warding", {"ac": 1}), ("of the Dragon", {"STR": 1, "CON": 1}), ("of Recovery", {"regen": 1}),
]
RARITY_NAMES = ["Common", "Uncommon", "Rare", "Epic", "Legendary"]
LEGEND_NAMES = ["Dawnrender", "Ashbringer", "Widowmaker", "Oathkeeper", "Stormcaller", "Nightfall", "Emberheart",
                "Kingsbane", "Wyrmtongue", "Sunderer", "Gravewhisper", "Starfall", "Thornmail", "Vaultbreaker"]

POTIONS = {  # id: (name, effect, magnitude, base_price)
    "heal1": ("Minor Healing Potion", "heal", 0.35, 18), "heal2": ("Healing Potion", "heal", 0.6, 40),
    "heal3": ("Greater Healing Potion", "heal", 0.85, 90), "heal4": ("Supreme Healing Potion", "heal", 1.0, 180),
    "mana1": ("Mana Draught", "mana", 0.5, 30), "mana2": ("Greater Mana Draught", "mana", 1.0, 80),
    "antidote": ("Antidote", "cure", 0, 15), "ironskin": ("Potion of Ironskin", "buff_ac", 4, 35),
    "might": ("Draught of Might", "buff_dmg", 4, 35), "oil": ("Flask of Alchemist's Fire", "throw", 0, 30),
    "smoke": ("Smoke Pellet", "escape", 0, 25),
}
SCROLLS = {
    "fireball": ("Scroll of Fireball", "aoe_fire", 55), "reveal": ("Scroll of Revealing", "reveal", 60),
    "recall": ("Scroll of Recall", "recall", 90), "mend": ("Scroll of Mending", "mend", 70),
    "frost": ("Scroll of Frost Nova", "aoe_frost", 55),
}
GEMS = ["Garnet", "Amethyst", "Opal", "Sapphire", "Emerald", "Ruby", "Black Pearl", "Star Diamond"]
RELICS = ["Gilded Chalice", "Ancient Coin Hoard", "Jewelled Dagger", "Silver Reliquary", "Ivory Idol",
          "Illuminated Codex", "Golden Torc", "Crown Fragment"]

# ───────────────────────── flavour ─────────────────────────
WHISPERS = {
    "plains": ["A hawk circles slowly overhead, patient as a judge.", "Wind ripples the grass like a green sea.",
               "You pass a rotting fence-post carved with a name no one remembers.",
               "Somewhere far off, a cowbell clanks. Then silence.", "A trampled wheel-rut hints at a caravan that passed at dawn."],
    "forest": ["Sunlight breaks into gold coins on the mossy floor.", "Something small watches you from a hollow log.",
               "The trees creak like old men complaining.", "You find an old blaze-mark on a trunk: an arrow pointing back.",
               "A stream chuckles somewhere out of sight."],
    "hills": ["Sheep-bells, or maybe something else entirely, echo through the valley.", "A ruined cairn stands atop the ridge.",
              "Larks burst from the heather at your feet.", "The wind tastes of rain and iron."],
    "mountain": ["Loose scree clatters far below. Was that your foot, or another's?", "The air thins; your breath smokes.",
                 "A vulture rides the thermals above, waiting.", "You find a frozen boot, the wearer nowhere to be seen."],
    "swamp": ["Bubbles rise and pop with a smell you'd rather not name.", "Fireflies dance, a little too deliberately.",
              "Something big slides into the water without a sound.", "The mud sucks at your boots like a hungry mouth."],
    "desert": ["Heat shimmers on the dunes. A mirage of a lake winks out.", "You pass the bleached ribcage of some enormous beast.",
               "Sand hisses over sand.", "A lone vulture. It isn't in a hurry."],
    "tundra": ["Snow squeaks underfoot. Your breath hangs in the air.", "Wolves howl, far away and coming no closer. Yet.",
               "A frozen waterfall hangs like glass.", "The sky is the colour of pewter."],
    "ash": ["Ash falls like grey snow. The ground is warm through your boots.", "A vent hisses sulphur.",
            "The horizon glows red where the earth has split open.", "Charred bones lie in the shape of a fleeing man."],
    "water": ["Cold water sloshes over your boots.", "Reeds whisper together, sharing secrets."],
}
NIGHT_WHISPERS = ["Stars wheel overhead, indifferent and countless.", "An owl calls. Another answers, closer.",
                  "Your torch throws long shadows that don't quite match your movements.",
                  "The night hums with unseen wings."]

RIDDLES = [
    ("I have cities but no houses, mountains but no trees, water but no fish. What am I?", ["A map", "A dream", "A ruined kingdom"]),
    ("The more you take, the more you leave behind. What am I?", ["Footsteps", "Coins", "Memories"]),
    ("I speak without a mouth and hear without ears. I have no body, but come alive with wind. What am I?", ["An echo", "A ghost", "A bell"]),
    ("What has roots that nobody sees, is taller than trees, up, up it goes, yet never grows?", ["A mountain", "A tower", "A dragon's shadow"]),
    ("The one who makes it sells it. The one who buys it never uses it. The one who uses it never knows. What is it?", ["A coffin", "A crown", "A sword"]),
    ("I am always hungry, I must always be fed. The finger I touch will soon turn red. What am I?", ["Fire", "A wolf", "A vampire"]),
    ("Voiceless it cries, wingless flutters, toothless bites, mouthless mutters. What is it?", ["The wind", "A ghost", "A dagger"]),
    ("Alive without breath, cold as death, never thirsty, ever drinking, all in mail, never clinking. What am I?", ["A fish", "A knight", "A statue"]),
    ("This thing all things devours: birds, beasts, trees, flowers. Gnaws iron, bites steel, grinds hard stones to meal. What is it?", ["Time", "A dragon", "Rust"]),
    ("A box without hinges, key, or lid, yet golden treasure inside is hid. What is it?", ["An egg", "A grave", "A chest"]),
    ("Forward I am heavy, backward I am not. What am I?", ["The word 'ton'", "A stone", "An anchor"]),
    ("I have keys but open no locks, space but no room. You can enter but never go outside. What am I?", ["A keyboard", "A dungeon", "A tomb"]),
]

RUMOR_LINES = [
    "They say {what} lies {dir}, {dist} leagues from here.",
    "A drunk swears he saw {what} to the {dir}, about {dist} leagues off.",
    "Travellers from the {dir} whisper of {what}. {dist} leagues, give or take.",
    "My cousin went {dir} looking for {what}. {dist} leagues. Never came back.",
]

TAVERN_SONGS = [
    "The minstrel sings of a knight who traded his shadow for a sword that never dulled.",
    "A bard plays a slow tune about a dragon who fell in love with the moon.",
    "Someone starts a drinking song. By the third verse, the whole room knows the words.",
    "An old soldier tells a story about the last siege of Harrowgate. Nobody interrupts.",
]

OMENS = ["A comet was seen last night.", "Crows gathered on the bell-tower all morning.",
         "The well ran dry, then ran red, then ran dry again.", "A two-headed calf was born in the north field."]
