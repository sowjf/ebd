"""Widgets: panels, bars, menus, story panels, dice, transitions."""
import random

from .term import PAL, mix, scale, vlen, wrap, parse, A_BOLD, A_DIM, esc
from .util import clamp

PART = " ▏▎▍▌▋▊▉█"


def hp_color(f):
    if f > 0.6:
        return mix(PAL["amber"], PAL["green"], (f - 0.6) / 0.4)
    if f > 0.3:
        return mix(PAL["red"], PAL["amber"], (f - 0.3) / 0.3)
    return PAL["red"]


def hints(pairs):
    return "  ".join(f"<dim>[</><gold>{k}</><dim>]</> <grey>{v}</>" for k, v in pairs)


def fit_hints(text, width):
    """Drop trailing hint items until the line fits."""
    parts = text.split("  ")
    while len(parts) > 1 and vlen("  ".join(parts)) > width - 2:
        parts.pop()
    return "  ".join(parts)


def bar(s, x, y, w, cur, mx, fg, bg=None, label=None, lfg=None):
    """Sub-cell precision bar. Optional centered label overlays the bar."""
    bg = PAL["dark"] if bg is None else bg
    f = 0 if mx <= 0 else clamp(cur / mx, 0, 1)
    if cur > 0 and f * w < 0.15:
        f = 0.15 / w
    cells = f * w
    full = int(cells)
    part = int((cells - full) * 8)
    s.put(x, y, " " * w, None, bg)
    if full:
        s.put(x, y, "█" * full, fg, bg)
    if full < w and part:
        s.put(x + full, y, PART[part], fg, bg)
    if label:
        lx = x + (w - len(label)) // 2
        for i, ch in enumerate(label):
            idx = y * s.w + lx + i
            if 0 <= lx + i < s.w:
                _, cfg, cbg, _ = s.cells[idx]
                filled = (lx + i - x) < int(cells + 0.5)
                if filled and lfg is None:
                    s.cells[idx] = (ch, 0x0c0a10, fg, A_BOLD)          # dark text on the fill colour
                else:
                    s.cells[idx] = (ch, lfg if lfg is not None else PAL["white"], cbg, A_BOLD)


def pips(n, mx, on="♦", off="◇", fg=None, ofg=None):
    return f"<{fg or 'gold'}>{on * n}</><dim>{off * (mx - n)}</>"


def rarity_color(r):
    return ["grey", "green", "blue", "purple", "amber"][clamp(r, 0, 4)]


class UI:
    def __init__(self, term):
        self.t = term
        self.s = term.screen

    # ------------------------------------------------------------- helpers
    @property
    def sc(self):
        return self.t.screen

    def begin(self):
        self.s = self.t.begin()
        return self.s

    def restore(self, snap):
        s = self.t.screen
        if len(snap) == len(s.cells):
            s.restore(snap)
        else:
            s.clear()

    def frame(self, title=None, footer=None, style="double", clear=True):
        s = self.begin()
        if clear:
            s.clear()
        s.box(0, 0, s.w, s.h - 1, style, PAL["edge"], PAL["bg"], title)
        if footer:
            s.center(s.h - 1, fit_hints(footer, s.w))
        return s

    def panel(self, x, y, w, h, title=None, style="single", fg=None, bg=None, tfg=None):
        self.sc.box(x, y, w, h, style, PAL["edge2"] if fg is None else fg, PAL["panel"] if bg is None else bg, title, tfg)

    def flush(self):
        self.t.flush()

    def key(self, timeout=None):
        return self.t.get_key(timeout)

    def wait_key(self, keys=None):
        while True:
            k = self.key()
            if k == "resize":
                return k
            if keys is None or k in keys:
                return k

    # ------------------------------------------------------------- transitions
    def reveal(self, steps=6, dt=0.03):
        """Fade the freshly drawn scene in from black."""
        if self.t.fast or self.t.test:
            return
        s = self.sc
        snap = s.snapshot()
        for i in range(1, steps):
            s.restore(snap)
            s.dim(i / steps)
            self.flush()
            self.t.sleep(dt, False)
        s.restore(snap)
        self.flush()

    def fade_out(self, steps=5, dt=0.03, color=None):
        if self.t.fast or self.t.test:
            return
        s = self.sc
        snap = s.snapshot()
        for i in range(1, steps + 1):
            s.restore(snap)
            s.dim(1 - i / steps)
            self.flush()
            self.t.sleep(dt, False)

    def dissolve(self, steps=9, dt=0.022, color=None, glyphs="░▒▓█"):
        """Random-cell dissolve into a solid color (encounter transitions)."""
        if self.t.fast or self.t.test:
            return
        s = self.sc
        color = PAL["bg"] if color is None else color
        idx = list(range(s.w * s.h))
        random.shuffle(idx)
        per = len(idx) // steps + 1
        for st in range(steps):
            for i in idx[st * per:(st + 1) * per]:
                _, fg, bg, at = s.cells[i]
                g = glyphs[min(len(glyphs) - 1, st * len(glyphs) // steps)]
                s.cells[i] = (g, mix(bg, color, 0.6), color if st > steps // 2 else mix(bg, color, 0.5), 0)
            self.flush()
            self.t.sleep(dt, False)
        s.fill(0, 0, s.w, s.h, " ", None, color)
        self.flush()

    def flash(self, color, t=0.5, frames=2, dt=0.04):
        """Brief screen tint."""
        if self.t.fast or self.t.test:
            return
        s = self.sc
        snap = s.snapshot()
        for i in range(frames):
            s.restore(snap)
            s.tint(color, t * (1 - i / (frames + 1)))
            self.flush()
            self.t.sleep(dt, False)
        s.restore(snap)
        self.flush()

    def shake(self, frames=4, dt=0.035, amp=1):
        if self.t.fast or self.t.test:
            return
        s = self.sc
        snap = s.snapshot()
        w, h = s.w, s.h
        for i in range(frames):
            dx = amp if i % 2 == 0 else -amp
            s.cells = [snap[(y * w + (x - dx) % w)] for y in range(h) for x in range(w)]
            self.flush()
            self.t.sleep(dt, False)
        s.restore(snap)
        self.flush()

    # ------------------------------------------------------------- dice
    def dice(self, sides, final, label="", x=None, y=None, color=None, hold=0.45):
        """Animated die popup drawn over the current screen."""
        s = self.sc
        if self.t.fast or self.t.test:
            return
        snap = s.snapshot()
        w = 13
        x = (s.w - w) // 2 if x is None else clamp(x, 1, s.w - w - 1)
        y = s.h // 2 - 3 if y is None else y
        crit = sides == 20 and final == 20
        fumble = sides == 20 and final == 1
        col = color or (PAL["gold"] if crit else PAL["red"] if fumble else PAL["white"])
        frames = 8
        for i in range(frames + 1):
            s.restore(snap)
            val = final if i == frames else random.randint(1, sides)
            s.box(x, y, w, 5, "round", col if i == frames else PAL["grey"], PAL["panel"])
            s.center(y + 2, f"<b>{val:>2}</>", col if i == frames else PAL["silver"], PAL["panel"], x, w)
            s.put(x + 2, y, f"d{sides}", PAL["dim"], PAL["panel"])
            if label:
                s.center(y + 5, f"<grey>{label}</>", None, None, x - 8, w + 16)
            self.flush()
            if i < frames and self.t.sleep(0.045 + i * 0.008):
                val_i = frames - 1      # key pressed: jump to the final face
                s.restore(snap)
                s.box(x, y, w, 5, "round", col, PAL["panel"])
                s.center(y + 2, f"<b>{final:>2}</>", col, PAL["panel"], x, w)
                s.put(x + 2, y, f"d{sides}", PAL["dim"], PAL["panel"])
                self.flush()
                break
        self.t.sleep(hold)
        s.restore(snap)

    # ------------------------------------------------------------- menus
    def menu(self, title, items, *, detail=None, width=None, start=0, cancel=True, numbered=True,
             subtitle=None, footer=None, dim=True, at=None, side=None, detail_lines=5):
        """Modal list. items: str | (label, enabled) | (label, enabled, right_text).
        Returns chosen index or None on cancel."""
        s = self.begin()
        norm = []
        for it in items:
            if isinstance(it, str):
                norm.append((it, True, ""))
            elif len(it) == 2:
                norm.append((it[0], it[1], ""))
            else:
                norm.append(it)
        if not norm:
            return None
        snap = s.snapshot()
        if dim:
            s.dim(0.4)
            snap = s.snapshot()
        sel = clamp(start, 0, len(norm) - 1)
        top = 0
        while True:
            s = self.begin()
            self.restore(snap)
            maxrows = max(3, s.h - 10 - (4 if detail else 0) - (2 if subtitle else 0))
            lw = max(vlen(l) + (4 if numbered else 2) + (vlen(r) + 2 if r else 0) for l, _, r in norm)
            w = clamp(max(lw + 6, vlen(title) + 8, 30, (width or 0)), 20, s.w - 4)
            det_lines = []
            if detail:
                d = detail(sel)
                det_lines = wrap(d, w - 4) if d else []
                det_lines = det_lines[:detail_lines]
            rows = min(len(norm), maxrows)
            h = rows + 2 + (len(det_lines) + 1 if det_lines else 0) + (len(wrap(subtitle, w - 4)) + 1 if subtitle else 0)
            x, y = (at if at else ((s.w - w) // 2, (s.h - h) // 2 - 1))
            s.box(x, y, w, h, "round", PAL["edge"], PAL["panel"], title)
            yy = y + 1
            if subtitle:
                for ln in wrap(subtitle, w - 4):
                    s.puts(x + 2, yy, ln, PAL["grey"], PAL["panel"])
                    yy += 1
                yy += 0
            if sel < top:
                top = sel
            if sel >= top + rows:
                top = sel - rows + 1
            for r in range(rows):
                i = top + r
                lab, en, right = norm[i]
                cur = i == sel
                bgc = PAL["panel2"] if cur else PAL["panel"]
                s.fill(x + 1, yy, w - 2, 1, " ", None, bgc)
                num = f"{i + 1}" if numbered and i < 9 else " "
                mark = "▸" if cur else " "
                fg = PAL["gold"] if cur else (PAL["white"] if en else PAL["dim"])
                s.put(x + 2, yy, mark, PAL["gold"], bgc)
                if numbered:
                    s.put(x + 4, yy, num, PAL["dim"] if not cur else PAL["amber"], bgc)
                s.puts(x + (6 if numbered else 4), yy, lab if en else strip_markup(lab), fg, bgc,
                       maxw=w - 8 - (vlen(right) + 1 if right else 0))
                if right:
                    s.puts(x + w - 2 - vlen(right), yy, right, PAL["grey"] if en else PAL["dim"], bgc)
                yy += 1
            if len(norm) > rows:
                s.put(x + w - 2, y + 1 + (1 if subtitle else 0), "▲" if top > 0 else " ", PAL["dim"], PAL["panel"])
                s.put(x + w - 2, y + h - 2, "▼" if top + rows < len(norm) else " ", PAL["dim"], PAL["panel"])
            if det_lines:
                s.hline(x + 1, yy, w - 2, "─", PAL["edge2"], PAL["panel"])
                yy += 1
                for ln in det_lines:
                    s.puts(x + 2, yy, ln, PAL["grey"], PAL["panel"])
                    yy += 1
            fh = footer if footer is not None else hints([("↑↓", "Choose"), ("Enter", "Select")] + ([("Esc", "Back")] if cancel else []))
            if fh:
                s.center(y + h, fh, None, None)
            self.flush()
            k = self.key()
            if k in ("up", "k", "w"):
                sel = (sel - 1) % len(norm)
            elif k in ("down", "j", "s"):
                sel = (sel + 1) % len(norm)
            elif k == "home":
                sel = 0
            elif k == "end":
                sel = len(norm) - 1
            elif k == "pgup":
                sel = max(0, sel - rows)
            elif k == "pgdn":
                sel = min(len(norm) - 1, sel + rows)
            elif k in ("enter", "space", "l", "right"):
                if norm[sel][1]:
                    self.restore(snap)
                    return sel
            elif k in ("esc", "q", "left", "backspace") and cancel:
                self.restore(snap)
                return None
            elif numbered and len(k) == 1 and k in "123456789":
                i = int(k) - 1
                if i < len(norm) and norm[i][1]:
                    self.restore(snap)
                    return i
                if i < len(norm):
                    sel = i

    def confirm(self, text, default=False, title="Confirm"):
        r = self.menu(title, ["Yes", "No"], subtitle=text, start=1 if not default else 0, numbered=False)
        return r == 0

    def message(self, title, text, color=None):
        st = Story(self, title, color=color)
        st.say(text)
        st.pause()
        st.close()

    def pager(self, title, lines, footer=None):
        """Scrollable full-width text (markup lines)."""
        pos = 0
        while True:
            s = self.frame(title, footer or hints([("↑↓", "Scroll"), ("Esc", "Close")]))
            rows = s.h - 4
            for i in range(rows):
                if pos + i < len(lines):
                    s.puts(3, 2 + i, lines[pos + i], PAL["white"], None, maxw=s.w - 6)
            if len(lines) > rows:
                s.put(s.w - 3, 2, "▲" if pos > 0 else " ", PAL["dim"])
                s.put(s.w - 3, s.h - 3, "▼" if pos + rows < len(lines) else " ", PAL["dim"])
            self.flush()
            k = self.key()
            if k in ("up", "k", "w"):
                pos = max(0, pos - 1)
            elif k in ("down", "j", "s"):
                pos = min(max(0, len(lines) - rows), pos + 1)
            elif k == "pgup":
                pos = max(0, pos - rows + 1)
            elif k == "pgdn":
                pos = min(max(0, len(lines) - rows), pos + rows - 1)
            elif k in ("esc", "q", "enter", "space"):
                return

    def text_input(self, title, prompt, default="", maxlen=18):
        s = self.begin()
        snap = s.snapshot()
        s.dim(0.4)
        snap = s.snapshot()
        val = default
        blink = 0
        deb, self.t.debounce = self.t.debounce, 0          # typing: never drop letters
        try:
            return self._text_input_loop(title, prompt, val, maxlen, snap, blink)
        finally:
            self.t.debounce = deb

    def _text_input_loop(self, title, prompt, val, maxlen, snap, blink):
        while True:
            s = self.begin()
            self.restore(snap)
            w = max(44, vlen(prompt) + 8)
            x, y = (s.w - w) // 2, s.h // 2 - 3
            s.box(x, y, w, 7, "round", PAL["edge"], PAL["panel"], title)
            s.puts(x + 3, y + 2, prompt, PAL["grey"], PAL["panel"])
            s.fill(x + 3, y + 4, w - 6, 1, " ", None, PAL["dark"])
            s.put(x + 4, y + 4, val, PAL["gold"], PAL["dark"], A_BOLD)
            if blink % 2 == 0:
                s.put(x + 4 + len(val), y + 4, "▌", PAL["amber"], PAL["dark"])
            s.center(y + 7, hints([("Enter", "Confirm"), ("Esc", "Cancel")]))
            self.flush()
            k = self.key(0.5)
            blink += 1
            if k is None:
                continue
            if k == "enter" and val.strip():
                self.restore(snap)
                return val.strip()
            if k == "esc":
                self.restore(snap)
                return None
            if k == "backspace":
                val = val[:-1]
            elif k == "space":
                if len(val) < maxlen:
                    val += " "
            elif len(k) == 1 and k.isprintable() and len(val) < maxlen and k not in "<>":
                val += k


def strip_markup(t):
    from .term import strip
    return strip(t)


class Story:
    """Interactive-fiction style panel: art on top, typed paragraphs, choice list at the bottom."""

    def __init__(self, ui, title, art=None, art_color=None, color=None, subtitle=None, width=None):
        self.ui = ui
        self.title = title
        self.art = art or []
        self.art_color = art_color
        self.color = color if color is not None else PAL["edge"]
        self.subtitle = subtitle
        self.paras = []                      # list of wrapped-line lists
        self.reveal = 0                      # visible chars revealed in last paragraph
        self.width = width
        s = ui.begin()
        s.dim(0.35)
        self.snap = s.snapshot()
        self.choices = None
        self.sel = 0
        self.h_seen = 0
        self.quiet = False            # True right after a choice while nothing new has been said

    # -- drawing ----------------------------------------------------------
    def _need(self, w):
        n = 4 + (1 if self.subtitle else 0) + (len(self.art) + 1 if self.art else 0)
        n += sum(len(p) for p in self.paras) + max(0, len(self.paras) - 1)
        n += (len(self.choices) + 1) if self.choices else 1
        return n

    def _geom(self):
        s = self.ui.begin()
        w = min(s.w - 4, self.width or 80)
        cap = min(s.h - 2, 30)
        self.h_seen = max(self.h_seen, min(cap, max(14, self._need(w))))
        h = self.h_seen
        return s, (s.w - w) // 2, (s.h - h) // 2, w, h

    def draw(self, typing=False):
        s, x, y, w, h = self._geom()
        self.ui.restore(self.snap)
        s.box(x, y, w, h, "double", self.color, PAL["panel"], self.title)
        iw = w - 6
        yy = y + 1
        if self.subtitle:
            s.center(yy, f"<grey><i>{self.subtitle}</></>", None, PAL["panel"], x, w)
            yy += 1
        if self.art:
            for ln in self.art:
                s.puts(x + max(3, (w - max(vlen(a) for a in self.art)) // 2), yy, ln,
                       self.art_color or PAL["silver"], PAL["panel"])
                yy += 1
            s.hline(x + 2, yy, w - 4, "─", PAL["edge2"], PAL["panel"])
            yy += 1
        nch = len(self.choices) if self.choices else 0
        foot = (nch + 1) if nch else 1
        text_rows = (y + h - 1) - yy - foot
        # flatten paragraphs → rows (blank line between paragraphs)
        rows = []
        for pi, p in enumerate(self.paras):
            if pi:
                rows.append(None)
            rows.extend(p)
        # reveal accounting for last paragraph
        last = self.paras[-1] if self.paras else []
        n_last = len(last)
        vis_rows = rows[-text_rows:] if text_rows > 0 else []
        # count characters available in the last paragraph rows
        remaining = self.reveal if typing else 10 ** 9
        start_idx = len(rows) - len(vis_rows)
        last_start = len(rows) - n_last
        yy_t = yy
        for ri, row in enumerate(vis_rows):
            gi = start_idx + ri
            if row is None:
                yy_t += 1
                continue
            txt = row
            if gi >= last_start and typing:
                n = vlen(row)
                if remaining <= 0:
                    yy_t += 1
                    continue
                txt = _cut_markup(row, remaining)
                remaining -= n
            s.puts(x + 3, yy_t, txt, PAL["white"], PAL["panel"], maxw=iw)
            yy_t += 1
        if start_idx > 0:
            s.put(x + w - 3, yy, "▲", PAL["dim"], PAL["panel"])
        if nch:
            base = y + h - 1 - nch - 1
            s.hline(x + 2, base, w - 4, "─", PAL["edge2"], PAL["panel"])
            for i, (lab, en) in enumerate(self.choices):
                cur = i == self.sel
                bgc = PAL["panel2"] if cur else PAL["panel"]
                s.fill(x + 2, base + 1 + i, w - 4, 1, " ", None, bgc)
                s.put(x + 3, base + 1 + i, "▸" if cur else " ", PAL["gold"], bgc)
                s.put(x + 5, base + 1 + i, f"{i + 1}", PAL["amber"] if cur else PAL["dim"], bgc)
                s.puts(x + 7, base + 1 + i, lab if en else strip_markup(lab),
                       PAL["gold"] if cur else (PAL["white"] if en else PAL["dim"]), bgc, maxw=w - 10)
        self._last_geom = (x, y, w, h)

    # -- content -------------------------------------------------------------
    def say(self, text, speed=1.0):
        s, x, y, w, h = self._geom()
        self.quiet = False
        lines = wrap(text, w - 6)
        self.paras.append(lines)
        total = sum(vlen(l) for l in lines)
        self.reveal = 0
        if self.ui.t.test or self.ui.t.fast:
            self.reveal = total
        step = max(2, int(3 * speed))
        while self.reveal < total:
            self.draw(typing=True)
            self.ui.flush()
            self.reveal += step
            if self.ui.t.sleep(0.012):
                break
        self.reveal = total
        self.draw()
        self.ui.flush()

    def line(self, text):
        s, x, y, w, h = self._geom()
        self.quiet = False
        self.paras.append(wrap(text, w - 6))
        self.reveal = 10 ** 6

    def replace_last(self, text):
        s, x, y, w, h = self._geom()
        if self.paras:
            self.paras[-1] = wrap(text, w - 6)
        else:
            self.line(text)
        self.draw()
        self.ui.flush()

    def check(self, label, bonus, dc, rng=random, adv=False):
        """Skill check with a rolling-number animation. Returns (success, natural, total)."""
        nat = rng.randint(1, 20)
        if adv:
            nat = max(nat, rng.randint(1, 20))
        total = nat + bonus
        self.line(f"<grey>{label}…</>")
        if not (self.ui.t.test or self.ui.t.fast):
            for i in range(9):
                self.replace_last(f"<grey>{label}</> <dim>d20</> <silver>{rng.randint(1, 20):>2}</>")
                if self.ui.t.sleep(0.05 + i * 0.01):
                    break
        ok = nat == 20 or (nat != 1 and total >= dc)
        col = "gold" if nat == 20 else "red" if nat == 1 else "green" if ok else "red"
        verdict = "CRITICAL!" if nat == 20 else "FUMBLE!" if nat == 1 else "Success" if ok else "Failure"
        b = f" {'+' if bonus >= 0 else '-'} {abs(bonus)}" if bonus else ""
        self.replace_last(f"<grey>{label}</> <dim>d20</> <b><{col}>{nat}</></>{b} = <b>{total}</> "
                          f"<dim>vs DC {dc}</>  <b><{col}>{verdict}</></>")
        return ok, nat, total

    def ask(self, choices, echo=True):
        """choices: list[str | (str, enabled)]. Returns index."""
        self.choices = [(c, True) if isinstance(c, str) else (c[0], c[1]) for c in choices]
        self.sel = next((i for i, c in enumerate(self.choices) if c[1]), 0)
        while True:
            self.draw()
            self.ui.flush()
            k = self.ui.key()
            n = len(self.choices)
            if k in ("up", "k", "w"):
                self.sel = (self.sel - 1) % n
            elif k in ("down", "j", "s"):
                self.sel = (self.sel + 1) % n
            elif k in ("enter", "space") and self.choices[self.sel][1]:
                break
            elif len(k) == 1 and k in "123456789" and int(k) <= n and self.choices[int(k) - 1][1]:
                self.sel = int(k) - 1
                break
        idx = self.sel
        lab = strip_markup(self.choices[idx][0])
        self.choices = None
        if echo:
            self.line(f"<gold>▸ {esc(lab)}</>")
        self.quiet = True
        self.draw()
        self.ui.flush()
        return idx

    def pause(self, prompt="Press any key"):
        if self.quiet:                # the player just chose to leave; nothing new to read
            return
        self.draw()
        s, x, y, w, h = self._geom()
        s.center(y + h - 2, f"<dim>{prompt}</>", None, PAL["panel"], x, w)
        self.ui.flush()
        self.ui.wait_key()

    def close(self):
        self.ui.restore(self.snap)


def _cut_markup(markup, nchars):
    """Return markup truncated to n visible chars."""
    out = []
    n = 0
    for text, fg, bg, at in parse(markup):
        take = text[:max(0, nchars - n)]
        n += len(take)
        out.append((take, fg, bg, at))
        if n >= nchars:
            break
    # rebuild as raw spans → use hex tags
    res = ""
    for text, fg, bg, at in out:
        tag = ""
        if fg is not None:
            tag += f"<#{fg:06x}>"
        if bg is not None:
            tag += f"<@{bg:06x}>"
        if at & A_BOLD:
            tag += "<b>"
        if at & A_DIM:
            tag += "<dim>"
        res += tag + text + "</>"
    return res
