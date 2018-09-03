import itertools
import random
import re
from collections import deque

from src import channels, users, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Cursed, Safe, Innocent, Wolf, All

from src.roles import doctor

#####################################################################################
########### ADDING CUSTOM TOTEMS AND SHAMAN ROLES TO YOUR BOT -- READ THIS ##########
#####################################################################################
# Before you can add custom totems or shamans, you need to have a basic knowledge   #
# of how the event system works in this bot. If you already know how events in this #
# bot work, you may skip this.                                                      #
#                                                                                   #
# To allow maximum flexibility and allow for customization, lykos makes use of an   #
# event system. The core system will fire events (also referred to as dispatching   #
# an event), which can be listened to by code elsewhere. For example, every role    #
# listens on the "transition_night_end" event, which is where role messages are     #
# sent out to the players. There are several of these kinds of events everywhere,   #
# and roles are expected to make use of the relevant events. For a more in-depth    #
# look at the event system, please check our wiki at https://werewolf.chat/Events   #
#                                                                                   #
# To add new totem types in your custom files:                                      #
# 1. Listen to the "default_totems" event at priority 1 and update                  #
#    chances with (totem name, empty dict) as the (key, value) pair                 #
# 2. Listen to the "default_totems" event at priority 5 (the default)               #
#    and set chances[totem][shaman_role] = 1 for relevant roles                     #
# 3. Add a message key totemname_totem in your custom messages.json file            #
#    describing the totem (this is displayed at night if !simple is off)            #
# 4. Add event listeners as necessary to implement the totem's functionality        #
#                                                                                   #
# To add new shaman roles in your custom files:                                     #
# 1. Listen to the "default_totems" event at priority 3 and add your shaman         #
#    role in evt.data["shaman_roles"]                                               #
# 2. Listen to the "default_totems" event at priority 5 (the default)               #
#    and set chances[totem][shaman_role] = 1 for the totems you wish to have        #
# 3. Setup variables and events with setup_variables(rolename, knows_totem)         #
#    filling in the role name and knows_totem depending on whether or not the       #
#    role knows about the totems they receive. This parameter is keyword-only       #
# 4. Implement the "transition_day_begin" and "transition_night_end" events to give #
#    out totems if the shaman didn't act, and send night messages, respectively.    #
#    Implementation of the "get_role_metadata" event with the "role_categories"     #
#    kind is also necessary for the bot to know that the role exists at all. You    #
#    may look at existing shamans for reference. If your shaman isn't a wolf role,  #
#    the "lycanthropy_role" kind should also be implemented as follows:             #
#    evt.data[role] = {"role": "wolf shaman", "prefix": "shaman"}                   #
#    You will also need to implement your own "give" command; see existing          #
#    shamans for reference, or ask for help in our development channel.             #
#                                                                                   #
# It is generally unneeded to modify this file to add new totems or shaman roles    #
#####################################################################################

DEATH = UserDict()          # type: Dict[users.User, List[users.User]]
PROTECTION = UserList()     # type: List[users.User]
REVEALING = UserSet()       # type: Set[users.User]
NARCOLEPSY = UserSet()      # type: Set[users.User]
SILENCE = UserSet()         # type: Set[users.User]
DESPERATION = UserSet()     # type: Set[users.User]
IMPATIENCE = UserList()     # type: List[users.User]
PACIFISM = UserList()       # type: List[users.User]
INFLUENCE = UserSet()       # type: Set[users.User]
EXCHANGE = UserSet()        # type: Set[users.User]
LYCANTHROPY = UserSet()     # type: Set[users.User]
LUCK = UserSet()            # type: Set[users.User]
PESTILENCE = UserSet()      # type: Set[users.User]
RETRIBUTION = UserSet()     # type: Set[users.User]
MISDIRECTION = UserSet()    # type: Set[users.User]
DECEIT = UserSet()          # type: Set[users.User]

# holding vars that don't persist long enough to need special attention in
# reset/exchange/nickchange
havetotem = []              # type: List[users.User]
brokentotem = set()         # type: Set[users.User]

# Generated message keys used across all shaman files:
# death_totem, protection_totem, revealing_totem, narcolepsy_totem,
# silence_totem, desperation_totem, impatience_totem, pacifism_totem,
# influence_totem, exchange_totem, lycanthropy_totem, luck_totem,
# pestilence_totem, retribution_totem, misdirection_totem, deceit_totem

def setup_variables(rolename, *, knows_totem):
    """Setup role variables and shared events."""
    TOTEMS = UserDict()     # type: Dict[users.User, str]
    LASTGIVEN = UserDict()  # type: Dict[users.User, users.User]
    SHAMANS = UserDict()    # type: Dict[users.User, List[users.User]]

    @event_listener("reset")
    def on_reset(evt, var):
        TOTEMS.clear()
        LASTGIVEN.clear()
        SHAMANS.clear()

    @event_listener("begin_day")
    def on_begin_day(evt, var):
        SHAMANS.clear()

    @event_listener("revealroles_role")
    def on_revealroles(evt, var, user, role):
        if role == rolename and user in TOTEMS:
            if user in SHAMANS:
                evt.data["special_case"].append("giving {0} totem to {1}".format(TOTEMS[user], SHAMANS[user][0]))
            elif var.PHASE == "night":
                evt.data["special_case"].append("has {0} totem".format(TOTEMS[user]))
            elif user in LASTGIVEN and LASTGIVEN[user]:
                evt.data["special_case"].append("gave {0} totem to {1}".format(TOTEMS[user], LASTGIVEN[user]))

    @event_listener("transition_day_begin", priority=7)
    def on_transition_day_begin2(evt, var):
        for shaman, (victim, target) in SHAMANS.items():
            totem = TOTEMS[shaman]
            if totem == "death": # this totem stacks
                if shaman not in DEATH:
                    DEATH[shaman] = UserList()
                DEATH[shaman].append(victim)
            elif totem == "protection": # this totem stacks
                PROTECTION.append(victim)
            elif totem == "revealing":
                REVEALING.add(victim)
            elif totem == "narcolepsy":
                NARCOLEPSY.add(victim)
            elif totem == "silence":
                SILENCE.add(victim)
            elif totem == "desperation":
                DESPERATION.add(victim)
            elif totem == "impatience": # this totem stacks
                IMPATIENCE.append(victim)
            elif totem == "pacifism": # this totem stacks
                PACIFISM.append(victim)
            elif totem == "influence":
                INFLUENCE.add(victim)
            elif totem == "exchange":
                EXCHANGE.add(victim)
            elif totem == "lycanthropy":
                LYCANTHROPY.add(victim)
            elif totem == "luck":
                LUCK.add(victim)
            elif totem == "pestilence":
                PESTILENCE.add(victim)
            elif totem == "retribution":
                RETRIBUTION.add(victim)
            elif totem == "misdirection":
                MISDIRECTION.add(victim)
            elif totem == "deceit":
                DECEIT.add(victim)
            # other totem types possibly handled in an earlier event,
            # as such there is no else: clause here

            if target is not victim:
                shaman.send(messages["totem_retarget"].format(victim))
            LASTGIVEN[shaman] = victim

        havetotem.extend(filter(None, LASTGIVEN.values()))

    @event_listener("del_player")
    def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
        for a,(b,c) in list(SHAMANS.items()):
            if user in (a, b, c):
                del SHAMANS[a]

    @event_listener("chk_nightdone")
    def on_chk_nightdone(evt, var):
        evt.data["actedcount"] += len(SHAMANS)
        evt.data["nightroles"].extend(get_players((rolename,)))

    @event_listener("get_role_metadata")
    def on_get_role_metadata(evt, var, kind):
        if kind == "night_kills":
            # only add shamans here if they were given a death totem
            # even though retribution kills, it is given a special kill message
            evt.data[rolename] = list(TOTEMS.values()).count("death")

    @event_listener("exchange_roles")
    def on_exchange(evt, var, actor, target, actor_role, target_role):
        actor_totem = None
        target_totem = None
        if actor_role == rolename:
            actor_totem = TOTEMS.pop(actor)
            if actor in SHAMANS:
                del SHAMANS[actor]
            if actor in LASTGIVEN:
                del LASTGIVEN[actor]

        if target_role == rolename:
            target_totem = TOTEMS.pop(target)
            if target in SHAMANS:
                del SHAMANS[target]
            if target in LASTGIVEN:
                del LASTGIVEN[target]

        if target_totem:
            if knows_totem:
                evt.data["actor_messages"].append(messages["shaman_totem"].format(target_totem))
            TOTEMS[actor] = target_totem
        if actor_totem:
            if knows_totem:
                evt.data["target_messages"].append(messages["shaman_totem"].format(actor_totem))
            TOTEMS[target] = actor_totem

    @event_listener("default_totems", priority=3)
    def add_shaman(evt, chances):
        evt.data["shaman_roles"].add(rolename)

    @event_listener("transition_night_end")
    def on_transition_night_begin(evt, var):
        if get_all_players((rolename,)) and var.CURRENT_GAMEMODE.TOTEM_CHANCES[rolename]["lycanthropy"] > 0:
            status.add_lycanthropy_scope(var, All)

    if knows_totem:
        @event_listener("myrole")
        def on_myrole(evt, var, user):
            if evt.data["role"] == rolename and var.PHASE == "night" and user not in SHAMANS:
                evt.data["messages"].append(messages["totem_simple"].format(TOTEMS[user]))

    return (TOTEMS, LASTGIVEN, SHAMANS)

def get_totem_target(var, wrapper, message, lastgiven):
    """Get the totem target."""
    target = get_target(var, wrapper, re.split(" +", message)[0], allow_self=True)
    if not target:
        return

    if lastgiven.get(wrapper.source) is target:
        wrapper.send(messages["shaman_no_target_twice"].format(target))
        return

    return target

def give_totem(var, wrapper, target, prefix, role, msg):
    """Give a totem to a player. Return the value of SHAMANS[user]."""

    orig_target = target
    orig_role = get_main_role(orig_target)

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]
    targrole = get_main_role(target)

    wrapper.send(messages["shaman_success"].format(prefix, msg, orig_target))
    debuglog("{0} ({1}) TOTEM: {2} ({3}) as {4} ({5})".format(wrapper.source, role, target, targrole, orig_target, orig_role))

    return UserList((target, orig_target))

@event_listener("see", priority=10)
def on_see(evt, var, seer, target):
    if (seer in DECEIT) ^ (target in DECEIT):
        role = evt.data["role"]
        if role in Cursed:
            role = "wolf"
        elif role in Safe | Innocent:
            role = "villager"
        elif role in Wolf:
            role = "wolf"
        else:
            role = "villager"

        if role == "wolf":
            evt.data["role"] = "villager"
        else:
            evt.data["role"] = "wolf"

@event_listener("get_voters")
def on_get_voters(evt, var):
    evt.data["voters"] -= NARCOLEPSY

@event_listener("chk_decision", priority=1)
def on_chk_decision(evt, var, force):
    nl = []
    for p in PACIFISM:
        if p in evt.params.voters:
            nl.append(p)
    # .remove() will only remove the first instance, which means this plays nicely with pacifism countering this
    for p in IMPATIENCE:
        if p in nl:
            nl.remove(p)
    evt.data["not_lynching"].update(nl)

    for votee, voters in evt.data["votelist"].items():
        numvotes = 0
        random.shuffle(IMPATIENCE)
        for v in IMPATIENCE:
            if v in evt.params.voters and v not in voters and v is not votee:
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

@event_listener("chk_decision_abstain")
def on_chk_decision_abstain(evt, var, not_lynching):
    for p in not_lynching:
        if p in PACIFISM and p not in var.NO_LYNCH:
            channels.Main.send(messages["player_meek_abstain"].format(p))

@event_listener("chk_decision_lynch", priority=1)
def on_chk_decision_lynch1(evt, var, voters):
    votee = evt.data["votee"]
    for p in voters:
        if p in IMPATIENCE and p not in var.VOTES[votee]:
            channels.Main.send(messages["impatient_vote"].format(p, votee))

# mayor is at exactly 3, so we want that to always happen before revealing totem
@event_listener("chk_decision_lynch", priority=3.1)
def on_chk_decision_lynch3(evt, var, voters):
    votee = evt.data["votee"]
    if votee in REVEALING:
        role = get_main_role(votee)
        rev_evt = Event("revealing_totem", {"role": role})
        rev_evt.dispatch(var, votee)
        role = rev_evt.data["role"]

        an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
        channels.Main.send(messages["totem_reveal"].format(votee, an, role))
        evt.data["votee"] = None
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("chk_decision_lynch", priority=5)
def on_chk_decision_lynch5(evt, var, voters):
    votee = evt.data["votee"]
    if votee in DESPERATION:
        # Also kill the very last person to vote them, unless they voted themselves last in which case nobody else dies
        target = voters[-1]
        if target is not votee:
            prots = deque(var.ACTIVE_PROTECTIONS[target])
            while len(prots) > 0:
                # an event can read the current active protection and cancel the totem
                # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                # so that it cannot be used again (if the protection is meant to be usable once-only)
                desp_evt = Event("desperation_totem", {})
                if not desp_evt.dispatch(var, votee, target, prots[0]):
                    return
                prots.popleft()
            if var.ROLE_REVEAL in ("on", "team"):
                r1 = get_reveal_role(target)
                an1 = "n" if r1.startswith(("a", "e", "i", "o", "u")) else ""
                tmsg = messages["totem_desperation"].format(votee, target, an1, r1)
            else:
                tmsg = messages["totem_desperation_no_reveal"].format(votee, target)
            channels.Main.send(tmsg)
            # we lie to this function so it doesn't devoice the player yet. instead, we'll let the call further down do it
            evt.data["deadlist"].append(target)
            evt.params.del_player(target, end_game=False, killer_role="shaman", deadlist=evt.data["deadlist"], ismain=False)

@event_listener("transition_day", priority=2)
def on_transition_day2(evt, var):
    for shaman, targets in DEATH.items():
        for target in targets:
            evt.data["victims"].append(target)
            evt.data["onlybywolves"].discard(target)
            evt.data["killers"][target].append(shaman)

@event_listener("transition_day", priority=4.1)
def on_transition_day3(evt, var):
    # protection totems are applied first in default logic, however
    # we set priority=4.1 to allow other modes of protection
    # to pre-empt us if desired
    pl = get_players()
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
                    var.ACTIVE_PROTECTIONS[v.nick].append("totem")
            evt.data["numkills"][v] = numkills
        else:
            for i in range(0, numtotems):
                var.ACTIVE_PROTECTIONS[v.nick].append("totem")

@event_listener("fallen_angel_guard_break")
def on_fagb(evt, var, victim, killer):
    # we'll never end up killing a shaman who gave out protection, but delete the totem since
    # story-wise it gets demolished at night by the FA
    while victim in havetotem:
        havetotem.remove(victim)
        brokentotem.add(victim)

@event_listener("transition_day_begin", priority=6)
def on_transition_day_begin(evt, var):
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

    # In transition_day_end we report who was given totems based on havetotem.
    # Fallen angel messes with this list, hence why it is separated from LASTGIVEN
    # and calculated here (updated in the separate role files)
    brokentotem.clear()
    havetotem.clear()

@event_listener("transition_day_resolve", priority=2)
def on_transition_day_resolve2(evt, var, victim):
    if evt.data["protected"].get(victim) == "totem":
        evt.data["message"][victim].append(messages["totem_protection"].format(victim))
        evt.data["novictmsg"] = False
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_day_resolve_end", priority=4)
def on_transition_day_resolve6(evt, var, victims):
    for victim in victims:
        if victim in RETRIBUTION:
            killers = list(evt.data["killers"].get(victim, []))
            loser = None
            while killers:
                loser = random.choice(killers)
                if loser in evt.data["dead"] or victim is loser:
                    killers.remove(loser)
                    continue
                break
            if loser in evt.data["dead"] or victim is loser:
                loser = None
            ret_evt = Event("retribution_kill", {"target": loser, "message": []})
            ret_evt.dispatch(var, victim, loser)
            loser = ret_evt.data["target"]
            evt.data["message"][loser].extend(ret_evt.data["message"])
            if loser in evt.data["dead"] or victim is loser:
                loser = None
            if loser is not None:
                prots = deque(var.ACTIVE_PROTECTIONS[loser.nick])
                while len(prots) > 0:
                    # an event can read the current active protection and cancel the totem
                    # if it cancels, it is responsible for removing the protection from var.ACTIVE_PROTECTIONS
                    # so that it cannot be used again (if the protection is meant to be usable once-only)
                    ret_evt = Event("retribution_totem", {"message": []})
                    if not ret_evt.dispatch(var, victim, loser, prots[0]):
                        evt.data["message"][loser].extend(ret_evt.data["message"])
                        return
                    prots.popleft()
                evt.data["dead"].append(loser)
                if var.ROLE_REVEAL in ("on", "team"):
                    role = get_reveal_role(loser)
                    an = "n" if role.startswith(("a", "e", "i", "o", "u")) else ""
                    evt.data["message"][loser].append(messages["totem_death"].format(victim, loser, an, role))
                else:
                    evt.data["message"][loser].append(messages["totem_death_no_reveal"].format(victim, loser))

@event_listener("transition_day_end", priority=1)
def on_transition_day_end(evt, var):
    message = []
    havetotem.sort(key=lambda x: x.nick)
    for player, tlist in itertools.groupby(havetotem):
        ntotems = len(list(tlist))
        message.append(messages["totem_posession"].format(
            player, "ed" if player not in get_players() else "s", "a" if ntotems == 1 else "\u0002{0}\u0002".format(ntotems), "s" if ntotems > 1 else ""))
    for player in brokentotem:
        message.append(messages["totem_broken"].format(player))
    channels.Main.send("\n".join(message))

@event_listener("begin_day")
def on_begin_day(evt, var):
    # Apply totem effects that need to begin on day proper
    var.EXCHANGED.update(p.nick for p in EXCHANGE)
    var.SILENCED.update(p.nick for p in SILENCE)
    for lycan in LYCANTHROPY:
        status.add_lycanthropy(var, lycan)
    for pestilent in PESTILENCE:
        status.make_diseased(var, pestilent)
    var.LUCKY.update(p.nick for p in LUCK)
    var.MISDIRECTED.update(p.nick for p in MISDIRECTION)

@event_listener("abstain")
def on_abstain(evt, var, user):
    if user in NARCOLEPSY:
        user.send(messages["totem_narcolepsy"])
        evt.prevent_default = True

@event_listener("lynch")
def on_lynch(evt, var, user):
    if user in NARCOLEPSY:
        user.send(messages["totem_narcolepsy"])
        evt.prevent_default = True

@event_listener("assassinate")
def on_assassinate(evt, var, killer, target, prot):
    if prot == "totem":
        var.ACTIVE_PROTECTIONS[target.nick].remove("totem")
        evt.prevent_default = True
        evt.stop_processing = True
        channels.Main.send(messages[evt.params.message_prefix + "totem"].format(killer, target))

@event_listener("reset")
def on_reset(evt, var):
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

    brokentotem.clear()
    havetotem.clear()

@event_listener("default_totems", priority=1)
def set_all_totems(evt, chances):
    chances.update({
        "death"         : {},
        "protection"    : {},
        "silence"       : {},
        "revealing"     : {},
        "desperation"   : {},
        "impatience"    : {},
        "pacifism"      : {},
        "influence"     : {},
        "narcolepsy"    : {},
        "exchange"      : {},
        "lycanthropy"   : {},
        "luck"          : {},
        "pestilence"    : {},
        "retribution"   : {},
        "misdirection"  : {},
        "deceit"        : {},
    })

# vim: set sw=4 expandtab:
