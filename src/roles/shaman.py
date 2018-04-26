import re
import random
import itertools
from collections import defaultdict, deque

import botconfig
from src.utilities import *
from src import debuglog, errlog, plog, users, channels
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.dispatcher import MessageDispatcher
from src.messages import messages
from src.events import Event

from src.roles._shaman_helper import setup_variables, get_totem_target, give_totem

def get_tags(var, totem):
    tags = set()
    if totem in var.BENEFICIAL_TOTEMS:
        tags.add("beneficial")
    return tags

TOTEMS, LASTGIVEN, SHAMANS = setup_variables("shaman", knows_totem=True, get_tags=get_tags)

@command("give", "totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("shaman",))
def shaman_totem(var, wrapper, message):
    """Give a totem to a player."""

    target = get_totem_target(var, wrapper, message, LASTGIVEN)
    if not target:
        return

    totem = TOTEMS[wrapper.source]

    SHAMANS[wrapper.source] = give_totem(var, wrapper, target, prefix="You", tags=get_tags(var, totem), role="shaman", msg=" of {0}".format(totem))

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt, var):
    # Select random totem recipients if shamans didn't act
    pl = get_players()
    for shaman in get_players(("shaman",)):
        if shaman not in SHAMANS and shaman.nick not in var.SILENCED:
            ps = pl[:]
            if shaman in LASTGIVEN:
                if LASTGIVEN[shaman] in ps:
                    ps.remove(LASTGIVEN[shaman])
            levt = Event("get_random_totem_targets", {"targets": ps})
            levt.dispatch(var, shaman)
            ps = levt.data["targets"]
            if ps:
                target = random.choice(ps)
                dispatcher = MessageDispatcher(shaman, shaman)

                tags = get_tags(var, TOTEMS[shaman])

                SHAMANS[shaman] = give_totem(var, dispatcher, target, prefix=messages["random_totem_prefix"], tags=tags, role="shaman", msg=" of {0}".format(TOTEMS[shaman]))
            else:
                LASTGIVEN[shaman] = None
        elif shaman not in SHAMANS:
            LASTGIVEN[shaman] = None

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, var):
    max_totems = 0
    ps = get_players()
    shamans = get_players(("shaman",))
    index = var.TOTEM_ORDER.index("shaman")
    for c in var.TOTEM_CHANCES.values():
        max_totems += c[index]

    for s in list(LASTGIVEN):
        if s not in shamans:
            del LASTGIVEN[s]

    for shaman in shamans:
        pl = ps[:]
        random.shuffle(pl)
        if LASTGIVEN.get(shaman):
            if LASTGIVEN[shaman] in pl:
                pl.remove(LASTGIVEN[shaman])

        target = 0
        rand = random.random() * max_totems
        for t in var.TOTEM_CHANCES.keys():
            target += var.TOTEM_CHANCES[t][index]
            if rand <= target:
                TOTEMS[shaman] = t
                break
        if shaman.prefers_simple():
            shaman.send(messages["shaman_simple"].format("shaman"))
            shaman.send(messages["totem_simple"].format(TOTEMS[shaman]))
        else:
            shaman.send(messages["shaman_notify"].format("shaman", ""))
            totem = TOTEMS[shaman]
            tmsg = messages["shaman_totem"].format(totem)
            tmsg += messages[totem + "_totem"]
            shaman.send(tmsg)
        shaman.send("Players: " + ", ".join(p.nick for p in pl))

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_players(("shaman",)))

# vim: set sw=4 expandtab:
