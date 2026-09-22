"""Infinite procedural overworld: biomes, chunks, features, fog of war."""
import base64
import math
import zlib

from .term import PAL, mix, scale
from .util import fbm, rnd2, hash2, seeded, weighted, place_name, region_name, town_name

CHUNK = 16
DEEP, SHALLOW, SAND, PLAINS, FOREST, DENSE, HILLS, MOUNTAIN, PEAK, SWAMP, DESERT, TUNDRA, SNOW, ASH, LAVA = range(15)

# id: (name, group, cost, passable, enc_mult, bg, fg, glyphs)
BIOMES = {
    DEEP: ("Deep Water", "water", 0, False, 0, 0x0e2748, 0x2f6fb0, ["~ ", " ~", "≈ ", " ≈"]),
    SHALLOW: ("Shallows", "water", 3, True, 0.5, 0x1a4a78, 0x6fb0e0, ["~ ", " ~", " ≈", "≈ "]),
    SAND: ("Shore", "plains", 1, True, 0.7, 0x8a7c55, 0xc4b686, ["· ", " ·", "..", "  ", ". "]),
    PLAINS: ("Grassland", "plains", 1, True, 1.0, 0x2a4a25, 0x63a34c, ['" ', ' "', ". ", " ·", "  ", ", "]),
    FOREST: ("Forest", "forest", 2, True, 1.2, 0x1a3320, 0x37954a, ["♣ ", " ♣", "♠ ", "♣♣", " ♠"]),
    DENSE: ("Darkwood", "forest", 3, True, 1.6, 0x10221a, 0x23744c, ["♠♠", "♣♠", "♠ ", " ♠", "♠♣"]),
    HILLS: ("Hills", "hills", 2, True, 1.0, 0x4a4a2c, 0x8fa04c, ["∩ ", " ∩", "^ ", "∩∩"]),
    MOUNTAIN: ("Mountains", "mountain", 4, True, 1.3, 0x4a4650, 0xb4aebc, ["▲ ", " ▲", "▲▲", "/\\"]),
    PEAK: ("Snowcapped Peaks", "mountain", 0, False, 0, 0x8a90a0, 0xf4f6ff, ["▲▲", "/\\", "▲ ", " ▲"]),
    SWAMP: ("Swamp", "swamp", 3, True, 1.3, 0x243a2e, 0x6a9a52, ["~,", " ~", '";', "~~", ", "]),
    DESERT: ("Desert", "desert", 2, True, 1.0, 0x8a6a38, 0xdcb464, ["~ ", " ~", "∙ ", "  ", ". "]),
    TUNDRA: ("Tundra", "tundra", 2, True, 1.0, 0x5a6a70, 0xc4d4dc, ["· ", " ·", ". ", "* "]),
    SNOW: ("Snowfield", "tundra", 2, True, 1.1, 0x9ab0c8, 0xeaf6ff, [" *", "* ", "  ", ". "]),
    ASH: ("Ashlands", "ash", 2, True, 1.5, 0x2a2222, 0x93503e, ["· ", " ▪", "∙ ", "~ "]),
    LAVA: ("Lava", "ash", 0, False, 0, 0x7a1a08, 0xff8a2a, ["~ ", "≈ ", " ≈"]),
}

# feature kind → (glyph, color, label)
FEATURES = {
    "village": ("⌂ ", 0xf2c14e, "Village"),
    "town": ("⌂⌂", 0xf2c14e, "Town"),
    "city": ("♜♜", 0xffe08a, "City"),
    "inn": ("◘ ", 0xffa63d, "Roadside Inn"),
    "shrine": ("† ", 0xa8e0ff, "Shrine"),
    "ruins": ("▚▞", 0xc8ccd6, "Ancient Ruins"),
    "cave": ("∩∩", 0xa8743d, "Cave Mouth"),
    "crypt": ("‡ ", 0xb082ee, "Crypt"),
    "tower": ("╥ ", 0x60d6d6, "Wizard's Tower"),
    "lair": ("Ω ", 0xff5533, "Dragon's Lair"),
    "camp": ("Δ ", 0xe05555, "Bandit Camp"),
}
SETTLEMENTS = ("village", "town", "city")
DUNGEONS = ("ruins", "cave", "crypt", "tower", "lair")
START = (4, 4)


class Feature:
    __slots__ = ("kind", "name", "x", "y", "seed", "level", "biome")

    def __init__(self, kind, name, x, y, seed, level, biome):
        self.kind, self.name, self.x, self.y, self.seed, self.level, self.biome = kind, name, x, y, seed, level, biome

    @property
    def key(self):
        return f"{self.x},{self.y}"

    @property
    def glyph(self):
        return FEATURES[self.kind][0]

    @property
    def color(self):
        return FEATURES[self.kind][1]

    @property
    def label(self):
        return FEATURES[self.kind][2]

    @property
    def is_settlement(self):
        return self.kind in SETTLEMENTS

    @property
    def is_dungeon(self):
        return self.kind in DUNGEONS


class Chunk:
    __slots__ = ("cx", "cy", "tiles", "vis", "feature")


class World:
    def __init__(self, seed):
        self.seed = seed
        self.chunks = {}
        self._order = []
        self.feats = {}

    # -- noise layers ----------------------------------------------------
    def elevation(self, x, y):
        s = self.seed
        return 0.68 * fbm(x / 46, y / 46, s, 5) + 0.32 * fbm(x / 170 + 40, y / 170 - 12, s + 3, 3) + 0.02

    def moisture(self, x, y):
        return fbm(x / 62 + 1000, y / 62, self.seed + 11, 3)

    def temperature(self, x, y):
        t = 0.5 + 0.30 * math.sin(y / 115.0) + (fbm(x / 95 - 500, y / 95, self.seed + 21, 3) - 0.5) * 0.9
        return t

    def volcanism(self, x, y):
        return fbm(x / 70 + 5000, y / 70 - 300, self.seed + 7, 3)

    def wildness(self, x, y):
        return fbm(x / 52 + 300, y / 52 - 70, self.seed + 5, 3)

    def biome_at(self, x, y):
        e = self.elevation(x, y)
        m = self.moisture(x, y)
        t = self.temperature(x, y) - max(0, e - 0.55) * 0.9
        v = self.volcanism(x, y)
        if e < 0.35:
            b = DEEP
        elif e < 0.39:
            b = SHALLOW
        elif e < 0.41:
            b = SAND if t > 0.3 else TUNDRA
        elif e > 0.715:
            b = PEAK if t < 0.6 or e > 0.76 else MOUNTAIN
        elif e > 0.645:
            b = MOUNTAIN
        elif v > 0.74 and e > 0.42:
            b = LAVA if v > 0.80 else ASH
        elif e > 0.585:
            b = HILLS
        elif t < 0.20:
            b = SNOW
        elif t < 0.33:
            b = FOREST if m > 0.58 else TUNDRA
        elif t > 0.68 and m < 0.46:
            b = DESERT
        elif m > 0.63 and e < 0.50:
            b = SWAMP
        elif m > 0.63:
            b = DENSE if m > 0.72 else FOREST
        elif m > 0.52:
            b = FOREST
        else:
            b = PLAINS
        d = math.hypot(x - START[0], y - START[1])
        if d < 9 and (not BIOMES[b][3] or b in (SHALLOW, LAVA)):
            b = PLAINS
        elif d < 8 and b in (SWAMP, DENSE, MOUNTAIN, ASH, FOREST, DESERT, SNOW, TUNDRA):
            b = PLAINS
        return b

    # -- levels & regions --------------------------------------------------
    def level_at(self, x, y):
        d = math.hypot(x - START[0], y - START[1])
        lv = 1 + int(d / 14)
        w = self.wildness(x, y)
        if w > 0.72:
            lv += 2
        elif w > 0.64:
            lv += 1
        return lv

    def region_at(self, x, y):
        rx, ry = math.floor(x / 64), math.floor(y / 64)
        cx, cy = rx * 64 + 32, ry * 64 + 32
        group = BIOMES[self.biome_at(cx, cy)][1]
        if group == "water":
            group = "plains"
        return region_name(seeded(self.seed, "region", rx, ry), group)

    # -- chunks --------------------------------------------------------------
    def chunk(self, cx, cy):
        key = (cx, cy)
        c = self.chunks.get(key)
        if c is not None:
            return c
        c = Chunk()
        c.cx, c.cy = cx, cy
        c.tiles = []
        c.vis = []
        for ly in range(CHUNK):
            for lx in range(CHUNK):
                x, y = cx * CHUNK + lx, cy * CHUNK + ly
                b = self.biome_at(x, y)
                c.tiles.append(b)
                name, group, cost, passable, enc, bg, fg, glyphs = BIOMES[b]
                h = hash2(x, y, self.seed + 77)
                g = glyphs[h % len(glyphs)]
                j = 0.86 + ((h >> 8) & 255) / 255 * 0.28
                c.vis.append((g, scale(fg, j), scale(bg, 0.92 + ((h >> 16) & 255) / 255 * 0.16)))
        c.feature = self.feature_of(cx, cy)
        if len(self._order) > 900:
            old = self._order.pop(0)
            self.chunks.pop(old, None)
        self._order.append(key)
        self.chunks[key] = c
        return c

    def feature_of(self, cx, cy):
        """The (single) feature of a chunk; cheap: evaluates biomes only at candidate spots."""
        key = (cx, cy)
        if key in self.feats:
            return self.feats[key]
        f = self._gen_feature(cx, cy)
        self.feats[key] = f
        return f

    def _gen_feature(self, cx, cy):
        rng = seeded(self.seed, "feat", cx, cy)
        forced = (cx, cy) == (START[0] // CHUNK, START[1] // CHUNK)
        if not forced and rng.random() > 0.72:
            return None
        for _ in range(8):
            lx, ly = rng.randint(2, CHUNK - 3), rng.randint(2, CHUNK - 3)
            if forced:
                lx, ly = 2, 2
            x, y = cx * CHUNK + lx, cy * CHUNK + ly
            b = self.biome_at(x, y)
            if BIOMES[b][3] and b not in (SHALLOW, LAVA):
                break
        else:
            return None
        if forced:
            return Feature("village", "Hearthmoor", x, y, hash2(x, y, self.seed), 1, b)
        level = self.level_at(x, y)
        g = BIOMES[b][1]
        w = {"village": 20, "town": 11, "city": 2.5, "inn": 9, "shrine": 8, "ruins": 8, "cave": 8, "crypt": 6,
             "tower": 4, "lair": 3.5 if level >= 3 else 0, "camp": 8}
        if g == "desert":
            w["village"] *= .5; w["town"] *= .6; w["ruins"] *= 2; w["crypt"] *= 1.5
        elif g in ("mountain", "hills"):
            w["cave"] *= 3; w["lair"] *= 2.5; w["village"] *= .6
        elif g == "swamp":
            w["crypt"] *= 2.5; w["village"] *= .5; w["city"] = 0
        elif g == "ash":
            w["lair"] *= 4; w["village"] *= .2; w["town"] *= .2; w["city"] = 0
        elif g == "tundra":
            w["village"] *= .6; w["cave"] *= 1.5
        elif g == "forest":
            w["camp"] *= 1.5; w["shrine"] *= 1.5
        if level < 3:
            w["city"] *= .3
        kind = weighted(rng, [(k, v) for k, v in w.items() if v > 0])
        return Feature(kind, place_name(kind, rng), x, y, hash2(x, y, self.seed), level, b)

    def feature_at(self, x, y):
        f = self.feature_of(x // CHUNK, y // CHUNK)
        return f if f and f.x == x and f.y == y else None

    def biome(self, x, y):
        return self.chunk(x // CHUNK, y // CHUNK).tiles[(y % CHUNK) * CHUNK + (x % CHUNK)]

    def vis(self, x, y):
        return self.chunk(x // CHUNK, y // CHUNK).vis[(y % CHUNK) * CHUNK + (x % CHUNK)]

    def features_near(self, x, y, radius, kinds=None):
        out = []
        r = radius // CHUNK + 1
        for cy in range(y // CHUNK - r, y // CHUNK + r + 1):
            for cx in range(x // CHUNK - r, x // CHUNK + r + 1):
                f = self.feature_of(cx, cy)
                if f and math.hypot(f.x - x, f.y - y) <= radius and (kinds is None or f.kind in kinds):
                    out.append(f)
        return out


class Explored:
    """Per-chunk seen-bitmaps, compactly serialisable."""

    def __init__(self):
        self.d = {}

    def mark(self, x, y):
        k = (x // CHUNK, y // CHUNK)
        a = self.d.get(k)
        if a is None:
            a = self.d[k] = bytearray(CHUNK * CHUNK)
        a[(y % CHUNK) * CHUNK + (x % CHUNK)] = 1

    def seen(self, x, y):
        a = self.d.get((x // CHUNK, y // CHUNK))
        return bool(a and a[(y % CHUNK) * CHUNK + (x % CHUNK)])

    def reveal(self, px, py, r):
        r2 = r * r + r
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r2:
                    self.mark(px + dx, py + dy)

    def to_dict(self):
        return {f"{cx},{cy}": base64.b64encode(zlib.compress(bytes(a))).decode() for (cx, cy), a in self.d.items()}

    @classmethod
    def from_dict(cls, d):
        e = cls()
        for k, v in d.items():
            cx, cy = map(int, k.split(","))
            e.d[(cx, cy)] = bytearray(zlib.decompress(base64.b64decode(v)))
        return e

    def count(self):
        return sum(sum(a) for a in self.d.values())
