from __future__ import annotations

import re
import random
import typing
from collections import defaultdict

from src.utilities import *
from src import users, channels, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_dying
from src.cats import Wolf, Win_Stealer

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

KILLS = UserDict() # type: UserDict[users.User, users.User]
PASSED = UserSet()

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_kill(wrapper: MessageDispatcher, message: str):
    """Kill someone at night, but you die too if they aren't a wolf or win stealer!"""
    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    KILLS[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.send(messages["player_kill"].format(orig))

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=("vigilante",))
def vigilante_retract(wrapper: MessageDispatcher, message: str):
    """Removes a vigilante's kill selection."""
    if wrapper.source not in KILLS and wrapper.source not in PASSED:
        return

    del KILLS[:wrapper.source:]
    PASSED.discard(wrapper.source)

    wrapper.send(messages["retracted_kill"])

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("vigilante",))
def vigilante_pass(wrapper: MessageDispatcher, message: str):
    """Do not kill anyone tonight as a vigilante."""
    del KILLS[:wrapper.source:]
    PASSED.add(wrapper.source)
    wrapper.send(messages["hunter_pass"])

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    PASSED.discard(player)
    del KILLS[:player:]
    for vigilante, target in list(KILLS.items()):
        if target is player:
            vigilante.send(messages["hunter_discard"])
            del KILLS[vigilante]

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    for vigilante, target in list(KILLS.items()):
        evt.data["victims"].append(target)
        evt.data["killers"][target].append(vigilante)
        # important, otherwise our del_player listener lets hunter kill again
        del KILLS[vigilante]

        if get_main_role(var, target) not in Wolf | Win_Stealer:
            add_dying(var, vigilante, "vigilante", "night_kill")

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "vigilante":
        del KILLS[:user:]
        PASSED.discard(user)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(KILLS)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_all_players(var, ("vigilante",)))

@event_listener("send_role")
def on_send_role(evt, var):
    ps = get_players(var)
    for vigilante in get_all_players(var, ("vigilante",)):
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(vigilante)
        vigilante.send(messages["vigilante_notify"])
        if var.NIGHT_COUNT > 0:
            vigilante.send(messages["players_list"].format(pl))

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        evt.data["vigilante"] = len(var.ROLES["vigilante"])
    elif kind == "role_categories":
        evt.data["vigilante"] = {"Village", "Killer", "Nocturnal", "Safe"}
