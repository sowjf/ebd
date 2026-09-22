"""Terminal layer: truecolor double-buffered screen, markup, key input."""
import os
import re
import select
import shutil
import sys
import time

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    termios = tty = None

# ───────────────────────── colors ─────────────────────────
PAL = dict(
    bg=0x0b0910, panel=0x131020, panel2=0x1c1730, edge=0x7a6540, edge2=0x4a3f2c,
    gold=0xf2c14e, amber=0xffa63d, ember=0xff6b2c, blood=0xc22f3a, red=0xe05555,
    green=0x7ccf5a, forest=0x2f7a3f, lime=0xb6e05a, blue=0x5a9fe8, navy=0x1d3a6b, cyan=0x60d6d6,
    purple=0xb082ee, violet=0x5b3a9a, pink=0xe07ab8, white=0xf1e8d6, grey=0x9a93a6, dim=0x5d5769,
    dark=0x2a2536, brown=0xa8743d, silver=0xc8ccd6, ice=0xa8e0ff, black=0x000000, sand=0xd8c27a,
    teal=0x2f9e8f, rose=0xf08a9a, bone=0xdad3bd, coal=0x1a1620,
)
A_BOLD, A_DIM, A_ITALIC, A_UNDER, A_REV = 1, 2, 4, 8, 16
ATTR_TAGS = {"b": A_BOLD, "dim": A_DIM, "i": A_ITALIC, "u": A_UNDER, "rev": A_REV}


def scale(c, f):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    return (min(255, int(r * f)) << 16) | (min(255, int(g * f)) << 8) | min(255, int(b * f))


def mix(c1, c2, t):
    if t <= 0:
        return c1
    if t >= 1:
        return c2
    r1, g1, b1 = (c1 >> 16) & 255, (c1 >> 8) & 255, c1 & 255
    r2, g2, b2 = (c2 >> 16) & 255, (c2 >> 8) & 255, c2 & 255
    return (int(r1 + (r2 - r1) * t) << 16) | (int(g1 + (g2 - g1) * t) << 8) | int(b1 + (b2 - b1) * t)


def rgb(r, g, b):
    return (max(0, min(255, int(r))) << 16) | (max(0, min(255, int(g))) << 8) | max(0, min(255, int(b)))


def to256(c):
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    if abs(r - g) < 10 and abs(g - b) < 10:
        gray = (r + g + b) // 3
        if gray < 8:
            return 16
        if gray > 248:
            return 231
        return 232 + (gray - 8) * 24 // 240
    q = lambda v: 0 if v < 48 else 1 if v < 115 else (v - 35) // 40
    return 16 + 36 * q(r) + 6 * q(g) + q(b)


# ───────────────────────── markup ─────────────────────────
_TAG = re.compile(r"<(/|[@#]?[A-Za-z0-9_]+)>")


def _tag_ok(name):
    if name == "/" or name in ATTR_TAGS:
        return True
    if name.startswith("@"):
        return name[1:] in PAL or _is_hex(name[1:])
    if name.startswith("#"):
        return _is_hex(name[1:])
    return name in PAL


def _is_hex(s):
    return len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s)


def _color_of(name):
    if name in PAL:
        return PAL[name]
    return int(name, 16)


def parse(s, fg=None, bg=None):
    """markup → list of (text, fg, bg, attr)"""
    spans = []
    cfg, cbg, cat = fg, bg, 0
    pos = 0
    for m in _TAG.finditer(s):
        name = m.group(1)
        if not _tag_ok(name):
            continue
        if m.start() > pos:
            spans.append((s[pos:m.start()], cfg, cbg, cat))
        pos = m.end()
        if name == "/":
            cfg, cbg, cat = fg, bg, 0
        elif name in ATTR_TAGS:
            cat |= ATTR_TAGS[name]
        elif name[0] == "@":
            cbg = _color_of(name[1:])
        elif name[0] == "#":
            cfg = _color_of(name[1:])
        else:
            cfg = PAL[name]
    if pos < len(s):
        spans.append((s[pos:], cfg, cbg, cat))
    return spans


def strip(s):
    return _TAG.sub(lambda m: m.group(0) if not _tag_ok(m.group(1)) else "", s)


def vlen(s):
    return len(strip(s))


def esc(s):
    """Neutralise anything that looks like a markup tag in user text."""
    return _TAG.sub(lambda m: "<" + m.group(1) + " >" if _tag_ok(m.group(1)) else m.group(0), s)


def wrap(text, width):
    """Markup-aware word wrap. Returns list of markup lines (style carried across lines)."""
    lines = []
    for para in text.split("\n"):
        state = []          # active tags carried across wrapped lines
        cur, curlen = "", 0
        pending_space = False
        tokens = re.split(r"(<[^<>]*>| +)", para)
        line_prefix = ""
        for tok in tokens:
            if tok == "":
                continue
            m = _TAG.fullmatch(tok)
            if m and _tag_ok(m.group(1)):
                cur += tok
                if m.group(1) == "/":
                    state.clear()
                else:
                    state.append(tok)
                continue
            if tok.isspace() and tok[0] == " ":
                if curlen > 0:
                    pending_space = True
                continue
            wl = len(tok)
            need = wl + (1 if pending_space and curlen else 0)
            if curlen + need > width and curlen > 0:
                lines.append(cur)
                cur = "".join(state)
                curlen = 0
                pending_space = False
            if pending_space and curlen:
                cur += " "
                curlen += 1
            pending_space = False
            while wl > width:                      # very long word
                cur += tok[:width]
                lines.append(cur)
                cur = "".join(state)
                tok = tok[width:]
                wl = len(tok)
                curlen = 0
            cur += tok
            curlen += wl
        lines.append(cur)
    return lines


# ───────────────────────── screen ─────────────────────────
BOXES = {
    "single": "┌┐└┘─│", "double": "╔╗╚╝═║", "round": "╭╮╰╯─│", "heavy": "┏┓┗┛━┃",
}
BLANK = (" ", PAL["white"], PAL["bg"], 0)


class Screen:
    def __init__(self, w, h, truecolor=True):
        self.truecolor = truecolor
        self.resize(w, h)

    def resize(self, w, h):
        self.w, self.h = w, h
        self.cells = [BLANK] * (w * h)
        self.prev = None
        self.clip = None

    # -- basic drawing ------------------------------------------------
    def clear(self, bg=None):
        self.cells = [(" ", PAL["white"], PAL["bg"] if bg is None else bg, 0)] * (self.w * self.h)

    def put(self, x, y, text, fg=None, bg=None, at=0):
        if y < 0 or y >= self.h:
            return x + len(text)
        w, cells = self.w, self.cells
        fg = PAL["white"] if fg is None else fg
        base = y * w
        for ch in text:
            if 0 <= x < w:
                i = base + x
                cells[i] = (ch, fg, cells[i][2] if bg is None else bg, at)
            x += 1
        return x

    def puts(self, x, y, markup, fg=None, bg=None, maxw=None):
        x0 = x
        for text, sfg, sbg, sat in parse(markup, fg, bg):
            if maxw is not None and x - x0 + len(text) > maxw:
                text = text[:max(0, maxw - (x - x0))]
            x = self.put(x, y, text, sfg, sbg, sat)
        return x

    def fill(self, x, y, w, h, ch=" ", fg=None, bg=None):
        for yy in range(max(0, y), min(self.h, y + h)):
            self.put(max(0, x), yy, ch * (min(self.w, x + w) - max(0, x)), fg, bg)

    def box(self, x, y, w, h, style="single", fg=None, bg=None, title=None, tfg=None, fillbg=True):
        c = BOXES[style]
        fg = PAL["edge"] if fg is None else fg
        if fillbg and bg is not None:
            self.fill(x, y, w, h, " ", None, bg)
        self.put(x, y, c[0] + c[4] * (w - 2) + c[1], fg, bg)
        for yy in range(y + 1, y + h - 1):
            self.put(x, yy, c[5], fg, bg)
            self.put(x + w - 1, yy, c[5], fg, bg)
        self.put(x, y + h - 1, c[2] + c[4] * (w - 2) + c[3], fg, bg)
        if title:
            tl = vlen(title)
            l, r = ("╡", "╞") if style in ("double", "heavy") else ("┤", "├")
            self.put(x + 2, y, l, fg, bg)
            self.puts(x + 3, y, f" {title} ", tfg if tfg is not None else PAL["gold"], bg)
            self.put(x + 3 + tl + 2, y, r, fg, bg)

    def hline(self, x, y, w, ch="─", fg=None, bg=None):
        self.put(x, y, ch * w, fg if fg is not None else PAL["edge2"], bg)

    def center(self, y, markup, fg=None, bg=None, x0=0, w=None):
        w = self.w if w is None else w
        self.puts(x0 + max(0, (w - vlen(markup)) // 2), y, markup, fg, bg)

    def snapshot(self):
        return list(self.cells)

    def restore(self, snap):
        if len(snap) != len(self.cells):       # terminal was resized meanwhile
            self.clear()
            return
        self.cells = list(snap)

    def dim(self, f=0.45, x=0, y=0, w=None, h=None):
        w = self.w - x if w is None else w
        h = self.h - y if h is None else h
        for yy in range(max(0, y), min(self.h, y + h)):
            for xx in range(max(0, x), min(self.w, x + w)):
                i = yy * self.w + xx
                ch, fg, bg, at = self.cells[i]
                self.cells[i] = (ch, scale(fg, f), scale(bg, f), at)

    def tint(self, color, t, x=0, y=0, w=None, h=None):
        w = self.w - x if w is None else w
        h = self.h - y if h is None else h
        for yy in range(max(0, y), min(self.h, y + h)):
            for xx in range(max(0, x), min(self.w, x + w)):
                i = yy * self.w + xx
                ch, fg, bg, at = self.cells[i]
                self.cells[i] = (ch, mix(fg, color, t), mix(bg, color, t), at)

    def dump(self):
        return "\n".join("".join(c[0] for c in self.cells[y * self.w:(y + 1) * self.w]).rstrip()
                         for y in range(self.h))

    # -- output -----------------------------------------------------------
    def _sgr(self, fg, bg, at):
        p = ["0"]
        if at & A_BOLD: p.append("1")
        if at & A_DIM: p.append("2")
        if at & A_ITALIC: p.append("3")
        if at & A_UNDER: p.append("4")
        if at & A_REV: p.append("7")
        if self.truecolor:
            p.append(f"38;2;{(fg >> 16) & 255};{(fg >> 8) & 255};{fg & 255}")
            p.append(f"48;2;{(bg >> 16) & 255};{(bg >> 8) & 255};{bg & 255}")
        else:
            p.append(f"38;5;{to256(fg)}")
            p.append(f"48;5;{to256(bg)}")
        return "\x1b[" + ";".join(p) + "m"

    def render(self, full=False):
        w, cells, prev = self.w, self.cells, self.prev
        out = []
        cur = None
        if prev is None or full or len(prev) != len(cells):
            prev = None
            out.append("\x1b[2J")
        for y in range(self.h):
            a = y * w
            b = a + w
            if prev is not None:
                if cells[a:b] == prev[a:b]:
                    continue
                x0 = 0
                while cells[a + x0] == prev[a + x0]:
                    x0 += 1
                x1 = w - 1
                while cells[a + x1] == prev[a + x1]:
                    x1 -= 1
            else:
                x0, x1 = 0, w - 1
            out.append(f"\x1b[{y + 1};{x0 + 1}H")
            for i in range(a + x0, a + x1 + 1):
                ch, fg, bg, at = cells[i]
                st = (fg, bg, at)
                if st != cur:
                    out.append(self._sgr(fg, bg, at))
                    cur = st
                out.append(ch)
        self.prev = list(cells)
        return "".join(out)


# ───────────────────────── terminal / input ─────────────────────────
class ScriptEnd(Exception):
    pass


_CSI = re.compile(r"\x1b\[([0-9;]*)([A-Za-z~])")
_KEYS_CSI = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end", "Z": "btab"}
_KEYS_TILDE = {"1": "home", "2": "insert", "3": "delete", "4": "end", "5": "pgup", "6": "pgdn",
               "7": "home", "8": "end", "11": "f1", "12": "f2", "13": "f3", "14": "f4", "15": "f5"}


class Term:
    MIN_W, MIN_H = 80, 24

    def __init__(self, script=None, size=None):
        self.script = list(script) if script is not None else None
        self.test = script is not None
        self.fd = None
        self.buf = b""
        self.keyq = []
        self.old = None
        self.fast = False                     # animations off
        self.debounce = 0.1                   # ignore the same key repeating faster than this (seconds)
        self._last_k = None
        self._last_t = 0.0
        if size:
            w, h = size
        else:
            sz = shutil.get_terminal_size((100, 32))
            w, h = sz.columns, sz.lines
        ct = os.environ.get("COLORTERM", "").lower()
        tc = ct in ("truecolor", "24bit") or "direct" in os.environ.get("TERM", "") or \
            os.environ.get("EMBERROAD_TRUECOLOR") == "1"
        self.screen = Screen(w, h, truecolor=tc or self.test)
        self.frames = 0
        self.snaps = []

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if self.test:
            return
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)
        tty.setraw(self.fd)
        import signal

        def _hup(signum, frame):            # window closed / killed: unwind so the game can save
            raise KeyboardInterrupt
        for sig in (signal.SIGHUP, signal.SIGTERM):
            try:
                signal.signal(sig, _hup)
            except (ValueError, OSError):
                pass
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        sys.stdout.flush()

    def stop(self):
        if self.test or self.old is None:
            return
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        self.old = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.stop()

    # -- size ------------------------------------------------------------
    @property
    def w(self):
        return self.screen.w

    @property
    def h(self):
        return self.screen.h

    def _check_resize(self):
        if self.test:
            return False
        sz = shutil.get_terminal_size((self.screen.w, self.screen.h))
        if (sz.columns, sz.lines) != (self.screen.w, self.screen.h):
            self.screen.resize(sz.columns, sz.lines)
            return True
        return False

    def begin(self):
        """Call at the start of every draw. Blocks while the terminal is too small."""
        self._check_resize()
        while (self.screen.w < self.MIN_W or self.screen.h < self.MIN_H) and not self.test:
            s = self.screen
            s.clear()
            s.center(s.h // 2 - 1, "<gold>EMBERROAD</> needs a bigger window")
            s.center(s.h // 2 + 1, f"<grey>Now {s.w}x{s.h} — need at least {self.MIN_W}x{self.MIN_H}</>")
            self.flush()
            self._raw_key(0.2)
            self._check_resize()
        return self.screen

    def flush(self):
        self.frames += 1
        if self.test:
            self.screen.prev = list(self.screen.cells)
            return
        data = self.screen.render()
        sys.stdout.write(data)
        sys.stdout.flush()

    def full_redraw(self):
        self.screen.prev = None

    # -- input -------------------------------------------------------------
    def _raw_key(self, timeout):
        """Return next key or None on timeout."""
        if self.keyq:
            return self.keyq.pop(0)
        deadline = None if timeout is None else time.time() + timeout
        while True:
            left = None if deadline is None else max(0.0, deadline - time.time())
            step = 0.1 if left is None else min(0.1, left)
            r, _, _ = select.select([self.fd], [], [], step)
            if r:
                try:
                    data = os.read(self.fd, 4096)
                except OSError:
                    data = b""
                if not data:
                    raise EOFError
                self.buf += data
                if self.buf == b"\x1b":            # lone ESC? wait a moment for the rest
                    r2, _, _ = select.select([self.fd], [], [], 0.03)
                    if r2:
                        self.buf += os.read(self.fd, 4096)
                before = len(self.keyq)
                self._parse()
                self._debounce(before)
                if self.keyq:
                    return self.keyq.pop(0)
            elif self._check_resize():
                return "resize"
            if deadline is not None and time.time() >= deadline:
                return None

    def _debounce(self, start):
        """Drop key-repeat floods: the same key arriving <debounce s after the last accepted one."""
        if not self.debounce:
            return
        now = time.monotonic()
        fresh = self.keyq[start:]
        del self.keyq[start:]
        for k in fresh:
            if k == self._last_k and now - self._last_t < self.debounce:
                continue
            self._last_k, self._last_t = k, now
            self.keyq.append(k)

    def _parse(self):
        s = self.buf.decode("utf-8", errors="ignore")
        if self.buf and not s and len(self.buf) < 4:
            return                                   # incomplete utf-8
        self.buf = b""
        i = 0
        while i < len(s):
            c = s[i]
            if c == "\x1b":
                m = _CSI.match(s, i)
                if m:
                    params, final = m.group(1), m.group(2)
                    if final == "~":
                        k = _KEYS_TILDE.get(params.split(";")[0], "unknown")
                    else:
                        k = _KEYS_CSI.get(final, "unknown")
                    self.keyq.append(k)
                    i = m.end()
                    continue
                if i + 2 < len(s) + 0 and s[i + 1] == "O" and i + 2 < len(s):
                    k = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end",
                         "P": "f1", "Q": "f2", "R": "f3", "S": "f4"}.get(s[i + 2], "unknown")
                    self.keyq.append(k)
                    i += 3
                    continue
                if i + 1 < len(s):
                    self.keyq.append("alt-" + s[i + 1])
                    i += 2
                    continue
                self.keyq.append("esc")
                i += 1
                continue
            i += 1
            if c in "\r\n":
                self.keyq.append("enter")
            elif c in "\x7f\x08":
                self.keyq.append("backspace")
            elif c == "\t":
                self.keyq.append("tab")
            elif c == " ":
                self.keyq.append("space")
            elif c == "\x03":
                self.keyq.append("ctrl-c")
            elif ord(c) < 32:
                self.keyq.append("ctrl-" + chr(ord(c) + 96))
            else:
                self.keyq.append(c)

    def get_key(self, timeout=None):
        if self.test:
            if self.screen.prev != self.screen.cells:
                self.undrawn = getattr(self, "undrawn", 0) + 1
                self.undrawn_where = getattr(self, "undrawn_where", None) or __import__("traceback").format_stack(limit=4)
            if not self.script:
                raise ScriptEnd
            k = self.script.pop(0)
            while k == "snap":
                self.snaps.append(self.screen.dump())
                if not self.script:
                    raise ScriptEnd
                k = self.script.pop(0)
            if k == "wait":
                return None
            return k
        if self.screen.prev is None or self.screen.prev != self.screen.cells:
            self.flush()                     # never block on input with an undrawn frame
        k = self._raw_key(timeout)
        if k == "ctrl-c":
            raise KeyboardInterrupt
        return k

    def flush_input(self):
        if self.test:
            return
        self.keyq.clear()
        while select.select([self.fd], [], [], 0)[0]:
            os.read(self.fd, 4096)

    def sleep(self, dt, skippable=True):
        """Sleep; returns True if a key press cut it short (key is consumed)."""
        if self.test or self.fast:
            return False
        if not skippable:
            time.sleep(dt)
            return False
        k = self._raw_key(dt)
        return k is not None and k != "resize"
