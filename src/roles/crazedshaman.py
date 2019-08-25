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
from src.status import try_misdirection, try_exchange, is_silent
from src.cats import Win_Stealer

from src.roles.helper.shamans import setup_variables, get_totem_target, give_totem

TOTEMS, LASTGIVEN, SHAMANS = setup_variables("crazed shaman", knows_totem=False)

@command("totem", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("crazed shaman",))
def crazed_shaman_totem(var, wrapper, message):
    """Give a random totem to a player."""

    target = get_totem_target(var, wrapper, message, LASTGIVEN)
    if not target:
        return

    give_totem(var, wrapper, target, key="shaman_success_night", role="crazed shaman")

@event_listener("player_win")
def on_player_win(evt, var, user, role, winner, survived):
    if role == "crazed shaman" and survived and singular(winner) not in Win_Stealer:
        evt.data["iwon"] = True

@event_listener("transition_day_begin", priority=4)
def on_transition_day_begin(evt, var):
    # Select random totem recipients if shamans didn't act
    pl = get_players()
    for shaman in get_players(("crazed shaman",)):
        if shaman not in SHAMANS and not is_silent(var, shaman):
            ps = pl[:]
            if shaman in LASTGIVEN:
                if LASTGIVEN[shaman] in ps:
                    ps.remove(LASTGIVEN[shaman])
            if ps:
                target = random.choice(ps)
                dispatcher = MessageDispatcher(shaman, shaman)

                give_totem(var, dispatcher, target, key="shaman_success_random", role="crazed shaman")
            else:
                LASTGIVEN[shaman] = None
        elif shaman not in SHAMANS:
            LASTGIVEN[shaman] = None

@event_listener("transition_night_end", priority=2.01)
def on_transition_night_end(evt, var):
    chances = var.CURRENT_GAMEMODE.TOTEM_CHANCES
    max_totems = sum(x["crazed shaman"] for x in chances.values())
    ps = get_players()
    shamans = get_players(("crazed shaman",))
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
            target += chances[t]["crazed shaman"]
            if rand <= target:
                TOTEMS[shaman] = t
                break
        if shaman.prefers_simple():
            shaman.send(messages["role_simple"].format("crazed shaman"))
        else:
            shaman.send(messages["shaman_random_notify"].format("crazed shaman"))
        shaman.send(messages["players_list"].format(pl))

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

# vim: set sw=4 expandtab:
