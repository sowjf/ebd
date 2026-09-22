"""Main game: overworld loop, HUD, screens, saving, character creation."""
import json
import math
import os
import random
import time

from . import events
from .art import SCENES, LOGO
from .chargen import roll_stats, assign, create_player
from .combat import Combat
from .data import (CLASSES, ORIGINS, STATS, STAT_NAMES, SKILLS, MONSTERS, WHISPERS, NIGHT_WHISPERS, xp_needed, title_for,
                   ELEMENTS)
from .dungeon import Dungeon, Died
from .entities import Player, Monster, INV_LIMIT, SLOTS
from .items import name_item, describe, gen_any, gen_potion, is_stackable, RCOL, gen_relic, gen_gem, gen_jewelry
from .quests import describe_quest, dir_name, arrow, dragon_of
from .spawn import spawn_group
from .term import PAL, mix, scale, vlen, wrap, esc, strip, A_BOLD, A_DIM, ScriptEnd
from .town import Town, compare_lines
from .ui import UI, Story, bar, hp_color, hints, rarity_color, fit_hints
from .util import mod, sign, seeded, fmt_clock, hash2, rnd2
from .world import (World, Explored, BIOMES, FEATURES, START, CHUNK, SHALLOW, SETTLEMENTS, DUNGEONS, MOUNTAIN, FOREST,
                    DENSE, SWAMP, DESERT, TUNDRA, SNOW, ASH, HILLS)

SAVE_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "emberroad")
VERSION = "1.0"
MOVES = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0), "w": (0, -1), "s": (0, 1), "a": (-1, 0),
         "d": (1, 0), "k": (0, -1), "j": (0, 1), "h": (-1, 0), "l": (1, 0), "y": (-1, -1), "u": (1, -1), "b": (-1, 1),
         "n": (1, 1), "8": (0, -1), "2": (0, 1), "4": (-1, 0), "6": (1, 0), "7": (-1, -1), "9": (1, -1), "1": (-1, 1),
         "3": (1, 1)}
GROUP_KEY = {"water": "swamp", "plains": "plains", "forest": "forest", "hills": "hills", "mountain": "mountain",
             "swamp": "swamp", "desert": "desert", "tundra": "tundra", "ash": "ash"}


class Game:
    def __init__(self, term, seed=None):
        self.t = term
        self.ui = UI(term)
        self.rng = random.Random(seed)
        self.p = None
        self.world = None
        self.explored = Explored()
        self.fstate = {}
        self.markers = set()
        self.log = []
        self.track = None
        self.dungeon = None
        self.ctx_level = 1
        self.pending_xp = 0
        self.slot = None
        self.settings = {"anim": True}
        self.tick = 0
        self.playtime = 0.0
        self._t0 = time.time()
        self.fade = False
        self.here = None
        self.active_combat = None
        self.combat_state = None

    # ═══════════════════════════ small helpers ═══════════════════════════
    def town_event(self, town):
        events.town_event(self, town)

    def scene(self, name):
        return SCENES.get(name, [])

    def msg(self, text):
        self.log.append(text)
        self.log = self.log[-200:]

    @property
    def day(self):
        return self.p.minutes // 1440 + 1

    def clock(self):
        return fmt_clock(self.p.minutes)

    def is_night(self):
        h = (self.p.minutes // 60) % 24
        return h >= 21 or h < 5

    def night_k(self):
        h = (self.p.minutes % 1440) / 60.0
        if 7 <= h <= 18:
            return 0.0
        if 18 < h < 21:
            return (h - 18) / 3
        if h >= 21 or h < 4:
            return 1.0
        if 4 <= h < 7:
            return 1 - (h - 4) / 3
        return 0.0

    def chronicle(self, text):
        self.p.deeds.append(f"Day {self.day}: {text}")

    def mark_known(self, f):
        self.markers.add(f.key)

    def vision_radius(self):
        p = self.p
        nk = self.night_k()
        b = self.world.biome(p.pos[0], p.pos[1])
        r = 10 - 5 * nk
        if b in (HILLS,):
            r += 1
        elif b in (MOUNTAIN,):
            r += 2
        elif b in (FOREST,):
            r -= 1.5
        elif b in (DENSE, SWAMP):
            r -= 2.5
        if self.weather() == "fog":
            r -= 2
        return max(2, int(r))

    def weather(self):
        p = self.p
        if not p:
            return "clear"
        rx, ry = p.pos[0] // 64, p.pos[1] // 64
        r = rnd2(rx + self.day * 7, ry, self.world.seed + 91)
        grp = BIOMES[self.world.biome(p.pos[0], p.pos[1])][1]
        if grp == "desert":
            return "clear" if r < 0.85 else "wind"
        if grp == "ash":
            return "ash" if r < 0.7 else "clear"
        if r < 0.55:
            return "clear"
        if r < 0.75:
            return "snow" if grp == "tundra" else "rain"
        if r < 0.88:
            return "fog"
        return "clear"

    def advance_time(self, minutes, resting=False):
        p = self.p
        before_h = p.minutes // 60
        before_d = p.minutes // 1440
        p.minutes += int(minutes)
        for hh in range(before_h + 1, p.minutes // 60 + 1):
            h = hh % 24
            if h == 21:
                self.msg("<blue>Night falls. The dark is watching.</>")
            elif h == 5:
                self.msg("<amber>The first grey light of dawn.</>")
        self.update_hunger()

    def update_hunger(self):
        """A ration feeds you for 24 h (timer `fed_until`). When it runs out you eat automatically;
        with no food you turn Hungry (penalties + slow HP loss) until food turns up, then you eat at once."""
        p = self.p
        if p is None:
            return
        fl = p.flags
        if fl.get("hungry") and p.food > 0:                       # food arrived while hungry
            p.food -= 1
            fl["hungry"] = False
            fl.pop("hunger_next", None)
            p.fed_until = p.minutes + 1440
            self.msg(f"<green>You eat a ration. The hunger fades.</> <dim>({p.food} left)</>")
            if p.food == 0:
                self.msg("<amber>That was your last ration!</>")
            return
        while not fl.get("hungry") and p.minutes >= p.fed_until:
            if p.food > 0:
                p.food -= 1
                p.fed_until += 1440
                self.msg(f"<grey>You eat a ration. ({p.food} left)</>")
                if p.food == 0:
                    self.msg("<amber>That was your last ration!</>")
            else:
                fl["hungry"] = True
                fl["hunger_next"] = p.fed_until
                self.msg("<b><red>You are hungry!</></> <dim>-2 to attack and checks, no natural healing. Buy or forage food.</>")
        if fl.get("hungry"):
            while p.minutes >= fl["hunger_next"]:
                loss = max(1, p.max_hp // 12)
                p.hp = max(1, p.hp - loss)
                self.msg(f"<red>Hunger gnaws at you: -{loss} HP.</>")
                fl["hunger_next"] += 1440

    def fed_hours(self):
        return max(0, (self.p.fed_until - self.p.minutes + 59) // 60)

    # ═══════════════════════════ layout / drawing ═══════════════════════════
    def layout(self):
        s = self.ui.begin()
        W, H = s.w, s.h
        side_w = 30 if W >= 100 else 27
        log_h = 6 if H >= 30 else 5 if H >= 27 else 4
        box_h = H - log_h - 4
        return dict(W=W, H=H, side_w=side_w, log_h=log_h, box_h=box_h)

    def draw_scene(self, draw_map, side=None, footer=None, header=None):
        s = self.ui.begin()
        s.clear()
        self.update_hunger()
        L = self.layout()
        W, H, sw, lh, bh = L["W"], L["H"], L["side_w"], L["log_h"], L["box_h"]
        p = self.p
        # header
        s.fill(0, 0, W, 1, " ", None, PAL["panel"])
        s.puts(1, 0, "<b><ember>✦</> <gold>EMBERROAD</> <ember>✦</></>", None, PAL["panel"])
        day, h, m = self.clock()
        nk = self.night_k()
        icon = "<blue>☾</>" if nk > 0.7 else ("<amber>◐</>" if nk > 0.1 else "<gold>☼</>")
        wx = {"clear": "", "rain": " <ice>rain</>", "snow": " <white>snow</>", "fog": " <grey>fog</>", "ash": " <ember>ashfall</>", "wind": " <sand>wind</>"}[self.weather()]
        right = f"Day {day} · {h:02d}:{m:02d} {icon}{wx}"
        s.puts(W - vlen(right) - 2, 0, right, PAL["white"], PAL["panel"])
        if header:
            s.center(0, header, PAL["silver"], PAL["panel"])
        # map
        s.box(0, 1, W - sw, bh, "single", PAL["edge"], PAL["bg"])
        draw_map(s, 1, 2, W - sw - 2, bh - 2)
        # sidebar
        self.draw_sidebar(s, W - sw, 1, sw, bh, side or [])
        # log
        ly = 1 + bh
        s.box(0, ly, W, lh + 2, "single", PAL["edge2"], PAL["panel"], "Journey log")
        lines = []
        for ln in self.log[-12:]:
            lines.extend(wrap(ln, W - 4))
        for i, ln in enumerate(lines[-lh:]):
            k = len(lines[-lh:]) - 1 - i
            s.puts(2, ly + 1 + i, ln, scale(PAL["white"], 1.0 if k < 2 else 0.72 if k < 4 else 0.5), PAL["panel"], maxw=W - 4)
        if footer:
            s.center(H - 1, fit_hints(footer, W))

    def draw_sidebar(self, s, x, y, w, h, extra):
        p = self.p
        s.box(x, y, w, h, "round", PAL["edge"], PAL["panel"], esc(p.name))
        ix, iw = x + 2, w - 4
        yy = y + 1
        cls = p.c
        col = cls["color"]
        s.puts(ix, yy, f"<{col}>Lv{p.level} {cls['name']}</>", PAL["white"], PAL["panel"]); yy += 1
        s.puts(ix, yy, f"<dim><i>{p.title}</></>", PAL["white"], PAL["panel"]); yy += 1
        bar(s, ix + 3, yy, iw - 3, p.hp, p.max_hp, hp_color(p.hp / p.max_hp), label=f"{p.hp}/{p.max_hp}")
        s.puts(ix, yy, "<red>HP</>", None, PAL["panel"]); yy += 1
        rc = {"Valor": PAL["silver"], "Focus": PAL["green"], "Guile": PAL["purple"], "Mana": PAL["blue"], "Faith": PAL["gold"], "Fury": PAL["red"]}[cls["resource"]]
        bar(s, ix + 3, yy, iw - 3, p.mp, p.max_mp, rc, label=f"{p.mp}/{p.max_mp}")
        s.puts(ix, yy, "<cyan>MP</>", None, PAL["panel"]); yy += 1
        compact = h < 21
        if not compact:
            bar(s, ix + 3, yy, iw - 3, p.xp, xp_needed(p.level), PAL["violet"], label=f"{p.xp}/{xp_needed(p.level)}")
            s.puts(ix, yy, "<purple>XP</>", None, PAL["panel"]); yy += 1
        rows = []
        n, sd = p.dice
        rows.append(f"<dim>AC</> <b>{p.ac}</> <dim>ATK</> <b>{sign(p.atk_bonus)}</> <dim>DMG</> <b>{round(n * (sd + 1) / 2 + p.dmg_flat)}</>")
        if not compact:
            rows.append("  ".join(f"<dim>{st}</> <b>{p.stat(st)}</>" for st in STATS[:3]))
            rows.append("  ".join(f"<dim>{st}</> <b>{p.stat(st)}</>" for st in STATS[3:]))
        rows.append(f"<gold>{p.gold}</> gold  <dim>·</> {p.food} <dim>rations</>" + ("  <red>!</>" if p.food == 0 else ""))
        if p.hungry:
            rows.append("<b><red>! HUNGRY</> <dim>-2 hit, no regen</>")
        else:
            fh = self.fed_hours()
            rows.append(f"<dim>Fed for</> <{'green' if fh > 6 else 'amber'}>{fh}h</>")
        if p.blessed_until > p.minutes:
            rows.append("<amber>✚ Blessed</>")
        if p.stat_points:
            rows.append(f"<green>★ {p.stat_points} stat point{'s' if p.stat_points > 1 else ''}! [C]</>")
        lines = [None] + rows + ([] if compact else [None]) + extra
        for ln in lines:
            if yy >= y + h - 1:
                break
            if ln is None:
                s.hline(x + 1, yy, w - 2, "─", PAL["edge2"], PAL["panel"])
            else:
                for wl in wrap(ln, iw) if vlen(ln) > iw else [ln]:
                    if yy >= y + h - 1:
                        break
                    s.puts(ix, yy, wl, PAL["white"], PAL["panel"], maxw=iw)
                    yy += 1
                continue
            yy += 1

    # ═══════════════════════════ overworld drawing ═══════════════════════════
    def draw_ow_map(self, s, x0, y0, w, h):
        p, wd = self.p, self.world
        cols, rows = w // 2, h
        px, py = p.pos
        ox, oy = px - cols // 2, py - rows // 2
        vr = self.vision_radius()
        vr2 = vr * vr + vr
        nk = self.night_k()
        wx = self.weather()
        NIGHT = 0x0a1236
        FOGC = 0x8a90a0
        tick = self.tick
        seen_at = self.explored.seen
        for j in range(rows):
            y = oy + j
            for i in range(cols):
                x = ox + i
                sx, sy = x0 + i * 2, y0 + j
                dx, dy = x - px, y - py
                vis = dx * dx + dy * dy <= vr2
                if not vis and not seen_at(x, y):
                    if (x * 31 + y * 17) % 13 == 0:
                        s.put(sx, sy, "· ", 0x191524, PAL["bg"])
                    continue
                g, fg, bg = wd.vis(x, y)
                b = wd.biome(x, y)
                if b <= SHALLOW:
                    g = ("~ ", " ~", "≈ ", " ≈")[(x + y + tick // 3) % 4] if b == 0 else ("~ ", " ~")[(x + y + tick // 2) % 2]
                if b == ASH and (x * 7 + y * 3 + tick // 2) % 23 == 0:
                    g, fg = "' ", 0xff7a2a
                if not vis:
                    fg = scale(mix(fg, 0x181828, 0.55), 0.75)
                    bg = scale(mix(bg, 0x101018, 0.5), 0.7)
                else:
                    d = math.sqrt(dx * dx + dy * dy)
                    f = 1.0 - 0.28 * (d / (vr + 1)) ** 2
                    fg, bg = scale(fg, f), scale(bg, f)
                if nk > 0:
                    fg = mix(fg, NIGHT, nk * 0.55)
                    bg = mix(bg, NIGHT, nk * 0.6)
                if wx == "fog":
                    fg, bg = mix(fg, FOGC, 0.3), mix(bg, FOGC, 0.3)
                s.put(sx, sy, g, fg, bg)
        # features
        for cy in range((oy // CHUNK) - 0, (oy + rows) // CHUNK + 1):
            for cx in range((ox // CHUNK) - 0, (ox + cols) // CHUNK + 1):
                f = wd.feature_of(cx, cy)
                if not f:
                    continue
                i, j = f.x - ox, f.y - oy
                if not (0 <= i < cols and 0 <= j < rows):
                    continue
                dx, dy = f.x - px, f.y - py
                vis = dx * dx + dy * dy <= vr2
                known = f.key in self.markers
                if not (vis or seen_at(f.x, f.y) or known):
                    continue
                sx, sy = x0 + i * 2, y0 + j
                _, _, bg, _ = s.cells[sy * s.w + sx]
                col = f.color
                st = self.fstate.get(f.key, {})
                if f.is_dungeon and st.get("cleared_day") and self.day - st["cleared_day"] < 5:
                    col = 0x60606a
                if not vis:
                    col = scale(col, 0.75 if known else 0.6)
                bgf = scale(mix(bg, col, 0.18), 0.9)
                if nk > 0 and vis:
                    col = mix(col, 0xffcc66, 0.3 * nk) if f.is_settlement else col
                s.put(sx, sy, f.glyph, col, bgf, A_BOLD)
        # weather particles
        if wx in ("rain", "snow", "ash", "wind"):
            r = random.Random(tick * 131 + 7)
            n = int(cols * rows * (0.05 if wx == "rain" else 0.035))
            ch, col = {"rain": ("/", 0x7aa8e0), "snow": ("*", 0xffffff), "ash": ("'", 0xff8a3a), "wind": ("-", 0xd8c27a)}[wx]
            for _ in range(n):
                i, j = r.randrange(cols), r.randrange(rows)
                sx, sy = x0 + i * 2 + r.randrange(2), y0 + j
                _, _, bg, _ = s.cells[sy * s.w + sx]
                s.put(sx, sy, ch, col, bg)
        # player
        sx, sy = x0 + (px - ox) * 2, y0 + (py - oy)
        _, _, bg, _ = s.cells[sy * s.w + sx]
        s.put(sx, sy, "@ ", PAL["gold"] if tick % 6 < 4 else PAL["white"], bg, A_BOLD)

    def home_line(self):
        """Respawn town (the last settlement you entered): name, distance and direction to walk."""
        p = self.p
        t = p.last_town or dict(name="Hearthmoor", x=START[0] - 2, y=START[1] - 2)
        dx, dy = t["x"] - p.pos[0], t["y"] - p.pos[1]
        if dx == 0 and dy == 0:
            return f"<dim>Home:</> <white>{esc(t['name'])}</> <green>(you are here)</>"
        return f"<dim>Home:</> <white>{esc(t['name'])}</> <cyan>{arrow(dx, dy)} {int(math.hypot(dx, dy))}</>"

    def ow_side(self):
        p, wd = self.p, self.world
        px, py = p.pos
        b = wd.biome(px, py)
        name, group, cost, passable, enc, *_ = BIOMES[b]
        lvl = wd.level_at(px, py)
        diff = lvl - p.level
        skulls = max(0, min(5, 2 + diff // 2 + (1 if diff > 0 else 0)))
        tcol = "green" if diff < -1 else "gold" if diff <= 1 else "amber" if diff <= 4 else "red"
        rating = "Peaceful" if diff < -3 else "Safe" if diff < -1 else "Fair" if diff <= 1 else "Risky" if diff <= 4 else "Deadly"
        out = [f"<dim>Here:</> <white>{name}</>", f"<dim>Land:</> <white>{esc(wd.region_at(px, py))}</>",
               f"<dim>Danger:</> <{tcol}>Lv{lvl} {rating}</>",
               self.home_line()]
        f = wd.feature_at(px, py)
        if f:
            out += [None, f"<gold>{f.glyph.strip()}</> <b>{esc(f.name)}</>", f"<dim>{f.label}</>", "<green>[Enter] Enter</>"]
        q = next((q for q in p.quests if q["id"] == self.track and q["state"] != "done"), None)
        if q is None:
            q = next((q for q in p.quests if q["state"] == "active"), None)
        if q:
            out.append(None)
            if q["state"] == "ready":
                out.append(f"<green>✓ {esc(q['title'])}</>")
                out.append(f"<dim>Return to</> <white>{esc(q['giver'])}</>")
                gk = q["giver_key"]
                gx, gy = map(int, gk.split(","))
                out.append(f"<cyan>{arrow(gx - px, gy - py)} {int(math.hypot(gx - px, gy - py))} leagues</>")
            else:
                out.append(f"<amber>▸ {esc(q['title'])}</>")
                if q.get("tx") is not None:
                    dx, dy = q["tx"] - px, q["ty"] - py
                    out.append(f"<cyan>{arrow(dx, dy)} {int(math.hypot(dx, dy))} leagues {dir_name(dx, dy)}</>")
                elif q["type"] == "hunt":
                    out.append(f"<white>{q['progress']}/{q['goal']}</> <dim>{q.get('plural', '')}</>")
        out += [None, "<gold>⌂</><dim> town </><amber>◘</><dim> inn </><ice>†</><dim> shrine</>",
                "<purple>‡</><dim> crypt </><silver>▚</><dim> ruins </><brown>∩</><dim> cave</>",
                "<cyan>╥</><dim> tower </><red>Ω</><dim> lair </><red>Δ</><dim> camp</>"]
        return out

    # ═══════════════════════════ input helpers ═══════════════════════════
    def move_key(self, k):
        return MOVES.get(k)

    def global_key(self, k):
        if k == "i":
            self.inventory()
        elif k == "c":
            self.character_sheet()
        elif k == "q":
            self.journal()
        elif k == "m":
            self.world_map()
        elif k == "?" or k == "f1":
            self.help_screen()
        elif k == "r" and self.dungeon is None:
            return "camp"
        elif k == "t":
            self.cycle_track()
        else:
            return None
        return True

    def cycle_track(self):
        act = [q for q in self.p.quests if q["state"] != "done"]
        if not act:
            return
        ids = [q["id"] for q in act]
        i = ids.index(self.track) if self.track in ids else -1
        self.track = ids[(i + 1) % len(ids)]
        self.msg(f"<amber>Tracking:</> {esc(act[(i + 1) % len(ids)]['title'])}")

    # ═══════════════════════════ overworld loop ═══════════════════════════
    def play(self):
        p = self.p
        self.t.fast = not self.settings["anim"]
        self.explored.reveal(p.pos[0], p.pos[1], self.vision_radius())
        if self.dungeon_state:
            self.resume_dungeon()
        self.ui.dissolve()
        while True:
            try:
                self.overworld_loop()
            except Died as e:
                self.dungeon = None
                if self.handle_death(str(e)):
                    return
            except (ToTitle, RetireHero):
                self.dungeon = None
                return

    dungeon_state = None

    def resume_dungeon(self):
        st, self.dungeon_state = self.dungeon_state, None
        f = self.world.feature_at(*map(int, st["key"].split(",")))
        d = Dungeon(self, f, st["level"], st["kind"], state=st)
        try:
            d.run()
        except Died as e:
            self.dungeon = None
            self.handle_death(str(e))
        self.dungeon = None

    def resume_overworld_combat(self):
        cs, self.combat_state = self.combat_state, None
        c = Combat.from_dict(self, cs)
        self.fight(c.enemies, combat=c)
        self.flush_xp()

    def overworld_loop(self):
        p = self.p
        if self.combat_state and not self.dungeon_state:
            self.resume_overworld_combat()
        while True:
            self.draw_scene(self.draw_ow_map, side=self.ow_side(),
                            footer=hints([("Arrows", "Move"), ("Enter", "Go in"), ("R", "Camp"), ("I", "Pack"), ("C", "Sheet"),
                                          ("Q", "Quests"), ("M", "Map"), ("?", "Help"), ("Esc", "Menu")]),
                            header=f"<grey>{esc(self.world.region_at(*p.pos))}</>")
            self.ui.flush()
            k = self.ui.key(0.22)
            if k is None:
                self.tick += 1
                continue
            if k == "resize":
                continue
            self.tick += 1
            self.flush_xp()
            d = self.move_key(k)
            if d:
                self.step(*d)
                continue
            if k in ("enter", "e", "space"):
                f = self.world.feature_at(*p.pos)
                if f:
                    self.enter_feature(f)
                else:
                    self.msg("<dim>There's nothing here but the road.</>")
            elif k == "esc":
                self.game_menu()
            elif k == ".":
                self.advance_time(10)
                self.msg("<dim>You wait a moment and listen.</>")
                self.encounter_check(0.5)
            else:
                r = self.global_key(k)
                if r == "camp":
                    self.camp()

    def flush_xp(self):
        if self.pending_xp:
            n, self.pending_xp = self.pending_xp, 0
            self.gain_xp(n)

    # ═══════════════════════════ movement & encounters ═══════════════════════════
    def step(self, dx, dy):
        p, wd = self.p, self.world
        x, y = p.pos[0] + dx, p.pos[1] + dy
        b = wd.biome(x, y)
        name, group, cost, passable, enc, *_ = BIOMES[b]
        if not passable:
            self.msg({"Deep Water": "<blue>Deep water. You'd need a boat.</>", "Snowcapped Peaks": "<white>Sheer ice-glazed cliffs block the way.</>",
                      "Lava": "<ember>A river of molten rock. No.</>"}.get(name, "<grey>You can't go that way.</>"))
            return
        p.pos = [x, y]
        p.steps += 1
        p.since_enc += 1
        mins = int(cost * 15 * (1.4 if dx and dy else 1.0))
        self.advance_time(mins)
        self.explored.reveal(x, y, self.vision_radius())
        if p.steps % 5 == 0:
            p.restore_mp(1)
        if not p.hungry:
            if p.regen and p.steps % 6 == 0:
                p.heal(p.regen)
            if p.steps % 25 == 0:
                p.heal(1 + p.level // 6)
        if b == SHALLOW and self.rng.random() < 0.08:
            self.msg("<ice>Cold water soaks your boots.</>")
        f = wd.feature_at(x, y)
        if f:
            self.mark_known(f)
            self.here = f
            self.msg(f"<gold>You arrive at {esc(f.name)}</> <dim>({f.label})</>")
            self.enter_feature(f, prompt=True)
            return
        if p.steps % 37 == 0 and self.rng.random() < 0.7:
            grp = group if group in WHISPERS else "plains"
            self.msg("<dim><i>" + self.rng.choice(NIGHT_WHISPERS if (self.is_night() and self.rng.random() < 0.6) else WHISPERS[grp]) + "</></>")
        if p.hp < p.max_hp * 0.25 and p.steps % 12 == 0:
            self.msg("<red>You are badly hurt. Consider resting (R).</>")
        self.encounter_check(enc)

    def encounter_check(self, mult):
        p, wd = self.p, self.world
        if mult <= 0:
            return
        near = wd.features_near(p.pos[0], p.pos[1], 5, SETTLEMENTS)
        base = 0.022 + 0.003 * p.since_enc
        if self.is_night():
            base *= 1.6
        if near:
            base *= 0.2
        if self.rng.random() < min(0.22, base * mult):
            p.since_enc = 0
            self.encounter()

    def encounter(self):
        p, wd = self.p, self.world
        x, y = p.pos
        lvl = wd.level_at(x, y)
        b = wd.biome(x, y)
        group = BIOMES[b][1]
        night = self.is_night()
        r = self.rng.random()
        ctx = dict(group=group, night=night, level=lvl)
        self.ctx_level = lvl
        if r < 0.66:
            key = GROUP_KEY.get(group, "plains")
            enemies = spawn_group(self.rng, lvl, key)
            ambush = self.rng.random() < (0.35 if night else 0.2)
            if ambush:
                pb = p.skill_bonus("Perception")
                if self.rng.randint(1, 20) + pb >= 12 + lvl // 4:
                    ambush = False
                    self.msg("<green>Your instincts prickle. You spot the ambush in time!</>")
            self.fight(enemies, ambush=ambush, title=f"{BIOMES[b][0]} — {'Night ' if night else ''}Encounter")
        else:
            events.random_event(self, ctx)
        self.flush_xp()

    # ═══════════════════════════ features ═══════════════════════════
    def enter_feature(self, f, prompt=False):
        p = self.p
        if prompt:
            self.draw_scene(self.draw_ow_map, side=self.ow_side())
            i = self.ui.menu(f"{f.label}", [f"Enter <gold>{esc(f.name)}</>", "Not now"], numbered=False, dim=False,
                             at=None, subtitle=f"Level {f.level} region" if not f.is_settlement else None)
            if i != 0:
                return
        k = f.kind
        self.ctx_level = max(1, f.level)
        if f.is_settlement:
            Town(self, f).run()
        elif k == "inn":
            events.enter_inn(self, f)
        elif k == "shrine":
            events.enter_shrine(self, f)
        elif k == "camp":
            events.enter_camp(self, f)
        else:
            self.enter_dungeon(f)
        self.quest_event("visit", f)
        self.flush_xp()

    def enter_dungeon(self, f):
        p = self.p
        st = self.fstate.setdefault(f.key, {})
        cd = st.get("cleared_day")
        if cd and self.day - cd >= 6:
            st["resets"] = st.get("resets", 0) + 1
            st.pop("cleared_day", None)
            cd = None
        art_key = f.kind if f.kind in SCENES else "cave"
        s = Story(self.ui, esc(f.name), art=self.scene(art_key), art_color=PAL[{"cave": "brown", "ruins": "silver", "crypt": "purple", "tower": "cyan", "lair": "red"}.get(f.kind, "grey")],
                  color=PAL["edge"], subtitle=f"{f.label} · level {f.level}")
        if cd:
            s.say("<grey>The halls are silent; what lived here is dead. But you can still explore them.</>")
        else:
            s.say({"cave": "A yawning mouth in the hillside breathes cold, damp air. Bones lie scattered in the entrance.",
                   "ruins": "Broken arches and half-fallen halls. Ivy chokes the stone. Something moves in the shadows between the pillars.",
                   "crypt": "A stone door, ajar, and steps descending into deep cold. Old, dry air rolls out.",
                   "tower": "A crooked tower of black stone, windows lit from within by a light that isn't fire.",
                   "lair": "The air shimmers with heat. Melted rock, gnawed bones, and a smell like a struck match. Something enormous breathes below."}[f.kind])
            if f.kind == "lair":
                tid, dname = dragon_of(f)
                s.say(f"<red>{esc(dname)}</> <dim>sleeps within. Suggested level: {max(9, f.level + 3)}+</>")
            need = max(9, f.level + 3) if f.kind == "lair" else f.level
            if need > p.level + 3:
                s.say(f"<b><red>Every instinct screams that this place is far beyond your strength (level {need}+ recommended).</></>")
        i = s.ask(["Enter", "Turn back"])
        s.close()
        if i != 0:
            return
        d = Dungeon(self, f, max(1, f.level))
        self.dungeon_ref = d
        self.ui.dissolve()
        d.run()
        self.dungeon = None
        self.autosave()

    # ═══════════════════════════ camping ═══════════════════════════
    def camp(self):
        p = self.p
        b = self.world.biome(*p.pos)
        lvl = self.world.level_at(*p.pos)
        f = self.world.feature_at(*p.pos)
        opts = [("Make camp and sleep until morning", True, "8 hours"),
                ("Short rest", True, "1 hour · heal 30%"),
                ("Forage for supplies (Survival)", True, "2 hours"),
                ("Cancel", True, "")]
        i = self.ui.menu("Make Camp", opts, width=54, subtitle=f"{'<red>Hungry! </>' if p.hungry else ''}<dim>{p.hp}/{p.max_hp} HP · {p.food} rations</>")
        if i is None or i == 3:
            return
        self.ctx_level = lvl
        st = Story(self.ui, "Camp", art=self.scene("camp"), art_color=PAL["amber"], color=PAL["amber"])
        group = BIOMES[b][1]
        if i == 1:
            self.advance_time(60)
            h = p.heal(p.max_hp * 0.3)
            m = p.restore_mp(p.max_mp * 0.5)
            st.say(f"You rest for an hour. <green>+{h} HP</>, <cyan>+{m} {p.c['resource']}</>.")
            st.pause()
            st.close()
            self.encounter_check(0.7)
            return
        if i == 2:
            self.advance_time(120)
            st.say("You spend two hours scouring the land for anything edible.")
            bonus = p.skill_bonus("Survival") + (1 if p.blessed_until > p.minutes else 0)
            ok, nat, tot = st.check("Survival", bonus, 10 + lvl // 3, self.rng)
            if ok:
                n = self.rng.randint(1, 3) + (2 if nat == 20 else 0)
                p.food += n
                st.say(f"<green>You gather {n} ration{'s' if n > 1 else ''} worth of food.</>")
                if self.rng.random() < 0.25:
                    it = gen_potion(self.rng, lvl, self.rng.choice(["heal1", "antidote"]))
                    st.say(f"You also find {name_item(it)}.")
                    if not self.give_item(it):
                        st.say("<grey>No room for it — you leave it behind.</>")
            else:
                st.say("<grey>Slim pickings. Berries that might kill you, and you wisely leave them.</>")
            st.pause()
            st.close()
            self.encounter_check(0.8)
            return
        # long rest
        if p.hungry:
            st.say("<amber>Hunger gnaws at you. With nothing to eat, sleep won't heal you fully.</>")
        night = self.is_night()
        day, h, m = self.clock()
        hours = (7 - h) % 24
        if hours < 6:
            hours += 24 if hours < 4 else 0
        hours = max(6, min(12, hours or 8))
        risk = 0.08 + 0.03 * max(0, lvl - p.level) + (0.1 if night else 0.04)
        if self.world.feature_at(*p.pos) or self.world.features_near(p.pos[0], p.pos[1], 4, SETTLEMENTS):
            risk *= 0.3
        st.say(f"You build a small fire, eat, and settle in. <dim>({hours} hours)</>")
        self.ui.fade_out()
        self.advance_time(hours * 60, resting=True)
        if self.rng.random() < risk:
            pb = p.skill_bonus("Perception")
            ok, _, _ = st.check("Perception (waking)", pb, 11 + lvl // 4, self.rng)
            st.say("<red>Something is creeping toward your camp!</>")
            st.pause()
            st.close()
            self.msg("<red>Your rest is interrupted!</>")
            enemies = spawn_group(self.rng, lvl, GROUP_KEY.get(group, "plains"))
            self.fight(enemies, ambush=not ok, title="Night Attack")
            if p.hp > 0:
                p.hp = max(p.hp, p.max_hp // 2)
            return
        hp = p.max_hp if not p.hungry else p.max_hp // 2 + p.hp // 2
        p.hp = max(p.hp, hp)
        p.mp = p.max_mp
        st.say("<green>You wake refreshed. Morning light on your face.</>")
        r = self.rng.random()
        if r < 0.2:
            st.say(f"<dim><i>{self.rng.choice(['You dream of a great red wing, blotting out the moon.', 'You dream of a door with no house behind it.', 'You dream of a road that never ends. You wake, and it is still there.'])}</></>")
        elif r < 0.3:
            lairs = self.world.features_near(p.pos[0], p.pos[1], 100, ("lair",))
            if lairs:
                l = min(lairs, key=lambda f: math.hypot(f.x - p.pos[0], f.y - p.pos[1]))
                self.mark_known(l)
                st.say(f"<purple>You dream of fire under stone, {dir_name(l.x - p.pos[0], l.y - p.pos[1])} of here. [marked on your map]</>")
        st.pause()
        st.close()
        self.autosave()

    # ═══════════════════════════ combat wrapper ═══════════════════════════
    def fight(self, enemies, ambush=False, title="Battle", boss=False, dungeon=False, can_flee=True, combat=None, ctx=None):
        p = self.p
        c = combat or Combat(self, enemies, ambush=ambush, can_flee=can_flee, title=title, boss=boss)
        if ctx:
            c.ctx = ctx
        if not combat and p.blessed_until > p.minutes:
            c.p_add("bless", 4)
        self.active_combat = c          # stays set if we are interrupted (quit / hangup) so the save can resume it
        res = c.run(resume=bool(combat))
        self.active_combat = None
        enemies = c.enemies
        self.advance_time(8 + 3 * len(enemies))
        if res == "gone":
            self.msg("<amber>Your foe slipped away into the wild, and with it any hope of loot.</>")
            return "win"
        if res == "win":
            self.victory(c)
            return "win"
        if res == "flee":
            self.msg("<amber>You escape by the skin of your teeth.</>")
            return "flee"
        raise Died("slain in battle")

    def on_kill(self, e):
        p = self.p
        p.kills[e.tid] = p.kills.get(e.tid, 0) + 1
        if e.tid.startswith("dragon"):
            p.dragons += 1
            p.stat_points += 2
            self.chronicle(f"Slew {e.name}, a {e.level}-level dragon!")
            self.msg(f"<b><gold>Dragon Mark earned! +2 stat points. Dragons slain: {p.dragons}</></>")
        elif e.boss or e.elite:
            self.chronicle(f"Defeated {e.name}.")
        for q in p.quests:
            if q["type"] == "hunt" and q["state"] == "active" and q.get("tid") == e.tid:
                q["progress"] += 1
                if q["progress"] >= q["goal"]:
                    q["state"] = "ready"
                    self.msg(f"<green>Quest ready to turn in: {esc(q['title'])}</>")
                else:
                    self.msg(f"<dim>Bounty: {q['progress']}/{q['goal']}</>")

    def victory(self, c):
        p = self.p
        rng = self.rng
        xp = sum(e.xp for e in c.defeated)
        gold = sum(e.gold for e in c.defeated)
        items = []
        boss = any(e.boss for e in c.defeated)
        for e in c.defeated:
            lvl = e.level
            if e.boss:
                for _ in range(2):
                    items.append(gen_any(rng, lvl, rarity=None if rng.random() > 0.5 else 3, kinds=[("weapon", 3), ("armor", 3), ("shield", 1), ("jewelry", 3)]))
                items.append(gen_relic(rng, lvl))
                items.append(gen_gem(rng, lvl))
            elif e.elite:
                items.append(gen_any(rng, lvl + 1, rarity=None))
            elif rng.random() < 0.24:
                items.append(gen_any(rng, lvl))
            elif rng.random() < 0.15:
                items.append(gen_potion(rng, lvl))
            if "beast" in e.tags and rng.random() < 0.25:
                p.food += 1
                self.msg("<dim>You harvest some meat. +1 ration.</>")
        p.gold += gold
        st = Story(self.ui, "Victory!", color=PAL["gold"], art=None)
        names = ", ".join(sorted({strip(e.name) for e in c.defeated}))
        st.say(f"<b><gold>★ Victory! ★</></>  <dim>{esc(names)} defeated.</>")
        st.line(f"<cyan>+{xp} XP</>   <gold>+{gold} gold</>" + (f"   <dim>(a thief got away with {sum(c.fled_with)}g)</>" if c.fled_with else ""))
        for it in items:
            st.line(f"<green>Loot:</> {name_item(it)}")
            st.draw(); self.ui.flush()          # line() doesn't paint on its own — force it before give_item()
            if not self.give_item(it):
                st.line("<grey>  ...no room for it — left behind.</>")
        lv = self.gain_xp(xp, story=st)
        st.pause()
        st.close()
        if p.stat_points:
            self.spend_stat_points()

    def gain_xp(self, n, story=None):
        p = self.p
        old = p.level
        old_ab = {a["id"] for a in p.abilities}
        gained = p.gain_xp(n)
        if gained:
            self.chronicle(f"Reached level {p.level}.")
            self.ui.flash(PAL["gold"], 0.55, 3)
            lines = [f"<b><gold>★ LEVEL UP! ★</>  You are now level {p.level} — {p.title}.</>"]
            for a in p.abilities:
                if a["id"] not in old_ab:
                    lines.append(f"<cyan>New {p.c['name']} art learned:</> <b>{a['name']}</> <dim>— {a['desc']}</>")
            if p.stat_points:
                lines.append(f"<green>{p.stat_points} stat point(s) to spend.</>")
            if story:
                for ln in lines:
                    story.line(ln)
            else:
                s = Story(self.ui, "Level Up!", color=PAL["gold"])
                for ln in lines:
                    s.say(ln)
                s.pause()
                s.close()
                if p.stat_points:
                    self.spend_stat_points()
        return gained

    def spend_stat_points(self):
        p = self.p
        while p.stat_points > 0:
            items = []
            for st in STATS:
                items.append((f"{STAT_NAMES[st]:<14} {p.stats[st]:>2} → <green>{p.stats[st] + 1}</>  <dim>(mod {sign(mod(p.stats[st]))} → {sign(mod(p.stats[st] + 1))})</>", p.stats[st] < 30))
            i = self.ui.menu(f"Spend a stat point ({p.stat_points} left)", items, width=60, numbered=True,
                             subtitle=f"<dim>Favoured by your class: {', '.join(p.c['prio'][:2])}</>")
            if i is None:
                return
            p.stats[STATS[i]] += 1
            p.stat_points -= 1
            p.clamp()

    # ═══════════════════════════ death ═══════════════════════════
    def handle_death(self, cause=""):
        """Returns True if the game session should end (return to title)."""
        p = self.p
        self.ui.flash(PAL["blood"], 0.8, 4)
        p.deaths += 1
        self.chronicle(f"Fell in battle ({cause}).")
        if p.hardcore:
            return self.hardcore_death()
        s = Story(self.ui, "Thou Hast Fallen", color=PAL["blood"], art=self.scene("skull"), art_color=PAL["red"])
        s.say("<dim>The world goes cold and quiet. Somewhere far away, a bell tolls once…</>")
        lost = p.gold // 4
        p.gold -= lost
        p.hp = max(1, p.max_hp // 2)
        p.mp = p.max_mp
        self.advance_time(480)
        town = p.last_town or dict(name="Hearthmoor", x=START[0] - 2, y=START[1] - 2)
        p.pos = [town["x"], town["y"]]
        self.explored.reveal(town["x"], town["y"], 8)
        s.say(f"A passing pilgrim finds you and drags you, groaning, to <white>{esc(town['name'])}</>. You lose <gold>{lost}</> gold to the healers, and the day.")
        s.say("<green>You wake with half your health and a fine new scar.</>")
        s.pause()
        s.close()
        self.msg("<red>You were carried back to safety.</>")
        self.autosave()
        return False

    def hardcore_death(self):
        p = self.p
        self.save_hof("Fell in battle")
        if self.slot:
            try:
                os.remove(self.save_path(self.slot))
            except OSError:
                pass
        s = Story(self.ui, "Here Lies " + esc(p.name), color=PAL["blood"], art=self.scene("crypt"), art_color=PAL["dim"])
        s.say(f"<b>{esc(p.name)}</>, level {p.level} {p.c['name']}, {p.title}.")
        s.say(f"<dim>Walked {p.steps} steps. Slew {sum(p.kills.values())} foes{', including ' + str(p.dragons) + ' dragon(s)' if p.dragons else ''}. Reached day {self.day}.</>")
        s.say("<grey>The road goes on without them. It always does.</>")
        s.pause()
        s.close()
        return True

    # ═══════════════════════════ quests ═══════════════════════════
    def quest_event(self, kind, f):
        p = self.p
        for q in p.quests:
            if q["state"] != "active":
                continue
            if kind == "cleared" and q["type"] in ("slay", "clear", "dragon") and q["target_key"] == f.key:
                q["state"] = "ready"
                self.msg(f"<b><green>Quest complete: {esc(q['title'])}. Return to {esc(q['giver'])}!</></>")
            elif kind == "artifact" and q["type"] == "retrieve" and q["target_key"] == f.key:
                q["state"] = "ready"
                self.msg(f"<b><green>Quest complete: {esc(q['title'])}. Return to {esc(q['giver'])}!</></>")
            elif kind == "arrive" and q["type"] == "deliver" and q["target_key"] == f.key:
                self.turn_in(q, delivered=True)

    def turn_in(self, q, delivered=False):
        p = self.p
        r = q["reward"]
        st = Story(self.ui, "Quest Complete", color=PAL["gold"])
        if delivered:
            st.say(f"You hand over the sealed letter at {esc(q['target_name'])}. The recipient reads it, pales, and pays you at once.")
        else:
            st.say(f"{esc(q['npc'])} beams as you report your success: <white>{esc(q['title'])}</>.")
        p.gold += r["gold"]
        st.line(f"<gold>+{r['gold']} gold</>   <cyan>+{r['xp']} XP</>")
        if r.get("item"):
            st.line(f"<green>Reward:</> {name_item(r['item'])}")
            st.draw(); self.ui.flush()          # line() doesn't paint on its own — force it before give_item()
            if not self.give_item(r["item"]):
                st.line("<grey>  ...no room for it — left behind.</>")
        p.rep += 2
        p.quests.remove(q)
        p.flags["quests_done"] = p.flags.get("quests_done", 0) + 1
        self.chronicle(f"Completed: {q['title']}.")
        self.gain_xp(r["xp"], story=st)
        st.pause()
        st.close()
        if p.stat_points:
            self.spend_stat_points()

    # ═══════════════════════════ inventory ═══════════════════════════
    def inventory(self):
        p, ui = self.p, self.ui
        sel = 0
        while True:
            entries = [("eq", sl, p.eq[sl]) for sl in SLOTS] + [("inv", None, it) for it in p.inv]
            sel = max(0, min(sel, len(entries) - 1))
            s = ui.frame("Pack & Equipment", hints([("↑↓", "Browse"), ("Enter", "Actions"), ("E", "Equip/Use"), ("D", "Drop"), ("Esc", "Close")]))
            W, H = s.w, s.h
            lw = min(52, W // 2 + 4)
            s.box(1, 1, lw, H - 3, "single", PAL["edge2"], PAL["panel"], f"Items {len(p.inv)}/{INV_LIMIT}")
            rows = H - 5
            top = max(0, min(sel - rows // 2, len(entries) - rows))
            for i in range(rows):
                j = top + i
                if j >= len(entries):
                    break
                kind, slot, it = entries[j]
                cur = j == sel
                bgc = PAL["panel2"] if cur else PAL["panel"]
                s.fill(2, 2 + i, lw - 2, 1, " ", None, bgc)
                s.put(3, 2 + i, "▸" if cur else " ", PAL["gold"], bgc)
                if kind == "eq":
                    lab = f"<dim>{slot.capitalize():<7}</> " + (name_item(it) if it else "<dim>— empty —</>")
                    s.puts(5, 2 + i, lab, None, bgc, maxw=lw - 6)
                else:
                    q = f" <dim>x{it['q']}</>" if it.get("q", 1) > 1 else ""
                    if j == len(SLOTS):
                        s.hline(2, 2 + i - 0, 0)
                    s.puts(5, 2 + i, name_item(it) + q, None, bgc, maxw=lw - 6)
            dx = lw + 2
            s.box(dx, 1, W - dx - 1, H - 3, "single", PAL["edge2"], PAL["panel"], "Details")
            kind, slot, it = entries[sel]
            if it:
                lines = []
                for ln in describe(it):
                    lines.extend(wrap(ln, W - dx - 5))
                if kind == "inv":
                    lines.append("")
                    lines.extend(compare_lines(p, it))
                for i, ln in enumerate(lines[:H - 6]):
                    s.puts(dx + 2, 2 + i, ln, PAL["white"], PAL["panel"])
            s.puts(dx + 2, H - 4, f"<gold>{p.gold}</> gold  <dim>·</> AC <b>{p.ac}</> <dim>·</> HP <b>{p.hp}/{p.max_hp}</>", PAL["white"], PAL["panel"])
            ui.flush()
            k = ui.key()
            if k in ("esc", "i", "q"):
                return
            elif k in ("up", "k", "w"):
                sel = (sel - 1) % len(entries)
            elif k in ("down", "j", "s"):
                sel = (sel + 1) % len(entries)
            elif k == "pgup":
                sel = max(0, sel - 8)
            elif k == "pgdn":
                sel = min(len(entries) - 1, sel + 8)
            elif k in ("enter", "space", "e", "d"):
                if not it:
                    continue
                if k == "d" and kind == "inv":
                    self.drop_item(it)
                elif kind == "eq":
                    r = ui.menu(strip(it["n"]), ["Unequip"], numbered=False)
                    if r == 0 and not p.unequip(slot):
                        self.msg("<red>Your pack is full.</>")
                else:
                    self.item_actions(it)

    def item_actions(self, it):
        p, ui = self.p, self.ui
        opts = []
        if p.slot_of(it):
            opts.append("Equip")
        if it["k"] in ("potion", "scroll"):
            opts.append("Use")
        opts += ["Drop", "Cancel"]
        i = ui.menu(strip(it["n"]), opts, numbered=False)
        if i is None:
            return
        a = opts[i]
        if a == "Equip":
            notes = p.equip(it)
            for n in notes:
                self.msg(f"<dim>{esc(n)}</>")
            self.msg(f"<green>Equipped {esc(it['n'])}.</>")
        elif a == "Use":
            self.use_field_item(it)
        elif a == "Drop":
            self.drop_item(it)

    def drop_item(self, it):
        if self.ui.confirm(f"Drop {esc(it['n'])}?", False, "Drop"):
            self.p.inv.remove(it)
            self.msg(f"<dim>You drop {esc(it['n'])}.</>")

    def give_item(self, it):
        """Add an item to the pack. If it's full, offer to free a slot for it instead of losing it.
        Returns True if the item ends up in the pack, False if it was left behind after all."""
        p = self.p
        if p.add_item(it):
            return True
        if not p.inv:                     # shouldn't happen (pack is "full" but empty) — nothing to free
            return False
        if not self.ui.confirm(f"Your pack is full. Drop something to make room for {name_item(it)}?",
                               True, "Pack full"):
            return False
        if self.free_up_space(it) is None:
            return False
        return p.add_item(it)

    def free_up_space(self, for_item=None):
        """Wizard: pick one item from the pack to leave behind. Returns the dropped item, or None if cancelled."""
        p, ui = self.p, self.ui
        items = list(p.inv)
        rows = []
        for x in items:
            q = f" <dim>x{x['q']}</>" if x.get("q", 1) > 1 else ""
            rows.append((name_item(x) + q, True))
        subtitle = f"Choose one item to leave behind" + (f", making room for {name_item(for_item)}" if for_item else "") + "."
        i = ui.menu("Free Up Space", rows, width=60, subtitle=subtitle,
                   detail=lambda i: "\n".join(describe(items[i])))
        if i is None:
            return None
        chosen = items[i]
        p.inv.remove(chosen)
        q = chosen.get("q", 1)
        self.msg(f"<dim>You leave behind {name_item(chosen)}" + (f" (all {q})" if q > 1 else "") + " to make room.</>")
        return chosen

    def use_field_item(self, it):
        p = self.p
        fx = it["fx"]
        ok = True
        if fx == "heal":
            if p.hp >= p.max_hp:
                self.ui.message("Pack", "You're already at full health.")
                return
            self.msg(f"<green>You drink {esc(it['n'])}: +{p.heal(p.max_hp * it['mag'])} HP.</>")
        elif fx == "mana":
            self.msg(f"<cyan>You drink {esc(it['n'])}: +{p.restore_mp(p.max_mp * it['mag'])} {p.c['resource']}.</>")
        elif fx == "cure":
            self.msg("<green>You feel cleansed.</>")
        elif fx == "reveal":
            self.explored.reveal(p.pos[0], p.pos[1], 22)
            self.msg("<cyan>The scroll unfolds a vision of the land around you.</>")
        elif fx == "recall":
            t = p.last_town
            if not t:
                self.ui.message("Pack", "You haven't visited a town yet.")
                return
            p.pos = [t["x"], t["y"]]
            self.advance_time(60)
            self.explored.reveal(t["x"], t["y"], 8)
            self.msg(f"<cyan>The world folds. You stand at {esc(t['name'])}.</>")
        elif fx == "mend":
            self.msg(f"<green>Warm light: +{p.heal(p.max_hp * 0.5)} HP.</>")
        else:
            self.ui.message("Pack", "That's best saved for battle.")
            return
        p.remove_one(it)

    # ═══════════════════════════ character sheet ═══════════════════════════
    def character_sheet(self):
        p, ui = self.p, self.ui
        while True:
            s = ui.frame(f"{esc(p.name)} — {p.c['name']}", hints(([("Enter", "Spend stat points")] if p.stat_points else []) + [("Esc", "Close")]))
            W, H = s.w, s.h
            lw = 44
            s.box(1, 1, lw, H - 3, "single", PAL["edge2"], PAL["panel"], "Attributes")
            y = 2
            s.puts(3, y, f"<{p.c['color']}>Level {p.level} {p.c['name']}</> <dim>·</> {ORIGINS[p.origin]['name']}", PAL["white"], PAL["panel"]); y += 1
            s.puts(3, y, f"<i><dim>{p.title}</></> <dim>·</> {p.c['tag']}", PAL["white"], PAL["panel"]); y += 1
            bar(s, 3, y, lw - 6, p.xp, xp_needed(p.level), PAL["violet"], label=f"XP {p.xp}/{xp_needed(p.level)}"); y += 2
            for st in STATS:
                v = p.stat(st)
                base = p.stats[st]
                extra = f" <cyan>({sign(v - base)} gear)</>" if v != base else ""
                pr = "<gold>★</>" if st in p.c["prio"][:2] else " "
                s.puts(3, y, f"{pr}<b>{STAT_NAMES[st]:<13}</> <b><white>{v:>2}</></>  <dim>mod</> <b>{sign(mod(v))}</>{extra}", PAL["white"], PAL["panel"])
                bar(s, 32, y, lw - 33, v, 30, PAL["gold"] if st in p.c["prio"][:2] else PAL["dim"])
                y += 1
            y += 1
            n, sd = p.dice
            rows = [("Hit Points", f"{p.hp}/{p.max_hp}"), (p.c["resource"], f"{p.mp}/{p.max_mp}"), ("Armor Class", p.ac),
                    ("Attack bonus", sign(p.atk_bonus)), ("Weapon damage", f"{n}d{sd}{sign(p.dmg_flat)}"),
                    ("Attacks / round", p.attacks), ("Proficiency", sign(p.prof)), ("Gold", p.gold),
                    ("Rations", p.food), ("Hunger", "<red>HUNGRY</>" if p.hungry else f"<green>fed for {self.fed_hours()}h</>"), ("Reputation", p.rep)]
            for lab, val in rows:
                if y < H - 3:
                    s.puts(3, y, f"<dim>{lab:<16}</><b>{val}</>", PAL["white"], PAL["panel"])
                    y += 1
            if y < H - 8:
                y += 1
                s.hline(2, y, lw - 2, "─", PAL["edge2"], PAL["panel"])
                for sl in SLOTS:
                    y += 1
                    it = p.eq[sl]
                    if y < H - 3:
                        s.puts(3, y, f"<dim>{sl.capitalize():<7}</> " + (name_item(it) if it else "<dim>—</>"), PAL["white"], PAL["panel"], maxw=lw - 5)
            rx = lw + 2
            s.box(rx, 1, W - rx - 1, H - 3, "single", PAL["edge2"], PAL["panel"], f"{p.c['resource']} arts & skills")
            abilities = p.c["abilities"]
            skills = sorted(set(p.c["skills"] + [ORIGINS[p.origin]["skill"]]))
            avail = W - rx - 4                      # usable columns at x = rx+2, up to the box's right border
            entry_w = max(len(sk) for sk in skills) + 5      # "Name  " + "+NN" (sign(...) is at most 3 chars)
            cols = 2 if avail >= entry_w * 2 + 1 else 1
            colw = entry_w + 1 if cols == 2 else avail       # stride between columns; +1 keeps a gap between them
            skill_rows = -(-len(skills) // cols)    # ceil
            reserve = 3 + skill_rows                # blank + rule + header + one row per skill line
            max_ability_y = H - 3 - reserve         # last row abilities may use before the skills block starts
            # full (2-row, with description) only fits if every unlocked ability gets its own description line too
            full_rows_needed = 2 + sum(2 if a["lv"] <= p.level else 1 for a in abilities)
            compact = full_rows_needed > max_ability_y - 1
            y = 2
            for a in abilities:
                if y > max_ability_y:
                    break
                un = a["lv"] <= p.level
                col = "gold" if un else "dim"
                # unlocked: show its cost (you already know when you got it); locked: show the level it unlocks at instead
                right = f"{a['cost']:>2} {p.c['resource']}" if un else f"Lv {a['lv']}"
                s.puts(rx + 2, y, f"<{col}>{'◆' if un else '◇'} {a['name']:<18}</> <dim>{right}</>", PAL["white"], PAL["panel"], maxw=W - rx - 5)
                if un and not compact:
                    s.puts(rx + 4, y + 1, f"<grey>{a['desc']}</>", PAL["white"], PAL["panel"], maxw=W - rx - 7)
                    y += 2
                else:
                    y += 1
            sy = max(y + 1, H - 3 - reserve)
            if sy < H - 4:
                s.hline(rx + 1, sy, W - rx - 3, "─", PAL["edge2"], PAL["panel"])
                s.puts(rx + 2, sy + 1, "<dim>Skills (proficient):</>", PAL["white"], PAL["panel"])
                for i, sk in enumerate(skills):
                    yy = sy + 2 + i // cols
                    if yy > H - 4:                   # would land on or past the box's own bottom border
                        break
                    x = rx + 2 + (i % cols) * colw
                    s.puts(x, yy, f"<white>{sk:<{entry_w - 4}}</> <gold>{sign(p.skill_bonus(sk)):>3}</>", PAL["white"], PAL["panel"], maxw=min(entry_w, avail))
            # equipment summary under the left panel stats
            eq_y = y if y < H - 8 else H - 8
            ui.flush()
            k = ui.key()
            if k in ("esc", "c", "q", "i"):
                return
            if k in ("enter", "+", "space") and p.stat_points:
                self.spend_stat_points()

    # ═══════════════════════════ journal ═══════════════════════════
    def journal(self):
        p, ui = self.p, self.ui
        tab, sel = 0, 0
        tabs = ["Quests", "Chronicle", "Bestiary"]
        while True:
            s = ui.frame("Journal", hints([("←→", "Tab"), ("↑↓", "Browse"), ("T", "Track quest"), ("X", "Abandon"), ("Esc", "Close")]))
            W, H = s.w, s.h
            x = 3
            for i, t in enumerate(tabs):
                on = i == tab
                s.put(x, 1, f" {t} ", PAL["bg"] if on else PAL["grey"], PAL["gold"] if on else PAL["panel"], A_BOLD if on else 0)
                x += len(t) + 4
            if tab == 0:
                qs = [q for q in p.quests if q["state"] != "done"]
                lw = 34
                s.box(1, 2, lw, H - 4, "single", PAL["edge2"], PAL["panel"], "Active")
                sel = min(sel, max(0, len(qs) - 1))
                if not qs:
                    s.puts(3, 4, "<dim>No quests yet. Find a notice</>", PAL["white"], PAL["panel"])
                    s.puts(3, 5, "<dim>board in any village or town.</>", PAL["white"], PAL["panel"])
                for i, q in enumerate(qs):
                    cur = i == sel
                    bgc = PAL["panel2"] if cur else PAL["panel"]
                    s.fill(2, 3 + i, lw - 2, 1, " ", None, bgc)
                    mk = {"active": "<amber>▸</>", "ready": "<green>✓</>"}[q["state"]]
                    tr = "<cyan>◎</>" if q["id"] == self.track else " "
                    s.puts(3, 3 + i, f"{mk}{tr}{esc(q['title'])}", PAL["white"], bgc, maxw=lw - 5)
                s.box(lw + 2, 2, W - lw - 3, H - 4, "single", PAL["edge2"], PAL["panel"], "Details")
                if qs:
                    y = 3
                    for ln in describe_quest(qs[sel], p.pos):
                        for wl in wrap(ln, W - lw - 8):
                            s.puts(lw + 4, y, wl, PAL["white"], PAL["panel"])
                            y += 1
            elif tab == 1:
                lines = list(reversed(p.deeds)) or ["<dim>Your story has yet to begin.</>"]
                s.box(1, 2, W - 2, H - 4, "single", PAL["edge2"], PAL["panel"], "Chronicle of deeds")
                rows = H - 6
                sel = max(0, min(sel, max(0, len(lines) - rows)))
                for i in range(rows):
                    if sel + i < len(lines):
                        s.puts(3, 3 + i, esc(lines[sel + i]) if not lines[sel + i].startswith("<") else lines[sel + i], PAL["white"], PAL["panel"], maxw=W - 6)
            else:
                ks = sorted(p.kills.items(), key=lambda kv: -kv[1])
                s.box(1, 2, W - 2, H - 4, "single", PAL["edge2"], PAL["panel"], f"Bestiary — {sum(p.kills.values())} slain")
                rows = (H - 6)
                cols = 2 if W > 90 else 1
                sel = max(0, min(sel, max(0, len(ks) - rows * cols)))
                for i, (tid, n) in enumerate(ks[sel:sel + rows * cols]):
                    t = MONSTERS[tid]
                    cx = 3 + (i // rows) * ((W - 4) // cols)
                    s.puts(cx, 3 + i % rows, f"<{t['color']}>{t['name']:<22}</> <b>{n:>4}</>  <dim>{', '.join(t['tags'])}</>", PAL["white"], PAL["panel"])
                if not ks:
                    s.puts(3, 3, "<dim>Nothing slain yet.</>", PAL["white"], PAL["panel"])
            ui.flush()
            k = ui.key()
            if k in ("esc", "q"):
                return
            elif k in ("left", "h"):
                tab, sel = (tab - 1) % 3, 0
            elif k in ("right", "l", "tab"):
                tab, sel = (tab + 1) % 3, 0
            elif k in ("up", "k", "w"):
                sel = max(0, sel - 1)
            elif k in ("down", "j", "s"):
                sel += 1
            elif k == "t" and tab == 0:
                qs = [q for q in p.quests if q["state"] != "done"]
                if qs:
                    self.track = qs[min(sel, len(qs) - 1)]["id"]
            elif k == "x" and tab == 0:
                qs = [q for q in p.quests if q["state"] != "done"]
                if qs and ui.confirm("Abandon this quest?", False, "Journal"):
                    p.quests.remove(qs[min(sel, len(qs) - 1)])

    # ═══════════════════════════ world map ═══════════════════════════
    def known_places(self):
        """Marked places (rumours, elders, visions) sorted by distance from the hero."""
        p = self.p
        out = []
        for k in self.markers:
            x, y = map(int, k.split(","))
            f = self.world.feature_at(x, y)
            if f and (x, y) != tuple(p.pos):
                out.append((math.hypot(x - p.pos[0], y - p.pos[1]), f))
        out.sort(key=lambda t: t[0])
        return [f for _, f in out]

    def world_map(self):
        p, wd, ui = self.p, self.world, self.ui
        z = 1
        cx, cy = p.pos
        blink = 0
        places = self.known_places()
        sel = -1
        while True:
            s = ui.frame("World map", hints([("Arrows", "Pan"), ("+/-", "Zoom"), ("Tab", "Next marked place"), ("P", "Me"), ("Esc", "Close")]))
            W, H = s.w, s.h
            mw, mh = (W - 4) // 2, H - 6
            ox, oy = cx - (mw // 2) * z, cy - (mh // 2) * z
            for j in range(mh):
                for i in range(mw):
                    x0, y0 = ox + i * z, oy + j * z
                    if z == 1:
                        seen = self.explored.seen(x0, y0)
                    else:
                        seen = any(self.explored.seen(x0 + a, y0 + b) for a in range(z) for b in range(z))
                    if not seen:
                        continue
                    g, fg, bg = wd.vis(x0 + z // 2, y0 + z // 2)
                    s.put(2 + i * 2, 2 + j, g if z == 1 else ("▒▒" if z == 2 else "░░"), fg, scale(bg, 0.85) if z == 1 else bg)
            for cyy in range(oy // CHUNK - 1, (oy + mh * z) // CHUNK + 2):
                for cxx in range(ox // CHUNK - 1, (ox + mw * z) // CHUNK + 2):
                    f = wd.feature_of(cxx, cyy)
                    if not f:
                        continue
                    marked = f.key in self.markers
                    if not (self.explored.seen(f.x, f.y) or marked):
                        continue
                    i, j = (f.x - ox) // z, (f.y - oy) // z
                    if 0 <= i < mw and 0 <= j < mh:
                        _, _, bg, _ = s.cells[(2 + j) * W + 2 + i * 2]
                        chosen = 0 <= sel < len(places) and places[sel].key == f.key
                        if chosen:
                            s.put(2 + i * 2, 2 + j, f.glyph, PAL["bg"], PAL["gold"] if blink % 2 == 0 else PAL["amber"], A_BOLD)
                        else:
                            s.put(2 + i * 2, 2 + j, f.glyph, f.color, mix(bg, f.color, 0.45 if marked else 0.2), A_BOLD)
                            if marked and i > 0:
                                s.put(2 + i * 2 - 1, 2 + j, "[", PAL["gold"], None)
            i, j = (p.pos[0] - ox) // z, (p.pos[1] - oy) // z
            if 0 <= i < mw and 0 <= j < mh and blink % 2 == 0:
                _, _, bg, _ = s.cells[(2 + j) * W + 2 + i * 2]
                s.put(2 + i * 2, 2 + j, "@ ", PAL["gold"], bg, A_BOLD)
            if 0 <= sel < len(places):
                f = places[sel]
                dx, dy = f.x - p.pos[0], f.y - p.pos[1]
                info = (f"<gold>▸ {esc(f.name)}</> <dim>({f.label}, level {f.level})</>  "
                        f"<cyan>{int(math.hypot(dx, dy))} leagues {dir_name(dx, dy)} {arrow(dx, dy)}</> <dim>[{sel + 1}/{len(places)}]</>")
            else:
                info = f"<dim>{len(places)} marked place{'s' if len(places) != 1 else ''} — press</> <gold>Tab</> <dim>to cycle through them</>"
            s.puts(3, H - 4, info, PAL["white"], PAL["bg"], maxw=W - 6)
            s.puts(3, H - 3, "<gold>⌂</> town  <amber>◘</> inn  <ice>†</> shrine  <purple>‡</> crypt  <silver>▚</> ruins  <brown>∩</> cave  <cyan>╥</> tower  <red>Ω</> lair  <red>Δ</> camp   " +
                   f"<dim>[ marked · zoom 1:{z} · {self.explored.count()} charted</>", PAL["white"], PAL["bg"], maxw=W - 6)
            ui.flush()
            k = ui.key(0.5)
            blink += 1
            if k is None:
                continue
            step = 4 * z
            if k in ("esc", "m", "q"):
                return
            elif k in ("up", "w", "k"): cy -= step
            elif k in ("down", "s", "j"): cy += step
            elif k in ("left", "a", "h"): cx -= step
            elif k in ("right", "d", "l"): cx += step
            elif k in ("+", "="): z = max(1, z // 2 if z > 1 else 1)
            elif k in ("-", "_"): z = min(4, z * 2)
            elif k == "p": cx, cy = p.pos; sel = -1
            elif k in ("tab", "n", "f") and places:
                sel = (sel + 1) % len(places)
                cx, cy = places[sel].x, places[sel].y
            elif k == "btab" and places:
                sel = (sel - 1) % len(places)
                cx, cy = places[sel].x, places[sel].y

    # ═══════════════════════════ help & menus ═══════════════════════════
    def help_screen(self):
        lines = [
            "<gold><b>EMBERROAD — How to play</></>", "",
            "<gold>Moving</>        Arrow keys / WASD / hjkl · diagonals: y u b n · numpad digits",
            "<gold>Enter / E</>     Enter the town, dungeon or shrine you're standing on",
            "<gold>R</>             Make camp (rest, forage). Sleeping in the wild can attract company.",
            "<gold>I</>             Pack & equipment (equip, use, drop) · compare gear at a glance",
            "<gold>C</>             Character sheet · spend stat points (a new one every 2 levels)",
            "<gold>Q</>             Journal: quests, chronicle, bestiary · <gold>T</> tracks a quest",
            "<gold>M</>             World map (zoom with + / -)   <gold>.</> wait & listen",
            "<gold>Esc</>           Game menu (save, settings, retire)", "",
            "<gold>Combat</>        Turn-based, d20 vs Armor Class. <b>A</>ttack · <b>S</>kills · <b>I</>tem · <b>D</>efend · <b>F</>lee",
            "               Crits on a natural 20. Watch for vulnerabilities: fire burns trolls, holy hurts undead.",
            "               Each class has its own resource that regenerates in battle.", "",
            "<gold>The world</>     Endless. The further you roam from home, the more dangerous it gets:",
            "               the sidebar shows the local danger level compared to yours.",
            "               Time passes as you travel: nights are darker and deadlier. A ration feeds you for 24 hours;",
            "               you eat automatically, and with no food you go Hungry (-2 to hit, no healing) until you find some.",
            "               Towns sell gear and supplies, heal you, and post quests on the notice board.",
            "               Dungeons hide loot and bosses. Dragon lairs hold the greatest hoards, and the greatest danger.", "",
            "<gold>Map legend</>   <gold>⌂</> village/town  <gold>♜</> city  <amber>◘</> inn  <ice>†</> shrine  <purple>‡</> crypt  <silver>▚</> ruins",
            "               <brown>∩</> cave  <cyan>╥</> wizard tower  <red>Ω</> dragon lair  <red>Δ</> bandit camp", "",
            "<dim>The road has no end. Good luck out there.</>",
        ]
        self.ui.pager("Help", lines)

    def game_menu(self, in_dungeon=False, in_combat=False):
        while True:
            opts = ["Resume", "Save game", f"Animations: {'On' if self.settings['anim'] else 'Off'}", "Help", "Retire this hero",
                    "Save & return to title"]
            if in_combat:
                opts[4] = "Retire this hero"
            i = self.ui.menu("Game menu", opts, numbered=True)
            if i is None or i == 0:
                return None
            if i == 1:
                if self.save(manual=True):
                    self.msg("<green>Game saved.</>")
                    self.ui.message("Saved", "Your journey is saved.", PAL["green"])
            elif i == 2:
                self.settings["anim"] = not self.settings["anim"]
                self.t.fast = not self.settings["anim"]
            elif i == 3:
                self.help_screen()
            elif i == 4:
                if self.ui.confirm("Retire this hero? Their story ends and enters the Hall of Fame.", False, "Retire"):
                    self.save_hof("Retired")
                    if self.slot:
                        try:
                            os.remove(self.save_path(self.slot))
                        except OSError:
                            pass
                    self.slot = None
                    self.dungeon = None
                    raise RetireHero
            elif i == 5:
                self.save(manual=True)
                raise ToTitle

    # ═══════════════════════════ saving ═══════════════════════════
    def save_path(self, slot):
        return os.path.join(SAVE_DIR, f"slot{slot}.json")

    def data(self):
        p = self.p
        self.playtime += time.time() - self._t0
        self._t0 = time.time()
        d = dict(version=VERSION, seed=self.world.seed, player=p.to_dict(), explored=self.explored.to_dict(),
                 fstate=self.fstate, markers=sorted(self.markers), log=self.log[-40:], track=self.track,
                 settings=self.settings, playtime=self.playtime, saved=time.time(),
                 dungeon=self.dungeon.to_dict() if self.dungeon else None,
                 combat=self.active_combat.to_dict() if self.active_combat else None,
                 meta=dict(name=p.name, cls=p.c["name"], level=p.level, day=self.day, hardcore=p.hardcore, steps=p.steps))
        return d

    def save(self, manual=False):
        if self.slot is None:
            self.slot = self.find_free_slot()
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            path = self.save_path(self.slot)
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(self.data(), fh)
            os.replace(tmp, path)
            return True
        except OSError as e:
            self.msg(f"<red>Save failed: {e}</>")
            return False

    def autosave(self):
        if self.t.test:
            return
        self.save()

    def find_free_slot(self):
        for i in range(1, 4):
            if not os.path.exists(self.save_path(i)):
                return i
        return 1

    @staticmethod
    def list_saves():
        out = []
        for i in range(1, 4):
            path = os.path.join(SAVE_DIR, f"slot{i}.json")
            if os.path.exists(path):
                try:
                    with open(path) as fh:
                        d = json.load(fh)
                    out.append((i, d.get("meta", {}), d.get("saved", 0)))
                except (OSError, ValueError):
                    pass
        return out

    def load(self, slot):
        with open(self.save_path(slot)) as fh:
            d = json.load(fh)
        self.slot = slot
        self.world = World(d["seed"])
        self.p = Player.from_dict(d["player"])
        if "fed_until" not in d["player"]:
            self.p.fed_until = self.p.minutes + 1440
        self.explored = Explored.from_dict(d["explored"])
        self.fstate = d["fstate"]
        self.markers = set(d["markers"])
        self.log = d.get("log", [])
        self.track = d.get("track")
        self.settings = d.get("settings", self.settings)
        self.playtime = d.get("playtime", 0)
        self._t0 = time.time()
        self.dungeon_state = d.get("dungeon")
        self.combat_state = d.get("combat")
        self.active_combat = None
        self.dungeon = None
        self.msg("<gold>Welcome back to the road.</>")

    # ═══════════════════════════ hall of fame ═══════════════════════════
    def save_hof(self, how):
        p = self.p
        path = os.path.join(SAVE_DIR, "hall_of_fame.json")
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            hof = []
            if os.path.exists(path):
                with open(path) as fh:
                    hof = json.load(fh)
            dist = int(max(abs(p.pos[0] - START[0]), abs(p.pos[1] - START[1])))
            score = p.level * 100 + sum(p.kills.values()) * 3 + p.dragons * 500 + dist * 2 + p.gold // 20 + p.flags.get("quests_done", 0) * 40
            if p.hardcore:
                score = int(score * 1.25)
            hof.append(dict(name=p.name, cls=p.c["name"], level=p.level, score=score, kills=sum(p.kills.values()),
                            dragons=p.dragons, days=self.day, how=how, hardcore=p.hardcore, quests=p.flags.get("quests_done", 0)))
            hof.sort(key=lambda h: -h["score"])
            with open(path, "w") as fh:
                json.dump(hof[:30], fh)
        except OSError:
            pass


class RetireHero(Exception):
    pass


class ToTitle(Exception):
    pass
