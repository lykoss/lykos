import itertools
import random
import re
from typing import Dict, List, Set, Any, Tuple, Optional
from collections import deque

from src import channels, users, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_all_roles, get_reveal_role, get_target
from src.utilities import complete_one_match
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_protection, try_exchange
from src.events import Event
from src.cats import Cursed, Safe, Innocent, Wolf, All

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
#    describing the totem                                                           #
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

DEATH = UserDict() # type: UserDict[users.User, UserList]
PROTECTION = UserList()
REVEALING = UserSet()
NARCOLEPSY = UserSet()
SILENCE = UserSet()
DESPERATION = UserSet()
IMPATIENCE = UserList()
PACIFISM = UserList()
INFLUENCE = UserSet()
EXCHANGE = UserSet()
LYCANTHROPY = UserSet()
LUCK = UserSet()
PESTILENCE = UserSet()
RETRIBUTION = UserSet()
MISDIRECTION = UserSet()
DECEIT = UserSet()

# holding vars that don't persist long enough to need special attention in
# reset/exchange/nickchange
havetotem = []              # type: List[users.User]
brokentotem = set()         # type: Set[users.User]

# holds mapping of shaman roles to their state vars, for debugging
# and unit testing purposes
_rolestate = {}             # type: Dict[str, Dict[str, Any]]

# Generated message keys used across all shaman files:
# death_totem, protection_totem, revealing_totem, narcolepsy_totem,
# silence_totem, desperation_totem, impatience_totem, pacifism_totem,
# influence_totem, exchange_totem, lycanthropy_totem, luck_totem,
# pestilence_totem, retribution_totem, misdirection_totem, deceit_totem

def setup_variables(rolename, *, knows_totem):
    """Setup role variables and shared events."""
    def ulf():
        # Factory method to create a DefaultUserDict[*, UserList]
        # this can be passed into a DefaultUserDict constructor so we can make nested defaultdicts easily
        return DefaultUserDict(UserList)
    TOTEMS = DefaultUserDict(dict)       # type: DefaultUserDict[users.User, Dict[str, int]]
    LASTGIVEN = DefaultUserDict(ulf)     # type: DefaultUserDict[users.User, DefaultUserDict[str, UserList]]
    SHAMANS = DefaultUserDict(ulf)       # type: DefaultUserDict[users.User, DefaultUserDict[str, UserList]]
    RETARGET = DefaultUserDict(UserDict) # type: DefaultUserDict[users.User, UserDict[users.User, users.User]]
    _rolestate[rolename] = {
        "TOTEMS": TOTEMS,
        "LASTGIVEN": LASTGIVEN,
        "SHAMANS": SHAMANS,
        "RETARGET": RETARGET
    }

    @event_listener("reset", listener_id="shamans.<{}>.on_reset".format(rolename))
    def on_reset(evt, var):
        TOTEMS.clear()
        LASTGIVEN.clear()
        SHAMANS.clear()
        RETARGET.clear()

    @event_listener("begin_day", listener_id="shamans.<{}>.on_begin_day".format(rolename))
    def on_begin_day(evt, var):
        SHAMANS.clear()
        RETARGET.clear()

    @event_listener("revealroles_role", listener_id="shamans.<{}>.revealroles_role".format(rolename))
    def on_revealroles(evt, var, user, role):
        if role == rolename and user in TOTEMS:
            if var.PHASE == "night":
                evt.data["special_case"].append(messages["shaman_revealroles_night"].format(
                    (messages["shaman_revealroles_night_totem"].format(num, totem)
                        for num, totem in TOTEMS[user].items()),
                    sum(TOTEMS[user].values())))
            elif user in LASTGIVEN and LASTGIVEN[user]:
                given = []
                for totem, recips in LASTGIVEN[user].items():
                    for recip in recips:
                        given.append(messages["shaman_revealroles_day_totem"].format(totem, recip))
                evt.data["special_case"].append(messages["shaman_revealroles_day"].format(given))

    @event_listener("transition_day_begin", priority=7, listener_id="shamans.<{}>.transition_day_begin".format(rolename))
    def on_transition_day_begin2(evt, var):
        LASTGIVEN.clear()
        for shaman, given in SHAMANS.items():
            for totem, targets in given.items():
                for target in targets:
                    victim = RETARGET[shaman].get(target, target)
                    if not victim:
                        continue
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
                    else:
                        event = Event("apply_totem", {})
                        event.dispatch(var, rolename, totem, shaman, victim)

                    if target is not victim:
                        shaman.send(messages["totem_retarget"].format(victim, target))
                    LASTGIVEN[shaman][totem].append(victim)
                    havetotem.append(victim)

    @event_listener("del_player", listener_id="shamans.<{}>.del_player".format(rolename))
    def on_del_player(evt, var, player, all_roles, death_triggers):
        for a, b in list(SHAMANS.items()):
            if player is a:
                del SHAMANS[a]
            else:
                for totem, c in b.items():
                    if player in c:
                        SHAMANS[a][totem].remove(player)
        del RETARGET[:player:]
        for a, b in list(RETARGET.items()):
            for c, d in list(b.items()):
                if player in (c, d):
                    del RETARGET[a][c]

    @event_listener("chk_nightdone", listener_id="shamans.<{}>.chk_nightdone".format(rolename))
    def on_chk_nightdone(evt, var):
        # only count shaman as acted if they've given out all of their totems
        for shaman in SHAMANS:
            totemcount = sum(TOTEMS[shaman].values())
            given = len(list(itertools.chain.from_iterable(SHAMANS[shaman].values())))
            if given == totemcount:
                evt.data["acted"].append(shaman)
        evt.data["nightroles"].extend(get_all_players((rolename,)))

    @event_listener("get_role_metadata", listener_id="shamans.<{}>.get_role_metadata".format(rolename))
    def on_get_role_metadata(evt, var, kind):
        if kind == "night_kills":
            # only add shamans here if they were given a death totem
            # even though retribution kills, it is given a special kill message
            evt.data[rolename] = list(itertools.chain.from_iterable(TOTEMS.values())).count("death")

    @event_listener("new_role", listener_id="shamans.<{}>.new_role".format(rolename))
    def on_new_role(evt, var, player, old_role):
        if evt.params.inherit_from in TOTEMS and old_role != rolename and evt.data["role"] == rolename:
            totems = TOTEMS.pop(evt.params.inherit_from)
            del SHAMANS[:evt.params.inherit_from:]
            del LASTGIVEN[:evt.params.inherit_from:]

            if knows_totem:
                evt.data["messages"].append(totem_message(totems))
            TOTEMS[player] = totems

    @event_listener("swap_role_state", listener_id="shamans.<{}>.swap_role_state".format(rolename))
    def on_swap_role_state(evt, var, actor, target, role):
        if role == rolename and actor in TOTEMS and target in TOTEMS:
            TOTEMS[actor], TOTEMS[target] = TOTEMS[target], TOTEMS[actor]
            del SHAMANS[:actor:]
            del SHAMANS[:target:]
            del LASTGIVEN[:actor:]
            del LASTGIVEN[:target:]

            if knows_totem:
                evt.data["actor_messages"].append(totem_message(TOTEMS[actor]))
                evt.data["target_messages"].append(totem_message(TOTEMS[target]))

    @event_listener("default_totems", priority=3, listener_id="shamans.<{}>.default_totems".format(rolename))
    def add_shaman(evt, chances):
        evt.data["shaman_roles"].add(rolename)

    @event_listener("transition_night_end", listener_id="shamans.<{}>.on_transition_night_end".format(rolename))
    def on_transition_night_end(evt, var):
        if var.NIGHT_COUNT == 0 or not get_all_players((rolename,)):
            return
        if var.CURRENT_GAMEMODE.TOTEM_CHANCES["lycanthropy"][rolename] > 0:
            status.add_lycanthropy_scope(var, All)
        if var.CURRENT_GAMEMODE.TOTEM_CHANCES["luck"][rolename] > 0:
            status.add_misdirection_scope(var, All, as_target=True)
        if var.CURRENT_GAMEMODE.TOTEM_CHANCES["misdirection"][rolename] > 0:
            status.add_misdirection_scope(var, All, as_actor=True)

    if knows_totem:
        @event_listener("myrole", listener_id="shamans.<{}>.on_myrole".format(rolename))
        def on_myrole(evt, var, user):
            if evt.data["role"] == rolename and var.PHASE == "night" and user not in SHAMANS:
                evt.data["messages"].append(totem_message(TOTEMS[user]))

    return (TOTEMS, LASTGIVEN, SHAMANS, RETARGET)

def totem_message(totems, count_only=False):
    totemcount = sum(totems.values())
    if not count_only and totemcount == 1:
        totem = list(totems.keys())[0]
        return messages["shaman_totem"].format(totem)
    elif count_only:
        return messages["shaman_totem_multiple_unknown"].format(totemcount)
    else:
        pieces = [messages["shaman_totem_piece"].format(num, totem) for totem, num in totems.items()]
        return messages["shaman_totem_multiple_known"].format(pieces)

def get_totem_target(var, wrapper, message, lastgiven, totems) -> Tuple[Optional[str], Optional[users.User]]:
    """Get the totem target."""
    pieces = re.split(" +", message)
    totem = None

    if len(pieces) > 1:
        # first piece might be a totem name
        totem = complete_one_match(pieces[0], totems)

    if totem:
        target_str = pieces[1]
    else:
        target_str = pieces[0]

    target = get_target(var, wrapper, target_str, allow_self=True)
    if not target:
        return None, None

    if target in itertools.chain.from_iterable(lastgiven.get(wrapper.source, {}).values()):
        wrapper.send(messages["shaman_no_target_twice"].format(target))
        return None, None

    return totem, target

def give_totem(var, wrapper, target, totem, *, key, role) -> Optional[Tuple[users.User, users.User]]:
    """Give a totem to a player."""

    orig_target = target
    orig_role = get_main_role(orig_target)

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    targrole = get_main_role(target)

    # keys: shaman_success_night_known, shaman_success_random_known, shaman_success_night_unknown, shaman_success_random_unknown
    wrapper.send(messages[key].format(orig_target, totem))
    debuglog("{0} ({1}) TOTEM: {2} ({3}) as {4} ({5}): {6}".format(wrapper.source, role, target, targrole, orig_target, orig_role, totem))

    return target, orig_target

def change_totem(var, player, totem, roles=None):
    """Change the player's totem to the specified totem.

    If roles is specified, only operates if the player has one of those roles.
    Otherwise, changes the totem for all shaman roles the player has.
    If the player previously gave out totems, they are retracted.
    """
    player_roles = get_all_roles(player)
    shaman_roles = set(player_roles & _rolestate.keys())
    if roles is not None:
        shaman_roles.intersection_update(roles)

    for role in shaman_roles:
        del _rolestate[role]["SHAMANS"][:player:]
        del _rolestate[role]["LASTGIVEN"][:player:]
        if isinstance(totem, str):
            if "," in totem:
                totemdict = {}
                tlist = totem.split(",")
                for t in tlist:
                    if ":" not in t:
                        raise ValueError("Expected format totem:count,totem:count,...")
                    tval, count = t.split(":")
                    tval = tval.strip()
                    count = int(count.strip())
                    if tval not in var.CURRENT_GAMEMODE.TOTEM_CHANCES:
                        raise ValueError("{0} is not a valid totem type.".format(tval))
                    if count < 1:
                        raise ValueError("Totem count for {0} cannot be less than 1.".format(tval))
                    totemdict[tval] = count
            else:
                if totem not in var.CURRENT_GAMEMODE.TOTEM_CHANCES:
                    raise ValueError("{0} is not a valid totem type.".format(totem))
                totemdict = {totem: 1}
        else:
            totemdict = totem
        _rolestate[role]["TOTEMS"][player] = totemdict

@event_listener("see", priority=10)
def on_see(evt, var, seer, target):
    if (seer in DECEIT) ^ (target in DECEIT):
        if evt.data["role"] == "wolf":
            evt.data["role"] = var.HIDDEN_ROLE
        else:
            evt.data["role"] = "wolf"

@event_listener("lynch_immunity")
def on_lynch_immunity(evt, var, user, reason):
    if reason == "totem":
        role = get_main_role(user)
        rev_evt = Event("role_revealed", {})
        rev_evt.dispatch(var, user, role)

        channels.Main.send(messages["totem_reveal"].format(user, role))
        evt.data["immune"] = True

@event_listener("lynch")
def on_lynch(evt, var, votee, voters):
    if votee in DESPERATION:
        # Also kill the very last person to vote them, unless they voted themselves last in which case nobody else dies
        target = voters[-1]
        if target is not votee:
            protected = try_protection(var, target, attacker=votee, attacker_role="shaman", reason="totem_desperation")
            if protected is not None:
                channels.Main.send(*protected)
                return

            to_send = "totem_desperation_no_reveal"
            if var.ROLE_REVEAL in ("on", "team"):
                to_send = "totem_desperation"
            channels.Main.send(messages[to_send].format(votee, target, get_reveal_role(target)))
            status.add_dying(var, target, killer_role="shaman", reason="totem_desperation")
            # no kill_players() call here; let our caller do that for us

@event_listener("transition_day", priority=2)
def on_transition_day2(evt, var):
    for shaman, targets in DEATH.items():
        for target in targets:
            evt.data["victims"].append(target)
            evt.data["killers"][target].append(shaman)

@event_listener("transition_day", priority=4.1)
def on_transition_day3(evt, var):
    # protection totems are applied first in default logic, however
    # we set priority=4.1 to allow other modes of protection
    # to pre-empt us if desired
    for player in PROTECTION:
        status.add_protection(var, player, protector=None, protector_role="shaman")

@event_listener("remove_protection")
def on_remove_protection(evt, var, target, attacker, attacker_role, protector, protector_role, reason):
    if attacker_role == "fallen angel" and protector_role == "shaman":
        # we'll never end up killing a shaman who gave out protection, but delete the totem since
        # story-wise it gets demolished at night by the FA
        evt.data["remove"] = True
        while target in havetotem:
            havetotem.remove(target)
            brokentotem.add(target)

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
                protected = try_protection(var, loser, victim, get_main_role(victim), "retribution_totem")
                if protected is not None:
                    channels.Main.send(*protected)
                    return

                evt.data["dead"].append(loser)
                to_send = "totem_death_no_reveal"
                if var.ROLE_REVEAL in ("on", "team"):
                    to_send = "totem_death"
                evt.data["message"][loser].append(messages[to_send].format(victim, loser, get_reveal_role(loser)))

@event_listener("transition_day_end", priority=1)
def on_transition_day_end(evt, var):
    message = []
    havetotem.sort(key=lambda x: x.nick)
    for player, tlist in itertools.groupby(havetotem):
        ntotems = len(list(tlist))
        to_send = "totem_possession_dead"
        if player in get_players():
            to_send = "totem_possession_alive"
        message.append(messages[to_send].format(player, ntotems))
    for player in brokentotem:
        message.append(messages["totem_broken"].format(player))
    channels.Main.send("\n".join(message))

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    # These are the totems of the *previous* nights
    # We need to add them here otherwise transition_night_begin
    # will remove them before they even get used
    for player in LYCANTHROPY:
        status.add_lycanthropy(var, player)
    for player in PESTILENCE:
        status.add_disease(var, player)

@event_listener("begin_day")
def on_begin_day(evt, var):
    # Apply totem effects that need to begin on day proper
    for player in NARCOLEPSY:
        status.add_absent(var, player, "totem")
    for player in IMPATIENCE:
        status.add_force_vote(var, player, get_all_players() - {player})
    for player in PACIFISM:
        status.add_force_abstain(var, player)
    for player in INFLUENCE:
        status.add_vote_weight(var, player)
    for player in REVEALING:
        status.add_lynch_immunity(var, player, "totem")
    for player in MISDIRECTION:
        status.add_misdirection(var, player, as_actor=True)
    for player in LUCK:
        status.add_misdirection(var, player, as_target=True)
    for player in EXCHANGE:
        status.add_exchange(var, player)
    for player in SILENCE:
        status.add_silent(var, player)

@event_listener("player_protected")
def on_player_protected(evt, var, target, attacker, attacker_role, protector, protector_role, reason):
    if protector_role == "shaman":
        evt.data["messages"].append(messages[reason + "_totem"].format(attacker, target))

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
