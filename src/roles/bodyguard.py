from __future__ import annotations

import re
from typing import Optional, Union

from src import config
from src.cats import Wolf
from src.containers import UserSet, UserDict
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target, get_main_role
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_protection, add_dying
from src.users import User
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState
from src.random import random

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

    # we want bodyguard to fire last out of actual protections
    add_protection(var, target, wrapper.source, "bodyguard", priority=20)
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
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
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

@event_listener("resolve_killer_tag")
def on_resolve_killer_tag(evt: Event, var: GameState, victim: User, tag: str):
    if tag == "@bodyguard":
        # bodyguard is attacked by the wolf they (mistakenly?) guarded
        evt.data["attacker"] = GUARDED[victim]
        evt.data["role"] = get_main_role(var, GUARDED[victim])
        evt.data["try_lycanthropy"] = True

@event_listener("night_kills")
def on_night_kills(evt: Event, var: GameState):
    chance = config.Main.get("gameplay.safes.bodyguard_dies")
    if chance == 0:
        return
    evt.data["kill_priorities"]["@bodyguard"] = 10
    wolves = get_players(var, Wolf)
    for bodyguard in get_all_players(var, ("bodyguard",)):
        if GUARDED.get(bodyguard) in wolves and random.random() * 100 < chance:
            evt.data["victims"].add(bodyguard)
            evt.data["killers"][bodyguard].append("@bodyguard")

@event_listener("night_death_message")
def on_night_death_message(evt: Event, var: GameState, victim: User, killer: Union[User, str]):
    if killer == "@bodyguard":
        evt.data["key"] = "protected_wolf" if var.role_reveal == "on" else "protected_wolf_no_reveal"
        evt.data["args"] = [victim, "bodyguard"]
    elif victim in DYING:
        # suppress the usual death message when bodyguard power activates
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    # needs to be here in order to allow bodyguard protections to work during the daytime
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

@event_listener("player_protected")
def on_player_protected(evt: Event, var: GameState, target: User, attacker: Optional[User], attacker_role: str, protector: User, protector_role: str, reason: str):
    if protector_role == "bodyguard":
        evt.data["messages"].append(messages[reason + "_bodyguard"].format(attacker, target, protector))
        add_dying(var, protector, killer_role=attacker_role, reason="bodyguard", killer=attacker)
        if var.current_phase == "night" and var.in_phase_transition: # currently transitioning
            DYING.add(protector)

@event_listener("remove_protection")
def on_remove_protection(evt: Event, var: GameState, target: User, attacker: Optional[User], attacker_role: str, protector: User, protector_role: str, reason: str):
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
