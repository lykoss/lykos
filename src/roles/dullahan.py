from __future__ import annotations

import math
import re
import random
import typing
from collections import defaultdict, deque

from src.functions import get_players, get_all_players, get_target, get_main_role, get_reveal_role
from src import users, channels
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event, event_listener
from src.status import try_misdirection, try_exchange, try_protection, add_dying, is_dead

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState
    from src.users import User
    from typing import Optional, Set

KILLS = UserDict() # type: UserDict[users.User, users.User]
TARGETS = UserDict() # type: UserDict[users.User, UserSet]

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("dullahan",))
def dullahan_kill(wrapper: MessageDispatcher, message: str):
    """Kill someone at night as a dullahan until everyone on your list is dead."""
    var = wrapper.game_state
    if not TARGETS[wrapper.source] & set(get_players(var)):
        wrapper.pm(messages["dullahan_targets_dead"])
        return

    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=("dullahan",))
def dullahan_retract(wrapper: MessageDispatcher, message: str):
    """Removes a dullahan's kill selection."""
    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: Set[str], winner: str, team_win: bool, survived: bool):
    if main_role != "dullahan":
        return
    alive = set(get_players(var))
    if not TARGETS[player] & alive:
        evt.data["individual_win"] = True

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: Set[str], death_triggers: bool):
    for h, v in list(KILLS.items()):
        if v is player:
            h.send(messages["hunter_discard"])
            del KILLS[h]
        elif h is player:
            del KILLS[h]
    if death_triggers and "dullahan" in all_roles:
        pl = get_players(var)
        with TARGETS[player].intersection(pl) as targets:
            if targets:
                target = random.choice(list(targets))
                protected = try_protection(var, target, player, "dullahan", "dullahan_die")
                if protected is not None:
                    channels.Main.send(*protected)
                    return

                if var.role_reveal in ("on", "team"):
                    role = get_reveal_role(var, target)
                    channels.Main.send(messages["dullahan_die_success"].format(player, target, role))
                else:
                    channels.Main.send(messages["dullahan_die_success_noreveal"].format(player, target))
                add_dying(var, target, "dullahan", "dullahan_die")

@event_listener("transition_day", priority=2)
def on_transition_day(evt: Event, var: GameState):
    while KILLS:
        k, d = KILLS.popitem()
        evt.data["victims"].append(d)
        evt.data["killers"][d].append(k)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if player in TARGETS and old_role == "dullahan" and evt.data["role"] != "dullahan":
        del KILLS[:player:] # type: ignore
        del TARGETS[player]

    if player not in TARGETS and evt.data["role"] == "dullahan":
        ps = get_players(var)
        max_targets = math.ceil(8.1 * math.log(len(ps), 10) - 5)
        TARGETS[player] = UserSet()

        dull_targets = Event("dullahan_targets", {"targets": TARGETS[player]}) # support sleepy
        dull_targets.dispatch(var, player, max_targets)

        ps.remove(player)
        while len(TARGETS[player]) < max_targets:
            target = random.choice(ps)
            ps.remove(target)
            TARGETS[player].add(target)

@event_listener("swap_role_state")
def on_swap_role_state(evt: Event, var: GameState, actor: User, target: User, role: str):
    if role == "dullahan":
        targ_targets = TARGETS.pop(target)
        if actor in targ_targets:
            targ_targets.remove(actor)
            targ_targets.add(target)
        act_targets = TARGETS.pop(actor)
        if target in act_targets:
            act_targets.remove(target)
            act_targets.add(actor)

        TARGETS[actor] = targ_targets
        TARGETS[target] = act_targets

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    spl = set(get_players(var))
    evt.data["acted"].extend(KILLS)
    for dullahan, targets in TARGETS.items():
        if targets & spl and dullahan in spl:
            evt.data["nightroles"].append(dullahan)

@event_listener("send_role")
def on_transition_night_end(evt: Event, var: GameState):
    for dullahan in get_all_players(var, ("dullahan",)):
        targets = list(TARGETS[dullahan])
        for target in targets[:]:
            if is_dead(var, target):
                targets.remove(target)
        if not targets: # already all dead
            continue
        random.shuffle(targets)
        t = messages["dullahan_targets"] if targets == list(TARGETS[dullahan]) else messages["dullahan_remaining_targets"]
        dullahan.send(messages["dullahan_notify"])
        if var.next_phase != "night":
            dullahan.send(t.format(targets))

@event_listener("visit")
def on_visit(evt: Event, var: GameState, visitor_role: str, visitor: User, visited: User):
    if visitor_role == "succubus":
        succubi = get_all_players(var, ("succubus",))
        if visited in TARGETS and TARGETS[visited].intersection(succubi):
            TARGETS[visited].difference_update(succubi)
            visited.send(messages["dullahan_no_kill_succubus"])

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    # Remind dullahans of their targets
    if user in var.roles["dullahan"]:
        targets = list(TARGETS[user])
        for target in list(targets):
            if is_dead(var, target):
                targets.remove(target)
        random.shuffle(targets)
        if targets:
            t = messages["dullahan_targets"] if set(targets) == TARGETS[user] else messages["dullahan_remaining_targets"]
            evt.data["messages"].append(t.format(targets))
        else:
            evt.data["messages"].append(messages["dullahan_targets_dead"])

@event_listener("revealroles_role")
def on_revealroles_role(evt: Event, var: GameState, user: User, role: str):
    if role == "dullahan" and user in TARGETS:
        targets = set(TARGETS[user])
        for target in TARGETS[user]:
            if is_dead(var, target):
                targets.remove(target)
        if targets:
            evt.data["special_case"].append(messages["dullahan_to_kill"].format(targets))
        else:
            evt.data["special_case"].append(messages["dullahan_all_dead"])

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    KILLS.clear()
    TARGETS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "night_kills":
        num = 0
        for dull in var.roles["dullahan"]:
            for target in TARGETS[dull]:
                if not is_dead(var, target):
                    num += 1
                    break
        evt.data["dullahan"] = num
    elif kind == "role_categories":
        evt.data["dullahan"] = {"Killer", "Nocturnal", "Neutral"}
