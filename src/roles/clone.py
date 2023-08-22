from __future__ import annotations

import random
import re
from typing import Optional

from src import users, config
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target, change_role
from src.gamestate import GameState
from src.messages import messages
from src.trans import NIGHT_IDLE_EXEMPT
from src.users import User

CLONED: UserDict[users.User, users.User] = UserDict()
CAN_ACT = UserSet()
ACTED = UserSet()
CLONE_ENABLED = False # becomes True if at least one person died and there are clones

@command("clone", chan=False, pm=True, playing=True, phases=("night",), roles=("clone",))
def clone(wrapper: MessageDispatcher, message: str):
    """Clone another player. You will turn into their role if they die."""
    if wrapper.source in CLONED:
        wrapper.pm(messages["already_cloned"])
        return

    params = re.split(" +", message)
    target = get_target(wrapper, params[0])
    if target is None:
        return

    CLONED[wrapper.source] = target
    ACTED.add(wrapper.source)
    wrapper.pm(messages["clone_target_success"].format(target))

@event_listener("get_reveal_role")
def on_get_reveal_role(evt: Event, var: GameState, user):
    if config.Main.get("gameplay.hidden.clone") and user in var.original_roles["clone"]:
        evt.data["role"] = "clone"

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: set[str], death_triggers: bool):
    # clone happens regardless of death_triggers being true or not
    if not var.in_game:
        return

    clones = get_all_players(var, ("clone",))
    mainrole = evt.params.main_role
    for clone in clones:
        if clone in CLONED:
            target = CLONED[clone]
            if player is target:
                del CLONED[clone]
                if not death_triggers:
                    # if the target idled out, clone can pick a new target but doesn't gain the target's role
                    # mark the clone as immune to night idle warnings for tonight
                    # so they aren't penalized for someone else being idle
                    NIGHT_IDLE_EXEMPT.add(clone)
                    continue

                # clone is cloning target, so clone becomes target's main role
                # clone does NOT get any of target's secondary roles (gunner/assassin/etc.)
                mainrole, _ = change_role(var, clone, "clone", mainrole, inherit_from=target)
                # if a clone is cloning a clone, clone who the old clone cloned
                if mainrole == "clone" and player in CLONED:
                    if CLONED[player] is clone:
                        clone.send(messages["forever_aclone"].format(player))
                    else:
                        CLONED[clone] = CLONED[player]
                        clone.send(messages["clone_success"].format(CLONED[clone]))

    del CLONED[:player:]
    CAN_ACT.discard(player)
    ACTED.discard(player)

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    CAN_ACT.update(get_all_players(var, ("clone",)) - CLONED.keys())
    for clone in get_all_players(var, ("clone",)):
        if clone in CLONED and not var.always_pm_role:
            continue
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(clone)
        clone.send(messages["clone_notify"])
        if var.next_phase == "night":
            clone.send(messages["players_list"].format(pl))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(ACTED)
    evt.data["nightroles"].extend(CAN_ACT)

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    # Select a random target for clone if they didn't choose someone
    pl = get_players(var)
    for clone in get_all_players(var, ("clone",)):
        if clone not in CLONED:
            ps = pl[:]
            ps.remove(clone)
            if ps:
                target = random.choice(ps)
                CLONED[clone] = target
                clone.send(messages["random_clone"].format(target))

@event_listener("swap_role_state")
def on_swap_role_state(evt: Event, var: GameState, actor, target, role):
    if role == "clone":
        CLONED[target], CLONED[actor] = CLONED.pop(actor), CLONED.pop(target)
        evt.data["target_messages"].append(messages["clone_target"].format(CLONED[target]))
        evt.data["actor_messages"].append(messages["clone_target"].format(CLONED[actor]))

@event_listener("del_player", priority=1)
def first_death_occured(evt: Event, var: GameState, player, all_roles, death_triggers):
    global CLONE_ENABLED
    if CLONE_ENABLED:
        return
    if CLONED and var.in_game:
        CLONE_ENABLED = True

@event_listener("update_stats")
def on_update_stats(evt: Event, var: GameState, player, mainrole, revealrole, allroles):
    if CLONE_ENABLED and not config.Main.get("gameplay.hidden.clone"):
        evt.data["possible"].add("clone")

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    # Remind clone who they have cloned
    if evt.data["role"] == "clone" and user in CLONED:
        evt.data["messages"].append(messages["clone_target"].format(CLONED[user]))

@event_listener("revealroles_role")
def on_revealroles_role(evt: Event, var: GameState, user, role):
    if role == "clone" and user in CLONED:
        evt.data["special_case"].append(messages["clone_revealroles"].format(CLONED[user]))

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    CAN_ACT.clear()
    ACTED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global CLONE_ENABLED
    CLONE_ENABLED = False
    CLONED.clear()
    CAN_ACT.clear()
    ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["clone"] = {"Village", "Team Switcher"}
