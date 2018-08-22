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

from src.roles._shaman_helper import setup_variables, get_totem_target, give_totem

TOTEMS, LASTGIVEN, SHAMANS = setup_variables("shaman", knows_totem=True)

@command("give", "totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("shaman",))
def shaman_totem(var, wrapper, message):
    """Give a totem to a player."""

    target = get_totem_target(var, wrapper, message, LASTGIVEN)
    if not target:
        return

    SHAMANS[wrapper.source] = give_totem(var, wrapper, target, prefix="You", role="shaman", msg=" of {0}".format(TOTEMS[wrapper.source]))

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
            if ps:
                target = random.choice(ps)
                dispatcher = MessageDispatcher(shaman, shaman)

                SHAMANS[shaman] = give_totem(var, dispatcher, target, prefix=messages["random_totem_prefix"], role="shaman", msg=" of {0}".format(TOTEMS[shaman]))
            else:
                LASTGIVEN[shaman] = None
        elif shaman not in SHAMANS:
            LASTGIVEN[shaman] = None

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, var):
    chances = var.CURRENT_GAMEMODE.TOTEM_CHANCES
    max_totems = sum(x["shaman"] for x in chances.values())
    ps = get_players()
    shamans = get_players(("shaman",))
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
        for t in chances:
            target += chances[t]["shaman"]
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
        shaman.send(messages["players_list"].format(", ".join(p.nick for p in pl)))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["shaman"] = {"Village", "Safe", "Nocturnal"}
    elif kind == "lycanthropy_role":
        evt.data["shaman"] = {"role": "wolf shaman", "prefix": "shaman"}

@event_listener("default_totems")
def set_shaman_totems(evt, var, chances):
    chances["death"]        ["shaman"] = 1
    chances["protection"]   ["shaman"] = 1
    chances["silence"]      ["shaman"] = 1
    chances["revealing"]    ["shaman"] = 1
    chances["desperation"]  ["shaman"] = 1
    chances["impatience"]   ["shaman"] = 1
    chances["pacifism"]     ["shaman"] = 1
    chances["influence"]    ["shaman"] = 1

# vim: set sw=4 expandtab:
