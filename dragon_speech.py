"""What a dragon says when it meets you, and what it says as it dies.

Each of the six dragon colours has its own voice. What it actually says depends on whether you've
stood before this exact dragon before, whether it has killed you here before, whether you've killed
it here before (lairs reset a season after being cleared — see dungeon.py), how experienced a
dragon-slayer you already are, and — for its last words — how many times you failed before this.
"""
from .term import esc

# personality per e.color value used by the six dragon templates in data.py
#   ember=red, ice=white, lime=green, purple=black, cyan=blue, bone=bone-dragon


def _tier(n):
    return 0 if n <= 0 else 1 if n <= 2 else 2 if n <= 5 else 3


GREET = {
    # ── RED : arrogant, wrathful, proud, loves fire and ruin ──────────────────
    "ember": dict(
        reborn=[
            "Heat shimmers off its scales before it even opens its eyes. <ember>“You. The ash remembers you, {name}, "
            "even if I only half do. Good. I'd hate to burn a stranger.”</>",
            "It rises unhurried, smoke curling from its nostrils. <ember>“Twice, then. I hope you brought something "
            "better than last time, {name} — I'd hate for this to be boring.”</>",
        ],
        hero_lost_before=[
            "It recognises your stance before your face. <ember>“Back on your feet. I'll give you that much, {name}. "
            "Most don't get up a second time.”</>",
            "A low rumble that might be a laugh. <ember>“You have my scar on your memory, I think. Come and even the score.”</>",
        ],
        first_novice=[
            "The heat hits you before the light does. <ember>“Another one. They always come, and they always burn "
            "the same colour. Let's see what colour you burn, {name}.”</>",
            "It uncoils across its hoard like poured bronze. <ember>“I smell fear under the courage. Good. Fear seasons well.”</>",
        ],
        first_veteran=[
            "It studies you a beat longer than it studies most. <ember>“You've stood over a dragon's bones before. "
            "I can smell the char on you, {name}. Let's see if you remember how it felt.”</>",
            "Its eyes narrow, pleased. <ember>“A slayer, are you. Then this won't be a slaughter. It'll be a proper fight — finally.”</>",
        ],
    ),
    # ── WHITE : cold, aristocratic, contemptuous, glacial ─────────────────────
    "ice": dict(
        reborn=[
            "Frost creaks as it turns its head, unsurprised. <ice>“You return, {name}. Persistence is the one warmth "
            "you mortals have. It will not save you twice.”</>",
            "<ice>“I remember the shape of your shadow on my ice. Sit if you like — I am in no hurry.”</> it says, and means it.",
        ],
        hero_lost_before=[
            "<ice>“You are the one who crawled out last time. How curious. Most simply stop.”</> It does not rise; it does not need to.",
            "<ice>“Back again, little coal. I wonder which part of you will be first to go cold.”</>",
        ],
        first_novice=[
            "The air turns to knives as it exhales. <ice>“Another warm thing, come to cool in my hall. Do sit — "
            "you'll be sitting a while, one way or another.”</>",
            "<ice>“I have watched a thousand winters pass this cave mouth. You will not outlast the next one, {name}.”</>",
        ],
        first_veteran=[
            "It regards you with something almost like interest. <ice>“You carry the cold of other deaths on you. "
            "Refreshing. Most who reach me still smell of summer.”</>",
            "<ice>“A dragon-slayer, in my hall. Well. I have been called worse company. Sit, {name}, and let us be brief.”</>",
        ],
    ),
    # ── GREEN : cunning, sly, riddling, poisons words as well as blades ───────
    "lime": dict(
        reborn=[
            "It smiles, if a dragon can. <lime>“{name}. We've played this game before, haven't we — and you won, and "
            "here I am regardless. Isn't that interesting? Let's see who's cleverer this time.”</>",
            "<lime>“Back for the encore. I do love a returning audience. Tell me — did you miss me, or the gold?”</>",
        ],
        hero_lost_before=[
            "<lime>“Oh, it's you. I still have the taste of our last conversation. Shall we finish the sentence I "
            "interrupted?”</> it says, and the words coil like the smoke.",
            "<lime>“You came back. How delightfully foolish. I was almost disappointed no one would.”</>",
        ],
        first_novice=[
            "<lime>“Oh, a new one. How lovely. Do sit — no, do come closer, I insist.”</> Its smile has entirely too many teeth in it.",
            "<lime>“I do enjoy a fresh face. Tell me a secret before you die, {name}. I collect them, the way others collect gold.”</>",
        ],
        first_veteran=[
            "It tilts its head, delighted. <lime>“Oh, you're one of the interesting ones. I can smell dragonfire that "
            "isn't mine on you. Do tell — was it quick, for the others?”</>",
            "<lime>“A slayer! How marvellous. I so rarely get to test my riddles on someone who might survive the answer.”</>",
        ],
    ),
    # ── BLACK : acid-tongued, cruel, gleefully vicious ────────────────────────
    "purple": dict(
        reborn=[
            "<purple>“You again. How tediously determined.”</> Acid hisses where it drips from its jaw. "
            "<purple>“I was almost fond of the last version of this. Let's not disappoint each other, {name}.”</>",
            "It laughs, a wet and ugly sound. <purple>“Back for seconds. I do hope you brought a better plan than last time — "
            "I'd hate to be bored to death.”</>",
        ],
        hero_lost_before=[
            "<purple>“Look who crawled back. I remember the sound you made. I've been looking forward to hearing it again.”</>",
            "<purple>“You survived me once already, which is more than most. Let's see if that was luck or skill, {name}.”</>",
        ],
        first_novice=[
            "Something drips and sizzles where it lands. <purple>“Oh good, a small one. I get so tired of the tough ones "
            "who take all afternoon to scream.”</>",
            "<purple>“Welcome to my little rot-garden, {name}. Everything here decays eventually. You'll fit right in.”</>",
        ],
        first_veteran=[
            "<purple>“Well, well — a killer of my kin, wandering into my den uninvited. How rude. How refreshing.”</> "
            "it purrs, delighted.",
            "<purple>“You've made corpses of my cousins, haven't you. I can smell them on you. Let's see if you're as "
            "clever as you are lucky.”</>",
        ],
    ),
    # ── BLUE : proud, imperious, obsessed with judgement and storms ───────────
    "cyan": dict(
        reborn=[
            "Lightning crawls between its horns as it looks up. <cyan>“You stand before me a second time, {name}. "
            "The storm does not forget a face. Neither do I.”</>",
            "<cyan>“Judgement was rendered once already. You appeal it, I see. Very well. I will hear your case again — briefly.”</>",
        ],
        hero_lost_before=[
            "<cyan>“The one the storm spared, out of some whim of its own. I did not agree with that verdict then, "
            "and I do not now.”</>",
            "<cyan>“You come again before my bench. Persistence is not the same as merit, {name}. We shall see which you have.”</>",
        ],
        first_novice=[
            "Thunder rolls though the sky outside is clear. <cyan>“State your case, small thing. Every creature that "
            "enters my hall is on trial, and I am not known for mercy.”</>",
            "<cyan>“You stand before the storm's judgement, {name}. Few understand what an honour that is. Fewer still survive it.”</>",
        ],
        first_veteran=[
            "It rises to its full, crackling height. <cyan>“Ah — a slayer of my kind, come before my bench. Now this "
            "is a trial worth presiding over.”</>",
            "<cyan>“The storm remembers every dragon you've felled, {name}. It is, against my better judgement, impressed.”</>",
        ],
    ),
    # ── BONE : ancient, patient, uncanny, speaks like a slow prophecy ─────────
    "bone": dict(
        reborn=[
            "It does not startle — it has been waiting. <bone>“You have stood in this hall before, and left it living. "
            "Death is patient, {name}. It simply asked you to come back.”</>",
            "<bone>“We have done this. I remember the shape of it, if not the ending. Let us see if the ending changes.”</>",
        ],
        hero_lost_before=[
            "<bone>“I have already worn your death once, briefly, and gave it back. That was a mistake I do not often make.”</>",
            "<bone>“You return from where I sent you. Interesting. Death rarely lets its guests wander back out.”</>",
        ],
        first_novice=[
            "Dust sifts from between old ribs as it turns. <bone>“Another small life, come to measure itself against "
            "a long one. I have outlived kingdoms, {name}. I can certainly outlive an afternoon.”</>",
            "<bone>“Sit with me a while before you die. I have all the time that ever was. You have rather less.”</>",
        ],
        first_veteran=[
            "Its hollow eyes seem to weigh you. <bone>“You carry the weight of other dragons in your step. I have felt "
            "that weight land on kingdoms before. It always lands eventually.”</>",
            "<bone>“A slayer of my kin stands in my hall of bones. Fitting, {name}. Everything ends here eventually. Even you.”</>",
        ],
    ),
}

DEATH = {
    "ember": dict(
        struggled=["Its roar breaks into something almost human. <ember>“So — it took you that many tries. I'm almost "
                   "flattered you didn't give up on me, {name}.”</> The fire in its throat finally gutters out."],
        first_kill=["<ember>“First blood, is it. Mine.”</> Something between fury and respect crosses its dying eyes. "
                    "<ember>“Remember this heat, {name}. It only gets hotter from here.”</>"],
        legend=["It laughs, wet and burning, even now. <ember>“Another notch, dragon-slayer. Go on — collect us all. "
                "Someone has to be the last of my kind you never meet.”</>"],
        default=["Flame gutters along its jaw as it slumps. <ember>“Well struck, {name}. The fire remembers you. "
                 "I hope that's a comfort, when it comes looking.”</> Then the light in its eyes goes out."],
    ),
    "ice": dict(
        struggled=["<ice>“So many failures, and still you came back. I will grant you this much, in the end: "
                   "you were never boring.”</> The frost in its voice cracks, just once, into something almost warm."],
        first_kill=["<ice>“Your first,”</> it says, quite calmly, as the cold leaves its blood. <ice>“Make it count for "
                    "something, {name}. Most don't get a first.”</>"],
        legend=["<ice>“One more for the tally. I always wondered who would finally thaw me.”</> It says it without anger, "
                "the way it has said everything: like weather, inevitable."],
        default=["The frost in its eyes dims to grey. <ice>“Efficient,”</> it manages, almost approving. "
                 "<ice>“I would have liked a longer winter, {name}. Ah, well.”</>"],
    ),
    "lime": dict(
        struggled=["It laughs even as it dies, delighted despite itself. <lime>“All those tries — I was starting to "
                   "think you'd become a regular. Well played at last, {name}. Well played.”</>"],
        first_kill=["<lime>“Oh — your very first. How sweet.”</> Its smile does not fade even as the light does. "
                    "<lime>“Do try to enjoy the taste of it, {name}. It doesn't last.”</>"],
        legend=["<lime>“Another secret for your collection, then — mine.”</> it whispers, still amused, always amused. "
                "<lime>“Do come back and tell me how the story ends. Oh — you can't. How funny.”</>"],
        default=["Its many-toothed smile finally slips. <lime>“Clever thing,”</> it concedes, and for once seems to "
                 "mean it. <lime>“I do so hate losing to someone interesting.”</>"],
    ),
    "purple": dict(
        struggled=["Its laughter turns to a wet gurgle. <purple>“All those little deaths of yours, and you kept "
                   "crawling back. Vile. I almost respect it, {name}.”</>"],
        first_kill=["<purple>“Your first kill,”</> it spits, delighted even now. <purple>“Savour it. The next one "
                    "won't feel half as good, {name}.”</>"],
        legend=["<purple>“Ah — another of us, chalked up on your tally.”</> Bile hisses where it pools. "
                "<purple>“Do give my regards to whichever of my kin you meet next. Tell them I said run.”</>"],
        default=["The rot in its voice finally slows. <purple>“Hnh. Not bad,”</> it manages, grudging to the last. "
                 "<purple>“Rot take you kindly, {name}. Slowly, though. I'd insist on slowly.”</>"],
    ),
    "cyan": dict(
        struggled=["<cyan>“Case reopened, and overturned,”</> it concedes, thunder rattling weakly in its chest. "
                   "<cyan>“It took you long enough to make your argument, {name}. I accept the verdict.”</>"],
        first_kill=["<cyan>“Your first judgement rendered, and won.”</> Lightning gutters between its horns. "
                    "<cyan>“Wear the verdict proudly, {name}. Few your age ever earn one.”</>"],
        legend=["<cyan>“The storm concedes to you again,”</> it says, almost formal even now. <cyan>“I will tell the "
                "others, wherever judges go when they die, that you argued well.”</>"],
        default=["The lightning in its eyes dims to a flicker. <cyan>“A fair verdict,”</> it admits, imperious to the "
                 "last breath. <cyan>“I withdraw my objection, {name}. This trial is closed.”</>"],
    ),
    "bone": dict(
        struggled=["<bone>“So many returns. I began to wonder if you, too, had learned patience.”</> Its hollow voice "
                   "does not weaken so much as recede. <bone>“You have earned this ending, {name}. Few do.”</>"],
        first_kill=["<bone>“Your first dragon,”</> it says, without malice, the way one notes a season changing. "
                    "<bone>“Remember the weight of it. It never entirely leaves you, {name}.”</>"],
        legend=["<bone>“Another of my kind returned to dust by your hand. I have watched slayers like you before. "
                "None of them lasted forever either, {name}.”</> it says, and means it kindly."],
        default=["Dust sighs from between its ribs as they still. <bone>“Well fought, small life,”</> it says, "
                 "unhurried even in dying. <bone>“I have all the time that ever was to remember this. You have rather less.”</>"],
    ),
}


def _pick(g, pool_dict, key, name):
    pool = pool_dict.get(key) or pool_dict["default" if "default" in pool_dict else next(iter(pool_dict))]
    line = g.rng.choice(pool)
    return line.format(name=esc(name))


def greet_lines(g, e, st):
    """Returns 1-2 markup lines for a dragon's greeting, given its running per-lair state."""
    color = e.color if e.color in GREET else "ember"
    pool = GREET[color]
    if st.get("dragon_deaths", 0) > 0:
        key = "reborn"
    elif st.get("hero_deaths", 0) > 0:
        key = "hero_lost_before"
    else:
        key = "first_veteran" if _tier(g.p.dragons) >= 1 else "first_novice"
    return [_pick(g, pool, key, g.p.name)]


def death_lines(g, e, st):
    """Returns 1 markup line for a dragon's dying words, given its running per-lair state."""
    color = e.color if e.color in DEATH else "ember"
    pool = DEATH[color]
    if st.get("hero_deaths", 0) > 0:
        key = "struggled"
    elif g.p.dragons <= 0:
        key = "first_kill"
    elif g.p.dragons >= 5:
        key = "legend"
    else:
        key = "default"
    return [_pick(g, pool, key, g.p.name)]
