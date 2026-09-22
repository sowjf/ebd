"""Turn-based D&D-flavoured combat with a full-screen TUI."""
import random

from .art import get_art
from .data import STATUS, ELEMENTS, CLASSES
from .dragon_speech import greet_lines, death_lines
from .items import name_item
from .term import PAL, vlen, wrap, mix, scale, strip, A_BOLD, esc
from .ui import bar, hp_color, hints, Story
from .util import roll_n, clamp, sign

VERBS = {"Dagger": "stab", "Shortsword": "slash", "Rapier": "thrust at", "Mace": "bash", "Longsword": "slash",
         "Warhammer": "smash", "Battleaxe": "hew", "Spear": "impale", "Greatsword": "cleave", "Greataxe": "chop",
         "Quarterstaff": "strike", "Wand": "zap", "Shortbow": "shoot", "Longbow": "shoot", "Crossbow": "shoot"}
MON_VERBS = {"beast": ["bites", "claws", "mauls"], "humanoid": ["slashes", "strikes", "hacks at"],
             "undead": ["rakes", "strikes", "claws"], "giant": ["smashes", "pummels", "clubs"],
             "demon": ["rends", "burns", "slashes"], "construct": ["pounds", "crushes", "slams"],
             "dragon": ["rakes", "bites", "lashes"], "elemental": ["scorches", "lashes", "engulfs"],
             "ooze": ["engulfs", "splashes", "smothers"], "plant": ["lashes", "crushes", "whips"]}
BREATH_TEXT = {"fire": "a roaring torrent of flame", "frost": "a howling cone of frost", "poison": "a cloud of choking venom",
               "acid": "a spray of hissing acid", "lightning": "a crackling arc of lightning", "dark": "a wave of grave-cold shadow"}


class Combat:
    def __init__(self, game, enemies, ambush=False, can_flee=True, title="Battle", scene=None, boss=False):
        self.g = game
        self.ui = game.ui
        self.p = game.p
        self.rng = game.rng
        self.enemies = enemies
        self.ambush = ambush
        self.can_flee = can_flee and not any(e.boss for e in enemies)
        self.title = title
        self.round = 0
        self.log = []
        self.pst = {}                  # player statuses {name: [turns, power]}
        self.sel = 0
        self.fx = {}
        self.sneak_used = False
        self.defeated = []
        self.fled_with = []
        self.buff_dmg = 0
        self.result = None
        self.dying = None
        self.ctx = None
        self.resume_skip = False
        self.dragon = enemies[0] if (len(enemies) == 1 and enemies[0].boss and enemies[0].tid.startswith("dragon")) else None

    # ═══════════════════════════ persistence ═══════════════════════════
    def to_dict(self):
        return dict(enemies=[e.to_dict() for e in self.enemies], can_flee=self.can_flee, title=self.title,
                    round=max(0, self.round - 1), log=self.log[-30:], pst=self.pst, sneak_used=self.sneak_used,
                    buff_dmg=self.buff_dmg, defeated=[self.enemies.index(e) for e in self.defeated if e in self.enemies],
                    fled_with=self.fled_with, ctx=self.ctx)

    @classmethod
    def from_dict(cls, game, d, enemies=None):
        from .entities import Monster
        en = enemies if enemies is not None else [Monster.from_dict(e) for e in d["enemies"]]
        c = cls(game, en, can_flee=d["can_flee"], title=d["title"])
        c.can_flee = d["can_flee"]
        c.round, c.log, c.pst = d["round"], d["log"], {k: list(v) for k, v in d["pst"].items()}
        c.sneak_used, c.buff_dmg, c.fled_with, c.ctx = d["sneak_used"], d["buff_dmg"], d["fled_with"], d.get("ctx")
        c.defeated = [en[i] for i in d["defeated"] if i < len(en)]
        c.resume_skip = True
        return c

    # ═══════════════════════════ logging & helpers ═══════════════════════════
    def say(self, text):
        self.log.append(text)
        self.log = self.log[-60:]

    def alive(self):
        return [e for e in self.enemies if e.hp > 0]

    def p_ac(self):
        ac = self.p.ac
        for name, (t, pw) in self.pst.items():
            if name == "shield":
                ac += pw
            elif name == "guard":
                ac += 4
            elif name == "exposed":
                ac -= 2
            elif name == "slow":
                ac -= 2
        return ac

    def p_hit_mod(self):
        m = 0
        if "slow" in self.pst: m -= 2
        if "fear" in self.pst: m -= 3
        return m

    def ele_mult(self, m, ele):
        if not ele or ele == "phys":
            return 1.0, ""
        if ele in m.weak:
            return 1.5, " <gold>(vulnerable!)</>"
        if ele in m.res:
            return 0.5, " <grey>(resisted)</>"
        return 1.0, ""

    # ═══════════════════════════ drawing ═══════════════════════════
    def geometry(self):
        s = self.ui.begin()
        W, H = s.w, s.h
        bh = 11
        y0 = H - 1 - bh
        return s, W, H, bh, y0

    def enemy_layout(self, s, W, y0):
        """Return list of (enemy, x, art_lines, w, compact) with bottom baseline."""
        # a slain enemy stays on stage until its death animation has played (kill_check adds it to `defeated`)
        alive = [e for e in self.enemies if e.hp > 0 or e is self.dying or e not in self.defeated]
        avail_h = y0 - 1 - 3                      # rows for art above the nameplate
        arts = []
        for e in alive:
            a = get_art(e.art)
            if len(a) > avail_h:
                a = get_art("wyrm") if e.art == "dragon" and len(get_art("wyrm")) <= avail_h else a[len(a) - avail_h:]
            arts.append(a)
        widths = [max(20, max(vlen(l) for l in a)) for a in arts]
        avail = W - 4

        def pick(room):
            chosen, used = [], 0
            for i in range(len(alive)):
                need = widths[i] + (3 if chosen else 0)
                if used + need <= room:
                    chosen.append(i)
                    used += need
            return chosen, used

        chosen, used = pick(avail)
        compact = [i for i in range(len(alive)) if i not in chosen]
        if compact:
            chosen, used = pick(avail - 21)
            compact = [i for i in range(len(alive)) if i not in chosen]
        x = 2 + max(0, (avail - used - (21 if compact else 0)) // 2)
        out = []
        for i in chosen:
            out.append((alive[i], x, arts[i], widths[i], False))
            x += widths[i] + 3
        for i in compact:
            out.append((alive[i], x, [], 18, True))
        return out

    def draw(self, target=None, menu=None, cursor=0, flash=None, popups=(), hero_flash=None, dissolve=None, note=None):
        s, W, H, bh, y0 = self.geometry()
        s.clear()
        s.box(0, 0, W, H - 1, "double", PAL["edge"], PAL["bg"], f"{self.title}")
        stage_h = y0 - 1
        # atmosphere: faint ground line
        for x in range(1, W - 1):
            s.put(x, y0 - 1, "░" if (x % 3) else "▒", PAL["edge2"], PAL["bg"])
        lay = self.enemy_layout(s, W, y0)
        s.puts(W - 22, 0, f"<dim> Round {max(1, self.round)} </>", PAL["dim"], PAL["bg"])
        base = y0 - 4
        cy = 1
        for idx, (e, x, art, w, compact) in enumerate(lay):
            col = PAL.get(e.color, PAL["silver"])
            if e.boss:
                col = mix(col, PAL["white"], 0.25)
            if flash and flash[0] is e:
                col = flash[1]
            if compact:
                y = 2 + idx % 6
                s.puts(x, cy + 1, f"<{e.color}>{esc(e.name)}</>", None, PAL["bg"])
                bar(s, x, cy + 2, 18, e.hp, e.max_hp, hp_color(e.hp / e.max_hp), label=f"{e.hp}/{e.max_hp}")
                cy += 3
                continue
            top = base - len(art) + 1
            top = max(1, top)
            for j, line in enumerate(art):
                yy = top + j
                if dissolve and dissolve[0] is e:
                    line = "".join(c if self.rng.random() > dissolve[1] else " " for c in line)
                s.puts(x + (w - max(vlen(l) for l in art)) // 2, yy, line, col, PAL["bg"])
            # nameplate
            ny = base + 1
            tag = "<gold>★ </>" if e.elite or e.boss else ""
            nm = f"{tag}<{'b'}>{esc(e.name)}</> <dim>Lv{e.level}</>"
            sel = target is not None and e is target
            if sel:
                s.center(top - 1 if top > 1 else 1, "<b><gold>▼</></>", None, PAL["bg"], x, w)
                nm = f"<gold>▸</> {nm} <gold>◂</>"
            s.center(ny, nm, PAL["white"], PAL["bg"], x, w)
            bw = min(w, 26)
            bar(s, x + (w - bw) // 2, ny + 1, bw, e.hp, e.max_hp, hp_color(e.hp / e.max_hp) if e.hp > 0 else PAL["dim"],
                label=f"{max(0, e.hp)}/{e.max_hp}")
            st = " ".join(f"<{STATUS[k][1]}>{STATUS[k][0]}{v[0]}</>" for k, v in e.st.items() if k in STATUS)
            if st:
                s.center(ny + 2, st, None, PAL["bg"], x, w)
        for (px, py, text, pcol) in popups:
            s.puts(px, py, f"<b>{text}</>", pcol, PAL["bg"])
        # ── bottom panels
        lw = W - 40
        s.box(0, y0, lw, bh, "single", PAL["edge2"], PAL["panel"], "Battle log")
        rows = bh - 2
        lines = []
        for ln in self.log[-14:]:
            lines.extend(wrap(ln, lw - 4))
        for i, ln in enumerate(lines[-rows:]):
            fade = 1.0 if i >= len(lines[-rows:]) - 3 else 0.7
            s.puts(2, y0 + 1 + i, ln, scale(PAL["white"], fade), PAL["panel"], maxw=lw - 4)
        hx = lw
        hw = W - hx
        bc = hero_flash if hero_flash else PAL["edge"]
        s.box(hx, y0, hw, bh, "round", bc, PAL["panel"],
              f"{esc(self.p.name)} <dim>·</> Lv{self.p.level} {self.p.c['name']}")
        p = self.p
        bar(s, hx + 6, y0 + 1, hw - 9, p.hp, p.max_hp, hp_color(p.hp / p.max_hp), label=f"{p.hp}/{p.max_hp}")
        s.puts(hx + 2, y0 + 1, "<red>HP</>", None, PAL["panel"])
        res_col = {"Valor": PAL["silver"], "Focus": PAL["green"], "Guile": PAL["purple"], "Mana": PAL["blue"],
                   "Faith": PAL["gold"], "Fury": PAL["red"]}[p.c["resource"]]
        bar(s, hx + 6, y0 + 2, hw - 9, p.mp, p.max_mp, res_col, label=f"{p.mp}/{p.max_mp}")
        s.puts(hx + 2, y0 + 2, "<cyan>MP</>", None, PAL["panel"])
        sts = " ".join(f"<{STATUS[k][1]}>{STATUS[k][0]}{v[0]}</>" for k, v in self.pst.items() if k in STATUS)
        s.puts(hx + 2, y0 + 3, f"<dim>AC</> <b>{self.p_ac()}</> <dim>ATK</> <b>{sign(self.p.atk_bonus)}</>  {sts}",
               PAL["white"], PAL["panel"], maxw=hw - 4)
        s.hline(hx + 1, y0 + 4, hw - 2, "─", PAL["edge2"], PAL["panel"])
        if menu:
            for i, (lab, en) in enumerate(menu):
                cur = i == cursor
                bgc = PAL["panel2"] if cur else PAL["panel"]
                s.fill(hx + 1, y0 + 5 + i, hw - 2, 1, " ", None, bgc)
                s.put(hx + 2, y0 + 5 + i, "▸" if cur else " ", PAL["gold"], bgc)
                s.puts(hx + 4, y0 + 5 + i, lab if en else strip(lab), PAL["gold"] if cur else (PAL["white"] if en else PAL["dim"]), bgc, maxw=hw - 6)
        if note:
            s.center(H - 1, note)

    def frame(self, dt=0.0, **kw):
        self.draw(**kw)
        self.ui.flush()
        if dt:
            self.ui.t.sleep(dt, False)

    # ═══════════════════════════ effects ═══════════════════════════
    def enemy_pos(self, e):
        s, W, H, bh, y0 = self.geometry()
        for (m, x, art, w, compact) in self.enemy_layout(s, W, y0):
            if m is e:
                return x + w // 2, max(1, y0 - 4 - len(art) + 1)
        return W // 2, 4

    def hit_fx(self, e, dmg, crit=False, heal=False, color=None):
        col = color or (PAL["gold"] if crit else PAL["red"])
        x, y = self.enemy_pos(e)
        txt = f"-{dmg}" if not heal else f"+{dmg}"
        if self.ui.t.fast or self.ui.t.test:
            return
        txt += "!" if crit else ""
        for i, fc in enumerate([PAL["white"], col, None]):
            self.frame(0.05, flash=(e, fc) if fc else None, popups=[(x - len(txt) // 2, y + 1 - i, txt, col)])
        self.frame(0.12, popups=[(x - len(txt) // 2, y - 1, txt, col)])
        if crit:
            self.ui.shake(3)

    def miss_fx(self, e):
        if self.ui.t.fast or self.ui.t.test:
            return
        x, y = self.enemy_pos(e)
        self.frame(0.18, popups=[(x - 2, y + 1, "miss", PAL["grey"])])

    def hurt_fx(self, dmg, crit=False):
        if self.ui.t.fast or self.ui.t.test:
            return
        for c in (PAL["red"], None):
            self.frame(0.06, hero_flash=c)
        if crit or dmg >= self.p.max_hp * 0.25:
            self.ui.flash(PAL["red"], 0.45, 2)
            self.ui.shake(3)

    def death_fx(self, e):
        if self.ui.t.fast or self.ui.t.test:
            return
        self.dying = e
        for f in (0.25, 0.5, 0.8, 1.0):
            self.frame(0.06, dissolve=(e, f))
        self.dying = None

    def roll_fx(self, target, nat):
        x, y = self.enemy_pos(target) if target else (40, 6)
        self.ui.dice(20, nat, "", x=x - 6, y=max(1, y - 1), hold=0.18)

    # ═══════════════════════════ statuses ═══════════════════════════
    def p_add(self, name, turns, power=0):
        cur = self.pst.get(name)
        if cur:
            cur[0] = max(cur[0], turns)
            cur[1] = max(cur[1], power)
        else:
            self.pst[name] = [turns, power]

    def m_add(self, m, name, turns, power=0):
        if name == "stun" and m.boss and m.flags.get("stun_resist", 0) >= 1:
            self.say(f"<dim>{esc(m.name)} shrugs off the effect.</>")
            return
        if name == "stun" and m.boss:
            m.flags["stun_resist"] = m.flags.get("stun_resist", 0) + 1
        cur = m.st.get(name)
        if cur:
            cur[0] = max(cur[0], turns)
            cur[1] = max(cur[1], power)
        else:
            m.st[name] = [turns, power]

    def dot_power(self, level=None):
        return 2 + (level or self.p.level) // 3

    # ═══════════════════════════ player damage ═══════════════════════════
    def apply_dmg(self, e, dmg, ele=None, crit=False, quiet=False):
        mult, tag = self.ele_mult(e, ele)
        dmg = max(1, int(dmg * mult))
        e.hp -= dmg
        return dmg, tag

    def weapon_attack(self, e, mult=1.0, hit=0, force_crit=False, ele=None, edice=None, status=None,
                      lifesteal=0.0, show_dice=True, verb=None):
        p = self.p
        nat = self.rng.randint(1, 20)
        if show_dice:
            self.roll_fx(e, nat)
        bless = self.rng.randint(1, 4) if "bless" in self.pst else 0
        tot = nat + p.atk_bonus + hit + bless + self.p_hit_mod()
        crit = force_crit or nat == 20
        hitp = crit or (nat != 1 and tot >= e.ac)
        w = p.weapon
        vb = verb or VERBS.get(w["base"] if w else "", "punch")
        if not hitp:
            self.say(f"You {vb} <{e.color}>{esc(e.name)}</>… <grey>miss</> <dim>({tot} vs AC {e.ac})</>")
            self.miss_fx(e)
            return 0
        n, s = p.dice
        d = roll_n(n * (2 if crit else 1), s, self.rng) + p.dmg_flat
        d = int(d * mult)
        extra = []
        if "rage" in self.pst:
            d += 2 + p.level // 4
        d += self.buff_dmg
        if "mark" in e.st:
            d += roll_n(1, 6, self.rng) + p.level // 6
            extra.append("marked")
        if p.sneak_dice and not self.sneak_used:
            sd = roll_n(p.sneak_dice, 6, self.rng)
            d += sd
            self.sneak_used = True
            extra.append(f"sneak +{sd}")
        if "weak" in self.pst:
            d = int(d * 0.75)
        d = max(1, d)
        if w and w.get("ele"):
            ed = roll_n(1, 6, self.rng) + p.level // 4
            m2, _ = self.ele_mult(e, w["ele"])
            d += int(ed * m2)
            extra.append(f"<{ELEMENTS[w['ele']][1]}>+{int(ed * m2)} {ELEMENTS[w['ele']][0]}</>")
        if edice:
            ed = roll_n(edice[0] + p.level // 5, edice[1], self.rng) + p.spell_mod // 2
            m2, tg = self.ele_mult(e, ele or "holy")
            d += int(ed * m2)
            extra.append(f"<white>+{int(ed * m2)} {ELEMENTS[ele or 'holy'][0]}</>{tg}")
        elif ele and not edice:
            pass
        if "phys" in e.res and not (w and w.get("ele")):
            d = max(1, d // 2)
            extra.append("<grey>resisted</>")
        e.hp -= d
        tagx = ("  <dim>" + ", ".join(extra) + "</>") if extra else ""
        crit_t = " <b><gold>CRITICAL!</></>" if crit else ""
        self.say(f"You {vb} <{e.color}>{esc(e.name)}</>{crit_t} <dim>({tot} vs {e.ac})</> → <b><red>{d}</></> dmg{tagx}")
        self.hit_fx(e, d, crit)
        if lifesteal:
            h = p.heal(int(d * lifesteal))
            if h:
                self.say(f"<green>You drink in {h} life.</>")
        if status and self.rng.random() <= status[2] and e.hp > 0:
            self.m_add(e, status[0], status[1], self.dot_power())
            self.say(f"<{STATUS[status[0]][1]}>{esc(e.name)} is {STATUS[status[0]][2].lower()}!</>")
        return d

    def kill_check(self, e):
        if e.flags.get("fled"):                        # a thief that got away is not a kill
            return
        if e.hp <= 0 and e not in self.defeated:
            if e is self.dragon:
                self.dragon_farewell()
            self.death_fx(e)
            self.say(f"<{e.color}>{esc(e.name)}</> <dim>falls.</>")
            self.defeated.append(e)
            self.g.on_kill(e)

    # ═══════════════════════════ player actions ═══════════════════════════
    def pick_target(self):
        al = self.alive()
        if not al:
            return None
        if len(al) == 1:
            return al[0]
        i = clamp(self.sel, 0, len(al) - 1)
        while True:
            self.draw(target=al[i], note=hints([("←→", "Choose target"), ("Enter", "Confirm"), ("Esc", "Cancel")]))
            self.ui.flush()
            k = self.ui.key()
            if k in ("left", "up", "h", "k", "a"):
                i = (i - 1) % len(al)
            elif k in ("right", "down", "l", "j", "d", "tab"):
                i = (i + 1) % len(al)
            elif k in ("enter", "space"):
                self.sel = i
                return al[i]
            elif k in ("esc", "q", "backspace"):
                return None
            elif k.isdigit() and 1 <= int(k) <= len(al):
                self.sel = i = int(k) - 1
                return al[i]

    def do_attack(self):
        e = self.pick_target()
        if not e:
            return False
        p = self.p
        n = p.attacks
        for i in range(n):
            if not e.alive:
                al = self.alive()
                if not al:
                    break
                e = al[0]
            self.weapon_attack(e, show_dice=(i == 0))
            self.kill_check(e)
        return True

    def do_defend(self):
        self.p_add("guard", 1, 4)
        got = self.p.restore_mp(self.p.c["regen"] + 2)
        self.say(f"You raise your guard. <cyan>+4 AC</> until your next turn" + (f", <cyan>+{got} {self.p.c['resource']}</>." if got else "."))
        return True

    def do_flee(self):
        p = self.p
        if not self.can_flee:
            self.say("<red>There is no escaping this fight!</>")
            return False
        nat = self.rng.randint(1, 20)
        bonus = p.m("DEX") + (p.prof if "Acrobatics" in p.c["skills"] or "Stealth" in p.c["skills"] else 0)
        dc = 9 + 2 * len(self.alive())
        self.roll_fx(None, nat)
        ok = nat + bonus >= dc or nat == 20
        self.say(f"You try to flee… <dim>(d20 {nat}{sign(bonus)} vs DC {dc})</>")
        if ok:
            self.say("<green>You break away and escape!</>")
            self.result = "flee"
        else:
            self.say("<red>They cut off your escape!</>")
        return True

    def do_item(self):
        p = self.p
        usable = [it for it in p.inv if it["k"] in ("potion", "scroll")]
        if not usable:
            self.say("<grey>You have nothing to use.</>")
            return False
        items = [(f"{name_item(it)}" + (f" <dim>x{it['q']}</>" if it.get("q", 1) > 1 else ""), True) for it in usable]
        s, W, H, bh, y0 = self.geometry()
        self.draw()
        i = self.ui.menu("Use item", items, numbered=True, dim=False, at=(W - 44, max(1, y0 - len(items) - 5)), footer="",
                         detail=lambda i: strip(" ".join(self.item_hint(usable[i]))))
        if i is None:
            return False
        return self.use_item(usable[i])

    def item_hint(self, it):
        from .items import describe
        return describe(it)[1:-1]

    def use_item(self, it):
        p = self.p
        fx = it["fx"]
        used = True
        if fx == "heal":
            h = p.heal(p.max_hp * it["mag"])
            self.say(f"You drink <b>{esc(it['n'])}</>. <green>+{h} HP</>")
        elif fx == "mana":
            h = p.restore_mp(p.max_mp * it["mag"])
            self.say(f"You drink <b>{esc(it['n'])}</>. <cyan>+{h} {p.c['resource']}</>")
        elif fx == "cure":
            for k in ("poison", "burn", "bleed"):
                self.pst.pop(k, None)
            self.say("You drink the antidote. <green>Your ailments fade.</>")
        elif fx == "buff_ac":
            self.p_add("shield", 99, it["mag"])
            self.say(f"Your skin hardens like iron. <cyan>+{it['mag']} AC</> for the battle.")
        elif fx == "buff_dmg":
            self.buff_dmg += it["mag"] + p.level // 4
            self.say(f"Power surges through you. <red>+{it['mag'] + p.level // 4} damage</> for the battle.")
        elif fx == "throw":
            e = self.pick_target()
            if not e:
                return False
            d = roll_n(2 + p.level // 4, 6, self.rng) + p.level * 2
            d, tag = self.apply_dmg(e, d, "fire")
            self.say(f"You hurl the flask at <{e.color}>{esc(e.name)}</>. <b><red>{d}</></> fire damage!{tag}")
            self.hit_fx(e, d, color=PAL["ember"])
            self.m_add(e, "burn", 3, self.dot_power())
            self.kill_check(e)
        elif fx == "escape":
            self.say("You crush the smoke pellet and vanish in a cloud!")
            self.result = "flee"
        elif fx in ("aoe_fire", "aoe_frost"):
            ele = "fire" if fx == "aoe_fire" else "frost"
            self.say(f"The scroll crumbles as {'flames' if ele == 'fire' else 'killing frost'} erupts!")
            for e in self.alive():
                d = roll_n(4 + p.level // 3, 6, self.rng) + p.level
                d, tag = self.apply_dmg(e, d, ele)
                self.say(f"  <{e.color}>{esc(e.name)}</> takes <b><red>{d}</></> {ele} damage.{tag}")
                if ele == "frost":
                    self.m_add(e, "slow", 3)
                self.hit_fx(e, d, color=PAL["ember"] if ele == "fire" else PAL["ice"])
                self.kill_check(e)
        elif fx == "mend":
            h = p.heal(p.max_hp * 0.5)
            self.say(f"Warm light knits your wounds. <green>+{h} HP</>")
        elif fx in ("reveal", "recall"):
            self.say("<grey>The scroll's magic fizzles in the heat of battle.</>")
            used = False
        if used:
            p.remove_one(it)
        return used

    def do_ability(self):
        p = self.p
        abs_ = p.abilities
        rn = p.c["resource"]
        items = []
        for a in abs_:
            ok = p.mp >= a["cost"]
            items.append((f"{a['name']}", ok, f"{a['cost']} {rn}"))
        s, W, H, bh, y0 = self.geometry()
        self.draw()
        i = self.ui.menu(f"{p.c['name']} arts", items, dim=False, at=(W - 46, max(1, y0 - len(items) - 6)), width=42, footer="",
                         detail=lambda i: abs_[i]["desc"])
        if i is None:
            return False
        return self.use_ability(abs_[i])

    def use_ability(self, a):
        p = self.p
        kind = a["kind"]
        targets = []
        single = kind in ("weapon", "spell", "debuff", "execute") and not a.get("aoe")
        if single:
            e = self.pick_target()
            if not e:
                return False
            targets = [e]
        elif a.get("aoe"):
            targets = self.alive()
            if a.get("only"):
                only = [e for e in targets if any(t in e.tags for t in a["only"])]
                targets = only or targets
        p.mp -= a["cost"]
        self.say(f"<b><{CLASSES[p.cls]['color']}>{a['name']}!</></>")
        first = True
        if kind == "weapon":
            n = a.get("n", 1)
            for e in list(targets):
                for i in range(n):
                    if not e.alive:
                        break
                    self.weapon_attack(e, a.get("mult", 1.0), a.get("hit", 0), a.get("crit", False), a.get("ele"),
                                       a.get("edice"), a.get("status"), a.get("lifesteal", 0),
                                       show_dice=first)
                    first = False
                self.kill_check(e)
            if a.get("selfstatus"):
                self.p_add(a["selfstatus"][0], a["selfstatus"][1])
        elif kind == "spell":
            n, s = a["dice"]
            n += p.level // a.get("per", 99)
            for e in targets:
                hits = a.get("hits", 1)
                if a.get("hper"):
                    hits += p.level // a["hper"]
                tot = 0
                tag = ""
                for _ in range(hits):
                    d = roll_n(n, s, self.rng) + a.get("flat", 0) + (p.spell_mod if hits == 1 else p.spell_mod // 3)
                    d, tag = self.apply_dmg(e, d, a.get("ele"))
                    tot += d
                col = ELEMENTS[a.get("ele", "force")][1]
                self.say(f"  <{e.color}>{esc(e.name)}</> takes <b><{col}>{tot}</></> {ELEMENTS[a['ele']][0]} damage.{tag}")
                self.hit_fx(e, tot, color=PAL[col])
                st = a.get("status")
                if st and e.hp > 0 and self.rng.random() <= st[2]:
                    self.m_add(e, st[0], st[1], self.dot_power())
                    self.say(f"  <{STATUS[st[0]][1]}>{esc(e.name)} is {STATUS[st[0]][2].lower()}!</>")
                self.kill_check(e)
            if a.get("heal"):
                h = p.heal(p.max_hp * a["heal"])
                self.say(f"  <green>You are mended for {h} HP.</>")
        elif kind == "heal":
            amt = p.max_hp * a.get("pct", 0) + roll_n(a["dice"][0] + p.level // 6, a["dice"][1], self.rng)
            h = p.heal(amt)
            self.say(f"  <green>You recover {h} HP.</>")
            self.frame(0.2)
            for b, t, pw in a.get("buffs", []):
                self.p_add(b, t, pw)
        elif kind == "buff":
            for b, t, pw in a["buffs"]:
                pw2 = pw + (p.level // 8 if b == "shield" else 0)
                self.p_add(b, t, pw2)
                self.say(f"  <{STATUS[b][1]}>You are {STATUS[b][2].lower()}!</>")
            if a.get("heal"):
                h = p.heal(p.max_hp * a["heal"])
                self.say(f"  <green>+{h} HP</>")
        elif kind == "debuff":
            for e in targets:
                st = a["status"]
                if self.rng.random() <= (st[2] if st[2] else 1.0):
                    self.m_add(e, st[0], st[1], self.dot_power())
                    self.say(f"  <{STATUS[st[0]][1]}>{esc(e.name)} is {STATUS[st[0]][2].lower()}!</>")
                else:
                    self.say(f"  <grey>{esc(e.name)} resists.</>")
                if a.get("dmg"):
                    d = roll_n(a["dmg"][0] + p.level // 4, a["dmg"][1], self.rng) + p.dmg_flat
                    e.hp -= d
                    self.say(f"  <b><red>{d}</></> damage.")
                    self.hit_fx(e, d)
                self.kill_check(e)
        elif kind == "execute":
            e = targets[0]
            if not e.boss and e.hp <= e.max_hp * 0.4:
                self.say(f"  <b><red>{esc(e.name)} is struck down without a sound.</></>")
                e.hp = 0
                self.hit_fx(e, 9999, crit=True)
            else:
                self.weapon_attack(e, 3.0, 3, False, show_dice=True)
            self.kill_check(e)
        return True

    # ═══════════════════════════ enemy AI ═══════════════════════════
    def tick_dots(self, who, is_player):
        """Apply damage-over-time. Returns True if the target died."""
        if is_player:
            for k in ("poison", "burn", "bleed"):
                if k in self.pst:
                    pw = self.pst[k][1] or 2
                    d = max(1, pw + self.rng.randint(0, 2))
                    self.p.hp -= d
                    self.say(f"<{STATUS[k][1]}>You suffer {d} {STATUS[k][2].lower().replace('ed', '').replace('ing', '')} damage.</>")
            return self.p.hp <= 0
        e = who
        for k in ("poison", "burn", "bleed"):
            if k in e.st:
                pw = e.st[k][1] or 2
                d = max(1, pw + self.rng.randint(0, 2))
                e.hp -= d
                self.say(f"<{STATUS[k][1]}>{esc(e.name)} suffers {d} from {k}.</>")
        if "regen" in e.sp and e.hp > 0 and not ("burn" in e.st):
            h = min(e.max_hp - e.hp, max(1, int(e.max_hp * 0.03)))
            if h:
                e.hp += h
                self.say(f"<green>{esc(e.name)} regenerates {h} HP.</>")
        return e.hp <= 0

    def tick_end(self, st):
        for k in list(st):
            st[k][0] -= 1
            if st[k][0] <= 0:
                del st[k]

    def enemy_turn(self, e):
        p = self.p
        if e.hp <= 0:
            return
        if self.tick_dots(e, False):
            self.kill_check(e)
            return
        if "stun" in e.st:
            self.say(f"<{STATUS['stun'][1]}>{esc(e.name)} is stunned and loses its turn.</>")
            self.tick_end(e.st)
            return
        if "fear" in e.st and self.rng.random() < 0.5:
            self.say(f"<purple>{esc(e.name)} cowers in fear.</>")
            self.tick_end(e.st)
            return
        # boss phase specials
        if "summon" in "".join(e.sp) and not e.flags.get("summoned") and e.hp <= e.max_hp * 0.6:
            sid = [s for s in e.sp if s.startswith("summon:")][0][7:]
            from .entities import Monster
            m = Monster(sid, max(1, e.level - 2), rng=self.rng)
            m.name = f"Summoned {m.name}"
            self.enemies.append(m)
            e.flags["summoned"] = True
            self.say(f"<b><purple>{esc(e.name)} calls forth {esc(m.name)}!</></>")
            self.frame(0.3)
            return
        if "rage" in e.sp and not e.flags.get("raged") and e.hp <= e.max_hp * 0.5:
            e.flags["raged"] = True
            self.say(f"<b><red>{esc(e.name)} flies into a rage!</></>")
            self.ui.flash(PAL["red"], 0.3, 2)
        if "fear" in e.sp and not e.flags.get("howled") and self.rng.random() < 0.5:
            e.flags["howled"] = True
            self.say(f"<purple>{esc(e.name)} lets out a blood-freezing shriek!</>")
            if self.rng.randint(1, 20) + p.m("WIS") < 11 + e.level // 3:
                self.p_add("fear", 2)
                self.say("<purple>  You are terrified! (-3 to hit)</>")
            else:
                self.say("<green>  You steel your nerves.</>")
            return
        br = e.breath
        if br and e.cd.get("breath", 0) <= 0 and (self.round > 1 or e.boss):
            e.cd["breath"] = 3
            self.breath(e, br)
            self.tick_end(e.st)
            return
        for k in e.cd:
            e.cd[k] -= 1
        n = e.multi
        atk_pen = -2 if "slow" in e.st else 0
        verbs = MON_VERBS.get(e.tags[0] if e.tags else "beast", MON_VERBS["beast"])
        for i in range(n):
            if p.hp <= 0:
                break
            nat = self.rng.randint(1, 20)
            tot = nat + e.atk + atk_pen
            ac = self.p_ac()
            crit = nat == 20
            hit = crit or (nat != 1 and tot >= ac)
            vb = self.rng.choice(verbs)
            if not hit:
                self.say(f"<{e.color}>{esc(e.name)}</> {vb} you… <grey>misses</> <dim>({tot} vs AC {ac})</>")
                continue
            d = roll_n(e.dice[0] * (2 if crit else 1), e.dice[1], self.rng) + e.flat
            if e.flags.get("raged"):
                d = int(d * 1.3)
            if "weak" in e.st:
                d = int(d * 0.7)
            if "rage" in self.pst:
                d = int(d * 0.75)
            d = max(1, d)
            p.hp -= d
            crit_t = " <b><gold>CRITICAL!</></>" if crit else ""
            self.say(f"<{e.color}>{esc(e.name)}</> {vb} you{crit_t} <dim>({tot} vs {ac})</> → <b><red>{d}</></> dmg")
            self.hurt_fx(d, crit)
            if p.c["resource"] == "Fury":
                p.restore_mp(1)
            if p.hp <= 0:
                break
            self.on_hit_effects(e, d)
        self.tick_end(e.st)

    def on_hit_effects(self, e, d):
        p, sp, r = self.p, e.sp, self.rng.random()
        pw = self.dot_power(e.level)
        if "poison" in sp and r < 0.4:
            self.p_add("poison", 3, pw)
            self.say("  <lime>You are poisoned!</>")
        elif "bleed" in sp and r < 0.4:
            self.p_add("bleed", 3, pw)
            self.say("  <red>You are bleeding!</>")
        elif "burn" in sp and r < 0.4:
            self.p_add("burn", 3, pw)
            self.say("  <ember>You catch fire!</>")
        elif "stun" in sp and r < 0.22:
            self.p_add("stun", 1)
            self.say("  <gold>You are stunned!</>")
        elif "slow" in sp and r < 0.4:
            self.p_add("slow", 3)
            self.say("  <ice>You are slowed!</>")
        elif "corrode" in sp and r < 0.5:
            self.p_add("weak", 3)
            self.say("  <grey>Your gear corrodes: weakened!</>")
        elif "curse" in sp and r < 0.4:
            self.p_add("weak", 3)
            self.say("  <purple>A curse saps your strength!</>")
        elif "fear" in sp and r < 0.15:
            self.p_add("fear", 2)
            self.say("  <purple>You are terrified!</>")
        if "drain" in sp:
            h = min(e.max_hp - e.hp, d // 2)
            if h > 0:
                e.hp += h
                self.say(f"  <purple>{esc(e.name)} drains {h} life.</>")
        if "steal" in sp and r > 0.55 and p.gold > 0:
            amt = min(p.gold, self.rng.randint(5, 20) + e.level * 6)
            p.gold -= amt
            self.say(f"  <gold>{esc(e.name)} snatches {amt} gold from your purse and bolts!</>")
            e.hp = 0
            e.flags["fled"] = True
            self.enemies.remove(e)
            self.fled_with.append(amt)

    def breath(self, e, ele):
        p = self.p
        col = ELEMENTS[ele][1]
        self.say(f"<b><{col}>{esc(e.name)} unleashes {BREATH_TEXT.get(ele, 'a torrent of power')}!</></>")
        self.ui.flash(PAL[col], 0.6, 3)
        d = roll_n(3 + e.level // 3, 6, self.rng) + e.flat // 2
        if "rage" in self.pst:
            d = int(d * 0.75)
        if "shield" in self.pst and self.pst["shield"][0] < 90:
            d -= self.pst["shield"][1]
        d = max(1, d)
        p.hp -= d
        self.say(f"  You take <b><red>{d}</></> {ELEMENTS[ele][0]} damage!")
        self.hurt_fx(d, True)
        if p.hp > 0:
            eff = {"fire": ("burn", 3), "frost": ("slow", 3), "poison": ("poison", 4), "acid": ("weak", 3),
                   "lightning": ("stun", 1), "dark": ("weak", 3)}.get(ele)
            if eff and self.rng.random() < 0.5:
                self.p_add(eff[0], eff[1], self.dot_power(e.level))
                self.say(f"  <{STATUS[eff[0]][1]}>You are {STATUS[eff[0]][2].lower()}!</>")

    # ═══════════════════════════ main loop ═══════════════════════════
    def run(self, resume=False):
        res = self._run_inner(resume)
        if res == "dead" and self.dragon:
            st = self.dragon_state()
            st["hero_deaths"] = st.get("hero_deaths", 0) + 1
        return res

    def dragon_state(self):
        """This dragon's memory of you: per-lair, keyed on the lair feature (always valid — dragons only fight inside their lair)."""
        f = self.g.dungeon.f
        return self.g.fstate.setdefault(f.key, {}).setdefault("dragon", {})

    def dragon_greeting(self):
        st = self.dragon_state()
        story = Story(self.ui, esc(self.dragon.name), art=get_art("dragon"), art_color=PAL.get(self.dragon.color, PAL["red"]),
                      color=PAL.get(self.dragon.color, PAL["red"]))
        for ln in greet_lines(self.g, self.dragon, st):
            story.say(ln)
        st["meetings"] = st.get("meetings", 0) + 1
        story.pause()
        story.close()

    def dragon_farewell(self):
        st = self.dragon_state()
        story = Story(self.ui, esc(self.dragon.name), art=get_art("dragon"), art_color=PAL.get(self.dragon.color, PAL["red"]),
                      color=PAL.get(self.dragon.color, PAL["blood"]))
        for ln in death_lines(self.g, self.dragon, st):
            story.say(ln)
        st["dragon_deaths"] = st.get("dragon_deaths", 0) + 1
        story.pause()
        story.close()

    def _run_inner(self, resume=False):
        p = self.p
        mon_names = ", ".join(f"<{e.color}>{esc(e.name)}</>" for e in self.enemies)
        if resume:
            self.ambush = False
            self.say("<amber>— You return to the battle —</>")
        else:
            self.say(f"<b>{mon_names}</> {'blocks' if len(self.enemies) == 1 else 'block'} your path!" if not self.ambush
                     else f"<b><red>Ambush!</></> {mon_names} spring from hiding!")
        self.ui.dissolve()
        self.draw()
        self.ui.reveal(5)
        if self.dragon and not resume:
            self.dragon_greeting()
        if self.ambush:
            self.ambush = False
            self.round = 1
            for e in list(self.enemies):
                self.enemy_turn(e)
                self.kill_check(e)
                self.frame(0.15)
                if p.hp <= 0:
                    return self.finish("dead")
            if not self.alive():                       # e.g. a thief grabbed your gold and bolted
                return self.finish("win" if self.defeated else "gone")
        while True:
            self.round += 1
            skip, self.resume_skip = self.resume_skip, False
            if not skip:
                self.sneak_used = False
                # start of player turn
                self.pst.pop("guard", None)
            if not skip and self.tick_dots(None, True):
                return self.finish("dead")
            if "stun" in self.pst and not skip:
                self.say("<gold>You are stunned and lose your turn!</>")
                self.tick_end(self.pst)
                self.frame(0.4)
            else:
                acted = False
                cursor = 0
                while not acted and self.result is None:
                    menu = [("<b>A</>ttack", True), (f"<b>S</>kills <dim>({len(p.abilities)})</>", True),
                            ("<b>I</>tem", True), ("<b>D</>efend", True),
                            ("<b>F</>lee" + ("" if self.can_flee else " <dim>(no escape)</>"), self.can_flee)]
                    self.draw(menu=menu, cursor=cursor, note=hints([("↑↓", "Choose"), ("Enter", "Act"), ("A S I D F", "Hotkeys"), ("C", "Sheet"), ("Esc", "Menu")]))
                    self.ui.flush()
                    k = self.ui.key()
                    if k in ("up", "k"):
                        cursor = (cursor - 1) % 5
                    elif k in ("down", "j"):
                        cursor = (cursor + 1) % 5
                    elif k in ("1", "2", "3", "4", "5"):
                        cursor = int(k) - 1
                        k = "enter"
                    elif k in ("a", "s", "i", "d", "f"):
                        cursor = "asidf".index(k)
                        k = "enter"
                    elif k == "c":
                        self.g.character_sheet()
                        continue
                    elif k == "esc":
                        self.g.game_menu(in_combat=True)
                        continue
                    if k in ("enter", "space", "l", "right"):
                        acted = [self.do_attack, self.do_ability, self.do_item, self.do_defend, self.do_flee][cursor]()
                if self.result == "flee":
                    return self.finish("flee")
            if not self.alive():
                return self.finish("win")
            # enemy phase
            self.frame(0.1)
            for e in list(self.enemies):
                if e.hp > 0:
                    self.enemy_turn(e)
                    self.kill_check(e)
                    if p.hp <= 0:
                        return self.finish("dead")
                    self.frame(0.12)
            if not self.alive():
                return self.finish("win" if self.defeated else "gone")
            # end of round
            self.tick_end(self.pst)
            p.restore_mp(p.c["regen"])

    def finish(self, result):
        self.result = result
        return result
