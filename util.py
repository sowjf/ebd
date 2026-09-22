"""Dice, noise, RNG helpers and procedural name generators."""
import math
import random
import re

M32 = 0xFFFFFFFF


# ───────────────────────── dice ─────────────────────────
_DICE_RE = re.compile(r"^\s*(\d+)d(\d+)\s*([+-]\s*\d+)?\s*$")


def parse_dice(spec):
    m = _DICE_RE.match(spec)
    if not m:
        raise ValueError(spec)
    n, s = int(m.group(1)), int(m.group(2))
    b = int(m.group(3).replace(" ", "")) if m.group(3) else 0
    return n, s, b


def roll(spec, rng=random, crit=False):
    n, s, b = parse_dice(spec) if isinstance(spec, str) else spec
    if crit:
        n *= 2
    return sum(rng.randint(1, s) for _ in range(n)) + b


def roll_n(n, s, rng=random):
    return sum(rng.randint(1, s) for _ in range(max(0, n)))


def d20(rng=random):
    return rng.randint(1, 20)


def mod(score):
    return (score - 10) // 2


def sign(n):
    return f"+{n}" if n >= 0 else str(n)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def weighted(rng, pairs):
    total = sum(w for _, w in pairs)
    r = rng.random() * total
    for item, w in pairs:
        r -= w
        if r <= 0:
            return item
    return pairs[-1][0]


def a_an(word):
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


# ───────────────────────── noise ─────────────────────────
def hash2(x, y, seed):
    h = (x * 374761393 + y * 668265263 + seed * 2246822519) & M32
    h = ((h ^ (h >> 13)) * 1274126177) & M32
    h = (h ^ (h >> 16)) & M32
    h = ((h ^ (h >> 11)) * 2654435761) & M32
    return h ^ (h >> 15)


def rnd2(x, y, seed):
    return hash2(x, y, seed) / 4294967296.0


def _smooth(t):
    return t * t * (3 - 2 * t)


def vnoise(x, y, seed):
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = _smooth(x - xi), _smooth(y - yi)
    a = rnd2(xi, yi, seed)
    b = rnd2(xi + 1, yi, seed)
    c = rnd2(xi, yi + 1, seed)
    d = rnd2(xi + 1, yi + 1, seed)
    return (a + (b - a) * xf) + ((c + (d - c) * xf) - (a + (b - a) * xf)) * yf


def fbm(x, y, seed, octaves=4):
    amp, freq, tot, norm = 1.0, 1.0, 0.0, 0.0
    for i in range(octaves):
        tot += vnoise(x * freq, y * freq, seed + i * 101) * amp
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return tot / norm


def seeded(*parts):
    """A deterministic Random from arbitrary hashable parts."""
    h = 1469598103934665603
    for p in parts:
        for ch in str(p):
            h = ((h ^ ord(ch)) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return random.Random(h)


# ───────────────────────── names ─────────────────────────
_T_PRE = ["Oak", "Stone", "Raven", "Iron", "Wolf", "Elm", "Ash", "Thorn", "Storm", "Gold", "Silver", "Frost",
          "Green", "Black", "White", "Red", "High", "Low", "Fair", "Grim", "Mist", "Hollow", "Bright", "Dun",
          "Kings", "Bramble", "Willow", "Crow", "Lark", "Hawk", "Amber", "Cinder", "Moss", "Ember", "Salt",
          "Barrow", "Copper", "Dawn", "Dusk", "Harrow", "Sable", "Wyrm"]
_T_SUF = ["haven", "bridge", "ford", "wick", "stead", "ton", "vale", "mere", "hold", "gate", "moor", "field",
          "brook", "watch", "crest", "fall", "ham", "bury", "cross", "reach", "wood", "shore", "rest", "helm",
          "keep", "marsh", "hollow", "den", "wall", "port"]
_P_FIRST = ["Aldric", "Bera", "Cedric", "Dagny", "Edda", "Fenwick", "Gwen", "Halvar", "Isolde", "Jorund",
            "Kael", "Lyra", "Mordan", "Nessa", "Osric", "Petra", "Quill", "Rowan", "Sigrid", "Torvin",
            "Ulric", "Vesna", "Wulf", "Yara", "Zeph", "Brannoc", "Corwen", "Delwyn", "Elspeth", "Garrick",
            "Hild", "Ivor", "Joss", "Kestrel", "Loric", "Maud", "Nial", "Orla", "Perrin", "Renna", "Stig",
            "Tamsin", "Alaric", "Bryn", "Cael", "Drusa", "Emric", "Freya", "Gareth", "Hestia"]
_P_LAST = ["Blackwood", "Stormcrow", "Ironhand", "Thornwall", "Ashford", "Greymane", "Oakenshield", "Redfern",
           "Brightblade", "Dunmere", "Hollowell", "Stonebrook", "Wolfsbane", "Emberfall", "Nightbloom",
           "Coldwater", "Highmarch", "Longstride", "Marrowind", "Swiftwater", "Fenwarden", "Duskmantle"]
_EPI = ["the Bold", "the Grim", "the Wary", "the Red", "the Lame", "the Unbroken", "Oathbreaker", "the Pale",
        "the Kind", "Twice-Hanged", "the Wanderer", "Ironbelly", "the Squint", "the Lucky", "Fell-Handed"]
_D_A = ["Ka", "Vor", "Zy", "Mor", "Thra", "Ny", "Gor", "Sha", "Xar", "Il", "Ur", "Bel", "Vhas", "Drak", "Ery",
        "Az", "Kry", "Skor", "Ael", "Nar"]
_D_B = ["gax", "thur", "rax", "nyth", "goth", "vyr", "zul", "drak", "morn", "kesh", "thas", "rion", "vex",
        "lith", "krom", "syx", "and", "orr"]
_D_C = ["", "", "ion", "us", "a", "ax", "is"]
_DTITLE = ["the Ember-Wyrm", "the Undying", "Skybreaker", "the Hoard-King", "Doom of Kings", "the Ashen Tyrant",
           "Bane of Banners", "the Sleepless", "Scourge of the Vale", "the Gilded Terror", "Mother of Ruin"]
_ADJ = ["Sunken", "Forgotten", "Weeping", "Broken", "Hollow", "Whispering", "Gilded", "Shattered", "Drowned",
        "Burning", "Silent", "Cursed", "Lost", "Bleak", "Howling", "Withered", "Ashen", "Sundered", "Hungering"]
_OF = ["Morgrath", "the Dead King", "Sorrow", "the Nine Hells", "Thal-Uzur", "Old Kings", "the Serpent",
       "Vael", "Bones", "the Black Sun", "Echoes", "Oblivion", "Cinders", "the Crow Lord", "Regret", "Ghouls"]
_REGION_A = ["Ashen", "Emerald", "Misty", "Iron", "Ivory", "Crimson", "Verdant", "Hollow", "Silent", "Thorned",
             "Sunlit", "Shadowed", "Frostbitten", "Golden", "Wailing", "Windswept", "Amber", "Sable", "Storm"]
_REGION_B = {"plains": ["Meadows", "Downs", "Fields", "Steppe"], "forest": ["Wood", "Weald", "Greenwood", "Boughs"],
             "hills": ["Barrows", "Highlands", "Tors", "Fells"], "mountain": ["Peaks", "Spines", "Crags", "Teeth"],
             "swamp": ["Mire", "Fen", "Bogs", "Morass"], "desert": ["Sands", "Dunes", "Waste", "Reach"],
             "tundra": ["Tundra", "Wastes", "Barrens", "Drift"], "ash": ["Cinderlands", "Wastes", "Ashfall"],
             "water": ["Waters", "Shallows", "Mere"]}


def town_name(rng):
    return rng.choice(_T_PRE) + rng.choice(_T_SUF)


def person_name(rng, epithet=False):
    n = rng.choice(_P_FIRST)
    if epithet and rng.random() < 0.8:
        n += " " + rng.choice(_EPI)
    elif rng.random() < 0.5:
        n += " " + rng.choice(_P_LAST)
    return n


def dragon_name(rng):
    return rng.choice(_D_A) + rng.choice(_D_B) + rng.choice(_D_C) + " " + rng.choice(_DTITLE)


def place_name(kind, rng):
    if kind == "crypt":
        return rng.choice(["Crypt", "Tomb", "Barrow", "Catacombs"]) + " of " + rng.choice(_OF)
    if kind == "ruins":
        return f"The {rng.choice(_ADJ)} " + rng.choice(["Citadel", "Abbey", "Fortress", "Chapel", "Bastion", "Halls"])
    if kind == "cave":
        return f"The {rng.choice(_ADJ)} " + rng.choice(["Caverns", "Den", "Grotto", "Depths", "Warren"])
    if kind == "tower":
        return rng.choice(["Tower", "Spire", "Observatory"]) + " of " + person_name(rng).split()[0]
    if kind == "lair":
        return rng.choice(["Lair", "Roost", "Aerie", "Furnace", "Hoard"]) + " of " + rng.choice(_OF)
    if kind == "camp":
        return rng.choice(["Bandit Camp", "Raider Camp", "Outlaw Hideout", "Warband Camp"])
    if kind == "shrine":
        return rng.choice(["Shrine", "Standing Stones", "Wayside Altar", "Moon Well", "Hermit's Chapel"])
    if kind == "inn":
        return "The " + rng.choice(["Gilded", "Crooked", "Drunken", "Rusty", "Laughing", "Sleeping", "Weary"]) + " " + \
               rng.choice(["Griffin", "Stag", "Dragon", "Goose", "Boar", "Lantern", "Anvil", "Crown", "Owl"])
    return town_name(rng)


def region_name(rng, group):
    return f"{rng.choice(_REGION_A)} {rng.choice(_REGION_B.get(group, _REGION_B['plains']))}"


def fmt_clock(minutes):
    day = minutes // 1440 + 1
    h = (minutes // 60) % 24
    m = minutes % 60
    return day, h, m
