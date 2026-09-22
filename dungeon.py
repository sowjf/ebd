"""Procedural dungeons: rooms, fog of war, roaming monsters, traps, chests, bosses."""
import math

from .combat import Combat
from .entities import Monster
from .items import gen_any, gen_potion, gen_relic, gen_gem, gen_jewelry, name_item
from .quests import dragon_of
from .spawn import spawn_group
from .term import PAL, scale, mix, A_BOLD, esc
from .ui import hints, Story
from .util import roll_n, seeded, clamp

FW, FH = 66, 30
THEMES = {
    "cave": dict(wall=0x7a6248, floor=0x1e1710, ffg=0x6d5640, title="Caverns", mob="cave"),
    "ruins": dict(wall=0x84906f, floor=0x181c13, ffg=0x76806a, title="Ruins", mob="ruins"),
    "crypt": dict(wall=0x7670b0, floor=0x131120, ffg=0x5c5890, title="Crypt", mob="crypt"),
    "tower": dict(wall=0x559aab, floor=0x0e191d, ffg=0x4a8494, title="Tower", mob="tower"),
    "lair": dict(wall=0x9a4a38, floor=0x1c0d09, ffg=0x8a4632, title="Lair", mob="lair"),
    "camp": dict(wall=0x7a6248, floor=0x1e1710, ffg=0x6d5640, title="Camp", mob="camp"),
}
TRAPS = [("a hidden dart launcher", "poison"), ("a hissing fire vent", "fire"), ("a spiked pit", "phys"),
         ("a rune of lightning", "shock")]
DIRS8 = [(0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1), (-1, -1)]


class Died(Exception):
    pass


class Floor:
    def __init__(self):
        self.grid = [["#"] * FW for _ in range(FH)]
        self.seen = [[False] * FW for _ in range(FH)]
        self.objs = {}                 # (x,y) -> dict
        self.mons = []                 # {"pos":(x,y), "group":[Monster], "awake":bool, "stun":int}
        self.rooms = []
        self.up = (1, 1)
        self.down = None
        self.pos = (1, 1)

    def walk(self, x, y):
        return 0 <= x < FW and 0 <= y < FH and self.grid[y][x] != "#"

    def mon_at(self, x, y):
        for m in self.mons:
            if m["pos"] == (x, y):
                return m
        return None

    def to_dict(self):
        return dict(grid=["".join(r) for r in self.grid], seen=["".join("1" if c else "0" for c in r) for r in self.seen],
                    objs=[[x, y, o] for (x, y), o in self.objs.items()],
                    mons=[dict(pos=list(m["pos"]), home=list(m.get("home", m["pos"])), awake=m["awake"],
                               stun=m.get("stun", 0), boss=bool(m.get("boss")),
                               group=[g.to_dict() for g in m["group"]]) for m in self.mons],
                    rooms=self.rooms, up=list(self.up), down=list(self.down) if self.down else None, pos=list(self.pos))

    @classmethod
    def from_dict(cls, d):
        f = cls()
        f.grid = [list(r) for r in d["grid"]]
        f.seen = [[c == "1" for c in r] for r in d["seen"]]
        f.objs = {(x, y): o for x, y, o in d["objs"]}
        f.mons = [dict(pos=tuple(m["pos"]), home=tuple(m.get("home", m["pos"])), awake=m["awake"],
                       stun=m.get("stun", 0), boss=m.get("boss", False),
                       group=[Monster.from_dict(g) for g in m["group"]]) for m in d["mons"]]
        f.rooms = [tuple(r) for r in d["rooms"]]
        f.up = tuple(d["up"])
        f.down = tuple(d["down"]) if d["down"] else None
        f.pos = tuple(d["pos"])
        return f


def gen_floor(rng, feature, level, idx, depth, quest=None, kind=None):
    kind = kind or feature.kind
    f = Floor()
    last = idx == depth - 1
    rooms = []
    blob = kind in ("cave", "lair")
    for _ in range(120):
        w, h = rng.randint(5, 13), rng.randint(4, 8)
        x, y = rng.randint(1, FW - w - 2), rng.randint(1, FH - h - 2)
        if any(x < ox + ow + 2 and ox < x + w + 2 and y < oy + oh + 2 and oy < y + h + 2 for ox, oy, ow, oh in rooms):
            continue
        rooms.append((x, y, w, h))
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if blob:
                    dx, dy = (xx - (x + w / 2 - 0.5)) / (w / 2), (yy - (y + h / 2 - 0.5)) / (h / 2)
                    if dx * dx + dy * dy > 1.05:
                        continue
                f.grid[yy][xx] = "."
        if len(rooms) >= 10:
            break
    ctr = lambda r: (r[0] + r[2] // 2, r[1] + r[3] // 2)
    for a, b in zip(rooms, rooms[1:]):
        (x1, y1), (x2, y2) = ctr(a), ctr(b)
        if rng.random() < 0.5:
            for xx in range(min(x1, x2), max(x1, x2) + 1): f.grid[y1][xx] = "."
            for yy in range(min(y1, y2), max(y1, y2) + 1): f.grid[yy][x2] = "."
        else:
            for yy in range(min(y1, y2), max(y1, y2) + 1): f.grid[yy][x1] = "."
            for xx in range(min(x1, x2), max(x1, x2) + 1): f.grid[y2][xx] = "."
    f.rooms = rooms
    f.up = f.pos = ctr(rooms[0])
    # farthest room from start for stairs / boss
    far = max(rooms[1:], key=lambda r: abs(ctr(r)[0] - f.up[0]) + abs(ctr(r)[1] - f.up[1]))
    theme = THEMES[kind]
    mob_level = max(1, level + idx)
    mons_rooms = [r for r in rooms[1:] if r is not far]
    for r in mons_rooms:
        if rng.random() < 0.72:
            x, y = rng.randint(r[0], r[0] + r[2] - 1), rng.randint(r[1], r[1] + r[3] - 1)
            if f.grid[y][x] == "." and (x, y) != f.up and f.mon_at(x, y) is None:
                grp = spawn_group(rng, mob_level, theme["mob"])
                f.mons.append(dict(pos=(x, y), group=grp, awake=rng.random() < 0.25, stun=0))
        if rng.random() < 0.3:
            x, y = rng.randint(r[0], r[0] + r[2] - 1), rng.randint(r[1], r[1] + r[3] - 1)
            if f.grid[y][x] == "." and (x, y) not in f.objs and (x, y) != f.up:
                f.objs[(x, y)] = dict(t="chest", open=False)
    for _ in range(rng.randint(2, 4)):
        r = rng.choice(rooms[1:])
        x, y = rng.randint(r[0], r[0] + r[2] - 1), rng.randint(r[1], r[1] + r[3] - 1)
        if f.grid[y][x] == "." and (x, y) not in f.objs and (x, y) != f.up:
            f.objs[(x, y)] = dict(t="trap", seen=False, kind=rng.randrange(len(TRAPS)))
    if rng.random() < 0.4:
        r = rng.choice(rooms[1:])
        x, y = ctr(r)
        if (x, y) not in f.objs and not f.mon_at(x, y):
            f.objs[(x, y)] = dict(t="altar", used=False, kind=rng.randrange(3))
    cx, cy = ctr(far)
    if not last:
        f.down = (cx, cy)
        f.objs[f.down] = dict(t="down")
        f.mons.append(dict(pos=(cx + 1 if f.grid[cy][cx + 1] == "." else cx - 1, cy), group=spawn_group(rng, mob_level + 1, theme["mob"], elite=True),
                           awake=False, stun=0))
    else:
        # boss chamber
        if kind == "lair":
            tid, dname = dragon_of(feature)
            if quest and quest.get("boss_tid"):
                tid, dname = quest["boss_tid"], quest["boss_name"]
            boss = Monster(tid, max(9, level + 3), boss=True, name=dname, rng=rng)
            grp = [boss]
        else:
            if quest and quest.get("boss_tid") and quest["type"] == "slay":
                boss = Monster(quest["boss_tid"], level + idx + 1, elite=True, boss=True, name=quest["boss_name"],
                               hp_mult=1.3, rng=rng)
                grp = [boss]
            else:
                grp = spawn_group(rng, mob_level + 2, theme["mob"], elite=True)
                for m in grp:
                    m.boss = True
                    m.max_hp = m.hp = int(m.hp * 1.4)
                grp[0].name = grp[0].name + " (Guardian)" if "Guardian" not in grp[0].name else grp[0].name
        bx, by = cx, cy
        f.mons.append(dict(pos=(bx, by), group=grp, awake=False, stun=0, boss=True))
        # hoard
        for dx, dy in [(-2, 0), (2, 0), (0, -1), (0, 1), (-1, -1), (1, 1)]:
            hx, hy = bx + dx, by + dy
            if f.walk(hx, hy) and (hx, hy) not in f.objs and not f.mon_at(hx, hy):
                f.objs[(hx, hy)] = dict(t="hoard", open=False)
                break
    for m in f.mons:
        m["home"] = m["pos"]            # spawn point: monsters wander, but a slain group is remembered by this
    return f


class Dungeon:
    def __init__(self, game, feature, level, kind=None, state=None):
        self.g = game
        self.f = feature
        self.level = level
        self.kind = kind or feature.kind
        self.theme = THEMES[self.kind]
        self.quest = None
        for q in game.p.quests:
            if q.get("target_key") == feature.key and q["state"] == "active":
                self.quest = q
        self.cleared = False
        self.empty = bool(game.fstate.get(feature.key, {}).get("cleared_day")) and not state
        if state:
            self.depth = state["depth"]
            self.idx = state["idx"]
            self.floors = {int(k): Floor.from_dict(v) for k, v in state["floors"].items()}
            self.resets = state.get("resets", 0)
        else:
            self.resets = game.fstate.setdefault(feature.key, {}).get("resets", 0)
            self.depth = clamp(2 + level // 9 + (1 if feature.seed % 3 == 0 else 0), 2, 5)
            if self.kind == "lair":
                self.depth = clamp(2 + level // 14, 2, 3)
            self.idx = 0
            self.floors = {}
        self.vis = set()
        self.rng = seeded("dungeon", feature.seed, self.resets)
        self.msg = ""

    # ── persistence ────────────────────────────────────────────────────────
    def to_dict(self):
        return dict(key=self.f.key, level=self.level, kind=self.kind, depth=self.depth, idx=self.idx, resets=self.resets,
                    floors={str(k): v.to_dict() for k, v in self.floors.items()})

    @property
    def floor(self):
        if self.idx not in self.floors:
            rng = seeded("floor", self.f.seed, self.resets, self.idx)
            fl = gen_floor(rng, self.f, self.level, self.idx, self.depth, self.quest, self.kind)
            if self.empty:                      # already cleared: silent halls, looted chests
                fl.mons = []
                for o in fl.objs.values():
                    if o["t"] in ("chest", "hoard"):
                        o["open"] = True
                    elif o["t"] == "altar":
                        o["used"] = True
                    elif o["t"] == "trap":
                        o["seen"] = True
            for pos in self._looted():          # remembered from earlier visits: stays open for good
                o = fl.objs.get(tuple(map(int, pos.split(","))))
                if o:
                    self._apply_used(o)
            slain = set(self._record("slain"))
            if slain:
                fl.mons = [m for m in fl.mons if f"{m['home'][0]},{m['home'][1]}" not in slain]
            self.floors[self.idx] = fl
        return self.floors[self.idx]

    @staticmethod
    def _apply_used(o):
        if o["t"] in ("chest", "hoard"):
            o["open"] = True
        elif o["t"] == "altar":
            o["used"] = True
        elif o["t"] == "trap":
            o["seen"] = True
            o["done"] = True

    def _looted_key(self):
        return f"{self.resets}:{self.idx}"

    def _record(self, what):
        return self.g.fstate.get(self.f.key, {}).get(what, {}).get(self._looted_key(), [])

    def _looted(self):
        return self._record("looted")

    def remember_slain(self, m):
        home = m.get("home", m["pos"])
        lst = self.g.fstate.setdefault(self.f.key, {}).setdefault("slain", {}).setdefault(self._looted_key(), [])
        key = f"{home[0]},{home[1]}"
        if key not in lst:
            lst.append(key)

    def remember(self, o):
        """Record that this object (chest, altar, sprung trap) has been used, so it is not reset on re-entry."""
        for pos, obj in self.floor.objs.items():
            if obj is o:
                lst = self.g.fstate.setdefault(self.f.key, {}).setdefault("looted", {}).setdefault(self._looted_key(), [])
                key = f"{pos[0]},{pos[1]}"
                if key not in lst:
                    lst.append(key)
                return

    # ── vision ─────────────────────────────────────────────────────────────
    def compute_fov(self, R=9):
        fl = self.floor
        px, py = fl.pos
        vis = {(px, py)}
        for dy in range(-R, R + 1):
            for dx in range(-R, R + 1):
                if dx * dx + dy * dy > R * R + R:
                    continue
                x0, y0 = px, py
                n = max(abs(dx), abs(dy))
                lx, ly = x0, y0                     # last point the ray actually reached
                for i in range(1, n + 1):
                    x = round(x0 + dx * i / n)
                    y = round(y0 + dy * i / n)
                    if not (0 <= x < FW and 0 <= y < FH):
                        break
                    if x != lx and y != ly and fl.grid[ly][x] == "#" and fl.grid[y][lx] == "#":
                        break                        # can't peek diagonally through a wall corner
                    vis.add((x, y))
                    if fl.grid[y][x] == "#":
                        break
                    lx, ly = x, y
        self.vis = vis
        for (x, y) in vis:
            fl.seen[y][x] = True

    # ── drawing ────────────────────────────────────────────────────────────
    def draw_map(self, s, x0, y0, w, h):
        fl = self.floor
        cols, rows = w // 2, h
        px, py = fl.pos
        ox, oy = px - cols // 2, py - rows // 2
        th = self.theme
        for j in range(rows):
            for i in range(cols):
                x, y = ox + i, oy + j
                sx, sy = x0 + i * 2, y0 + j
                if not (0 <= x < FW and 0 <= y < FH) or not fl.seen[y][x]:
                    continue
                visible = (x, y) in self.vis
                d = math.hypot(x - px, y - py)
                light = (0.55 + 0.6 * max(0, 1 - d / 10.5)) if visible else 0.38
                c = fl.grid[y][x]
                if c == "#":
                    near = any(fl.walk(x + a, y + b) for a, b in DIRS8)
                    if not near:
                        continue
                    jit = 0.9 + ((x * 7 + y * 13) % 5) * 0.05
                    if fl.walk(x, y + 1):
                        s.put(sx, sy, "▀▀", scale(th["wall"], light * 1.25 * jit), scale(th["wall"], light * 0.55))
                    else:
                        s.put(sx, sy, "▒░" if (x + y) % 2 else "░▒", scale(th["wall"], light * 0.9 * jit), scale(th["wall"], light * 0.42))
                    continue
                fc = scale(th["floor"], light * 1.5)
                s.put(sx, sy, "  ", None, fc)
                if (x * 3 + y * 5) % 4 == 0:
                    s.put(sx, sy, " ·", scale(th["ffg"], light * 1.2), fc)
                o = fl.objs.get((x, y))
                if o and (visible or o["t"] in ("down",)):
                    t = o["t"]
                    if t == "chest":
                        s.put(sx, sy, "▣ ", PAL["gold"] if not o["open"] else PAL["dim"], fc, A_BOLD)
                    elif t == "hoard":
                        s.put(sx, sy, "▣▣", PAL["amber"] if not o["open"] else PAL["dim"], fc, A_BOLD)
                    elif t == "trap" and o["seen"]:
                        s.put(sx, sy, "^ ", PAL["red"], fc)
                    elif t == "altar":
                        s.put(sx, sy, "Ω ", PAL["cyan"] if not o["used"] else PAL["dim"], fc, A_BOLD)
                    elif t == "down":
                        s.put(sx, sy, "> ", PAL["white"], fc, A_BOLD)
                if (x, y) == fl.up:
                    s.put(sx, sy, "< ", PAL["white"], fc, A_BOLD)
        for m in fl.mons:
            x, y = m["pos"]
            if (x, y) in self.vis:
                sx, sy = x0 + (x - ox) * 2, y0 + (y - oy)
                if not (x0 <= sx < x0 + w - 1 and y0 <= sy < y0 + h):
                    continue
                g = m["group"][0]
                col = PAL.get(g.color, PAL["white"])
                _, _, bgc, _ = s.cells[sy * s.w + sx]
                tail = str(len(m["group"])) if len(m["group"]) > 1 else ("★" if g.boss or g.elite else " ")
                s.put(sx, sy, g.glyph + tail, PAL["red"] if g.boss else col, bgc, A_BOLD)
        sx, sy = x0 + (px - ox) * 2, y0 + (py - oy)
        _, _, bgc, _ = s.cells[sy * s.w + sx]
        s.put(sx, sy, "@ ", PAL["gold"], bgc, A_BOLD)

    def side_info(self):
        fl = self.floor
        left = sum(len(m["group"]) for m in fl.mons if (m["pos"]) in self.vis)
        return [f"<gold>{self.theme['title']}</> <dim>·</> {esc(self.f.name)}",
                f"Floor <white>{self.idx + 1}</>/{self.depth}  <dim>Lv{self.level + self.idx}</>",
                "", "<dim>@</> you  <dim>></> stairs down  <dim><</> up",
                "<gold>▣</> chest  <cyan>Ω</> altar  <red>^</> trap", "<dim>g2</> foes  <red>★</> elite/boss"]

    # ── main loop ──────────────────────────────────────────────────────────
    def run(self):
        g = self.g
        fl = self.floor
        self.compute_fov()
        g.dungeon = self
        cs, g.combat_state = g.combat_state, None
        if cs and (cs.get("ctx") or {}).get("kind") == "dungeon":
            m = self.floor.mon_at(*cs["ctx"]["pos"])
            if m:
                self.engage(m, resume=cs)
        while True:
            fl = self.floor
            g.draw_scene(lambda s, x, y, w, h: self.draw_map(s, x, y, w, h), side=self.side_info(),
                         footer=hints([("Arrows", "Move"), ("Enter", "Use"), (".", "Search"), ("I", "Pack"), ("C", "Sheet"), ("Q", "Quests"), ("Esc", "Menu")]),
                         header=f"{self.theme['title']} — {esc(self.f.name)}")
            g.ui.flush()
            k = g.ui.key()
            if k == "resize":
                continue
            d = g.move_key(k)
            if d:
                r = self.move(*d)
                if r == "exit":
                    g.dungeon = None
                    return "exit"
                continue
            if k in ("enter", "e", "space"):
                r = self.use_here()
                if r == "exit":
                    g.dungeon = None
                    return "exit"
            elif k == ".":
                self.search()
                self.monsters_act()
            elif k == "esc":
                g.game_menu(in_dungeon=True)
            else:
                g.global_key(k)

    def free_cell_near(self, pos):
        fl = self.floor
        for dx, dy in DIRS8:
            x, y = pos[0] + dx, pos[1] + dy
            if fl.walk(x, y) and not fl.mon_at(x, y):
                return (x, y)
        return pos

    def move(self, dx, dy):
        g, fl = self.g, self.floor
        nx, ny = fl.pos[0] + dx, fl.pos[1] + dy
        if not fl.walk(nx, ny):
            return None
        m = fl.mon_at(nx, ny)
        if m:
            return self.engage(m)
        fl.pos = (nx, ny)
        g.advance_time(6)
        g.p.steps += 1
        if g.p.steps % 4 == 0:
            g.p.restore_mp(1)
        self.compute_fov()
        o = fl.objs.get((nx, ny))
        if o:
            r = self.on_object(o, (nx, ny))
            if r:
                return r
        return self.monsters_act()

    def monsters_act(self):
        fl, g = self.floor, self.g
        px, py = fl.pos
        for m in list(fl.mons):
            if m not in fl.mons:
                continue
            if m.get("stun", 0) > 0:
                m["stun"] -= 1
                continue
            mx, my = m["pos"]
            dist = max(abs(mx - px), abs(my - py))
            if not m["awake"]:
                if m.get("boss"):
                    if (mx, my) in self.vis and dist <= 7:
                        m["awake"] = True
                        g.msg(f"<b><red>{esc(m['group'][0].name)} rises to face you!</></>")
                elif dist <= 4 and self.g.rng.random() < 0.35:
                    m["awake"] = True
                    g.msg(f"<amber>Something stirs nearby…</>")
                continue
            if m.get("boss") and dist > 2 and False:
                continue
            if dist <= 1:
                return self.engage(m, ambush=self.g.rng.random() < 0.2)
            if (mx, my) in self.vis or dist <= 9:
                best = None
                for ddx, ddy in DIRS8:
                    x, y = mx + ddx, my + ddy
                    if not fl.walk(x, y) or fl.mon_at(x, y) or (x, y) == fl.pos:
                        continue
                    d2 = (x - px) ** 2 + (y - py) ** 2
                    if best is None or d2 < best[0]:
                        best = (d2, (x, y))
                if best and best[0] < dist * dist + 1:
                    m["pos"] = best[1]
                    if max(abs(best[1][0] - px), abs(best[1][1] - py)) <= 1:
                        return self.engage(m, ambush=self.g.rng.random() < 0.2)
        return None

    def engage(self, m, ambush=False, resume=None):
        g, fl = self.g, self.floor
        grp = m["group"]
        boss = m.get("boss") or any(e.boss for e in grp)
        ctx = dict(kind="dungeon", pos=list(m["pos"]))
        combat = Combat.from_dict(g, resume, enemies=grp) if resume else None
        res = g.fight(grp, ambush=ambush, title=f"{self.theme['title']} · {esc(self.f.name)}", boss=boss, dungeon=True,
                      combat=combat, ctx=ctx)
        if res == "win":
            if m in fl.mons:
                fl.mons.remove(m)
            self.remember_slain(m)
            if boss and fl.down is None:
                self.on_boss_dead()
        elif res == "flee":
            m["stun"] = 3
            m["awake"] = True
            fl.pos = self.free_cell_near(fl.pos) if fl.mon_at(*fl.pos) else fl.pos
            # step away from the monster
            best = None
            for dx, dy in DIRS8:
                x, y = fl.pos[0] + dx, fl.pos[1] + dy
                if fl.walk(x, y) and not fl.mon_at(x, y):
                    d = abs(x - m["pos"][0]) + abs(y - m["pos"][1])
                    if best is None or d > best[0]:
                        best = (d, (x, y))
            if best:
                fl.pos = best[1]
            self.compute_fov()
        return None

    def on_boss_dead(self):
        g = self.g
        self.cleared = True
        g.msg("<b><gold>The heart of the place falls silent. The hoard lies unguarded!</></>")
        g.fstate.setdefault(self.f.key, {})["cleared_day"] = g.day
        g.chronicle(f"Cleared {self.f.name}.")
        g.quest_event("cleared", self.f)
        if self.kind == "lair" and self.quest is None:
            pass

    # ── objects ──────────────────────────────────────────────────────────
    def on_object(self, o, pos):
        g, fl = self.g, self.floor
        t = o["t"]
        if t == "trap":
            if o.get("done"):
                return None
            bonus = g.p.skill_bonus("Perception")
            if o["seen"]:
                g.msg("<dim>You carefully step around the trap.</>")
                return None
            if self.g.rng.randint(1, 20) + bonus >= 12 + self.level // 3:
                o["seen"] = True
                g.msg("<amber>You spot a hidden trap just in time and skirt it.</>")
                fl.pos = fl.pos
                return None
            desc, kind = TRAPS[o["kind"]]
            o["seen"] = True
            o["done"] = True
            self.remember(o)
            dmg = roll_n(2 + (self.level + self.idx) // 4, 6, g.rng) + self.level
            save = g.rng.randint(1, 20) + g.p.m("DEX") >= 11 + self.level // 3
            if save:
                dmg //= 2
            g.p.hp -= dmg
            g.msg(f"<red>You trigger {desc}! {dmg} damage{' (half, you dodge)' if save else ''}.</>")
            g.ui.flash(PAL["red"], 0.4, 2)
            if g.p.hp <= 0:
                raise Died("trap")
            if kind == "poison" and not save:
                g.msg("<lime>The darts were poisoned; you feel sick.</>")
        elif t in ("chest", "hoard"):
            if not o["open"]:
                return self.open_chest(o, hoard=(t == "hoard"))
        elif t == "altar":
            if not o["used"]:
                self.use_altar(o)
        elif t == "down":
            g.msg("<white>Stairs lead down into the dark. Press <b>Enter</> to descend.</>")
        return None

    def open_chest(self, o, hoard=False):
        g = self.g
        p = g.p
        lv = self.level + self.idx
        st = Story(g.ui, "Treasure Chest" if not hoard else "The Hoard", art=g.scene("chest"), art_color=PAL["gold"],
                   color=PAL["amber"])
        st.say("An iron-bound chest, dusty but sound. " if not hoard else
               "Beyond the fallen guardian glitters what it died protecting: a heap of coin, glass and steel.")
        trapped = (not hoard) and g.rng.random() < 0.3
        choice = 0
        if not hoard:
            choice = st.ask(["Open it", "Search for traps first (Investigation)", "Leave it"])
        if choice == 2:
            st.close()
            return None
        if choice == 1:
            ok, _, _ = st.check("Investigation", p.skill_bonus("Investigation"), 11 + lv // 3)
            if ok:
                if trapped:
                    st.say("<green>You find a hair-thin wire and cut it. Whatever it was for, it won't happen now.</>")
                trapped = False
        if trapped:
            dmg = roll_n(2 + lv // 4, 6, g.rng) + lv
            ok, _, _ = st.check("Reflex (DEX)", p.m("DEX"), 11 + lv // 3)
            if ok:
                dmg //= 2
            p.hp -= dmg
            st.say(f"A spring-loaded blade snaps out! <red>{dmg} damage.</>")
            if p.hp <= 0:
                st.pause()
                st.close()
                raise Died("chest")
        o["open"] = True
        self.remember(o)
        rng = g.rng
        gold = int(rng.randint(8, 22) * (lv + 2) * (3 if hoard else 1))
        p.gold += gold
        st.say(f"<gold>+{gold} gold.</>")
        items = []
        n = 3 if hoard else (1 if rng.random() < 0.5 else 0)
        for i in range(n):
            it = gen_any(rng, lv + (2 if hoard else 0), rarity=None if not hoard else max(2, 2 + (rng.random() < .3)),
                         kinds=[("weapon", 3), ("armor", 3), ("shield", 1), ("jewelry", 3), ("potion", 3), ("scroll", 1), ("gem", 2)])
            items.append(it)
        if hoard:
            items.append(gen_relic(rng, lv))
            if self.quest and self.quest["type"] == "retrieve":
                pass
        if rng.random() < 0.4:
            items.append(gen_potion(rng, lv))
        for it in items:
            st.say(f"You find {name_item(it)}.")
            if not g.give_item(it):
                st.say("<grey>No room for it — you leave it where it fell.</>")
        if self.quest and self.quest["type"] == "retrieve" and (hoard or self.idx == self.depth - 1) and hoard:
            g.quest_event("artifact", self.f)
            st.say(f"<b><cyan>Among the coins lies the {esc(self.quest['artifact'])}!</></>")
        st.pause()
        st.close()
        return None

    def use_altar(self, o):
        g, p = self.g, self.g.p
        kinds = [("Font of Renewal", "A basin of clear, glowing water."), ("Ember Shrine", "A brazier that burns without fuel."),
                 ("Bone Altar", "An altar of knuckle-bones, stained dark.")]
        name, desc = kinds[o["kind"]]
        st = Story(g.ui, name, art=g.scene("shrine"), art_color=PAL["cyan"], color=PAL["cyan"])
        st.say(desc)
        i = st.ask(["Drink / pray / touch it", "Leave it be"])
        if i == 1:
            st.close()
            return
        o["used"] = True
        self.remember(o)
        if o["kind"] == 0:
            h = p.heal(p.max_hp)
            p.restore_mp(p.max_mp)
            st.say(f"<green>Cool light runs through you. Fully restored (+{h} HP).</>")
        elif o["kind"] == 1:
            p.blessed_until = p.minutes + 720
            st.say("<amber>The flames lean toward you. You are <b>Blessed</> for the next half-day.</>")
        else:
            ok, _, _ = st.check("Religion", p.skill_bonus("Religion"), 12 + self.level // 3)
            if ok:
                x = int(50 + self.level * 30)
                p.gold += x
                st.say(f"<gold>The bones rattle out an offering: +{x} gold.</>")
            else:
                dmg = max(1, p.max_hp // 6)
                p.hp = max(1, p.hp - dmg)
                st.say(f"<red>Cold fingers rake your soul. -{dmg} HP.</>")
        st.pause()
        st.close()

    def use_here(self):
        g, fl = self.g, self.floor
        pos = fl.pos
        o = fl.objs.get(pos)
        if o and o["t"] == "down":
            if g.ui.confirm("Descend to the next floor?", True, "Stairs"):
                self.idx += 1
                self.floor.pos = self.floor.up
                self.compute_fov()
                g.msg(f"<white>You descend to floor {self.idx + 1}.</>")
                g.autosave()
            return None
        if pos == fl.up:
            if self.idx == 0:
                if g.ui.confirm("Leave this place?", True, "Exit"):
                    return "exit"
            else:
                self.idx -= 1
                fl2 = self.floor
                fl2.pos = fl2.down
                self.compute_fov()
                g.msg("<white>You climb back up.</>")
            return None
        if o and o["t"] in ("chest", "hoard") and not o["open"]:
            return self.open_chest(o, o["t"] == "hoard")
        # adjacent chest?
        for dx, dy in DIRS8:
            oo = fl.objs.get((pos[0] + dx, pos[1] + dy))
            if oo and oo["t"] in ("chest", "hoard", "altar") and not oo.get("open") and not oo.get("used"):
                fl.pos = (pos[0] + dx, pos[1] + dy)
                self.compute_fov()
                return self.on_object(oo, fl.pos)
        g.msg("<dim>Nothing here to use.</>")
        return None

    def search(self):
        g, fl = self.g, self.floor
        found = 0
        bonus = g.p.skill_bonus("Perception") + 3
        for (x, y), o in fl.objs.items():
            if o["t"] == "trap" and not o["seen"] and abs(x - fl.pos[0]) <= 3 and abs(y - fl.pos[1]) <= 3:
                if g.rng.randint(1, 20) + bonus >= 11 + self.level // 3:
                    o["seen"] = True
                    found += 1
        g.advance_time(10)
        g.msg(f"<amber>You search carefully and find {found} hidden trap{'s' if found != 1 else ''}.</>" if found else "<dim>You search, but find nothing.</>")
