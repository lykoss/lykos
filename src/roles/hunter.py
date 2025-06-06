from __future__ import annotations

import re
from typing import Optional

from src import users
from src.containers import UserSet, UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.users import User
from src.random import random

KILLS: UserDict[users.User, users.User] = UserDict()
HUNTERS = UserSet()
PASSED = UserSet()

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_kill(wrapper: MessageDispatcher, message: str):
    """Kill someone once per game."""
    if wrapper.source in HUNTERS and wrapper.source not in KILLS:
        wrapper.pm(messages["hunter_already_killed"])
        return
    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    KILLS[wrapper.source] = target
    HUNTERS.add(wrapper.source)
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["player_kill"].format(orig))

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=("hunter",))
def hunter_retract(wrapper: MessageDispatcher, message: str):
    """Removes a hunter's kill selection."""
    if wrapper.source not in KILLS and wrapper.source not in PASSED:
        return

    del KILLS[:wrapper.source:]
    HUNTERS.discard(wrapper.source)
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["retracted_kill"])

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hunter",))
def hunter_pass(wrapper: MessageDispatcher, message: str):
    """Do not use hunter's once-per-game kill tonight."""
    if wrapper.source in HUNTERS and wrapper.source not in KILLS:
        wrapper.pm(messages["hunter_already_killed"])
        return

    del KILLS[:wrapper.source:]
    HUNTERS.discard(wrapper.source)
    PASSED.add(wrapper.source)
    wrapper.pm(messages["hunter_pass"])

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    HUNTERS.discard(player)
    PASSED.discard(player)
    del KILLS[:player:]
    for h, v in list(KILLS.items()):
        if v is player:
            HUNTERS.discard(h)
            h.send(messages["hunter_discard"])
            del KILLS[h]

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    for k, d in list(KILLS.items()):
        evt.data["victims"].add(d)
        evt.data["killers"][d].append(k)
        # important, otherwise our del_player listener instructs hunter to kill again
        del KILLS[k]

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "hunter":
        del KILLS[:player:]
        HUNTERS.discard(player)
        PASSED.discard(player)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(KILLS)
    evt.data["acted"].extend(PASSED)
    hunter_users = get_all_players(var, ("hunter",))
    evt.data["nightroles"].extend([p for p in hunter_users if p not in HUNTERS or p in KILLS])

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    for hunter in get_all_players(var, ("hunter",)):
        if hunter in HUNTERS:
            continue # already killed
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(hunter)
        hunter.send(messages["hunter_notify"])
        if var.next_phase == "night":
            hunter.send(messages["players_list"].format(pl))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    KILLS.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    KILLS.clear()
    PASSED.clear()
    HUNTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "night_kills":
        # hunters is the set of all hunters that have not killed in a *previous* night
        # (if they're in both HUNTERS and KILLS, then they killed tonight and should be counted)
        hunters = (var.roles["hunter"] - HUNTERS) | set(KILLS.keys())
        evt.data["hunter"] = len(hunters)
    elif kind == "role_categories":
        evt.data["hunter"] = {"Village", "Killer", "Safe"}
