from __future__ import annotations

import re
import random
import itertools
import math
from collections import defaultdict
from typing import Set, Optional, List, TYPE_CHECKING

from src.functions import get_players, get_all_players, get_target, get_main_role
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_protection, add_dying
from src.events import Event, event_listener
from src.cats import Wolf
from src.users import User
from src import config

if TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState

GUARDED: UserDict[User, User] = UserDict()
PASSED = UserSet()
DYING = UserSet()

@command("guard", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("bodyguard",))
def guard(wrapper: MessageDispatcher, message: str):
    """Guard a player, preventing them from being killed that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="cannot_guard_self")
    if not target:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    add_protection(var, target, wrapper.source, "bodyguard")
    GUARDED[wrapper.source] = target

    wrapper.pm(messages["protecting_target"].format(target))
    target.send(messages["target_protected"])

@command("pass", chan=False, pm=True, playing=True, phases=("night",), roles=("bodyguard",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Decline to use your special power for that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return
    PASSED.add(wrapper.source)
    wrapper.pm(messages["guardian_no_protect"])

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: Set[str], death_triggers: bool):
    if var.current_phase == "night" and player in GUARDED:
        GUARDED[player].send(messages["protector_disappeared"])
    for k,v in list(GUARDED.items()):
        if player in (k, v):
            del GUARDED[k]
    PASSED.discard(player)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "bodyguard" and evt.data["role"] != "bodyguard":
        if player in GUARDED:
            guarded = GUARDED.pop(player)
            guarded.send(messages["protector_disappeared"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(GUARDED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_players(var, ("bodyguard",)))

@event_listener("transition_day_resolve_end", priority=3)
def on_transition_day_resolve_end(evt: Event, var: GameState, victims: List[User]):
    for bodyguard in DYING:
        evt.data["message"][bodyguard].clear()
    DYING.clear()
    for bodyguard in get_all_players(var, ("bodyguard",)):
        if GUARDED.get(bodyguard) in get_players(var, Wolf) and bodyguard not in evt.data["dead"]:
            r = random.random() * 100
            if r < config.Main.get("gameplay.safes.bodyguard_dies"):
                if var.role_reveal == "on":
                    evt.data["message"][bodyguard].append(messages["bodyguard_protected_wolf"].format(bodyguard))
                else: # off and team
                    evt.data["message"][bodyguard].append(messages["bodyguard_protection"].format(bodyguard))
                evt.data["dead"].append(bodyguard)

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    # needs to be here in order to allow bodyguard protections to work during the daytime
    # (right now they don't due to other reasons, but that may change)
    GUARDED.clear()

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    for bg in get_all_players(var, ("bodyguard",)):
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(bg)
        chance = config.Main.get("gameplay.safes.bodyguard_dies")

        bg.send(messages["bodyguard_notify"])
        if var.next_phase != "night":
            return
        if chance > 0:
            bg.send(messages["bodyguard_death_chance"].format(chance))
        bg.send(messages["players_list"].format(pl))

@event_listener("try_protection")
def on_try_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, reason: str):
    if len(evt.data["protections"]) <= 1: # We only care if there's 2+ protections
        return
    for (protector, protector_role, scope) in list(evt.data["protections"]):
        if protector_role == "bodyguard":
            evt.data["protections"].remove((protector, protector_role, scope))
            evt.data["protections"].append((protector, protector_role, scope))

@event_listener("player_protected")
def on_player_protected(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if protector_role == "bodyguard":
        evt.data["messages"].append(messages[reason + "_bodyguard"].format(attacker, target, protector))
        add_dying(var, protector, killer_role=attacker_role, reason="bodyguard")
        if var.current_phase == "night" and var.in_phase_transition: # currently transitioning
            DYING.add(protector)

@event_listener("remove_protection")
def on_remove_protection(evt: Event, var: GameState, target: User, attacker: User, attacker_role: str, protector: User, protector_role: str, reason: str):
    if attacker_role == "fallen angel" and protector_role == "bodyguard":
        evt.data["remove"] = True
        add_dying(var, protector, killer_role="fallen angel", reason=reason)
        protector.send(messages[reason + "_success"].format(target))
        target.send(messages[reason + "_deprotect"])

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    PASSED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    GUARDED.clear()
    PASSED.clear()
    DYING.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["bodyguard"] = {"Village", "Safe", "Nocturnal"}
