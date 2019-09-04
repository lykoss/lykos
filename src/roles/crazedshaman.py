import re
import random
import itertools
from collections import defaultdict, deque

from src.utilities import *
from src import debuglog, errlog, plog, users, channels
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.events import Event
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.dispatcher import MessageDispatcher
from src.messages import messages
from src.status import try_misdirection, try_exchange, is_silent
from src.cats import Win_Stealer

from src.roles.helper.shamans import setup_variables, get_totem_target, give_totem, totem_message

TOTEMS, LASTGIVEN, SHAMANS, RETARGET = setup_variables("crazed shaman", knows_totem=False)

@command("give", "totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("crazed shaman",))
def crazed_shaman_totem(var, wrapper, message):
    """Give a random totem to a player."""

    totem_types = list(TOTEMS[wrapper.source].keys())
    totem, target = get_totem_target(var, wrapper, message, LASTGIVEN, []) # don't pass totem_types so they can't autocomplete what random totems they have
    if not target:
        return

    # get the first totem type they haven't fully given out yet
    for type in totem_types:
        given = len(SHAMANS[wrapper.source][type])
        total = TOTEMS[wrapper.source][type]
        if given < total:
            totem = type
            break
    else: # all totems are given out, change targets for a random one
        totem = random.choice(totem_types)

    orig_target = target
    target = RETARGET[wrapper.source].get(target, target)
    if target in itertools.chain.from_iterable(SHAMANS[wrapper.source].values()):
        wrapper.send(messages["shaman_no_stacking"].format(orig_target))
        return

    given = give_totem(var, wrapper, target, prefix="You", role="crazed shaman", msg="")
    if given:
        victim, target = given
        if victim is not target:
            RETARGET[wrapper.source][target] = victim
        SHAMANS[wrapper.source][totem].append(victim)
        if len(SHAMANS[wrapper.source][totem]) > TOTEMS[wrapper.source][totem]:
            SHAMANS[wrapper.source][totem].pop(0)

@event_listener("player_win")
def on_player_win(evt, var, user, role, winner, survived):
    if role == "crazed shaman" and survived and singular(winner) not in Win_Stealer:
        evt.data["iwon"] = True

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt, var):
    # Select random totem recipients if shamans didn't act
    pl = get_players()
    for shaman in get_players(("crazed shaman",)):
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
                    given = give_totem(var, dispatcher, target, prefix=messages["random_totem_prefix"], role="crazed shaman", msg="")
                    if given:
                        SHAMANS[shaman][totem].append(given[0])

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, var):
    chances = var.CURRENT_GAMEMODE.TOTEM_CHANCES
    max_totems = sum(x["crazed shaman"] for x in chances.values())
    ps = get_players()
    shamans = get_players(("crazed shaman",))
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
            target += chances[t]["crazed shaman"]
            if rand <= target:
                TOTEMS[shaman] = {t: 1}
                break
        event = Event("totem_assignment", {"totems": TOTEMS[shaman]})
        event.dispatch(var, "crazed shaman")
        TOTEMS[shaman] = event.data["totems"]

        num_totems = sum(TOTEMS[shaman].values())
        if shaman.prefers_simple():
            shaman.send(messages["shaman_simple"].format("crazed shaman"))
        else:
            if num_totems > 1:
                shaman.send(messages["shaman_notify_multiple_random"].format("crazed shaman"))
            else:
                shaman.send(messages["shaman_notify"].format("crazed shaman"))
        shaman.send(totem_message(TOTEMS[shaman], count_only=True))
        shaman.send(messages["players_list"].format(", ".join(p.nick for p in pl)))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["crazed shaman"] = {"Neutral", "Nocturnal"}
    elif kind == "lycanthropy_role":
        evt.data["crazed shaman"] = {"role": "wolf shaman", "prefix": "shaman"}

@event_listener("default_totems")
def set_crazed_totems(evt, chances):
    for chance in chances.values():
        chance["crazed shaman"] = 1
