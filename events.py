"""Random encounters, shrines, camps, inns and tavern stories."""
import math

from .data import RIDDLES, WHISPERS
from .items import gen_potion, gen_any, gen_jewelry, gen_weapon, gen_scroll, gen_gem, name_item, gen_relic, gen_armor
from .quests import dir_name, dragon_of, make_quest
from .spawn import spawn_group
from .term import PAL, esc
from .town import Market, rename_plus
from .ui import Story, hints
from .util import roll_n, weighted, person_name, seeded


def bonus(g, skill):
    return g.p.skill_bonus(skill) + (1 if g.p.blessed_until > g.p.minutes else 0)


def chk(g, st, skill, dc, adv=False):
    return st.check(skill, bonus(g, skill), dc, g.rng, adv)[0]


def dc(g, base=10, div=2):
    return base + max(1, g.ctx_level) // div


def reward_gold(g, st, mult=1.0):
    n = int((12 + g.ctx_level * 9) * mult * g.rng.uniform(0.8, 1.3))
    g.p.gold += n
    st.say(f"<gold>+{n} gold.</>")
    return n


def reward_xp(g, st, mult=1.0):
    n = int((20 + g.ctx_level * 14) * mult)
    st.say(f"<cyan>+{n} XP.</>")
    g.pending_xp += n
    return n


def hurt(g, st, frac, why):
    p = g.p
    n = max(1, int(p.max_hp * frac))
    p.hp -= n
    st.say(f"<red>{why} You lose {n} HP.</>")
    if p.hp <= 0:
        st.pause()
        st.close()
        from .dungeon import Died
        raise Died(why)


# ═══════════════════════════ overworld events ═══════════════════════════
def ev_merchant(g, ctx):
    st = Story(g.ui, "A Wandering Merchant", art=g.scene("merchant"), art_color=PAL["sand"], color=PAL["sand"])
    st.say("A cart creaks around the bend, hung with pots, blades and bundles. The driver raises a hand: <dim>“Good prices for good faces, friend. Yours will do.”</>")
    i = st.ask(["Browse the wares", "Wave and walk on"])
    if i == 0:
        rng = g.rng
        lv = g.ctx_level + 1
        stock = [gen_potion(rng, lv, "heal2" if lv < 10 else "heal3", 99), gen_potion(rng, lv, "antidote", 99),
                 gen_weapon(rng, lv), gen_armor(rng, lv), gen_jewelry(rng, lv), gen_scroll(rng, lv, None, 99)]
        st.close()
        Market(g, "Wandering Merchant", stock, buy_mult=0.95, sell_mult=0.5).run()
    else:
        st.close()


def ev_traveler(g, ctx):
    st = Story(g.ui, "A Traveller in Need", art=g.scene("road"), art_color=PAL["grey"], color=PAL["grey"])
    st.say("A man sits against a milestone, clutching a bloodied leg. His pack has been slashed open. <dim>“Bandits… took the horse and the money. Please.”</>")
    heal = next((it for it in g.p.inv if it["k"] == "potion" and it["fx"] == "heal"), None)
    opts = ["Tend his wounds (Medicine)"] + ([f"Give him a {heal['n']}"] if heal else []) + ["Walk on"]
    i = st.ask(opts)
    if i == len(opts) - 1:
        g.p.rep -= 1
        st.say("<dim>You walk on. He doesn't call after you.</>")
    elif i == 0 and not chk(g, st, "Medicine", dc(g, 11, 3)):
        st.say("<grey>Your bandaging is clumsy. He thanks you anyway and limps off.</>")
        reward_xp(g, st, 0.3)
    else:
        if i == 1:
            g.p.remove_one(heal)
        st.say("He weeps with relief. <dim>“There's a place I overheard them talk about…”</>")
        near = [f for f in g.world.features_near(g.p.pos[0], g.p.pos[1], 60, ("ruins", "cave", "crypt", "camp", "lair")) if f.key not in g.markers]
        if near:
            f = g.rng.choice(near)
            g.mark_known(f)
            st.say(f"<cyan>[{esc(f.name)} marked on your map]</>")
        reward_gold(g, st, 0.8)
        reward_xp(g, st, 0.8)
        g.p.rep += 1
    st.pause()
    st.close()


def ev_toll(g, ctx):
    st = Story(g.ui, "The Toll-Keeper", art=g.scene("road"), art_color=PAL["brown"], color=PAL["brown"])
    toll = 8 + g.ctx_level * 6
    st.say(f"A chain is stretched across the road between two stakes, and a large person with a larger club stands beside it. <dim>“Toll's {toll} gold. Or… a conversation.”</>")
    opts = [(f"Pay {toll} gold", g.p.gold >= toll), "Persuade him to wave you through (Persuasion)", "Intimidate him (Intimidation)", "Fight"]
    i = st.ask(opts)
    if i == 0:
        g.p.gold -= toll
        st.say("<grey>He weighs the coins and lifts the chain with a grunt.</>")
    elif i in (1, 2):
        ok = chk(g, st, "Persuasion" if i == 1 else "Intimidation", dc(g, 12, 3))
        if ok:
            st.say("<green>He shrugs, mutters, and unhooks the chain. “Fine. Fine. Don't tell the others.”</>")
            reward_xp(g, st, 0.6)
        else:
            st.say("<red>“That's cute,” he says, raising the club. “Very cute.”</>")
            st.pause()
            st.close()
            g.fight(spawn_group(g.rng, g.ctx_level, "plains", elite=False), title="Toll Road")
            return
    else:
        st.pause()
        st.close()
        g.fight(spawn_group(g.rng, g.ctx_level, "plains"), title="Toll Road")
        return
    st.pause()
    st.close()


def ev_wayshrine(g, ctx):
    st = Story(g.ui, "A Wayside Shrine", art=g.scene("shrine"), art_color=PAL["ice"], color=PAL["ice"])
    st.say("A little stone shrine leans by the path, ringed with stubs of candles and rusted coins. Someone has left fresh flowers.")
    i = st.ask(["Leave a coin (10g)", "Say a prayer (Religion)", "Move on"])
    if i == 0 and g.p.gold >= 10:
        g.p.gold -= 10
        r = g.rng.random()
        if r < 0.25:
            g.p.hp = g.p.max_hp
            st.say("<green>The candles flare. Your wounds close.</>")
        elif r < 0.55:
            g.p.blessed_until = g.p.minutes + 600
            st.say("<amber>You feel watched over. <b>Blessed</> for half a day.</>")
        else:
            st.say("<grey>The coin rolls in among the others. Nothing happens. It never does.</>")
    elif i == 1:
        if chk(g, st, "Religion", dc(g, 11, 3)):
            g.p.hp = min(g.p.max_hp, g.p.hp + g.p.max_hp // 3)
            st.say("<green>A quiet peace. You feel lighter. Some wounds close.</>")
        else:
            st.say("<grey>The words come out flat. The shrine keeps its counsel.</>")
    st.pause()
    st.close()


def ev_fairy(g, ctx):
    st = Story(g.ui, "The Fairy Ring", art=g.scene("well"), art_color=PAL["pink"], color=PAL["pink"])
    st.say("A ring of pale mushrooms glows softly in the grass. Music, thin and far away, seems to come from the middle.")
    i = st.ask(["Step inside", "Throw a stone in", "Walk around it"])
    if i == 2:
        st.say("<dim>Wise. The music sulks.</>")
    elif i == 1:
        st.say("<dim>The stone lands with a sound like a laugh. The ring dims.</>")
    else:
        if chk(g, st, "Insight", dc(g, 13, 3)):
            g.p.restore_mp(g.p.max_mp)
            st.say("<cyan>You dance one turn and step out again, laughing. Your mind sparkles: resources restored.</>")
            reward_xp(g, st, 0.8)
        else:
            g.advance_time(360)
            st.say("<purple>You blink. It is six hours later, and your boots are on the wrong feet.</>")
    st.pause()
    st.close()


def ev_camp(g, ctx):
    st = Story(g.ui, "An Abandoned Camp", art=g.scene("camp"), art_color=PAL["brown"], color=PAL["brown"])
    st.say("The fire is cold but the bedrolls are still tidy. Whoever was here left in a hurry. A crate sits half-covered by a tarp.")
    i = st.ask(["Search carefully (Investigation)", "Grab what you can", "Move on"])
    if i == 2:
        st.close()
        return
    if i == 0 and chk(g, st, "Investigation", dc(g, 12, 3)):
        st.say("<green>Under the tarp: supplies, and a hidden pouch.</>")
        reward_gold(g, st, 1.2)
        it = gen_any(g.rng, g.ctx_level)
        st.say(f"You find {name_item(it)}.")
        g.give_item(it)
    elif i == 1 and g.rng.random() < 0.6:
        st.say("You pull the crate free and something snaps. <red>A tripwire!</>")
        st.pause()
        st.close()
        g.fight(spawn_group(g.rng, g.ctx_level, ctx["group"], elite=False), ambush=True, title="Ambush")
        return
    else:
        st.say("<grey>Nothing but moldy blankets. The trap was the trip itself.</>")
        g.p.food += 1
        st.say("<dim>You do find a ration.</>")
    st.pause()
    st.close()


def ev_sphinx(g, ctx):
    q, answers = g.rng.choice(RIDDLES)
    st = Story(g.ui, "The Riddler", art=g.scene("skull"), art_color=PAL["gold"], color=PAL["gold"])
    st.say("A cat the size of a bull lies across the road, wearing a very old crown. <dim>“Answer three riddles,”</> it yawns, <dim>“or pay me the price of my nap.”</>")
    st.say(f"<white>“{q}”</>")
    order = list(range(3))
    g.rng.shuffle(order)
    i = st.ask([answers[j] for j in order])
    if order[i] == 0:
        st.say("<green>“Hm,” purrs the sphinx. “You have a brain, and you didn't leave it at home.”</>")
        it = gen_any(g.rng, g.ctx_level + 1, rarity=2)
        st.say(f"It flicks a paw and drops {name_item(it)} at your feet.")
        g.give_item(it)
        reward_xp(g, st, 1.0)
    else:
        loss = min(g.p.gold, 10 + g.ctx_level * 6)
        g.p.gold -= loss
        st.say(f"<red>“Wrong,” it says, delighted. It takes {loss} gold from your purse with a claw the size of a dagger.</>")
    st.pause()
    st.close()


def ev_enchanter(g, ctx):
    st = Story(g.ui, "The Hedge Wizard", art=g.scene("tower"), art_color=PAL["cyan"], color=PAL["cyan"])
    price = 60 + g.ctx_level * 25
    st.say(f"A stooped mage sits on a stump, muttering to a raven. <dim>“Ah! A customer. I do enchantments. Cheap. Mostly reliable. {price} gold.”</>")
    targets = [k for k in ("weapon", "armor", "shield") if g.p.eq[k]]
    opts = [(f"Enchant my {g.p.eq[k]['base']} (+1)", g.p.gold >= price) for k in targets] + ["No thanks"]
    i = st.ask(opts)
    if i < len(targets):
        g.p.gold -= price
        it = g.p.eq[targets[i]]
        if g.rng.random() < 0.8:
            it["plus"] += 1
            it["v"] += 60 * it["plus"]
            rename_plus(it)
            st.say(f"<cyan>Sparks crawl over the metal. It is now </><b>{esc(it['n'])}</><cyan>.</>")
        else:
            st.say("<grey>The spell fizzles into a shower of confetti. The wizard looks embarrassed. The raven does not.</>")
    st.pause()
    st.close()


def ev_caravan(g, ctx):
    st = Story(g.ui, "Caravan Under Attack", art=g.scene("merchant"), art_color=PAL["red"], color=PAL["red"])
    st.say("Shouts and the clash of steel ahead: a merchant caravan is being robbed on the road. A guard waves you frantically.")
    i = st.ask(["Charge in to help", "Circle around and stay out of it"])
    if i == 0:
        st.close()
        r = g.fight(spawn_group(g.rng, g.ctx_level, "camp", elite=False) + spawn_group(g.rng, g.ctx_level, "camp", elite=False)[:1], title="The Caravan Road")
        if r == "win":
            st2 = Story(g.ui, "The Caravan's Thanks", color=PAL["gold"])
            st2.say("The merchant kisses your hand, then remembers himself and hands over a purse instead.")
            reward_gold(g, st2, 2.0)
            it = gen_potion(g.rng, g.ctx_level, None, 2)
            st2.say(f"He adds {name_item(it)}. <dim>\"For the road.\"</>")
            g.give_item(it)
            g.p.rep += 1
            st2.pause()
            st2.close()
    else:
        st.say("<dim>You keep your head down. The screaming stops eventually.</>")
        st.pause()
        st.close()


def ev_storm(g, ctx):
    grp = ctx["group"]
    kind = {"tundra": ("Blizzard", "A wall of white slams down; you can't see your hand."),
            "desert": ("Sandstorm", "The horizon turns brown and roars."),
            "ash": ("Ashstorm", "The sky rains hot grey flakes that burn your lungs."),
            "swamp": ("Miasma", "A yellow fog rolls off the water, thick and sweet.")}.get(grp, ("Storm", "The sky turns the colour of a bruise and unloads."))
    st = Story(g.ui, kind[0], color=PAL["ice"])
    st.say(kind[1])
    i = st.ask(["Find shelter and wait it out (Survival)", "Push on through"])
    if i == 0:
        if chk(g, st, "Survival", dc(g, 11, 3)):
            g.advance_time(120)
            st.say("<green>You find a hollow and wait. Two cold hours, but you're intact.</>")
        else:
            g.advance_time(120)
            hurt(g, st, 0.15, "You're battered and half-frozen before you find cover.")
    else:
        hurt(g, st, 0.2, "The weather batters you every step.")
        reward_xp(g, st, 0.4)
    st.pause()
    st.close()


def ev_thieves(g, ctx):
    st = Story(g.ui, "Light Fingers", color=PAL["purple"])
    st.say("A child bumps into you, apologises, and is gone before you notice your purse feels lighter.")
    if chk(g, st, "Perception", dc(g, 12, 3)):
        st.say("<green>You catch their wrist! A very small thief blinks up at you and slowly hands the purse back.</>")
        reward_xp(g, st, 0.4)
    else:
        loss = min(g.p.gold, int(g.p.gold * 0.15) + 5)
        i = st.ask(["Give chase (Acrobatics)", "Let it go"])
        if i == 0 and chk(g, st, "Acrobatics", dc(g, 12, 3)):
            st.say("<green>You vault a fence and tackle the thief. They surrender the purse with dignity.</>")
        else:
            g.p.gold -= loss
            st.say(f"<red>Gone. You lose {loss} gold.</>")
    st.pause()
    st.close()


def ev_ghost(g, ctx):
    st = Story(g.ui, "The Ghost Knight", art=g.scene("skull"), art_color=PAL["ice"], color=PAL["ice"])
    st.say("Mist thickens. A rider in ruined armour stands in the road, visor down. <dim>“Halt. A duel of honour, or a courteous word. The choice is yours.”</>")
    i = st.ask(["Accept the duel", "Bow and speak courteously (Religion)", "Turn back"])
    if i == 0:
        st.pause()
        st.close()
        from .entities import Monster
        r = g.fight([Monster("fknight", g.ctx_level, elite=True, name="The Ghost Knight", rng=g.rng)], title="Duel of Honour")
        if r == "win":
            st2 = Story(g.ui, "Honour Satisfied", color=PAL["ice"])
            st2.say("The knight fades with a salute. Something heavy is left behind.")
            it = gen_weapon(g.rng, g.ctx_level + 1, rarity=3)
            st2.say(f"You take up {name_item(it)}.")
            g.give_item(it)
            st2.pause()
            st2.close()
        return
    if i == 1:
        if chk(g, st, "Religion", dc(g, 13, 3)):
            st.say("<green>The knight inclines his head. “Good manners are rarer than good swords.” A cold blessing settles on you.</>")
            g.p.blessed_until = g.p.minutes + 1440
            reward_xp(g, st, 1.0)
        else:
            st.say("<grey>The knight says nothing, and lets you pass in a silence that feels like disappointment.</>")
    st.pause()
    st.close()


def ev_herbs(g, ctx):
    st = Story(g.ui, "A Patch of Herbs", color=PAL["green"])
    st.say("Something useful grows here, half-hidden among the weeds: silver-veined leaves and a cluster of odd blue mushrooms.")
    i = st.ask(["Gather the herbs (Survival)", "Taste a mushroom (…what could go wrong)", "Ignore them"])
    if i == 0:
        if chk(g, st, "Survival", dc(g, 10, 3)):
            it = gen_potion(g.rng, g.ctx_level, g.rng.choice(["heal1", "heal2", "antidote"]), g.rng.randint(1, 2))
            st.say(f"<green>You brew what you gather into {name_item(it)}.</>")
            g.give_item(it)
        else:
            st.say("<grey>Nothing but weeds, you're fairly sure now.</>")
    elif i == 1:
        if chk(g, st, "Insight", dc(g, 12, 3)):
            g.p.restore_mp(g.p.max_mp)
            g.p.heal(g.p.max_hp // 4)
            st.say("<cyan>Tastes like the colour blue. You feel wonderful. Mana refilled, wounds soothed.</>")
        else:
            g.p.hp = max(1, g.p.hp - g.p.max_hp // 8)
            st.say("<red>Colours become sounds. Then you are sick in a bush. -12% HP.</>")
    st.pause()
    st.close()


def ev_dragon_sky(g, ctx):
    st = Story(g.ui, "A Shadow on the Sun", art=g.scene("dragon_sky"), art_color=PAL["red"], color=PAL["red"])
    st.say("The light dims. Something vast passes overhead, wings rustling like a thousand banners. The birds fall silent. Every animal within a mile holds its breath.")
    i = st.ask(["Freeze and hide (Stealth)", "Run for cover (Athletics)", "Stand and watch"])
    ok = False
    if i == 0:
        ok = chk(g, st, "Stealth", dc(g, 13, 2))
    elif i == 1:
        ok = chk(g, st, "Athletics", dc(g, 14, 2))
    else:
        ok = g.rng.random() < 0.35
        st.say("<dim>Awe is not a defence.</>")
    if ok:
        st.say("<green>It passes. You breathe again, and you saw where it was going.</>")
        lairs = sorted(g.world.features_near(g.p.pos[0], g.p.pos[1], 100, ("lair",)), key=lambda f: math.hypot(f.x - g.p.pos[0], f.y - g.p.pos[1]))
        if lairs:
            g.mark_known(lairs[0])
            st.say(f"<cyan>[{esc(lairs[0].name)} marked on your map]</>")
        reward_xp(g, st, 1.5)
    else:
        hurt(g, st, 0.25, "A gout of flame licks the ground where you stand.")
    st.pause()
    st.close()


def ev_well(g, ctx):
    st = Story(g.ui, "The Old Well", art=g.scene("well"), art_color=PAL["blue"], color=PAL["blue"])
    st.say("A moss-covered well stands alone in the field. Coins glint at the bottom. A crooked sign reads: <i>WISH RESPONSIBLY</>.")
    i = st.ask(["Toss in a coin (20g)", "Drink from the bucket", "Leave"])
    if i == 0 and g.p.gold >= 20:
        g.p.gold -= 20
        r = g.rng.random()
        if r < 0.2:
            n = 20 * g.rng.randint(3, 6)
            g.p.gold += n
            st.say(f"<gold>The well coughs up {n} gold. You suspect it's other people's wishes.</>")
        elif r < 0.5:
            g.pending_xp += 40 + g.ctx_level * 12
            st.say("<cyan>A voice whispers a truth about you. It's uncomfortably accurate. (XP)</>")
        else:
            st.say("<grey>Plop.</>")
    elif i == 1:
        if g.rng.random() < 0.7:
            g.p.heal(g.p.max_hp // 5)
            st.say("<green>Cold, sweet water. You feel refreshed.</>")
        else:
            st.say("<lime>Tastes of pennies. You feel slightly worse about it.</>")
    st.pause()
    st.close()


def ev_gambler(g, ctx):
    st = Story(g.ui, "A Roadside Gambler", color=PAL["gold"])
    st.say("A woman sits on a barrel with three cups and a pea. <dim>“Find the pea, double your coin. Miss it, and I'll drink to you.”</>")
    bets = [b for b in (10, 40, 100) if b <= g.p.gold]
    if not bets:
        st.say("<grey>You have nothing to bet.</>")
        st.pause()
        st.close()
        return
    i = st.ask([f"Bet {b}g" for b in bets] + ["Walk away"])
    if i < len(bets):
        b = bets[i]
        names = ["left", "middle", "right"]
        pea = g.rng.randint(0, 2)                     # where the pea really is
        st.say("She slides the cups around in a blur. Can you keep your eyes on the pea?")
        if chk(g, st, "Perception", 13 + g.ctx_level // 4):
            st.say(f"<green>You follow it the whole way. It's under the <b>{names[pea]}</> cup.</>")
        else:
            st.say("<grey>You lose track of it somewhere around the third shuffle. It's a guess now.</>")
        j = st.ask(["Left cup", "Middle cup", "Right cup"])
        if j == pea:
            g.p.gold += b
            st.say(f"<green>The pea! You win {b} gold.</>")
        else:
            g.p.gold -= b
            st.say(f"<red>An empty cup. The pea was under the {names[pea]} one. She toasts you. -{b} gold.</>")
    st.pause()
    st.close()


def ev_pilgrim(g, ctx):
    st = Story(g.ui, "A Lost Pilgrim", color=PAL["white"])
    st.say("An old woman with a walking staff and a shell on her hat squints at you. <dim>“I'm walking to the sea, dear. Is it this way?”</> It is nowhere near this way.")
    i = st.ask(["Take a while to point the way properly (30 min)", "Give her some rations", "Just point vaguely"])
    if i == 0:
        g.advance_time(30)
        st.say("<green>She pats your cheek and whispers a blessing that smells of lavender.</>")
        g.p.blessed_until = g.p.minutes + 360
        g.p.rep += 1
    elif i == 1 and g.p.food > 0:
        g.p.food -= 1
        st.say("<green>She insists on giving you a lucky charm in return: a small polished stone that hums.</>")
        it = gen_jewelry(g.rng, g.ctx_level, rarity=1)
        st.say(f"You gain {name_item(it)}.")
        g.give_item(it)
        g.p.rep += 1
    else:
        st.say("<dim>She wanders off in the wrong direction, cheerfully.</>")
    st.pause()
    st.close()


def ev_wisps(g, ctx):
    st = Story(g.ui, "Will-o'-the-Wisps", color=PAL["cyan"])
    st.say("Pale lights bob among the trees, patient and gentle. They seem to be leading somewhere. The path they suggest is not the one you were on.")
    i = st.ask(["Follow them", "Ignore them (Insight)", "Go back the way you came"])
    if i == 0:
        if chk(g, st, "Insight", dc(g, 13, 3)):
            st.say("<green>At the end of the lights: a small chest half-sunk in moss. The wisps wink out, satisfied.</>")
            reward_gold(g, st, 1.6)
            it = gen_any(g.rng, g.ctx_level)
            st.say(f"Inside: {name_item(it)}.")
            g.give_item(it)
        else:
            g.advance_time(180)
            hurt(g, st, 0.15, "You stumble into a bog after them; hours pass.")
    elif i == 1:
        if chk(g, st, "Insight", dc(g, 12, 3)):
            st.say("<green>You look away in time. The lights sulk and dwindle.</>")
            reward_xp(g, st, 0.5)
        else:
            st.say("<purple>You keep looking. You lose an hour without noticing.</>")
            g.advance_time(60)
    st.pause()
    st.close()


def ev_oasis(g, ctx):
    st = Story(g.ui, "An Oasis?", color=PAL["cyan"])
    st.say("Palms and clear water shimmer ahead, exactly where they'd be if you'd designed the desert yourself.")
    i = st.ask(["Rush to it", "Approach carefully (Survival)", "Ignore it"])
    if i in (0, 1):
        if i == 1:
            real = chk(g, st, "Survival", dc(g, 11, 3))
        else:
            real = g.rng.random() < 0.5
        if real:
            g.p.hp = g.p.max_hp
            g.p.food += 1
            st.say("<green>Real! Cool water and dates. Fully healed, and you pack a ration.</>")
        else:
            st.say("<grey>Heat-haze. Nothing but sand and thirst.</>")
            if i == 0:
                hurt(g, st, 0.1, "You waste precious effort.")
    st.pause()
    st.close()


def ev_map(g, ctx):
    st = Story(g.ui, "A Dead Man's Map", color=PAL["sand"])
    st.say("A skeleton sits propped against a boulder, one bony hand clutching a rolled scroll. It isn't holding it very tightly.")
    near = [f for f in g.world.features_near(g.p.pos[0], g.p.pos[1], 80, ("ruins", "cave", "crypt", "tower", "lair", "camp")) if f.key not in g.markers]
    i = st.ask(["Take the map", "Leave the dead in peace"])
    if i == 0 and near:
        g.rng.shuffle(near)
        for f in near[:2]:
            g.mark_known(f)
            st.say(f"<cyan>The map shows: {esc(f.name)} — {dir_name(f.x - g.p.pos[0], f.y - g.p.pos[1])}, {int(math.hypot(f.x - g.p.pos[0], f.y - g.p.pos[1]))} leagues.</>")
        reward_xp(g, st, 0.6)
    elif i == 0:
        st.say("<grey>A shopping list, mostly.</>")
    st.pause()
    st.close()


def ev_find(g, ctx):
    st = Story(g.ui, "A Small Find", color=PAL["gold"])
    r = g.rng.random()
    if r < 0.4:
        st.say(g.rng.choice(["Something glints in the dirt beside the road. A purse, lost long ago, its owner presumably regretful.",
                             "A dead tree has a hollow, and the hollow has a jar, and the jar has coins."]))
        reward_gold(g, st, 1.0)
    elif r < 0.7:
        g.p.food += 2
        st.say("You find a rabbit-snare, still baited, and two fat hares. <green>+2 rations.</>")
    else:
        it = gen_potion(g.rng, g.ctx_level)
        st.say(f"A traveller's satchel, dropped in a ditch. Inside: {name_item(it)}.")
        g.give_item(it)
    st.pause()
    st.close()


# (weight, condition, function)
OVERWORLD_EVENTS = [
    (8, lambda g, c: True, ev_find),
    (6, lambda g, c: True, ev_merchant),
    (6, lambda g, c: True, ev_traveler),
    (5, lambda g, c: c["group"] in ("plains", "hills", "forest"), ev_toll),
    (4, lambda g, c: True, ev_wayshrine),
    (3, lambda g, c: c["group"] in ("forest", "plains", "swamp"), ev_fairy),
    (5, lambda g, c: True, ev_camp),
    (3, lambda g, c: True, ev_sphinx),
    (3, lambda g, c: True, ev_enchanter),
    (4, lambda g, c: c["level"] >= 2, ev_caravan),
    (4, lambda g, c: c["group"] in ("tundra", "desert", "ash", "swamp", "mountain"), ev_storm),
    (4, lambda g, c: g.p.gold > 30, ev_thieves),
    (3, lambda g, c: c["night"] or c["group"] in ("swamp",), ev_ghost),
    (5, lambda g, c: c["group"] in ("forest", "plains", "hills", "swamp"), ev_herbs),
    (3, lambda g, c: c["level"] >= 5 and not c["night"], ev_dragon_sky),
    (3, lambda g, c: True, ev_well),
    (3, lambda g, c: g.p.gold >= 10, ev_gambler),
    (3, lambda g, c: True, ev_pilgrim),
    (4, lambda g, c: c["night"] and c["group"] in ("swamp", "forest", "tundra"), ev_wisps),
    (4, lambda g, c: c["group"] == "desert", ev_oasis),
    (3, lambda g, c: True, ev_map),
]


def random_event(g, ctx):
    pool = [(f, w) for w, cond, f in OVERWORLD_EVENTS if cond(g, ctx)]
    f = weighted(g.rng, pool)
    g.ctx_level = ctx["level"]
    f(g, ctx)


# ═══════════════════════════ feature interactions ═══════════════════════════
def enter_shrine(g, f):
    key = f.key
    st_ = g.fstate.setdefault(key, {})
    st = Story(g.ui, esc(f.name), art=g.scene("shrine"), art_color=PAL["ice"], color=PAL["ice"])
    g.ctx_level = max(1, g.world.level_at(f.x, f.y))
    st.say("A place of quiet power, old beyond memory. The air tastes like rain that hasn't fallen yet.")
    last_pray = st_.get("prayed", -99)
    last_med = st_.get("meditated", -99)
    opts = [(f"Pray at the altar{'' if g.day > last_pray else ' <dim>(done today)</>'}", g.day > last_pray),
            (f"Meditate on the road ahead (Religion){'' if g.day > last_med else ' <dim>(done today)</>'}", g.day > last_med),
            "Leave"]
    i = st.ask(opts)
    if i == 0:
        st_["prayed"] = g.day
        g.p.hp = g.p.max_hp
        g.p.restore_mp(g.p.max_mp)
        g.p.blessed_until = max(g.p.blessed_until, g.p.minutes + 720)
        st.say("<green>You kneel. A stillness comes. Wounds close; resources return; you are <b>Blessed</>.</>")
        g.chronicle(f"Prayed at {f.name}.")
    elif i == 1:
        st_["meditated"] = g.day          # the attempt costs the day's chance, win or lose — no re-rolling
        if chk(g, st, "Religion", dc(g, 11, 3)):
            near = [x for x in g.world.features_near(f.x, f.y, 70) if x.key not in g.markers and x.key != f.key]
            if near:
                x = g.rng.choice(near)
                g.mark_known(x)
                st.say(f"<cyan>A vision: {esc(x.name)}, {dir_name(x.x - f.x, x.y - f.y)}. [marked on your map]</>")
            reward_xp(g, st, 0.8)
        else:
            st.say("<grey>Silence. Only your own thoughts, which are not helpful.</>")
    st.pause()
    st.close()


def enter_camp(g, f):
    st_ = g.fstate.setdefault(f.key, {})
    lvl = max(1, g.world.level_at(f.x, f.y))
    g.ctx_level = lvl
    quest = next((q for q in g.p.quests if q.get("target_key") == f.key and q["state"] == "active"), None)
    if st_.get("cleared_day") and g.day - st_["cleared_day"] < 6:
        g.ui.message(esc(f.name), "<grey>The camp is a heap of cold ashes and trampled tents. Whoever lived here won't again.</>")
        return
    st = Story(g.ui, esc(f.name), art=g.scene("camp"), art_color=PAL["red"], color=PAL["red"])
    st.say("Tents of patched hide, a bonfire, a pile of loot beside a chained wagon. Half a dozen hard faces look up from their dice.")
    i = st.ask(["Attack the camp", "Sneak in and steal from the wagon (Stealth)", "Back away quietly"])
    if i == 2:
        st.close()
        return
    if i == 1:
        if chk(g, st, "Stealth", dc(g, 13, 2)):
            st.say("<green>You slip between tents and lift the wagon's strongbox. Nobody notices.</>")
            reward_gold(g, st, 3.0)
            it = gen_any(g.rng, lvl + 1, rarity=1)
            st.say(f"Also: {name_item(it)}.")
            g.give_item(it)
            st_["cleared_day"] = g.day
            st.pause()
            st.close()
            return
        st.say("<red>A twig snaps. “INTRUDER!”</>")
    st.pause()
    st.close()
    grp = spawn_group(g.rng, lvl + 1, "camp", elite=True)
    if len(grp) < 3:
        grp += spawn_group(g.rng, lvl, "camp", elite=False)[:2]
    if quest and quest["type"] == "slay":
        from .entities import Monster
        grp = [Monster(quest["boss_tid"], lvl + 2, elite=True, boss=True, name=quest["boss_name"], hp_mult=1.2, rng=g.rng)] + grp[:2]
    r = g.fight(grp, title=esc(f.name), boss=any(m.boss for m in grp))
    if r == "win":
        st_["cleared_day"] = g.day
        g.chronicle(f"Broke the {f.name}.")
        g.quest_event("cleared", f)
        s2 = Story(g.ui, "The Camp Falls", art=g.scene("chest"), art_color=PAL["gold"], color=PAL["gold"])
        s2.say("Silence, and the crackle of the bonfire. The wagon's strongbox is yours to open.")
        reward_gold(g, s2, 3.5)
        for _ in range(2):
            it = gen_any(g.rng, lvl + 1, rarity=None)
            s2.say(f"You find {name_item(it)}.")
            g.give_item(it)
        if quest and quest["type"] == "retrieve":
            g.quest_event("artifact", f)
        s2.pause()
        s2.close()


def enter_inn(g, f):
    lvl = max(1, g.world.level_at(f.x, f.y))
    g.ctx_level = lvl
    p = g.p
    g.mark_known(f)
    g.autosave()
    while True:
        cost = int((5 + 2.5 * p.level))
        s = g.ui.begin()
        st = Story(g.ui, esc(f.name), art=g.scene("tavern"), art_color=PAL["amber"], color=PAL["amber"])
        st.say("A lamp burns in the window. The smell of stew and wet dog wafts out. It's the friendliest thing you've seen all day.")
        i = st.ask([(f"Take a room ({cost}g)", p.gold >= cost), ("Buy supplies", True), ("Listen for rumours (8g)", p.gold >= 8), "Move on"])
        st.close()
        if i == 0:
            p.gold -= cost
            day, h, m = g.clock()
            g.ui.fade_out()
            g.advance_time(((7 - h) % 24 or 24) * 60, resting=True)
            p.hp, p.mp = p.max_hp, p.max_mp
            g.msg("<green>You sleep soundly at the inn.</>")
            g.autosave()
        elif i == 1:
            rng = seeded("innstock", f.seed, p.minutes // 10080)
            stock = [dict(k="food", n="Travel Ration", r=0, v=6, q=99, food=1), gen_potion(rng, lvl, "heal2" if lvl < 10 else "heal3", 99),
                     gen_potion(rng, lvl, "antidote", 99), gen_potion(rng, lvl, "smoke", 99)]
            Market(g, esc(f.name) + " — Supplies", stock, buy_mult=1.4, sell_mult=0.3).run()
        elif i == 2:
            p.gold -= 8
            cands = [x for x in g.world.features_near(f.x, f.y, 70) if x.key not in g.markers and x.key != f.key]
            if cands:
                x = g.rng.choice(cands)
                g.mark_known(x)
                g.ui.message("Rumours", f"“Try {esc(x.name)}, {dir_name(x.x - f.x, x.y - f.y)} of here,” a drover says between mouthfuls. <cyan>[marked on your map]</>", PAL["amber"])
            else:
                g.ui.message("Rumours", "Nothing new; the regulars have heard everything twice.", PAL["amber"])
        else:
            return


# ═══════════════════════════ tavern stories ═══════════════════════════
def town_event(g, town):
    r = g.rng.randint(0, 5)
    g.ctx_level = max(1, town.level)
    p = g.p
    st = Story(g.ui, "In the Common Room", art=g.scene("tavern"), art_color=PAL["amber"], color=PAL["amber"])
    if r == 0:
        st.say("A big man with a bigger moustache thumps the table. <dim>“Arm-wrestle! Winner takes a drink, loser takes a bruise.”</>")
        i = st.ask(["Accept (Athletics)", "Decline"])
        if i == 0:
            if chk(g, st, "Athletics", dc(g, 13, 3)):
                st.say("<green>His knuckles hit the wood. The tavern roars. He buys you a drink and a story.</>")
                reward_xp(g, st, 0.6)
                reward_gold(g, st, 0.4)
            else:
                st.say("<red>Your wrist won't forgive you for a week.</>")
    elif r == 1:
        st.say("A hooded figure by the fire beckons you closer. <dim>“I have coin for a person who asks no questions.”</>")
        i = st.ask(["Listen", "Ignore them"])
        if i == 0:
            q = make_quest(g.world, town.f, seeded("stranger", g.p.steps, town.f.seed), g.rng.choice(["slay", "clear", "hunt"]), 999 + p.steps, 0)
            if q and len([x for x in p.quests if x["state"] in ("active", "ready")]) < 6:
                q["desc"] = "A hooded stranger pays in advance: " + q["desc"]
                q["reward"]["gold"] = int(q["reward"]["gold"] * 1.4)
                p.quests.append(q)
                g.track = q["id"]
                st.say(f"<gold>New quest: {esc(q['title'])}</> <dim>(see your journal)</>")
            else:
                st.say("<grey>They mutter something and lose interest.</>")
    elif r == 2:
        st.say("A bard with a battered lute challenges the room to a song-duel. The crowd looks at you.")
        i = st.ask(["Take the stage (Persuasion)", "Tap your foot politely"])
        if i == 0:
            if chk(g, st, "Persuasion", dc(g, 13, 3)):
                st.say("<green>You improvise a verse about a goat. The room adores it.</>")
                reward_gold(g, st, 1.0)
            else:
                st.say("<grey>Tumbleweed. Somebody coughs in the same key.</>")
    elif r == 3:
        st.say("An old scarred veteran nurses a mug and watches you over its rim. <dim>“Sit. Let me tell you how not to die.”</>")
        i = st.ask(["Listen", "Buy him a drink (8g)"])
        if i == 1 and p.gold >= 8:
            p.gold -= 8
        st.say("<cyan>“Keep your back to a wall. Never fight in the open if you can help it. And carry potions. Always carry potions.”</>")
        reward_xp(g, st, 0.6 if i == 0 else 1.0)
    elif r == 4:
        st.say("A crash: someone flips a table, someone else swings a stool. Three toughs turn toward you. <dim>“You. You looked at my sister.”</>")
        i = st.ask(["Fight", "Talk them down (Persuasion)", "Slip out the back (Acrobatics)"])
        st.close()
        if i == 0:
            from .entities import Monster
            g.fight([Monster("bandit", g.ctx_level, rng=g.rng, name="Tavern Tough") for _ in range(2)], title="Tavern Brawl", can_flee=False)
        else:
            st = Story(g.ui, "In the Common Room", color=PAL["amber"])
            if chk(g, st, "Persuasion" if i == 1 else "Acrobatics", dc(g, 12, 3)):
                st.say("<green>Somehow it ends with everyone hugging. You're not sure how.</>")
            else:
                st.say("<red>A stool finds you. You lose some pride and a little health.</>")
                p.hp = max(1, p.hp - max(1, p.max_hp // 10))
            st.pause()
            st.close()
        return
    else:
        st.say("A dwarf with a beard braided in three colours sets down his mug. <dim>“A round of Liar's Toast! The rules: you say something true about yourself, and I say if you lie.”</>")
        i = st.ask(["Play (Deception or Insight)", "Nah"])
        if i == 0:
            if chk(g, st, "Insight", dc(g, 12, 3)) or g.rng.random() < 0.3:
                st.say("<green>He laughs so hard he spills his beer, then hands you a token from his belt.</>")
                it = gen_jewelry(g.rng, g.ctx_level, rarity=1)
                st.say(f"You gain {name_item(it)}.")
                g.give_item(it)
            else:
                st.say("<grey>He caught you in a lie about your height. You buy the next round.</>")
                p.gold = max(0, p.gold - 8)
    st.pause()
    st.close()
