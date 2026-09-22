"""Entry point: python -m emberroad  (or ./emberroad.py)"""
import os
import random
import sys

from .game import Game
from .term import Term
from .title import run_title


FAREWELLS = [
    "May the road rise to meet you.",
    "The fire will keep until you return.",
    "Sheathe your blade, wanderer. The road will wait.",
    "Somewhere, a dragon turns over in its sleep.",
    "Go gently. The hearth remembers you.",
    "The tavern lamp is lit. Your seat is empty, but not forgotten.",
    "Ale, rest and a dry cloak. You have earned all three.",
    "The stars keep watch over the endless road.",
    "Until the next crossroads, traveller.",
    "Even legends must sleep. Farewell, for now.",
    "The map is unfinished. So are you.",
    "Beware the dark, cherish the dawn. Safe travels.",
    "Your name is quietly spoken in distant halls.",
    "The wolves are howling elsewhere tonight. Rest easy.",
]


def farewell(name=None):
    """Clear the terminal, then print a random parting line."""
    line = random.choice(FAREWELLS)
    if name and random.random() < 0.4:
        line = random.choice([f"Rest well, {name}. The road will be here.", f"Farewell, {name}. Till the next dawn.",
                              f"{name} lays down the sword. For now."])
    tc = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
    gold, dim = ("\x1b[38;2;242;193;78m", "\x1b[38;2;154;147;166m") if tc else ("\x1b[33m", "\x1b[90m")
    sys.stdout.write("\x1b[H\x1b[2J\x1b[3J\x1b[H")   # like `clear`: screen + scrollback, cursor to top
    sys.stdout.write(f"\n  {gold}✦ EMBERROAD ✦\x1b[0m\n\n  {dim}\x1b[3m{line}\x1b[0m\n\n")
    sys.stdout.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "-h" in argv or "--help" in argv:
        print("EMBERROAD — an endless terminal quest\n\nusage: play.py [--no-anim] [--256]\n"
              "  Needs a terminal of at least 80x24 with unicode; truecolor recommended.")
        return 0
    if not sys.stdin.isatty():
        print("EMBERROAD needs an interactive terminal.")
        return 1
    if "--256" in argv:
        os.environ["COLORTERM"] = ""
    term = Term()
    g = Game(term)
    if "--no-anim" in argv:
        g.settings["anim"] = False
        term.fast = True
    try:
        with term:
            run_title(g)
    except (KeyboardInterrupt, EOFError):
        pass
    name = g.p.name if g.p else None
    farewell(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
