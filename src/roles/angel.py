from __future__ import annotations

import re
import random
import itertools
import math
import typing
from collections import defaultdict

from src.utilities import *
from src import users, channels
from src.functions import get_players, get_all_players, get_target, get_main_role
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_protection, add_dying
from src.events import Event, event_listener
from src.cats import Wolf

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState
    from typing import Optional, Set
    from src.users import User

GUARDED = UserDict() # type: UserDict[users.User, users.User]
LASTGUARDED = UserDict() # type: UserDict[users.User, users.User]
PASSED = UserSet()

@command("guard", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("guardian angel",))
def guard(wrapper: MessageDispatcher, message: str):
    """Guard a player, preventing them from being killed that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], allow_self=var.GUARDIAN_ANGEL_CAN_GUARD_SELF, not_self_message="cannot_guard_self")
    if not target:
        return

    if LASTGUARDED.get(wrapper.source) is target:
        wrapper.pm(messages["guardian_target_another"].format(target))
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    add_protection(var, target, wrapper.source, "guardian angel")
    GUARDED[wrapper.source] = target
    LASTGUARDED[wrapper.source] = target

    if wrapper.source is target:
        wrapper.pm(messages["guardian_guard_self"])
    else:
        wrapper.pm(messages["protecting_target"].format(target))
        target.send(messages["target_protected"])

@command("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("guardian angel",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Decline to use your special power for that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    PASSED.add(wrapper.source)
    wrapper.pm(messages["guardian_no_protect"])

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: Set[str], death_triggers: bool):
    if var.PHASE == "night" and player in GUARDED:
        GUARDED[player].send(messages["protector_disappeared"])
    for dictvar in (GUARDED, LASTGUARDED):
        for k,v in list(dictvar.items()):
            if player in (k, v):
                del dictvar[k]
    PASSED.discard(player)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "guardian angel" and evt.data["role"] != "guardian angel":
        if player in GUARDED:
            guarded = GUARDED.pop(player)
            guarded.send(messages["protector_disappeared"])
        del LASTGUARDED[:player:]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(GUARDED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_players(var, ("guardian angel",)))

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end(evt: Event, var: GameState, victims):
    for gangel in get_all_players(var, ("guardian angel",)):
        if GUARDED.get(gangel) in get_players(var, Wolf) and gangel not in evt.data["dead"]:
            r = random.random()
            if r < var.GUARDIAN_ANGEL_DIES_CHANCE:
                to_send = "guardian_angel_protected_wolf_no_reveal"
                if var.role_reveal == "on":
                    to_send = "guardian_angel_protected_wolf"
                evt.data["message"][gangel].append(messages[to_send].format(gangel))
                evt.data["dead"].append(gangel)

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    # needs to be here in order to allow protections to work during the daytime
    # (right now they don't due to other reasons, but that may change)
    GUARDED.clear()

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    for gangel in get_all_players(var, ("guardian angel",)):
        pl = ps[:]
        random.shuffle(pl)
        if gangel in LASTGUARDED:
            if LASTGUARDED[gangel] in pl:
                pl.remove(LASTGUARDED[gangel])
        chance = math.floor(var.GUARDIAN_ANGEL_DIES_CHANCE * 100)

        gangel.send(messages["guardian_angel_notify"])
        if var.NIGHT_COUNT == 0:
            return
        if chance > 0:
            gangel.send(messages["bodyguard_death_chance"].format(chance))
        if var.GUARDIAN_ANGEL_CAN_GUARD_SELF:
            gangel.send(messages["guardian_self_notification"])
        else:
            pl.remove(gangel)
        gangel.send(messages["players_list"].format(pl))

@event_listener("player_protected")
def on_player_protected(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if protector_role == "guardian angel":
        evt.data["messages"].append(messages[reason + "_angel"].format(attacker, target))

@event_listener("remove_protection")
def on_remove_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if attacker_role == "fallen angel" and protector_role == "guardian angel":
        evt.data["remove"] = True
        if protector is not target:
            protector.send(messages[reason + "_success"].format(target))
        target.send(messages[reason + "_deprotect"])
        if random.random() < var.FALLEN_ANGEL_KILLS_GUARDIAN_ANGEL_CHANCE:
            add_dying(var, protector, killer_role="fallen angel", reason=reason)

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    PASSED.clear()
    # clear out LASTGUARDED for people that didn't guard last night
    for g in list(LASTGUARDED.keys()):
        if g not in GUARDED:
            del LASTGUARDED[g]

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    GUARDED.clear()
    LASTGUARDED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["guardian angel"] = {"Village", "Safe", "Nocturnal"}
    elif kind == "lycanthropy_role":
        evt.data["guardian angel"] = {"role": "fallen angel", "prefix": "fallen_angel", "secondary_roles": {"assassin"}}
