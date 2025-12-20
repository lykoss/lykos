from __future__ import annotations

import re
from typing import Optional, Union

from src import config
from src import users
from src.cats import Wolf
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target, get_main_role
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_protection, add_dying
from src.users import User
from src.random import random

GUARDED: UserDict[users.User, users.User] = UserDict()
LASTGUARDED: UserDict[users.User, users.User] = UserDict()
PASSED = UserSet()

@command("guard", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("guardian angel",))
def guard(wrapper: MessageDispatcher, message: str):
    """Guard a player, preventing them from being killed that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], allow_self=config.Main.get("gameplay.safes.guard_self"), not_self_message="cannot_guard_self")
    if not target:
        return

    if LASTGUARDED.get(wrapper.source) is target:
        wrapper.pm(messages["guardian_target_another"].format(target))
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    add_protection(var, target, wrapper.source, "guardian angel")
    PASSED.discard(wrapper.source)
    GUARDED[wrapper.source] = target
    LASTGUARDED[wrapper.source] = target

    if wrapper.source is target:
        wrapper.pm(messages["guardian_guard_self"])
    else:
        wrapper.pm(messages["protecting_target"].format(target))
        target.send(messages["target_protected"])

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("guardian angel",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Decline to use your special power for that night."""
    if wrapper.source in GUARDED:
        wrapper.pm(messages["already_protecting"])
        return

    PASSED.add(wrapper.source)
    wrapper.pm(messages["guardian_no_protect"])

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    if var.current_phase == "night" and player in GUARDED:
        GUARDED[player].send(messages["protector_disappeared"])
    for dictvar in (GUARDED, LASTGUARDED):
        for k, v in list(dictvar.items()):
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
    evt.data["nightroles"].extend(get_all_players(var, ("guardian angel",)))

@event_listener("resolve_killer_tag")
def on_resolve_killer_tag(evt: Event, var: GameState, victim: User, tag: str):
    if tag == "@angel":
        # GA is attacked by the wolf they (mistakenly?) guarded
        evt.data["attacker"] = GUARDED[victim]
        evt.data["role"] = get_main_role(var, GUARDED[victim])
        evt.data["try_lycanthropy"] = True

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    chance = config.Main.get("gameplay.safes.angel_dies")
    if chance == 0:
        return
    evt.data["kill_priorities"]["@angel"] = 10
    wolves = get_players(var, Wolf)
    for angel in get_all_players(var, ("guardian angel",)):
        if GUARDED.get(angel) in wolves and random.random() * 100 < chance:
            evt.data["victims"].add(angel)
            evt.data["killers"][angel].append("@angel")

@event_listener("night_death_message")
def on_night_death_message(evt: Event, var: GameState, victim: User, killer: Union[User, str]):
    if killer == "@angel":
        evt.data["key"] = "protected_wolf" if var.role_reveal == "on" else "protected_wolf_no_reveal"
        evt.data["args"] = [victim, "guardian angel"]

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
        chance = config.Main.get("gameplay.safes.angel_dies")

        gangel.send(messages["guardian_angel_notify"])
        if var.next_phase != "night":
            return
        if chance > 0:
            gangel.send(messages["bodyguard_death_chance"].format(chance))
        if config.Main.get("gameplay.safes.guard_self"):
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
        if (random.random() * 100) < config.Main.get("gameplay.safes.fallen_kills"):
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
