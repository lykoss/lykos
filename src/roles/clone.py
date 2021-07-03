from __future__ import annotations

import re
import random
import itertools
import typing
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target, change_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Win_Stealer
from src.events import EventListener

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

CLONED = UserDict() # type: UserDict[users.User, users.User]
CAN_ACT = UserSet()
ACTED = UserSet()
CLONE_ENABLED = False # becomes True if at least one person died and there are clones

@command("clone", chan=False, pm=True, playing=True, phases=("night",), roles=("clone",))
def clone(wrapper: MessageDispatcher, message: str):
    """Clone another player. You will turn into their role if they die."""
    if wrapper.source in CLONED:
        wrapper.pm(messages["already_cloned"])
        return

    var = wrapper.game_state

    params = re.split(" +", message)
    target = get_target(var, wrapper, params[0])
    if target is None:
        return

    CLONED[wrapper.source] = target
    ACTED.add(wrapper.source)
    wrapper.pm(messages["clone_target_success"].format(target))

    debuglog("{0} (clone) CLONE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, user):
    if var.HIDDEN_CLONE and user in var.ORIGINAL_ROLES["clone"]:
        evt.data["role"] = "clone"

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    # clone happens regardless of death_triggers being true or not
    if var.PHASE not in var.GAME_PHASES:
        return

    clones = get_all_players(("clone",))
    mainrole = evt.params.main_role
    for clone in clones:
        if clone in CLONED:
            target = CLONED[clone]
            if player is target:
                # clone is cloning target, so clone becomes target's role
                # clone does NOT get any of target's templates (gunner/assassin/etc.)
                del CLONED[clone]
                mainrole = change_role(var, clone, "clone", mainrole, inherit_from=target)
                # if a clone is cloning a clone, clone who the old clone cloned
                if mainrole == "clone" and player in CLONED:
                    if CLONED[player] is clone:
                        clone.send(messages["forever_aclone"].format(player))
                    else:
                        CLONED[clone] = CLONED[player]
                        clone.send(messages["clone_success"].format(CLONED[clone]))
                        debuglog("{0} (clone) CLONE: {1} ({2})".format(clone, CLONED[clone], get_main_role(CLONED[clone])))

                debuglog("{0} (clone) CLONE DEAD PLAYER: {1} ({2})".format(clone, target, mainrole))

    del CLONED[:player:]
    CAN_ACT.discard(player)
    ACTED.discard(player)

@event_listener("send_role")
def on_send_role(evt, var):
    ps = get_players(var)
    CAN_ACT.update(get_all_players(("clone",)) - CLONED.keys())
    for clone in get_all_players(("clone",)):
        if clone in CLONED and not var.ALWAYS_PM_ROLE:
            continue
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(clone)
        clone.send(messages["clone_notify"])
        if var.NIGHT_COUNT > 0:
            clone.send(messages["players_list"].format(pl))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(ACTED)
    evt.data["nightroles"].extend(CAN_ACT)

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
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
def on_swap_role_state(evt, var, actor, target, role):
    if role == "clone":
        CLONED[target], CLONED[actor] = CLONED.pop(actor), CLONED.pop(target)
        evt.data["target_messages"].append(messages["clone_target"].format(CLONED[target]))
        evt.data["actor_messages"].append(messages["clone_target"].format(CLONED[actor]))

@event_listener("player_win")
def on_player_win(evt, var, player, main_role, all_roles, winner, team_win, survived):
    # this means they ended game while being clone and not some other role
    if main_role == "clone" and survived and singular(winner) not in Win_Stealer:
        evt.data["individual_win"] = True

@event_listener("del_player", priority=1)
def first_death_occured(evt, var, player, all_roles, death_triggers):
    global CLONE_ENABLED
    if CLONE_ENABLED:
        return
    if CLONED and var.PHASE in var.GAME_PHASES:
        CLONE_ENABLED = True

@event_listener("update_stats")
def on_update_stats(evt, var, player, mainrole, revealrole, allroles):
    if CLONE_ENABLED and not var.HIDDEN_CLONE:
        evt.data["possible"].add("clone")

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind clone who they have cloned
    if evt.data["role"] == "clone" and user in CLONED:
        evt.data["messages"].append(messages["clone_target"].format(CLONED[user]))

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "clone" and user in CLONED:
        evt.data["special_case"].append(messages["clone_revealroles"].format(CLONED[user]))

@event_listener("begin_day")
def on_begin_day(evt, var):
    CAN_ACT.clear()
    ACTED.clear()

@event_listener("reset")
def on_reset(evt, var):
    global CLONE_ENABLED
    CLONE_ENABLED = False
    CLONED.clear()
    CAN_ACT.clear()
    ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["clone"] = {"Neutral", "Team Switcher"}
