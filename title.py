"""Title screen, character creation, hall of fame."""
import json
import math
import os
import random
import time

from .art import LOGO, SCENES
from .chargen import roll_stats, assign, create_player
from .data import CLASSES, ORIGINS, STATS, STAT_NAMES
from .game import Game, SAVE_DIR, VERSION, RetireHero, ToTitle
from .items import name_item
from .term import PAL, mix, scale, vlen, wrap, esc, A_BOLD, strip as strip_tags
from .ui import Story, bar, hints
from .util import mod, sign
from .world import World, Explored, START

DRAGON_SPRITE = [
    ["   \\\\      //   ", "    \\\\____//    ", "  ---(oo)>===-  ", "    /|  |\\      "],
    ["                ", "  ,-\"\"\"\"\"\"-,   ", "  ---(oo)>===-  ", "     '--'       "],
]


class Title:
    def __init__(self, game):
        self.g = game
        self.ui = game.ui
        self.rng = random.Random(7)
        self.stars = None
        self.embers = []
        self.t0 = time.time()
        self.dragon_x = -30
        self.star_size = None

    def sky(self, s, W, H, tick):
        # gradient sky
        for y in range(H - 1):
            f = y / max(1, H - 1)
            c = mix(0x07050c, 0x3a1424, f ** 1.6)
            s.put(0, y, " " * W, None, c)
        if self.stars is None or self.star_size != (W, H):
            r = random.Random(3)
            self.stars = [(r.randrange(W), r.randrange(max(1, H // 2)), r.random()) for _ in range(W // 3)]
            self.star_size = (W, H)
            self.embers = [e for e in self.embers if 1 < e[1] < H - 1 and 0 <= e[0] < W]
        for i, (x, y, ph) in enumerate(self.stars):
            b = 0.5 + 0.5 * math.sin(tick * 0.15 + ph * 6)
            _, _, bg, _ = s.cells[y * W + x]
            s.put(x, y, "·" if b < 0.7 else "✦" if ph > 0.85 else "+", mix(bg, 0xe8e0ff, 0.25 + 0.6 * b), bg)
        # moon — only *fully solid* cells ('█') get a real white background, so embers landing on
        # the body of the disc show against white. The half/quadrant glyphs (▄▀▟▙▜▛) are what round
        # off the disc's corners: each one is only PART covered, so their background must stay the
        # dark sky or the "uncovered" part fills in too and the moon reads as a plain square. The
        # ',' / "'" corner accents aren't part of the disc at all, so they're left fully untouched.
        mx, my = W - 18, 11
        moon_fg = 0xf2f2ec
        for dy, row in enumerate([" ,▄██▄, ", "▟██████▙", "▜██████▛", " '▀██▀' "]):
            for dx, ch in enumerate(row):
                if ch == " " or not (0 <= mx + dx < W and 0 <= my + dy < H - 1):
                    continue
                if ch in ",'":
                    _, _, bg, _ = s.cells[(my + dy) * W + mx + dx]
                    s.put(mx + dx, my + dy, ch, 0xe8dcc0, bg)
                elif ch == "█":
                    s.put(mx + dx, my + dy, ch, moon_fg, moon_fg)
                else:                                    # ▄ ▀ ▟ ▙ ▜ ▛ : half/quadrant-filled — keep the dark sky behind them
                    _, _, bg, _ = s.cells[(my + dy) * W + mx + dx]
                    s.put(mx + dx, my + dy, ch, moon_fg, bg)
        # mountains
        horizon = H - 4
        for x in range(W):
            h1 = int(3 + 2.5 * math.sin(x / 7.0) + 1.8 * math.sin(x / 3.1 + 1) + 2 * math.sin(x / 15.0 + 2))
            h2 = int(2 + 1.5 * math.sin(x / 5.0 + 4) + 1.2 * math.sin(x / 2.3))
            for j in range(max(0, h1)):
                s.put(x, horizon - j, "▓" if j == h1 - 1 else "█", 0x1a0d18, 0x1a0d18)
            for j in range(max(0, h2)):
                s.put(x, horizon + 1 - j + 1, "█", 0x0e070d, 0x0e070d)
        s.fill(0, horizon + 1, W, H - horizon - 2, "█", 0x0a050a, 0x0a050a)
        # dragon fly-by
        if tick % 400 == 100:
            self.dragon_x = -20
        if self.dragon_x < W + 5:
            self.dragon_x += 0.6
            spr = DRAGON_SPRITE[(tick // 4) % 2]
            dy = 8 + int(2 * math.sin(self.dragon_x / 9))
            for j, row in enumerate(spr):
                for i, ch in enumerate(row):
                    x = int(self.dragon_x) + i
                    if ch != " " and 0 <= x < W and 0 <= dy + j < H - 1:
                        _, _, bg, _ = s.cells[(dy + j) * W + x]
                        s.put(x, dy + j, ch, 0x0d060b, bg)
        # embers
        if self.rng.random() < 0.6:
            self.embers.append([self.rng.randrange(W), H - 3, -self.rng.uniform(0.15, 0.5), self.rng.random()])
        keep = []
        for e in self.embers:
            e[1] += e[2]
            e[0] += math.sin(e[1] * 0.7 + e[3] * 9) * 0.3
            if 1 < e[1] < H - 1 and 0 <= int(e[0]) < W:
                life = (e[1] / H)
                col = mix(0xffe08a, 0xd03010, 1 - life)
                _, _, bg, _ = s.cells[int(e[1]) * W + int(e[0])]
                s.put(int(e[0]), int(e[1]), "·" if life < 0.5 else "*" if e[3] > .7 else "'", col, bg)
                keep.append(e)
        self.embers = keep[-260:]

    def draw(self, items, sel, tick, note=""):
        s = self.ui.begin()
        W, H = s.w, s.h
        self.sky(s, W, H, tick)
        top = 2
        if W >= 82 and H >= 28:
            lx = (W - 78) // 2
            for j, ln in enumerate(LOGO):
                col = mix(0xffd76a, 0xc02020, j / 5)
                for i, ch in enumerate(ln):
                    if ch != " " and 0 <= lx + i < W:
                        _, _, bg, _ = s.cells[(top + j) * W + lx + i]
                        shimmer = 0.85 + 0.15 * math.sin(tick * 0.2 + i * 0.15 - j)
                        s.put(lx + i, top + j, ch, scale(col, shimmer), bg, A_BOLD)
            ty = top + 7
        else:
            s.center(top + 1, "<b><gold>E M B E R R O A D</></>")
            ty = top + 3
        s.center(ty, "<i><sand>— the endless road —</></>")
        my = ty + 3
        w = 34
        x = (W - w) // 2
        s.box(x - 2, my - 1, w + 4, len(items) + 2, "round", PAL["edge"], 0x120a14)
        for i, (lab, en) in enumerate(items):
            cur = i == sel
            bgc = 0x2a1422 if cur else 0x120a14
            s.fill(x - 1, my + i, w + 2, 1, " ", None, bgc)
            s.puts(x + 1, my + i, ("<b><gold>▸ " if cur else "  ") + (lab if en else f"<dim>{lab}</>") + "</>",
                   PAL["gold"] if cur else PAL["silver"], bgc)
        s.center(H - 1, f"<dim>v{VERSION}  ·  ↑↓ Enter  ·  {note}</>", None, 0x0a050a)

    def menu(self, items, note=""):
        sel = next((i for i, (_, en) in enumerate(items) if en), 0)
        tick = 0
        while True:
            self.draw(items, sel, tick, note)
            self.ui.flush()
            k = self.ui.key(0.09)
            tick += 1
            if k is None or k == "resize":
                continue
            if k in ("up", "k", "w"):
                sel = (sel - 1) % len(items)
                while not items[sel][1]:
                    sel = (sel - 1) % len(items)
            elif k in ("down", "j", "s"):
                sel = (sel + 1) % len(items)
                while not items[sel][1]:
                    sel = (sel + 1) % len(items)
            elif k in ("enter", "space"):
                return sel
            elif k in ("q", "esc"):
                return None
            elif k.isdigit() and 1 <= int(k) <= len(items) and items[int(k) - 1][1]:
                return int(k) - 1


def run_title(g):
    t = Title(g)
    while True:
        saves = g.list_saves()
        items = [("Continue journey", bool(saves)), ("New journey", True), ("Hall of Fame", True), ("How to play", True), ("Quit", True)]
        i = t.menu(items, f"{len(saves)} save(s)")
        if i is None or i == 4:
            return
        if i == 0:
            slot = choose_slot(g, t, saves)
            if slot:
                try:
                    g.load(slot)
                except Exception as e:   # corrupted save
                    g.ui.message("Load failed", f"<red>Could not load this save:</> {esc(str(e))}")
                    continue
                play_session(g)
        elif i == 1:
            if new_game(g):
                play_session(g)
        elif i == 2:
            hall_of_fame(g)
        elif i == 3:
            g.p = None
            g.help_screen()


def play_session(g):
    try:
        g.play()
    except (RetireHero, ToTitle):
        pass
    except (KeyboardInterrupt, EOFError):
        if g.p and g.slot:
            g.save()
        raise
    except Exception:
        if g.p and g.slot:
            try:
                g.save()
            except Exception:
                pass
        raise
    finally:
        g.dungeon = None


def choose_slot(g, t, saves):
    items = []
    for i, meta, ts in saves:
        hc = " <red>[HARDCORE]</>" if meta.get("hardcore") else ""
        items.append((f"<b>{esc(meta.get('name', '?'))}</> Lv{meta.get('level', '?')} {meta.get('cls', '')} · day {meta.get('day', '?')}{hc}", True))
    items.append(("Back", True))
    while True:
        r = g.ui.menu("Continue which journey?", items, width=64)
        if r is None or r >= len(saves):
            return None
        slot = saves[r][0]
        a = g.ui.menu(strip_tags(items[r][0]), ["Load", "Delete this journey", "Back"], numbered=True)
        if a == 0:
            return slot
        if a == 1 and g.ui.confirm("Delete this journey forever?", False, "Delete"):
            try:
                os.remove(g.save_path(slot))
            except OSError:
                pass
            return None


# ═══════════════════════════ character creation ═══════════════════════════
def new_game(g):
    ui = g.ui
    name = ui.text_input("A Legend Begins", "What are you called, traveller?", "", 16)
    if not name:
        return False
    cls = choose_class(g, name)
    if cls is None:
        return False
    origin = choose_origin(g)
    if origin is None:
        return False
    rolls = roll_screen(g, cls)
    if rolls is None:
        return False
    m = ui.menu("Choose your fate", ["Normal — fall in battle and be carried back to town", "Hardcore — one life. Death is final. (+25% Hall of Fame score)"],
                numbered=True, width=70)
    if m is None:
        return False
    saves = g.list_saves()
    slot = None
    if len(saves) >= 3:
        opts = [f"Overwrite: <b>{esc(m.get('name', '?'))}</> Lv{m.get('level', '?')} {m.get('cls', '')}" for _, m, _ in saves]
        r = ui.menu("All three save slots are in use", opts + ["Cancel"], numbered=True, width=64)
        if r is None or r >= len(saves):
            return False
        slot = saves[r][0]
    seed = random.SystemRandom().randrange(1, 2 ** 31)
    rng = random.Random(seed)
    g.rng = random.Random()
    p = create_player(rng, name, cls, origin, rolls, hardcore=(m == 1))
    g.world = World(seed)
    g.explored = Explored()
    g.fstate, g.markers, g.log, g.track = {}, set(), [], None
    g.dungeon_state = None
    g.combat_state = None
    g.active_combat = None
    g.dungeon = None
    g.slot = slot
    g.p = p
    p.pos = list(START)
    f = g.world.feature_at(2, 2)
    p.last_town = dict(name=f.name, x=f.x, y=f.y, key=f.key)
    g.markers.add(f.key)
    from .quests import make_quest
    from .util import seeded
    q = None
    for kind in ("hunt", "hunt", "deliver"):
        q = make_quest(g.world, f, seeded("starter", seed, kind), kind, 0, 0)
        if q:
            break
    if q:
        q["desc"] = "The elder of Hearthmoor wants proof that you can handle yourself out there. " + q["desc"]
        q["reward"]["gold"] = max(q["reward"]["gold"], 60)
        p.quests.append(q)
        p.flags.setdefault("taken", []).append(q["id"])
        g.track = q["id"]
    g.msg(f"<gold>Your journey begins near {f.name}.</> <dim>Press <b>Enter</> on a place to go in, <b>?</> for help.</>")
    intro(g, p, f)
    g.save()
    return True


def intro(g, p, f):
    o = ORIGINS[p.origin]
    st = Story(g.ui, "Prologue", art=SCENES["road"], art_color=PAL["sand"], color=PAL["sand"])
    st.say(f"<i>{o['intro']}</>")
    st.say(f"Behind you, the chimneys of <white>{f.name}</> smoke against a low sun. Ahead, the road runs out in every direction: through forest and marsh, across mountain and ash, and it does not end.")
    st.say(f"<dim>They say the further you walk, the darker it gets, and that something very old sleeps under every mountain. Perhaps you'll find out.</>")
    st.say(f"<gold>{p.name}</>, <white>{o['name']}</>, <{p.c['color']}>{p.c['name']}</>. Your journey begins.")
    st.pause("Press any key to step onto the road")
    st.close()


def choose_class(g, name):
    ui = g.ui
    ids = list(CLASSES)
    sel = 0
    while True:
        s = ui.frame(f"Choose your path, {esc(name)}", hints([("↑↓", "Browse"), ("Enter", "Choose"), ("Esc", "Back")]))
        W, H = s.w, s.h
        lw = 26
        s.box(1, 1, lw, len(ids) * 2 + 3, "single", PAL["edge2"], PAL["panel"], "Classes")
        for i, cid in enumerate(ids):
            c = CLASSES[cid]
            cur = i == sel
            bgc = PAL["panel2"] if cur else PAL["panel"]
            s.fill(2, 3 + i * 2, lw - 2, 1, " ", None, bgc)
            s.puts(3, 3 + i * 2, f"{'▸' if cur else ' '} <{c['color']}><b>{c['name']}</></>", PAL["white"], bgc)
            s.puts(5, 4 + i * 2, f"<dim>{c['resource']} · d{c['hit']}</>", PAL["white"], PAL["panel"])
        c = CLASSES[ids[sel]]
        dx = lw + 3
        s.box(dx, 1, W - dx - 1, H - 3, "single", PAL["edge2"], PAL["panel"], f"{c['name']}")
        y = 2
        s.puts(dx + 2, y, f"<i><{c['color']}>{c['tag']}</></>", PAL["white"], PAL["panel"]); y += 2
        for ln in wrap(c["blurb"], W - dx - 6):
            s.puts(dx + 2, y, ln, PAL["white"], PAL["panel"]); y += 1
        y += 1
        s.puts(dx + 2, y, f"<dim>Hit die</> <b>d{c['hit']}</>   <dim>Resource</> <b>{c['resource']}</>   <dim>Prime stats</> <gold>{c['prio'][0]}, {c['prio'][1]}</>", PAL["white"], PAL["panel"]); y += 1
        kit = c["kit"]
        s.puts(dx + 2, y, f"<dim>Starts with</> {kit['weapon']}, {kit['armor']}" + (f", {kit['shield']}" if kit.get('shield') else ""), PAL["white"], PAL["panel"]); y += 2
        s.puts(dx + 2, y, "<gold>Signature arts</>", PAL["white"], PAL["panel"]); y += 1
        for a in c["abilities"][:6]:
            if y >= H - 4:
                break
            s.puts(dx + 2, y, f"<{c['color']}>◆ {a['name']:<17}</><dim>Lv{a['lv']:>2}</> <grey>{a['desc']}</>", PAL["white"], PAL["panel"], maxw=W - dx - 5)
            y += 1
        ui.flush()
        k = ui.key()
        if k in ("up", "k", "w"):
            sel = (sel - 1) % len(ids)
        elif k in ("down", "j", "s"):
            sel = (sel + 1) % len(ids)
        elif k in ("enter", "space"):
            return ids[sel]
        elif k in ("esc", "q"):
            return None
        elif k.isdigit() and 1 <= int(k) <= len(ids):
            sel = int(k) - 1


def choose_origin(g):
    ui = g.ui
    ids = list(ORIGINS)
    items = [(f"<b>{ORIGINS[i]['name']}</>", True, f"<dim>{ORIGINS[i]['perk']}</>") for i in ids]
    r = ui.menu("Where do you come from?", items, width=78, detail=lambda i: ORIGINS[ids[i]]["intro"])
    return None if r is None else ids[r]


def roll_screen(g, cls):
    ui = g.ui
    rng = random.Random()
    c = CLASSES[cls]
    rolls = roll_stats(rng)
    rerolls = 0
    while True:
        s = ui.frame("Roll your fate", hints([("R", "Reroll the dice"), ("Enter", "Accept"), ("Esc", "Back")]))
        W, H = s.w, s.h
        s.center(3, f"<dim>4d6, drop the lowest. The best rolls go to what your <{c['color']}>{c['name']}</> needs most.</>")
        stats = assign(cls, rolls)
        x0 = (W - 50) // 2
        for i, st in enumerate(STATS):
            v = stats[st]
            y = 6 + i * 2
            pr = st in c["prio"][:2]
            s.puts(x0, y, f"<b>{STAT_NAMES[st]:<14}</>", PAL["gold"] if pr else PAL["white"])
            bar(s, x0 + 16, y, 22, v, 20, PAL["gold"] if pr else PAL["blue"])
            s.puts(x0 + 40, y, f"<b>{v:>2}</> <dim>({sign(mod(v))})</>", PAL["white"])
        total = sum(rolls)
        s.center(6 + 12 + 1, f"<dim>Total {total} (average roll: 73) · rerolls: {rerolls}</>")
        if total >= 80:
            s.center(6 + 14, "<gold>A heroic set of rolls!</>")
        elif total <= 64:
            s.center(6 + 14, "<grey>Modest. But heroes are made, not rolled.</>")
        ui.flush()
        k = ui.key()
        if k in ("r", "space"):
            for _ in range(0 if ui.t.fast or ui.t.test else 6):
                tmp = sorted([sum(sorted(rng.randint(1, 6) for _ in range(4))[1:]) for _ in range(6)], reverse=True)
                st2 = assign(cls, tmp)
                for i, st in enumerate(STATS):
                    s.puts(x0 + 40, 6 + i * 2, f"<b>{st2[st]:>2}</>   ", PAL["grey"])
                ui.flush()
                ui.t.sleep(0.05, False)
            rolls = roll_stats(rng)
            rerolls += 1
        elif k in ("enter",):
            return rolls
        elif k in ("esc", "q"):
            return None


# ═══════════════════════════ hall of fame ═══════════════════════════
def hall_of_fame(g):
    path = os.path.join(SAVE_DIR, "hall_of_fame.json")
    hof = []
    try:
        with open(path) as fh:
            hof = json.load(fh)
    except (OSError, ValueError):
        pass
    ui = g.ui
    s = ui.frame("Hall of Fame", hints([("Esc", "Back")]))
    W, H = s.w, s.h
    s.center(2, "<i><dim>Those who walked the road, and where it took them.</></>")
    if not hof:
        s.center(H // 2, "<dim>Nobody yet. Be the first legend.</>")
    else:
        s.puts(4, 4, f"<dim>{'#':>2}  {'Hero':<18}{'Class':<11}{'Lv':>3}  {'Score':>7}  {'Foes':>5}  {'Dragons':>7}  {'Days':>5}  End</>", PAL["white"])
        for i, h_ in enumerate(hof[:H - 8]):
            col = "gold" if i == 0 else "silver" if i == 1 else "brown" if i == 2 else "white"
            hc = " <red>†</>" if h_.get("hardcore") else ""
            s.puts(4, 5 + i, f"<{col}>{i + 1:>2}  {esc(h_['name'])[:17]:<18}{h_['cls']:<11}{h_['level']:>3}  {h_['score']:>7}  {h_['kills']:>5}  {h_['dragons']:>7}  {h_['days']:>5}</>  <dim>{h_['how']}</>{hc}", PAL["white"])
    ui.flush()
    ui.wait_key()
