import re
import random
import itertools
from collections import defaultdict, deque

import botconfig
import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

# To add new totem types in your custom roles/whatever.py file:
# 1. Add a key to var.TOTEM_CHANCES with the totem name
# 2. Add a message totemname_totem to your custom messages.json describing
#    the totem (this is displayed at night if !simple is off)
# 3. Add events as necessary to implement the totem's functionality
#
# To add new shaman roles in your custom roles/whatever.py file:
# 1. Expand var.TOTEM_ORDER and upate var.TOTEM_CHANCES to account for the new width
# 2. Add the role to var.ROLE_GUIDE
# 3. Add the role to whatever other holding vars are necessary based on what it does
# 4. Implement custom events if the role does anything else beyond giving totems.
#
# Modifying this file to add new totems or new shaman roles is generally never required

TOTEMS = {}          # type: Dict[str, str]
LASTGIVEN = {}       # type: Dict[str, str]
SHAMANS = {}         # type: Dict[str, Tuple[str, str]]

DEATH = {}           # type: Dict[str, str]
PROTECTION = []      # type: List[str]
REVEALING = set()    # type: Set[str]
NARCOLEPSY = set()   # type: Set[str]
SILENCE = set()      # type: Set[str]
DESPERATION = set()  # type: Set[str]
IMPATIENCE = []      # type: List[str]
PACIFISM = []        # type: List[str]
INFLUENCE = set()    # type: Set[str]
EXCHANGE = set()     # type: Set[str]
LYCANTHROPY = set()  # type: Set[str]
LUCK = set()         # type: Set[str]
PESTILENCE = set()   # type: Set[str]
RETRIBUTION = set()  # type: Set[str]
MISDIRECTION = set() # type: Set[str]
DECEIT = set()       # type: Set[str]

# holding vars that don't persist long enough to need special attention in
# reset/exchange/nickchange
havetotem = [] # type: List[str]
brokentotem = set() # type: Set[str]

@cmd("give", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=var.TOTEM_ORDER)
@cmd("totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=var.TOTEM_ORDER)
def totem(cli, nick, chan, rest, prefix="You"): # XXX: The transition_day_begin event needs updating alongside this
    """Give a totem to a player."""
    victim = get_victim(cli, nick, re.split(" +",rest)[0], False, True)
    if not victim:
        return
    if LASTGIVEN.get(nick) == victim:
        pm(cli, nick, messages["shaman_no_target_twice"].format(victim))
        return

    original_victim = victim
    role = get_role(nick)
    totem = ""
    if role != "crazed shaman":
        totem = " of " + TOTEMS[nick]

    tags = set()
    if role != "crazed shaman" and TOTEMS[nick] in var.BENEFICIAL_TOTEMS:
        tags.add("beneficial")

    evt = Event("targeted_command", {"target": victim, "misdirection": True, "exchange": True},
            action="give a totem{0} to".format(totem))
    evt.dispatch(cli, var, "totem", nick, victim, frozenset(tags))
    if evt.prevent_default:
        return
    victim = evt.data["target"]
    victimrole = get_role(victim)

    pm(cli, nick, messages["shaman_success"].format(prefix, totem, original_victim))
    if role == "wolf shaman":
        relay_wolfchat_command(cli, nick, messages["shaman_wolfchat"].format(nick, original_victim), ("wolf shaman",), is_wolf_command=True)
    SHAMANS[nick] = (victim, original_victim)
    debuglog("{0} ({1}) TOTEM: {2} ({3})".format(nick, role, victim, TOTEMS[nick]))
    chk_nightdone(cli)

@event_listener("rename_player")
def on_rename(evt, cli, var, prefix, nick):
    if prefix in TOTEMS:
        TOTEMS[nick] = TOTEMS.pop(prefix)

    for dictvar in (LASTGIVEN, DEATH):
        kvp = {}
        for a,b in dictvar.items():
            s = nick if a == prefix else a
            t = nick if b == prefix else b
            kvp[s] = t
        dictvar.update(kvp)
        if prefix in dictvar:
            del dictvar[prefix]

    kvp = {}
    for a,(b,c) in SHAMANS.items():
        s = nick if a == prefix else a
        t1 = nick if b == prefix else b
        t2 = nick if c == prefix else c
        kvp[s] = (t1, t2)
    SHAMANS.update(kvp)
    if prefix in SHAMANS:
        del SHAMANS[prefix]

    for listvar in (PROTECTION, IMPATIENCE, PACIFISM):
        for i,a in enumerate(listvar):
            if a == prefix:
                listvar[i] = nick

    for setvar in (REVEALING, NARCOLEPSY, SILENCE, DESPERATION,
                   INFLUENCE, EXCHANGE, LYCANTHROPY, LUCK, PESTILENCE,
                   RETRIBUTION, MISDIRECTION, DECEIT):
        for a in list(setvar):
            if a == prefix:
                setvar.discard(a)
                setvar.add(nick)

@event_listener("see", priority=10)
def on_see(evt, cli, var, nick, victim):
    if (victim in DECEIT) ^ (nick in DECEIT):
        if evt.data["role"] in var.SEEN_WOLF and evt.data["role"] not in var.SEEN_DEFAULT:
            evt.data["role"] = "villager"
        else:
            evt.data["role"] = "wolf"

@event_listener("del_player")
def on_del_player(evt, cli, var, nick, nickrole, nicktpls, death_triggers):
    for a,(b,c) in list(SHAMANS.items()):
        if nick in (a, b, c):
            del SHAMANS[a]

@event_listener("night_acted")
def on_acted(evt, cli, var, nick, sender):
    if nick in SHAMANS:
        evt.data["acted"] = True

@event_listener("get_special")
def on_get_special(evt, cli, var):
    evt.data["special"].update(list_players(("shaman", "crazed shaman", "wolf shaman")))

@event_listener("exchange_roles")
def on_exchange(evt, cli, var, actor, nick, actor_role, nick_role):
    actor_totem = None
    nick_totem = None
    if actor_role in var.TOTEM_ORDER:
        actor_totem = TOTEMS.pop(actor)
        if actor in SHAMANS:
            del SHAMANS[actor]
        if actor in LASTGIVEN:
            del LASTGIVEN[actor]
    if nick_role in var.TOTEM_ORDER:
        nick_totem = TOTEMS.pop(nick)
        if nick in SHAMANS:
            del SHAMANS[nick]
        if nick in LASTGIVEN:
            del LASTGIVEN[nick]
    if nick_totem:
        if nick_role != "crazed shaman":
            evt.data["actor_messages"].append(messages["shaman_totem"].format(nick_totem))
        TOTEMS[actor] = nick_totem
    if actor_totem:
        if actor_role != "crazed shaman":
            evt.data["nick_messages"].append(messages["shaman_totem"].format(actor_totem))
        TOTEMS[nick] = actor_totem

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, cli, var):
    evt.data["actedcount"] += len(SHAMANS)
    evt.data["nightroles"].extend(list_players(var.TOTEM_ORDER))

@event_listener("get_voters")
def on_get_voters(evt, cli, var):
    evt.data["voters"] -= NARCOLEPSY

@event_listener("chk_decision", priority=1)
def on_chk_decision(evt, cli, var, force):
    nl = []
    for p in PACIFISM:
        if p in evt.params.voters:
            nl.append(p)
    # .remove() will only remove the first instance, which means this plays nicely with pacifism countering this
    for p in IMPATIENCE:
        if p in nl:
            nl.remove(p)
    evt.data["not_lynching"] |= set(nl)

    for votee, voters in evt.data["votelist"].items():
        numvotes = 0
        random.shuffle(IMPATIENCE)
        for v in IMPATIENCE:
            if v in evt.params.voters and v not in voters and v != votee:
                # don't add them in if they have the same number or more of pacifism totems
                # this matters for desperation totem on the votee
                imp_count = IMPATIENCE.count(v)
                pac_count = PACIFISM.count(v)
                if pac_count >= imp_count:
                        continue

                # yes, this means that one of the impatient people will get desperation totem'ed if they didn't
                # already !vote earlier. sucks to suck. >:)
                voters.append(v)
        for v in voters:
            weight = 1
            imp_count = IMPATIENCE.count(v)
            pac_count = PACIFISM.count(v)
            if pac_count > imp_count:
                weight = 0 # more pacifists than impatience totems
            elif imp_count == pac_count and v not in var.VOTES[votee]:
                weight = 0 # impatience and pacifist cancel each other out, so don't count impatience
            if v in INFLUENCE:
                weight *= 2
            numvotes += weight
            if votee not in evt.data["weights"]:
                evt.data["weights"][votee] = {}
            evt.data["weights"][votee][v] = weight
        evt.data["numvotes"][votee] = numvotes

@event_listener("chk_decision", priority=1.1)
def on_hurry_up(evt, cli, var, force):
    if evt.params.timeout:
       evt.stop_processing = True

@event_listener("chk_decision_abstain")
def on_chk_decision_abstain(evt, cli, var, nl):
    for p in nl:
        if p in PACIFISM and p not in var.NO_LYNCH:
            cli.msg(botconfig.CHANNEL, messages["player_meek_abstain"].format(p))

@event_listener("chk_decision_lynch", priority=1)
def on_chk_decision_lynch1(evt, cli, var, voters):
    votee = evt.data["votee"]
    for p in voters:
        if p in IMPATIENCE and p not in var.VOTES[votee]:
            cli.msg(botconfig.CHANNEL, messages["impatient_vote"].format(p, votee))

# mayor is at exactly 3, so we want that to always happen before revealing totem
@event_listener("chk_decision_lynch", priority=3.1)
def on_chk_decision_lynch3(evt, cli, var, voters):
    votee = evt.data["votee"]
    if votee in REVEALING:
        role = get_role(votee)
        rev_evt = Event("revealing_totem", {"role": role})
        rev_evt.dispatch(cli, var, votee)
        role = rev_evt.data["role"]
        if role == "amnesiac":
            var.ROLES["amnesiac"].remove(votee)
            role = var.AMNESIAC_ROLES[votee]
            var.ROLES[role].add(votee)
            var.AMNESIACS.add(votee)
            var.FINAL_ROLES[votee] = role
            pm(cli, votee, messages["totem_amnesia_clear"])
            # If wolfteam, don't bother giving list of wolves since night is about to start anyway
            # Existing wolves also know that someone just joined their team because revealing totem says what they are
            # If turncoat, set their initial starting side to "none" just in case game ends before they can set it themselves
            if role == "turncoat":
                var.TURNCOATS[votee] = ("none", -1)

        an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
        cli.msg(botconfig.CHANNEL, messages["totem_reveal"].format(votee, an, role))
        evt.data["votee"] = None
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("chk_decision_lynch", priority=5)
def on_chk_decision_lynch5(evt, cli, var, voters):
    votee = evt.data["votee"]
    if votee in DESPERATION:
        # Also kill the very last person to vote them, unless they voted themselves last in which case nobody else dies
        target = voters[-1]
        if target != votee:
            prots = deque(var.ACTIVE_PROTECTIONS[target])
            while len(prots) > 0:
                # an event can read the current active protection and cancel the totem
                # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                # so that it cannot be used again (if the protection is meant to be usable once-only)
                desp_evt = Event("desperation_totem", {})
                if not desp_evt.dispatch(cli, var, votee, target, prots[0]):
                    return
                prots.popleft()
            if var.ROLE_REVEAL in ("on", "team"):
                r1 = get_reveal_role(target)
                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                tmsg = messages["totem_desperation"].format(votee, target, an1, r1)
            else:
                tmsg = messages["totem_desperation_no_reveal"].format(votee, target)
            cli.msg(botconfig.CHANNEL, tmsg)
            # we lie to this function so it doesn't devoice the player yet. instead, we'll let the call further down do it
            evt.data["deadlist"].append(target)
            evt.params.del_player(cli, target, True, end_game=False, killer_role="shaman", deadlist=evt.data["deadlist"], original=target, ismain=False)

@event_listener("player_win")
def on_player_win(evt, var, user, rol, winner, survived):
    if rol == "crazed shaman" and survived and not winner.startswith("@") and singular(winner) not in var.WIN_STEALER_ROLES:
        evt.data["iwon"] = True

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt, cli, var):
    # Select random totem recipients if shamans didn't act
    pl = list_players()
    for shaman in list_players(var.TOTEM_ORDER):
        if shaman not in SHAMANS and shaman not in var.SILENCED:
            ps = pl[:]
            if LASTGIVEN.get(shaman) in ps:
                ps.remove(LASTGIVEN.get(shaman))
            levt = Event("get_random_totem_targets", {"targets": ps})
            levt.dispatch(cli, var, shaman)
            ps = levt.data["targets"]
            if ps:
                target = random.choice(ps)
                totem.func(cli, shaman, shaman, target, messages["random_totem_prefix"]) # XXX: Old API
            else:
                LASTGIVEN[shaman] = None
        elif shaman not in SHAMANS:
            LASTGIVEN[shaman] = None

@event_listener("transition_day_begin", priority=6)
def on_transition_day_begin2(evt, cli, var):
    # Reset totem variables
    DEATH.clear()
    PROTECTION.clear()
    REVEALING.clear()
    NARCOLEPSY.clear()
    SILENCE.clear()
    DESPERATION.clear()
    IMPATIENCE.clear()
    PACIFISM.clear()
    INFLUENCE.clear()
    EXCHANGE.clear()
    LYCANTHROPY.clear()
    LUCK.clear()
    PESTILENCE.clear()
    RETRIBUTION.clear()
    MISDIRECTION.clear()
    DECEIT.clear()

    # Give out totems here
    for shaman, (victim, target) in SHAMANS.items():
        totemname = TOTEMS[shaman]
        if totemname == "death": # this totem stacks
            DEATH[shaman] = victim
        elif totemname == "protection": # this totem stacks
            PROTECTION.append(victim)
        elif totemname == "revealing":
            REVEALING.add(victim)
        elif totemname == "narcolepsy":
            NARCOLEPSY.add(victim)
        elif totemname == "silence":
            SILENCE.add(victim)
        elif totemname == "desperation":
            DESPERATION.add(victim)
        elif totemname == "impatience": # this totem stacks
            IMPATIENCE.append(victim)
        elif totemname == "pacifism": # this totem stacks
            PACIFISM.append(victim)
        elif totemname == "influence":
            INFLUENCE.add(victim)
        elif totemname == "exchange":
            EXCHANGE.add(victim)
        elif totemname == "lycanthropy":
            LYCANTHROPY.add(victim)
        elif totemname == "luck":
            LUCK.add(victim)
        elif totemname == "pestilence":
            PESTILENCE.add(victim)
        elif totemname == "retribution":
            RETRIBUTION.add(victim)
        elif totemname == "misdirection":
            MISDIRECTION.add(victim)
        elif totemname == "deceit":
            DECEIT.add(victim)
        # other totem types possibly handled in an earlier event,
        # as such there is no else: clause here
        if target != victim:
            pm(cli, shaman, messages["totem_retarget"].format(victim))
        LASTGIVEN[shaman] = victim

    # In transition_day_end we report who was given totems based on havetotem.
    # Fallen angel messes with this list, hence why it is separated from LASTGIVEN
    # and calculated here.
    brokentotem.clear()
    havetotem.clear()
    havetotem.extend(sorted(filter(None, LASTGIVEN.values())))

@event_listener("transition_day", priority=2)
def on_transition_day2(evt, cli, var):
    for k, d in DEATH.items():
        evt.data["victims"].append(d)
        evt.data["onlybywolves"].discard(d)
        evt.data["killers"][d].append(k)

@event_listener("transition_day", priority=4.1)
def on_transition_day3(evt, cli, var):
    # protection totems are applied first in default logic, however
    # we set priority=4.1 to allow other modes of protection
    # to pre-empt us if desired
    pl = list_players()
    vs = set(evt.data["victims"])
    for v in pl:
        numtotems = PROTECTION.count(v)
        if v in vs:
            if v in var.DYING:
                continue
            numkills = evt.data["numkills"][v]
            for i in range(0, numtotems):
                numkills -= 1
                if numkills >= 0:
                    evt.data["killers"][v].pop(0)
                if numkills <= 0 and v not in evt.data["protected"]:
                    evt.data["protected"][v] = "totem"
                elif numkills <= 0:
                    var.ACTIVE_PROTECTIONS[v].append("totem")
            evt.data["numkills"][v] = numkills
        else:
            for i in range(0, numtotems):
                var.ACTIVE_PROTECTIONS[v].append("totem")

@event_listener("fallen_angel_guard_break")
def on_fagb(evt, cli, var, victim, killer):
    # we'll never end up killing a shaman who gave out protection, but delete the totem since
    # story-wise it gets demolished at night by the FA
    while victim in havetotem:
        havetotem.remove(victim)
        brokentotem.add(victim)

@event_listener("transition_day_resolve", priority=2)
def on_transition_day_resolve2(evt, cli, var, victim):
    if evt.data["protected"].get(victim) == "totem":
        evt.data["message"].append(messages["totem_protection"].format(victim))
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve", priority=6)
def on_transition_day_resolve6(evt, cli, var, victim):
    # TODO: remove these checks once everything is split
    # right now they're needed because otherwise retribution may fire off when the target isn't actually dying
    # that will not be an issue once everything is using the event
    if evt.data["protected"].get(victim):
        return
    if victim in var.ROLES["lycan"] and victim in evt.data["onlybywolves"] and victim not in var.IMMUNIZED:
        return
    # END checks to remove

    if victim in RETRIBUTION:
        killers = list(evt.data["killers"].get(victim, []))
        loser = None
        while killers:
            loser = random.choice(killers)
            if loser in evt.data["dead"] or victim == loser:
                killers.remove(loser)
                continue
            break
        if loser in evt.data["dead"] or victim == loser:
            loser = None
        ret_evt = Event("retribution_kill", {"target": loser, "message": []})
        ret_evt.dispatch(cli, var, victim, loser)
        loser = ret_evt.data["target"]
        evt.data["message"].extend(ret_evt.data["message"])
        if loser in evt.data["dead"] or victim == loser:
            loser = None
        if loser is not None:
            prots = deque(var.ACTIVE_PROTECTIONS[loser])
            while len(prots) > 0:
                # an event can read the current active protection and cancel the totem
                # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                # so that it cannot be used again (if the protection is meant to be usable once-only)
                ret_evt = Event("retribution_totem", {"message": []})
                if not ret_evt.dispatch(cli, var, victim, loser, prots[0]):
                    evt.data["message"].extend(ret_evt.data["message"])
                    return
                prots.popleft()
            evt.data["dead"].append(loser)
            if var.ROLE_REVEAL in ("on", "team"):
                role = get_reveal_role(loser)
                an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                evt.data["message"].append(messages["totem_death"].format(victim, loser, an, role))
            else:
                evt.data["message"].append(messages["totem_death_no_reveal"].format(victim, loser))

@event_listener("transition_day_end", priority=1)
def on_transition_day_end(evt, cli, var):
    message = []
    for player, tlist in itertools.groupby(havetotem):
        ntotems = len(list(tlist))
        message.append(messages["totem_posession"].format(
            player, "ed" if player not in list_players() else "s", "a" if ntotems == 1 else "\u0002{0}\u0002".format(ntotems), "s" if ntotems > 1 else ""))
    for player in brokentotem:
        message.append(messages["totem_broken"].format(player))
    cli.msg(botconfig.CHANNEL, "\n".join(message))

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, cli, var):
    max_totems = defaultdict(int)
    ps = list_players()
    shamans = list_players(var.TOTEM_ORDER)
    for ix in range(len(var.TOTEM_ORDER)):
        for c in var.TOTEM_CHANCES.values():
            max_totems[var.TOTEM_ORDER[ix]] += c[ix]
    for s in list(LASTGIVEN.keys()):
        if s not in shamans:
            del LASTGIVEN[s]
    for shaman in list_players(var.TOTEM_ORDER):
        pl = ps[:]
        random.shuffle(pl)
        if shaman in LASTGIVEN and LASTGIVEN[shaman] in pl:
            pl.remove(LASTGIVEN[shaman])
        role = get_role(shaman)
        indx = var.TOTEM_ORDER.index(role)
        target = 0
        rand = random.random() * max_totems[var.TOTEM_ORDER[indx]]
        for t in var.TOTEM_CHANCES.keys():
            target += var.TOTEM_CHANCES[t][indx]
            if rand <= target:
                TOTEMS[shaman] = t
                break
        if shaman in var.PLAYERS and not is_user_simple(shaman):
            if role not in var.WOLFCHAT_ROLES:
                pm(cli, shaman, messages["shaman_notify"].format(role, "random " if shaman in var.ROLES["crazed shaman"] else ""))
            if role != "crazed shaman":
                totem = TOTEMS[shaman]
                tmsg = messages["shaman_totem"].format(totem)
                try:
                    tmsg += messages[totem + "_totem"]
                except KeyError:
                    tmsg += messages["generic_bug_totem"]
                pm(cli, shaman, tmsg)
        else:
            if role not in var.WOLFCHAT_ROLES:
                pm(cli, shaman, messages["shaman_simple"].format(role))
            if role != "crazed shaman":
                pm(cli, shaman, messages["totem_simple"].format(TOTEMS[shaman]))
        if role not in var.WOLFCHAT_ROLES:
            pm(cli, shaman, "Players: " + ", ".join(pl))

@event_listener("begin_day")
def on_begin_day(evt, cli, var):
    # Apply totem effects that need to begin on day proper
    var.EXCHANGED.update(EXCHANGE)
    var.SILENCED.update(SILENCE)
    var.LYCANTHROPES.update(LYCANTHROPY)
    # pestilence doesn't take effect on immunized players
    var.DISEASED.update(PESTILENCE - var.IMMUNIZED)
    var.LUCKY.update(LUCK)
    var.MISDIRECTED.update(MISDIRECTION)

    SHAMANS.clear()

@event_listener("abstain")
def on_abstain(evt, cli, var, nick):
    if nick in NARCOLEPSY:
        pm(cli, nick, messages["totem_narcolepsy"])
        evt.prevent_default = True

@event_listener("lynch")
def on_lynch(evt, cli, var, nick):
    if nick in NARCOLEPSY:
        pm(cli, nick, messages["totem_narcolepsy"])
        evt.prevent_default = True

@event_listener("assassinate")
def on_assassinate(evt, cli, var, nick, target, prot):
    if prot == "totem":
        var.ACTIVE_PROTECTIONS[target].remove("totem")
        evt.prevent_default = True
        evt.stop_processing = True
        cli.msg(botconfig.CHANNEL, messages[evt.params.message_prefix + "totem"].format(nick, target))

@event_listener("succubus_visit")
def on_succubus_visit(evt, cli, var, nick, victim):
    if (SHAMANS.get(victim, (None, None))[1] in var.ROLES["succubus"] and
       (get_role(victim) == "crazed shaman" or TOTEMS[victim] not in var.BENEFICIAL_TOTEMS)):
        pm(cli, victim, messages["retract_totem_succubus"].format(SHAMANS[victim]))
        del SHAMANS[victim]

@event_listener("myrole")
def on_myrole(evt, cli, var, nick):
    role = evt.data["role"]
    if role in var.TOTEM_ORDER and role != "crazed shaman" and var.PHASE == "night" and nick not in SHAMANS:
        evt.data["messages"].append(messages["totem_simple"].format(TOTEMS[nick]))

@event_listener("revealroles_role")
def on_revealroles(evt, var, wrapper, nickname, role):
    if role in var.TOTEM_ORDER and nickname in TOTEMS:
        if nickname in SHAMANS:
            evt.data["special_case"].append("giving {0} totem to {1}".format(TOTEMS[nickname], SHAMANS[nickname][0]))
        elif var.PHASE == "night":
            evt.data["special_case"].append("has {0} totem".format(TOTEMS[nickname]))
        elif nickname in LASTGIVEN and LASTGIVEN[nickname]:
            evt.data["special_case"].append("gave {0} totem to {1}".format(TOTEMS[nickname], LASTGIVEN[nickname]))

@event_listener("reset")
def on_reset(evt, var):
    TOTEMS.clear()
    LASTGIVEN.clear()
    SHAMANS.clear()
    DEATH.clear()
    PROTECTION.clear()
    REVEALING.clear()
    NARCOLEPSY.clear()
    SILENCE.clear()
    DESPERATION.clear()
    IMPATIENCE.clear()
    PACIFISM.clear()
    INFLUENCE.clear()
    EXCHANGE.clear()
    LYCANTHROPY.clear()
    LUCK.clear()
    PESTILENCE.clear()
    RETRIBUTION.clear()
    MISDIRECTION.clear()
    DECEIT.clear()

@event_listener("frole_role")
def on_frole_role(evt, cli, var, who, role, oldrole, args):
    if role in var.TOTEM_ORDER:
        if len(args) == 2:
            TOTEMS[who] = args[1]
        else:
            max_totems = defaultdict(int)
            for ix in range(len(var.TOTEM_ORDER)):
                for c in var.TOTEM_CHANCES.values():
                    max_totems[var.TOTEM_ORDER[ix]] += c[ix]
            for shaman in list_players(var.TOTEM_ORDER):
                indx = var.TOTEM_ORDER.index(role)
                target = 0
                rand = random.random() * max_totems[var.TOTEM_ORDER[indx]]
                for t in var.TOTEM_CHANCES.keys():
                    target += var.TOTEM_CHANCES[t][indx]
                    if rand <= target:
                        TOTEMS[shaman] = t
                        break

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, cli, var, kind):
    if kind == "night_kills":
        # only add shamans here if they were given a death totem
        # even though retribution kills, it is given a special kill message
        # note that all shaman types (shaman/CS/wolf shaman) are lumped under the "shaman" key
        evt.data["shaman"] = list(TOTEMS.values()).count("death")

# vim: set sw=4 expandtab:
