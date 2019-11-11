import re
import random
import itertools
from collections import defaultdict, deque

from src.utilities import *
from src import debuglog, errlog, plog, users, channels
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.dispatcher import MessageDispatcher
from src.messages import messages
from src.events import Event
from src.status import try_misdirection, try_exchange, is_silent

from src.roles.helper.shamans import get_totem_target, give_totem, setup_variables, totem_message
from src.roles.helper.wolves import register_killer

TOTEMS, LASTGIVEN, SHAMANS, RETARGET = setup_variables("wolf shaman", knows_totem=True)

register_killer("wolf shaman")

@command("totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("wolf shaman",))
def wolf_shaman_totem(var, wrapper, message):
    """Give a totem to a player."""

    totem_types = list(TOTEMS[wrapper.source].keys())
    totem, target = get_totem_target(var, wrapper, message, LASTGIVEN, totem_types)
    if not target:
        return

    if not totem:
        totem_types = list(TOTEMS[wrapper.source].keys())
        if len(totem_types) == 1:
            totem = totem_types[0]
        else:
            wrapper.send(messages["shaman_ambiguous_give"])
            return

    orig_target = target
    target = RETARGET[wrapper.source].get(target, target)
    if target in itertools.chain.from_iterable(SHAMANS[wrapper.source].values()):
        wrapper.send(messages["shaman_no_stacking"].format(orig_target))
        return

    given = give_totem(var, wrapper, target, key="shaman_success_night_known", role="wolf shaman")
    if given:
        victim, target = given
        if victim is not target:
            RETARGET[wrapper.source][target] = victim
        SHAMANS[wrapper.source][totem].append(victim)
        if len(SHAMANS[wrapper.source][totem]) > TOTEMS[wrapper.source][totem]:
            SHAMANS[wrapper.source][totem].pop(0)

    relay_wolfchat_command(wrapper.client, wrapper.source.nick, messages["shaman_wolfchat"].format(wrapper.source, target), ("wolf shaman",), is_wolf_command=True)

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt, var):
    # Select random totem recipients if shamans didn't act
    pl = get_players()
    for shaman in get_players(("wolf shaman",)):
        if is_silent(var, shaman):
            continue

        ps = pl[:]
        for given in itertools.chain.from_iterable(LASTGIVEN[shaman].values()):
            if given in ps:
                ps.remove(given)
        for given in itertools.chain.from_iterable(SHAMANS[shaman].values()):
            if given in ps:
                ps.remove(given)
        for totem, count in TOTEMS[shaman].items():
            mustgive = count - len(SHAMANS[shaman][totem])
            for i in range(mustgive):
                if ps:
                    target = random.choice(ps)
                    ps.remove(target)
                    dispatcher = MessageDispatcher(shaman, shaman)
                    given = give_totem(var, dispatcher, target, key="shaman_success_random_known", role="wolf shaman")
                    if given:
                        relay_wolfchat_command(shaman.client, shaman.nick, messages["shaman_wolfchat"].format(shaman, target), ("wolf shaman",), is_wolf_command=True)
                        SHAMANS[shaman][totem].append(given[0])

@event_listener("transition_night_end", priority=1.99)
def on_transition_night_end(evt, var):
    chances = var.CURRENT_GAMEMODE.TOTEM_CHANCES
    max_totems = sum(x["wolf shaman"] for x in chances.values())
    ps = get_players()
    shamans = get_players(("wolf shaman",))
    for s in list(LASTGIVEN):
        if s not in shamans:
            del LASTGIVEN[s]

    shamans = list(shamans)
    random.shuffle(shamans)
    for shaman in shamans:
        pl = ps[:]
        random.shuffle(pl)
        for given in itertools.chain.from_iterable(LASTGIVEN[shaman].values()):
            if given in pl:
                pl.remove(given)

        target = 0
        rand = random.random() * max_totems
        for t in chances:
            target += chances[t]["wolf shaman"]
            if rand <= target:
                TOTEMS[shaman] = {t: 1}
                break
        event = Event("totem_assignment", {"totems": TOTEMS[shaman]})
        event.dispatch(var, "wolf shaman")
        TOTEMS[shaman] = event.data["totems"]

        num_totems = sum(TOTEMS[shaman].values())
        if shaman.prefers_simple():
            shaman.send(messages["role_simple"].format("wolf shaman"))
        else:
            if num_totems > 1:
                shaman.send(messages["shaman_notify_multiple_known"].format("wolf shaman"))
            else:
                shaman.send(messages["shaman_notify"].format("wolf shaman"))
        tmsg = totem_message(TOTEMS[shaman])
        if not shaman.prefers_simple():
            for totem in TOTEMS[shaman]:
                tmsg += " " + messages[totem + "_totem"]
        shaman.send(tmsg)
        # player list and notification that WS can kill is handled by shared wolves handler

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["wolf shaman"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal"}

@event_listener("default_totems")
def set_wolf_totems(evt, chances):
    chances["protection"]   ["wolf shaman"] = 1
    chances["silence"]      ["wolf shaman"] = 1
    chances["impatience"]   ["wolf shaman"] = 1
    chances["pacifism"]     ["wolf shaman"] = 1
    chances["lycanthropy"]  ["wolf shaman"] = 1
    chances["luck"]         ["wolf shaman"] = 1
    chances["retribution"]  ["wolf shaman"] = 1
    chances["misdirection"] ["wolf shaman"] = 1
    chances["deceit"]       ["wolf shaman"] = 1
