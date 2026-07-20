from __future__ import annotations

import math
import re
from typing import Optional

from src import users, channels
from src.cats import Category
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target, get_reveal_role
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange, try_protection, add_dying, is_dead
from src.users import User
from src.random import random

KILLS: UserDict[users.User, users.User] = UserDict()
TARGETS: UserDict[users.User, UserSet] = UserDict()

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("dullahan",))
async def dullahan_kill(wrapper: MessageDispatcher, message: str):
    """Kill someone at night as a dullahan until everyone on your list is dead."""
    var = wrapper.game_state
    if not TARGETS[wrapper.source] & set(get_players(var)):
        await wrapper.pm(messages["dullahan_targets_dead"])
        return

    target = await get_target(wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    if target not in TARGETS[wrapper.source]:
        await wrapper.pm(messages["dullahan_not_target"].format(target))
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if await try_exchange(var, wrapper.source, target):
        return

    KILLS[wrapper.source] = target
    await wrapper.pm(messages["player_kill"].format(orig))

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=("dullahan",))
async def dullahan_retract(wrapper: MessageDispatcher, message: str):
    """Removes a dullahan's kill selection."""
    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        await wrapper.pm(messages["retracted_kill"])

@event_listener("player_win")
async def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: Category, team_win: bool, survived: bool):
    if main_role != "dullahan":
        return
    alive = set(get_players(var))
    if not TARGETS[player] & alive:
        evt.data["individual_win"] = True

@event_listener("del_player")
async def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
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
                protected = await try_protection(var, target, player, "dullahan", "dullahan_die")
                if protected is not None:
                    await channels.Main.send(*protected)
                    return

                if var.role_reveal in ("on", "team"):
                    role = await get_reveal_role(var, target)
                    await channels.Main.send(messages["dullahan_die_success"].format(player, target, role))
                else:
                    await channels.Main.send(messages["dullahan_die_success_noreveal"].format(player, target))
                add_dying(var, target, "dullahan", "dullahan_die", killer=player)

@event_listener("night_kills")
async def on_night_kills(evt: Event, var: GameState):
    while KILLS:
        k, d = KILLS.popitem()
        evt.data["victims"].add(d)
        evt.data["killers"][d].append(k)

@event_listener("new_role")
async def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if player in TARGETS and old_role == "dullahan" and evt.data["role"] != "dullahan":
        del KILLS[:player:] # type: ignore
        del TARGETS[player]

    if player not in TARGETS and evt.data["role"] == "dullahan":
        pl = get_players(var)
        max_targets = math.ceil(8.1 * math.log(len(pl), 10) - 5)
        TARGETS[player] = UserSet()

        dull_targets = Event("dullahan_targets", {"targets": set(), "exclude": set(), "num_targets": max_targets})
        await dull_targets.dispatch(var, player, max_targets)
        TARGETS[player].update(dull_targets.data["targets"] - dull_targets.data["exclude"])
        max_targets = dull_targets.data["num_targets"]

        pl = list(set(pl) - dull_targets.data["exclude"] - {player})
        while pl and len(TARGETS[player]) < max_targets:
            target = random.choice(pl)
            pl.remove(target)
            TARGETS[player].add(target)

@event_listener("swap_role_state")
async def on_swap_role_state(evt: Event, var: GameState, actor: User, target: User, role: str):
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
async def on_chk_nightdone(evt: Event, var: GameState):
    spl = set(get_players(var))
    evt.data["acted"].extend(KILLS)
    for dullahan, targets in TARGETS.items():
        if targets & spl and dullahan in spl:
            evt.data["nightroles"].append(dullahan)

@event_listener("send_role")
async def on_transition_night_end(evt: Event, var: GameState):
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
        if var.next_phase == "night":
            dullahan.send(t.format(targets))

@event_listener("visit")
async def on_visit(evt: Event, var: GameState, visitor_role: str, visitor: User, visited: User):
    if visitor_role == "succubus":
        succubi = get_all_players(var, ("succubus",))
        if visited in TARGETS and TARGETS[visited].intersection(succubi):
            TARGETS[visited].difference_update(succubi)
            visited.send(messages["dullahan_no_kill_succubus"])

@event_listener("myrole")
async def on_myrole(evt: Event, var: GameState, user):
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
async def on_revealroles_role(evt: Event, var: GameState, user: User, role: str):
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
async def on_begin_day(evt: Event, var: GameState):
    KILLS.clear()

@event_listener("reset")
async def on_reset(evt: Event, var: GameState):
    KILLS.clear()
    TARGETS.clear()

@event_listener("get_role_metadata")
async def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
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
