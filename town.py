"""Settlements: market, smithy, temple, tavern, notice board."""
import math
import re

from .data import RUMOR_LINES, TAVERN_SONGS, OMENS, POTIONS, SCROLLS
from .items import (gen_weapon, gen_armor, gen_shield, gen_jewelry, gen_potion, gen_scroll, gen_gem, name_item,
                    describe, is_stackable, roll_rarity)
from .quests import gen_board, describe_quest, dir_name, dragon_of, DRAGON_NAMES, arrow
from .term import PAL, esc, vlen, wrap
from .ui import hints, Story, bar
from .util import seeded, person_name, roll_n, sign
from .world import FEATURES, BIOMES

PROSP = {"village": 1, "town": 2, "city": 3}
PLACE_WORD = {"ruins": "a ruin of the old kingdoms", "cave": "a cave that breathes cold air", "crypt": "a sealed crypt",
              "tower": "a tower with a light in its window", "lair": "a dragon's lair", "camp": "a bandit camp",
              "shrine": "a forgotten shrine", "inn": "a roadside inn", "village": "a village", "town": "a town", "city": "a walled city"}


def stat_line(p):
    n, s = p.dice
    return dict(AC=p.ac, ATK=p.atk_bonus, DMG=round(n * (s + 1) / 2 + p.dmg_flat, 1), HP=p.max_hp, MP=p.max_mp)


def compare_lines(p, it):
    slot = p.slot_of(it)
    if not slot:
        return []
    old = p.eq[slot]
    before = stat_line(p)
    p.eq[slot] = it
    try:
        after = stat_line(p)
    finally:
        p.eq[slot] = old
    out = []
    for k in ("AC", "ATK", "DMG", "HP", "MP"):
        d = round(after[k] - before[k], 1)
        if d:
            col = "green" if d > 0 else "red"
            out.append(f"<{col}>{'+' if d > 0 else ''}{d:g} {k}</>")
    return ["<grey>vs equipped:</> " + ("  ".join(out) if out else "<dim>no change</>")]


def rename_plus(it):
    plus = it.get("plus", 0)
    if re.search(r"\+\d+", it["n"]):
        it["n"] = re.sub(r"\+\d+", f"+{plus}", it["n"], 1)
    else:
        base = it.get("base", "")
        it["n"] = it["n"].replace(base, f"{base} +{plus}", 1) if base in it["n"] else it["n"] + f" +{plus}"


class Market:
    def __init__(self, game, title, stock, buy_mult=1.0, sell_mult=0.4, art=None, can_sell=True):
        self.g, self.ui, self.p = game, game.ui, game.p
        self.title, self.stock = title, stock
        self.buy_mult, self.sell_mult = buy_mult, sell_mult
        self.can_sell = can_sell
        self.tab = 0
        self.sel = [0, 0]

    def buy_price(self, it):
        cha = max(0, self.p.m("CHA"))
        rep = min(0.10, self.p.rep * 0.01)
        return max(1, int(it["v"] * self.buy_mult * (1 - 0.02 * cha - rep)))

    def sell_price(self, it):
        mult = 0.7 if it["k"] in ("gem", "relic") else self.sell_mult
        return max(1, int(it["v"] * (mult + 0.01 * max(0, self.p.m("CHA")))))

    def run(self):
        ui, p = self.ui, self.p
        while True:
            self.g.update_hunger()
            items = self.stock if self.tab == 0 else p.inv
            sel = self.sel[self.tab] = max(0, min(self.sel[self.tab], len(items) - 1))
            s = ui.frame(self.title, hints([("←→", "Buy/Sell"), ("↑↓", "Browse"), ("Enter", "Buy" if self.tab == 0 else "Sell")]
                                           + ([("A", "Sell all junk")] if self.tab == 1 else []) + [("Esc", "Leave")]))
            W, H = s.w, s.h
            lw = W // 2 - 2
            # tabs
            for i, name in enumerate(["  Buy  ", "  Sell  "]):
                if i == 1 and not self.can_sell:
                    continue
                on = i == self.tab
                s.put(3 + i * 10, 1, name, PAL["bg"] if on else PAL["grey"], PAL["gold"] if on else PAL["panel"], 1 if on else 0)
            s.puts(W - 24, 1, f"<gold>{p.gold}</> gold", PAL["white"])
            s.box(1, 2, lw, H - 4, "single", PAL["edge2"], PAL["panel"])
            rows = H - 6
            top = max(0, min(sel - rows // 2, max(0, len(items) - rows)))
            for i in range(rows):
                j = top + i
                if j >= len(items):
                    break
                it = items[j]
                cur = j == sel
                bgc = PAL["panel2"] if cur else PAL["panel"]
                s.fill(2, 3 + i, lw - 2, 1, " ", None, bgc)
                q = f" <dim>x{it['q']}</>" if 1 < it.get("q", 1) < 99 else ""
                price = self.buy_price(it) if self.tab == 0 else self.sell_price(it)
                afford = self.tab == 1 or p.gold >= price
                s.put(3, 3 + i, "▸" if cur else " ", PAL["gold"], bgc)
                s.puts(5, 3 + i, name_item(it) + q, None, bgc, maxw=lw - 14)
                if self.tab == 1 and any(it is e for e in p.eq.values()):
                    pass
                s.puts(lw - 8, 3 + i, f"<{'gold' if afford else 'red'}>{price:>5}g</>", None, bgc)
            if not items:
                s.puts(4, 4, "<dim>Nothing here.</>", None, PAL["panel"])
            # detail
            dx = lw + 2
            s.box(dx, 2, W - dx - 1, H - 4, "single", PAL["edge2"], PAL["panel"], "Details")
            if items:
                it = items[sel]
                lines = []
                for ln in describe(it):
                    lines.extend(wrap(ln, W - dx - 5))
                lines.append("")
                lines.extend(compare_lines(p, it))
                for i, ln in enumerate(lines[:H - 8]):
                    s.puts(dx + 2, 3 + i, ln, PAL["white"], PAL["panel"])
            ui.flush()
            k = ui.key()
            if k in ("esc", "q"):
                return
            elif k in ("left", "h") and self.tab == 1:
                self.tab = 0
            elif k in ("right", "l", "tab") and self.can_sell:
                self.tab = 1 if self.tab == 0 else 0
            elif k == "tab" and not self.can_sell:
                pass
            elif k in ("up", "k", "w"):
                self.sel[self.tab] = max(0, sel - 1)
            elif k in ("down", "j", "s"):
                self.sel[self.tab] = min(len(items) - 1, sel + 1)
            elif k in ("pgup",):
                self.sel[self.tab] = max(0, sel - 8)
            elif k in ("pgdn",):
                self.sel[self.tab] = min(len(items) - 1, sel + 8)
            elif k == "a" and self.tab == 1:
                self.sell_junk()
            elif k in ("enter", "space") and items:
                self.buy(items[sel]) if self.tab == 0 else self.sell(items[sel])

    def buy(self, it):
        p, ui = self.p, self.ui
        price = self.buy_price(it)
        if p.gold < price:
            self.g.msg("<red>You can't afford that.</>")
            ui.message("Market", "You don't have enough gold.")
            return
        qty = 1
        if is_stackable(it) and it.get("q", 1) > 1 or it["k"] == "food":
            opts = [1, 3, 5, 10]
            opts = [n for n in opts if n <= it.get("q", 99) and p.gold >= price * n]
            i = ui.menu(f"Buy {it['n']}", [f"{n}  <dim>({price * n}g)</>" for n in opts], numbered=True)
            if i is None:
                return
            qty = opts[i]
        elif not ui.confirm(f"Buy {esc(it['n'])} for {price} gold?", True, "Buy"):
            return
        new = dict(it)
        if is_stackable(it) or it["k"] == "food":
            new["q"] = qty
        if it["k"] == "food":
            p.food += qty
        elif not self.g.give_item(new):
            return
        p.gold -= price * qty
        if not (is_stackable(it) and it.get("q", 1) > 1) and it in self.stock and it["k"] not in ("potion", "food"):
            self.stock.remove(it)
        elif "q" in it and it["k"] == "gem":
            it["q"] -= qty
            if it["q"] <= 0:
                self.stock.remove(it)

    def sell(self, it):
        p = self.p
        price = self.sell_price(it)
        eq = [k for k, v in p.eq.items() if v is it]
        if not self.ui.confirm(f"Sell {esc(it['n'])} for {price} gold?", True, "Sell"):
            return
        n = 1
        if it.get("q", 1) > 1:
            i = self.ui.menu("How many?", ["One", f"All ({it['q']})"], numbered=True)
            if i is None:
                return
            n = 1 if i == 0 else it["q"]
        p.gold += price * n
        if n >= it.get("q", 1):
            p.inv.remove(it)
        else:
            it["q"] -= n

    def sell_junk(self):
        p = self.p
        junk = [it for it in p.inv if it["k"] in ("gem", "relic")]
        total = sum(self.sell_price(it) * it.get("q", 1) for it in junk)
        if not junk:
            return
        if self.ui.confirm(f"Sell all gems & relics for {total} gold?", True, "Sell junk"):
            p.gold += total
            p.inv = [it for it in p.inv if it not in junk]


class Town:
    def __init__(self, game, feature):
        self.g, self.ui, self.p, self.f = game, game.ui, game.p, feature
        self.prosp = PROSP.get(feature.kind, 1)
        self.week = self.p.minutes // (1440 * 7)
        self.rng = seeded("town", feature.seed)
        self.keeper = person_name(self.rng)
        self.mayor = person_name(self.rng, True)
        self.level = max(1, game.world.level_at(feature.x, feature.y))

    # ── entry ──────────────────────────────────────────────────────────────
    def run(self):
        g, p, f = self.g, self.p, self.f
        p.last_town = dict(name=f.name, x=f.x, y=f.y, key=f.key)
        g.mark_known(f)
        g.quest_event("arrive", f)
        g.autosave()
        st = g.fstate.setdefault(f.key, {})
        first = not st.get("visited")
        st["visited"] = True
        if first:
            g.chronicle(f"First visited {f.name}.")
        while True:
            night = g.is_night()
            s = self.ui.begin()
            s.clear()
            self.draw_header()
            opts = [("The Tavern", True, "rest, rumours, dice"), ("The Market", True, "buy & sell"),
                    ("The Smithy", True, "enhance gear"), ("The Temple", True, "healing, blessings"),
                    ("Notice Board", True, "quests"), (f"Speak with {self.mayor.split()[0]}", True, "local lore"),
                    ("Leave", True, "")]
            ready = [q for q in p.quests if q["state"] == "ready" and q["giver_key"] == f.key]
            if ready:
                opts[4] = ("Notice Board", True, f"<green>{len(ready)} to turn in!</>")
            i = self.ui.menu(f"{f.name}", opts, dim=False, at=(self.menu_x(s), 12 + (0 if s.h < 30 else 1)), width=44, cancel=True,
                             footer=hints([("↑↓", "Choose"), ("Enter", "Go"), ("Esc", "Leave town")]))
            if i is None or i == 6:
                return
            [self.tavern, self.market, self.smith, self.temple, self.board, self.elder][i]()

    def menu_x(self, s):
        return (s.w - 44) // 2

    def draw_header(self):
        s = self.ui.sc
        f, g = self.f, self.g
        g.update_hunger()
        s.box(0, 0, s.w, s.h - 1, "double", PAL["edge"], PAL["bg"], f"{f.label} of {esc(f.name)}")
        art = g.scene("town")
        night = g.is_night()
        col = PAL["silver"] if not night else PAL["blue"]
        x0 = (s.w - max(vlen(a) for a in art)) // 2
        for j, ln in enumerate(art):
            s.puts(x0, 2 + j, ln, col, PAL["bg"])
        if night:
            for i in range(14):
                s.put(x0 + (i * 7) % 34, 1 + (i * 3) % 3, "·", PAL["gold"], PAL["bg"])
        day, h, m = g.clock()
        s.center(10, f"<dim>Day {day}, {h:02d}:{m:02d}  ·  Prosperity {'★' * self.prosp}{'☆' * (3 - self.prosp)}  ·  {['Village', 'Town', 'City'][self.prosp - 1]}</>", None, PAL["bg"])
        s.center(s.h - 1, "")
        s.puts(3, s.h - 3, f"<gold>{g.p.gold}</> gold   <green>{g.p.hp}/{g.p.max_hp}</> HP   <dim>rations</> {g.p.food}" + ("  <red>HUNGRY</>" if g.p.hungry else f"  <dim>fed for</> {g.fed_hours()}h"), PAL["white"], PAL["bg"])

    # ── market ─────────────────────────────────────────────────────────────
    def stock(self):
        rng = seeded("stock", self.f.seed, self.week)
        lv = self.level + self.prosp
        p = self.p
        stock = []
        stock.append(dict(k="food", n="Travel Ration", r=0, v=6, q=99, food=1))
        for pid in (["heal1", "heal2"] if lv < 8 else ["heal2", "heal3"] if lv < 16 else ["heal3", "heal4"]):
            stock.append(gen_potion(rng, lv, pid, 99))
        stock.append(gen_potion(rng, lv, "antidote", 99))
        stock.append(gen_potion(rng, lv, "mana1" if lv < 12 else "mana2", 99))
        stock.append(gen_potion(rng, lv, "smoke", 99))
        for _ in range(2 + self.prosp):
            stock.append(gen_scroll(rng, lv, None, 99) if rng.random() < 0.4 else gen_potion(rng, lv, rng.choice(["ironskin", "might", "oil"]), 99))
        n = 5 + self.prosp * 2
        for _ in range(n):
            r = rng.random()
            bonus = 0.1 * self.prosp
            rar = roll_rarity(rng, lv, bonus)
            if r < 0.35:
                it = gen_weapon(rng, lv, rar)
            elif r < 0.65:
                it = gen_armor(rng, lv, rar)
            elif r < 0.8:
                it = gen_shield(rng, lv, rar)
            else:
                it = gen_jewelry(rng, lv, rar)
            stock.append(it)
        seen = set()
        out = []
        for it in stock:
            if (it["n"]) in seen:
                continue
            seen.add(it["n"])
            out.append(it)
        # persist sold-out state in fstate so stock persists within the week
        stt = self.g.fstate.setdefault(self.f.key, {})
        sold = set(stt.get("sold", {}).get(str(self.week), []))
        return [it for it in out if it["n"] not in sold]

    def market(self):
        stock = self.stock()
        m = Market(self.g, f"{esc(self.f.name)} Market", stock, buy_mult=1.25 - 0.05 * self.prosp)
        before = {it["n"] for it in stock}
        m.run()
        after = {it["n"] for it in m.stock}
        sold = before - after
        if sold:
            stt = self.g.fstate.setdefault(self.f.key, {})
            stt.setdefault("sold", {}).setdefault(str(self.week), [])
            stt["sold"][str(self.week)] = list(set(stt["sold"][str(self.week)]) | sold)

    # ── smithy ─────────────────────────────────────────────────────────────
    def smith(self):
        p, ui, g = self.p, self.ui, self.g
        cap = 4 + 3 * self.prosp
        while True:
            rows, slots = [], []
            for slot in ("weapon", "armor", "shield"):
                it = p.eq[slot]
                if not it:
                    continue
                cost = int((25 + 20 * (it["plus"] + 1) ** 2) * (1 + p.level * 0.12))
                slots.append((slot, it, cost))
                ok = p.gold >= cost and it["plus"] < cap
                rows.append((f"{name_item(it)}", ok, f"→ +{it['plus'] + 1}  {cost}g" if it["plus"] < cap else "<dim>at max here</>"))
            if not rows:
                ui.message("Smithy", "You have nothing equipped that the smith can work on.")
                return
            s = ui.begin()
            s.clear()
            s.box(0, 0, s.w, s.h - 1, "double", PAL["edge"], PAL["bg"], "The Smithy")
            art = ["       ,--,      ", "   ___/ /\\ \\___  ", "  |___/__\\__/___| ", "  ,-'  <ember>*</>   '-,   ", " /_/\\_[====]_/\\_\\ ", "  _|__________|_  "]
            for j, ln in enumerate(art):
                s.puts((s.w - 20) // 2, 2 + j, ln, PAL["silver"], PAL["bg"])
            s.center(9, f"<dim>{esc(self.keeper)} the smith works iron and orders the flame.  Masters here can push gear to +{cap}.</>")
            s.center(10, f"<gold>{p.gold}</> gold", PAL["white"])
            i = ui.menu("Enhance equipment", rows, dim=False, at=((s.w - 60) // 2, 12), width=60,
                        footer=hints([("Enter", "Enhance"), ("Esc", "Leave")]))
            if i is None:
                return
            slot, it, cost = slots[i]
            if p.gold < cost:
                continue
            p.gold -= cost
            it["plus"] += 1
            it["v"] += 60 * (it["plus"])
            rename_plus(it)
            g.msg(f"<gold>The smith reforges {esc(it['n'])}!</>")
            ui.flash(PAL["ember"], 0.35, 3)

    # ── temple ─────────────────────────────────────────────────────────────
    def temple(self):
        p, ui, g = self.p, self.ui, self.g
        while True:
            heal_cost = 4 + 2 * p.level
            bless_cost = 25 + 12 * p.level
            opts = [(f"Healing prayer", p.hp < p.max_hp and p.gold >= heal_cost, f"{heal_cost}g"),
                    (f"Blessing of the Dawn", p.gold >= bless_cost, f"{bless_cost}g"),
                    ("Make an offering", p.gold >= 25, "25g"), ("Leave", True, "")]
            s = ui.begin()
            s.clear()
            s.box(0, 0, s.w, s.h - 1, "double", PAL["edge"], PAL["bg"], "The Temple")
            for j, ln in enumerate(g.scene("shrine")):
                s.puts((s.w - 30) // 2, 2 + j, ln, PAL["ice"], PAL["bg"])
            s.center(10, f"<dim>Candles gutter in the dark. A priest watches you with tired kindness.</>")
            s.center(11, f"<green>{p.hp}/{p.max_hp}</> HP   <gold>{p.gold}</> gold   " + ("<amber>Blessed</>" if p.blessed_until > p.minutes else ""))
            i = ui.menu("Temple", opts, dim=False, at=((s.w - 46) // 2, 13), width=46)
            if i is None or i == 3:
                return
            if i == 0:
                p.gold -= heal_cost
                p.hp = p.max_hp
                p.restore_mp(p.max_mp)
                g.advance_time(30)
                g.msg("<green>Warm light closes your wounds.</>")
                ui.message("Temple", "<green>The priest lays hands on you. Your wounds close, your mind clears, and your mana returns.</>", PAL["green"])
            elif i == 1:
                p.gold -= bless_cost
                p.blessed_until = p.minutes + 1440
                ui.message("Temple", "<amber>A blessing of morning light settles over you for a full day: +1 to attack and to all checks, and a shield of grace in every fight.</>", PAL["amber"])
            else:
                p.gold -= 25
                p.rep += 1
                r = g.rng.random()
                if r < 0.15:
                    p.hp = p.max_hp
                    ui.message("Temple", "<gold>The candles flare bright. Something old and kind notices you. You are fully healed.</>")
                elif r < 0.3:
                    p.blessed_until = max(p.blessed_until, p.minutes + 480)
                    ui.message("Temple", "<amber>The priest presses a warm hand to your brow. A short blessing follows you out.</>")
                else:
                    ui.message("Temple", "<grey>\"Go gently,\" says the priest. Your offering vanishes into the alms-bowl. Your reputation grows.</>")

    # ── tavern ─────────────────────────────────────────────────────────────
    def tavern(self):
        p, ui, g = self.p, self.ui, self.g
        while True:
            rest_cost = int((6 + 3 * p.level) * (1.1 - 0.05 * self.prosp))
            opts = [("Rent a bed", p.gold >= rest_cost, f"{rest_cost}g · full rest"),
                    ("Buy a round & listen for rumours", p.gold >= 8, "8g"),
                    ("Play Dragon Dice", p.gold >= 5, "gamble"),
                    ("Chat with the patrons", True, "story"),
                    ("Leave", True, "")]
            s = ui.begin()
            s.clear()
            s.box(0, 0, s.w, s.h - 1, "double", PAL["edge"], PAL["bg"], f"{esc(self.f.name)} — The Tavern")
            for j, ln in enumerate(g.scene("tavern")):
                s.puts((s.w - 34) // 2, 2 + j, ln, PAL["amber"], PAL["bg"])
            s.center(10, f"<dim>Fire, ale, and a low murmur. {esc(self.keeper)} polishes a mug behind the bar.</>")
            s.center(11, f"<gold>{p.gold}</> gold   <green>{p.hp}/{p.max_hp}</> HP")
            i = ui.menu("Tavern", opts, dim=False, at=((s.w - 50) // 2, 13), width=50)
            if i is None or i == 4:
                return
            if i == 0:
                self.rest_at_inn(rest_cost)
            elif i == 1:
                self.rumours()
            elif i == 2:
                self.dice()
            elif i == 3:
                g.town_event(self)

    def rest_at_inn(self, cost):
        p, g = self.p, self.g
        p.gold -= cost
        day, h, m = g.clock()
        to_morning = (7 - h) % 24 or 24
        g.fade = True
        self.ui.fade_out()
        g.advance_time(to_morning * 60, resting=True)
        p.hp, p.mp = p.max_hp, p.max_mp
        g.msg("<green>You sleep in a real bed. Fully rested.</>")
        g.autosave()
        st = Story(self.ui, "A Good Night's Sleep", color=PAL["green"])
        st.say(g.rng.choice(["You wake to the smell of bacon and the sound of somebody else's dog barking. For a moment the road feels very far away.",
                             "You dream of dragons. In the dream, they are polite. You wake rested and suspicious.",
                             "The bed is lumpy, the blankets scratch, and you sleep like the dead. Morning sun is a small miracle."]))
        st.say(f"<green>HP and resources fully restored.</> <dim>Day {g.day}, 07:00.</>")
        st.pause()
        st.close()

    def rumours(self):
        g, p, ui = self.g, self.p, self.ui
        p.gold -= 8
        g.advance_time(45)
        f = self.f
        st = Story(ui, "Rumours", art=g.scene("tavern"), art_color=PAL["amber"], color=PAL["amber"])
        st.say(g.rng.choice(TAVERN_SONGS))
        cands = [x for x in g.world.features_near(f.x, f.y, 75) if x.key != f.key and x.key not in g.markers]
        g.rng.shuffle(cands)
        rev = 0
        for x in cands[:2]:
            dx, dy = x.x - f.x, x.y - f.y
            what = PLACE_WORD.get(x.kind, "a place")
            line = g.rng.choice(RUMOR_LINES).format(what=what, dir=dir_name(dx, dy), dist=int(math.hypot(dx, dy)))
            st.say(f"<white>“{line}”</>  <cyan>[marked on your map]</>")
            g.mark_known(x)
            rev += 1
        if not rev:
            st.say("<grey>Nobody has anything new to say. You've heard all the local gossip.</>")
        st.say(f"<dim>{g.rng.choice(OMENS)}</>")
        st.pause()
        st.close()

    def dice(self):
        g, p, ui = self.g, self.p, self.ui
        st = Story(ui, "Dragon Dice", color=PAL["gold"])
        st.say("A wiry gambler slides two ivory dice across the table. <dim>\"Highest total takes the pot. Ties go to the house. Nobody cheats.\"</> He winks, badly.")
        while True:
            bets = [b for b in (5, 20, 50, 100, 250, 500) if b <= p.gold]
            if not bets:
                st.say("<grey>You're out of coin.</>")
                st.pause()
                break
            i = st.ask([f"Bet {b}g" for b in bets] + ["Walk away"], echo=False)
            if i == len(bets):
                break
            bet = bets[i]
            a, b = g.rng.randint(1, 6), g.rng.randint(1, 6)
            c, d = g.rng.randint(1, 6), g.rng.randint(1, 6)
            cheat = g.rng.random() < 0.06
            you, him = a + b, c + d
            st.line(f"You roll <b>{a}</> + <b>{b}</> = <gold>{you}</>. He rolls <b>{c}</> + <b>{d}</> = <red>{him}</>.")
            if you > him:
                p.gold += bet
                st.say(f"<green>You win {bet} gold!</>")
            elif you == him:
                p.gold -= bet
                st.say("<grey>A tie. The house takes it.</>")
            else:
                p.gold -= bet
                st.say(f"<red>You lose {bet} gold.</>")
            if you > him and g.rng.random() < 0.08:
                st.say("<dim>The gambler eyes you like a man doing arithmetic.</>")
        st.close()

    # ── notice board ───────────────────────────────────────────────────────
    def board(self):
        g, p, ui = self.g, self.p, self.ui
        while True:
            taken = set(p.flags.get("taken", []))
            board = gen_board(g.world, self.f, self.week, taken)
            ready = [q for q in p.quests if q["state"] == "ready" and q["giver_key"] == self.f.key]
            opts = [(f"<green>Turn in:</> {q['title']}", True, "reward!") for q in ready]
            opts += [(q["title"], len([x for x in p.quests if x["state"] in ("active", "ready")]) < 6,
                      f"Lv{q['level']}  {q['reward']['gold']}g") for q in board]
            opts.append(("Leave", True, ""))
            i = ui.menu("Notice Board", opts, width=70, detail_lines=10, detail=lambda i: (
                "\n".join(describe_quest(ready[i]["title"] and ready[i], p.pos)) if i < len(ready) else
                ("\n".join(describe_quest(board[i - len(ready)], p.pos)) if i - len(ready) < len(board) else "")))
            if i is None or i == len(opts) - 1:
                return
            if i < len(ready):
                g.turn_in(ready[i])
                continue
            q = board[i - len(ready)]
            if ui.confirm(f"Accept: {esc(q['title'])}?", True, "Notice Board"):
                p.quests.append(q)
                p.flags.setdefault("taken", []).append(q["id"])
                g.msg(f"<gold>Quest accepted:</> {esc(q['title'])}")
                g.chronicle(f"Accepted quest: {q['title']}.")
                g.track = q["id"]

    # ── elder ──────────────────────────────────────────────────────────────
    def elder(self):
        g, p, ui, f = self.g, self.p, self.ui, self.f
        st = Story(ui, f"{esc(self.mayor)}", art=g.scene("road"), art_color=PAL["sand"], subtitle="Elder of " + esc(f.name),
                   color=PAL["sand"])
        lairs = sorted(g.world.features_near(f.x, f.y, 110, ("lair",)), key=lambda x: math.hypot(x.x - f.x, x.y - f.y))
        st.say(f"“Sit, traveller. {esc(f.name)} has seen better days and worse ones, and the road outside has seen all of them.”")
        if lairs and self.g.rng.random() < 0.8:
            lair = lairs[0]
            tid, dname = dragon_of(lair)
            dx, dy = lair.x - f.x, lair.y - f.y
            st.say(f"“In the old songs, <red>{esc(dname)}</> slumbers in <white>{esc(lair.name)}</>, {int(math.hypot(dx, dy))} leagues {dir_name(dx, dy)} of here. "
                   f"A {DRAGON_NAMES[tid]}, they say. Nothing that reaches for that hoard has come back the same.”")
            st.say(f"<cyan>[{esc(lair.name)} marked on your map]</> <dim>Suggested level: {max(9, lair.level + 3)}+</>")
            g.mark_known(lair)
        else:
            lvl = g.world.level_at(p.pos[0], p.pos[1])
            st.say("“The further you walk from the hearth, the darker the roads become. Every dozen leagues, the wild grows teeth.”")
        st.say(f"<dim>{g.rng.choice(OMENS)}</>")
        st.pause()
        st.close()
