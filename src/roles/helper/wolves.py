import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src.functions import get_main_role, get_players, get_all_roles
from src.decorators import event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src import events
from src.cats import Wolf, Wolfchat, Killer

CAN_KILL = set() # type: Set[str]

def _set_wolf_killers(evt):
    CAN_KILL.update(Wolf & Killer)

events.add_listener("init", _set_wolf_killers)

_kill_cmds = ("kill", "retract")

def wolf_can_kill(var, wolf):
    # a wolf can kill if wolves in general can kill, and the wolf belongs to a role in CAN_KILL
    # this is a utility function meant to be used by other wolf role modules
    nevt = events.Event("wolf_numkills", {"numkills": 1})
    nevt.dispatch(var)
    num_kills = nevt.data["numkills"]
    if num_kills == 0:
        return False
    wolfroles = get_all_roles(wolf)
    return bool(CAN_KILL & wolfroles)

def get_wolfchat_roles(var):
    wolves = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wolves = Wolf
        else:
            wolves = Wolf | {"traitor"}
    return wolves

def is_known_wolf_ally(var, actor, target):
    actor_role = get_main_role(actor)
    target_role = get_main_role(target)
    wolves = get_wolfchat_roles(var)
    return actor_role in wolves and target_role in wolves

def send_wolfchat_message(var, user, message, roles, *, role=None, command=None):
    if role not in CAN_KILL and var.RESTRICT_WOLFCHAT & var.RW_NO_INTERACTION:
        return
    if command not in _kill_cmds and var.RESTRICT_WOLFCHAT & var.RW_ONLY_KILL_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            return
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            return
    if not is_known_wolf_ally(var, user, user):
        return

    wcroles = Wolfchat
    if var.RESTRICT_WOLFCHAT & var.RW_ONLY_SAME_CMD:
        if var.PHASE == "night" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_NIGHT:
            wcroles = roles
        if var.PHASE == "day" and var.RESTRICT_WOLFCHAT & var.RW_DISABLE_DAY:
            wcroles = roles
    elif var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
        if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
            wcroles = Wolf
        else:
            wcroles = Wolf | {"traitor"}

    wcwolves = get_players(wcroles)
    wcwolves.remove(user)

    player = None
    for player in wcwolves:
        player.queue_message(message)
    for player in var.SPECTATING_WOLFCHAT:
        player.queue_message("[wolfchat] " + message)
    if player is not None:
        player.send_messages()

# vim: set sw=4 expandtab:
