from __future__ import annotations

import functools
import itertools
import random
import re
from typing import Any, Optional

from src import channels, users, status
from src.cats import All, Wolf, Killer
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.events import Event, event_listener
from src.functions import (get_players, get_all_players, get_main_role, get_all_roles, get_reveal_role, get_target,
                           match_totem)
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_protection, try_exchange, is_dying, add_dying
from src.dispatcher import MessageDispatcher
from src.users import User
from src.locations import move_player_home

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
# listens on the "send_role" event, which is where role messages are sent out to    #
# the players. There are several of these kinds of events everywhere, and roles     #
# are expected to make use of the relevant events. For a more in-depth explanation  #
# of the event system, please check our wiki at https://werewolf.chat/Events        #
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

DEATH: UserDict[users.User, UserList] = UserDict()
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
havetotem: list[users.User] = []
brokentotem: set[users.User] = set()

# holds mapping of shaman roles to their state vars, for debugging
# and unit testing purposes
_rolestate: dict[str, dict[str, Any]] = {}

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
    TOTEMS: DefaultUserDict[users.User, dict[str, int]] = DefaultUserDict(dict)
    LASTGIVEN: DefaultUserDict[users.User, DefaultUserDict[str, UserList]] = DefaultUserDict(ulf)
    SHAMANS: DefaultUserDict[users.User, DefaultUserDict[str, UserList]] = DefaultUserDict(ulf)
    RETARGET: DefaultUserDict[users.User, UserDict[users.User, users.User]] = DefaultUserDict(UserDict)
    _rolestate[rolename] = {
        "TOTEMS": TOTEMS,
        "LASTGIVEN": LASTGIVEN,
        "SHAMANS": SHAMANS,
        "RETARGET": RETARGET
    }

    @event_listener("reset", listener_id="shamans.<{}>.on_reset".format(rolename))
    def on_reset(evt: Event, var: GameState):
        TOTEMS.clear()
        LASTGIVEN.clear()
        SHAMANS.clear()
        RETARGET.clear()

    @event_listener("begin_day", listener_id="shamans.<{}>.on_begin_day".format(rolename))
    def on_begin_day(evt: Event, var: GameState):
        SHAMANS.clear()
        RETARGET.clear()

    @event_listener("revealroles_role", listener_id="shamans.<{}>.revealroles_role".format(rolename))
    def on_revealroles(evt: Event, var: GameState, user, role):
        if role == rolename and user in TOTEMS:
            if var.current_phase == "night":
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
    def on_transition_day_begin2(evt: Event, var: GameState):
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
                        # protector role is "shaman" regardless of actual shaman role to simplify logic elsewhere
                        status.add_protection(var, victim, protector=None, protector_role="shaman")
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
    def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
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
    def on_chk_nightdone(evt: Event, var: GameState):
        # only count shaman as acted if they've given out all of their totems
        for shaman in SHAMANS:
            totemcount = sum(TOTEMS[shaman].values())
            given = len(list(itertools.chain.from_iterable(SHAMANS[shaman].values())))
            if given == totemcount:
                evt.data["acted"].append(shaman)
        evt.data["nightroles"].extend(get_all_players(var, (rolename,)))

    @event_listener("get_role_metadata", listener_id="shamans.<{}>.get_role_metadata".format(rolename))
    def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
        if kind == "night_kills":
            # only add shamans here if they were given a death totem
            # even though retribution kills, it is given a special kill message
            evt.data[rolename] = list(itertools.chain.from_iterable(TOTEMS.values())).count("death")

    @event_listener("new_role", listener_id="shamans.<{}>.new_role".format(rolename))
    def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
        if evt.params.inherit_from in TOTEMS and old_role != rolename and evt.data["role"] == rolename:
            totems = TOTEMS.pop(evt.params.inherit_from)
            del SHAMANS[:evt.params.inherit_from:]
            del LASTGIVEN[:evt.params.inherit_from:]

            if knows_totem:
                evt.data["messages"].append(totem_message(totems))
            TOTEMS[player] = totems

    @event_listener("swap_role_state", listener_id="shamans.<{}>.swap_role_state".format(rolename))
    def on_swap_role_state(evt: Event, var: GameState, actor, target, role):
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
    def add_shaman(evt: Event, chances: dict[str, dict[str, int]]):
        evt.data["shaman_roles"].add(rolename)

    @event_listener("transition_night_end", listener_id="shamans.<{}>.on_transition_night_end".format(rolename))
    def on_transition_night_end(evt: Event, var: GameState):
        # check if this role gave out any totems the previous night
        # (lycanthropy, luck, and misdirection all apply the night after they were handed out)
        # since LASTGIVEN is a DefaultUserDict we can't rely on bool() to operate properly as examining state may
        # have inserted keys with default (empty) values
        for user in LASTGIVEN:
            if functools.reduce(lambda x, y: bool(x) or bool(y), LASTGIVEN[user].values(), False):
                # if this is True, this user gave out at least one totem last night
                break
        else:
            # we get here if no users gave out totems last night
            return

        if var.current_mode.TOTEM_CHANCES["lycanthropy"][rolename] > 0:
            status.add_lycanthropy_scope(var, All)
        if var.current_mode.TOTEM_CHANCES["luck"][rolename] > 0:
            status.add_misdirection_scope(var, All, as_target=True)
        if var.current_mode.TOTEM_CHANCES["misdirection"][rolename] > 0:
            status.add_misdirection_scope(var, All, as_actor=True)

    if knows_totem:
        @event_listener("myrole", listener_id="shamans.<{}>.on_myrole".format(rolename))
        def on_myrole(evt: Event, var: GameState, user):
            if evt.data["role"] == rolename and var.current_phase == "night" and user not in SHAMANS:
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

def get_totem_target(var: GameState, wrapper: MessageDispatcher, message, lastgiven, totems) -> tuple[Optional[str], Optional[users.User]]:
    """Get the totem target."""
    pieces = re.split(" +", message)
    totem = None
    match = None

    if len(pieces) > 1:
        # first piece might be a totem name
        match = match_totem(pieces[0], scope=totems)

    if match:
        totem = match.get().key
        target_str = pieces[1]
    else:
        target_str = pieces[0]

    target = get_target(wrapper, target_str, allow_self=True)
    if not target:
        return None, None

    if target in itertools.chain.from_iterable(lastgiven.get(wrapper.source, {}).values()):
        wrapper.send(messages["shaman_no_target_twice"].format(target))
        return None, None

    return totem, target

def give_totem(var: GameState, wrapper: MessageDispatcher, target: User, totem: str, *, key, role) -> Optional[tuple[users.User, users.User]]:
    """Give a totem to a player."""

    orig_target = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return None

    # keys: shaman_success_night_known, shaman_success_random_known, shaman_success_night_unknown, shaman_success_random_unknown
    wrapper.send(messages[key].format(orig_target, totem))
    return target, orig_target

def change_totem(var: GameState, player: User, totem: str, roles=None):
    """Change the player's totem to the specified totem.

    If roles is specified, only operates if the player has one of those roles.
    Otherwise, changes the totem for all shaman roles the player has.
    If the player previously gave out totems, they are retracted.
    """
    player_roles = get_all_roles(var, player)
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
                        # FIXME: localize
                        raise ValueError("Expected format totem:count,totem:count,...")
                    tval, count = t.split(":")
                    tval = tval.strip()
                    count = int(count.strip())
                    match = match_totem(tval, scope=var.current_mode.TOTEM_CHANCES)
                    if not match:
                        # FIXME: localize
                        raise ValueError("{0} is not a valid totem type.".format(tval))
                    tval = match.get().key
                    if count < 1:
                        # FIXME: localize
                        raise ValueError("Totem count for {0} cannot be less than 1.".format(tval))
                    totemdict[tval] = count
            else:
                match = match_totem(totem, scope=var.current_mode.TOTEM_CHANCES)
                if not match:
                    # FIXME: localize
                    raise ValueError("{0} is not a valid totem type.".format(totem))
                totemdict = {match.get().key: 1}
        else:
            totemdict = totem
        _rolestate[role]["TOTEMS"][player] = totemdict

@event_listener("see", priority=10)
def on_see(evt: Event, var: GameState, seer, target):
    if (seer in DECEIT) ^ (target in DECEIT):
        if evt.data["role"] == "wolf":
            evt.data["role"] = var.hidden_role
        else:
            evt.data["role"] = "wolf"

@event_listener("lynch_immunity")
def on_lynch_immunity(evt: Event, var: GameState, user, reason):
    if reason == "totem":
        role = get_main_role(var, user)
        rev_evt = Event("role_revealed", {})
        rev_evt.dispatch(var, user, role)

        channels.Main.send(messages["totem_reveal"].format(user, role))
        evt.data["immune"] = True

@event_listener("lynch")
def on_lynch(evt: Event, var: GameState, votee, voters):
    if votee in DESPERATION:
        # Also kill the very last person to vote them, unless they voted themselves last in which case nobody else dies
        target = voters[-1]
        main_role = get_main_role(var, votee)
        if target is not votee:
            protected = try_protection(var, target, attacker=votee, attacker_role=main_role, reason="totem_desperation")
            if protected is not None:
                channels.Main.send(*protected)
                return

            to_send = "totem_desperation_no_reveal"
            if var.role_reveal in ("on", "team"):
                to_send = "totem_desperation"
            channels.Main.send(messages[to_send].format(votee, target, get_reveal_role(var, target)))
            status.add_dying(var, target, killer_role=main_role, reason="totem_desperation", killer=votee)
            # no kill_players() call here; let our caller do that for us

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    for shaman, targets in DEATH.items():
        for target in targets:
            evt.data["victims"].add(target)
            evt.data["killers"][target].append(shaman)

@event_listener("remove_protection")
def on_remove_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if attacker_role == "fallen angel" and protector_role == "shaman":
        # we'll never end up killing a shaman who gave out protection, but delete the totem since
        # story-wise it gets demolished at night by the FA
        evt.data["remove"] = True
        while target in havetotem:
            havetotem.remove(target)
            brokentotem.add(target)

@event_listener("transition_day_begin", priority=6)
def on_transition_day_begin(evt: Event, var: GameState):
    # Reset totem variables
    DEATH.clear()
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

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if not death_triggers or player not in RETRIBUTION:
        return
    loser = evt.params.killer
    if loser is None and evt.params.killer_role == "wolf" and evt.params.reason == "night_kill":
        pl = get_players(var, Wolf & Killer)
        if pl:
            loser = random.choice(pl)
    if loser is None or is_dying(var, loser):
        # person that killed us is already dead?
        return

    ret_evt = Event("retribution_kill", {"target": loser, "message": []})
    ret_evt.dispatch(var, player, loser)
    loser = ret_evt.data["target"]
    channels.Main.send(*ret_evt.data["message"])
    if loser is not None and is_dying(var, loser):
        loser = None
    if loser is not None:
        protected = try_protection(var, loser, player, evt.params.main_role, "retribution_totem")
        if protected is not None:
            channels.Main.send(*protected)
            return

        to_send = "totem_death_no_reveal"
        if var.role_reveal in ("on", "team"):
            to_send = "totem_death"
        channels.Main.send(messages[to_send].format(player, loser, get_reveal_role(var, loser)))
        add_dying(var, loser, evt.params.main_role, "retribution_totem", killer=player)

@event_listener("transition_day_end")
def on_transition_day_end(evt: Event, var: GameState):
    message = []
    havetotem.sort(key=lambda x: x.nick)
    for player, tlist in itertools.groupby(havetotem):
        ntotems = len(list(tlist))
        to_send = "totem_possession_dead"
        if player in get_players(var):
            to_send = "totem_possession_alive"
        message.append(messages[to_send].format(player, ntotems))
    for player in brokentotem:
        message.append(messages["totem_broken"].format(player))
    channels.Main.send("\n".join(message))

@event_listener("transition_night_end")
def on_transition_night_end(evt: Event, var: GameState):
    # These are the totems of the *previous* nights
    # We need to add them here otherwise transition_night_begin
    # will remove them before they even get used
    for player in LYCANTHROPY:
        status.add_lycanthropy(var, player)
    for player in PESTILENCE:
        status.add_disease(var, player)

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    # Apply totem effects that need to begin on day proper
    for player in NARCOLEPSY:
        status.add_absent(var, player, "totem")
        move_player_home(var, player)
    for player in IMPATIENCE:
        status.add_force_vote(var, player, get_all_players(var) - {player})
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
def on_player_protected(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if protector_role == "shaman":
        evt.data["messages"].append(messages[reason + "_totem"].format(attacker, target))

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    DEATH.clear()
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
def set_all_totems(evt: Event, chances: dict[str, dict[str, int]]):
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
