import re
import random
import itertools
import math
from collections import defaultdict, deque
from typing import Optional, Set

from src import channels, users
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.gamestate import GameState
from src.status import try_misdirection, try_exchange, try_protection, add_dying
from src.events import Event, event_listener
from src.users import User

def _get_targets(var: GameState, pl: Set[User], user: User):
    """Gets the mad scientist's targets.

    var - settings module
    pl - list of alive players
    nick - nick of the mad scientist

    """

    index = var.ALL_PLAYERS.index(user)
    num_players = len(var.ALL_PLAYERS)
    # determine left player
    i = index
    while True:
        i = (i - 1) % num_players
        if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] is user:
            target1 = var.ALL_PLAYERS[i]
            break
    # determine right player
    i = index
    while True:
        i = (i + 1) % num_players
        if var.ALL_PLAYERS[i] in pl or var.ALL_PLAYERS[i] is user:
            target2 = var.ALL_PLAYERS[i]
            break

    return (target1, target2)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: Set[str], death_triggers: bool):
    if not death_triggers or "mad scientist" not in all_roles:
        return

    target1, target2 = _get_targets(var, get_players(var), player)

    prots1 = try_protection(var, target1, player, "mad scientist", "mad_scientist_fail")
    prots2 = try_protection(var, target2, player, "mad scientist", "mad_scientist_fail")
    if prots1:
        channels.Main.send(*prots1)
    if prots2:
        channels.Main.send(*prots2)

    kill1 = prots1 is None and add_dying(var, target1, killer_role="mad scientist", reason="mad_scientist")
    kill2 = prots2 is None and target1 is not target2 and add_dying(var, target2, killer_role="mad scientist", reason="mad_scientist")

    role1 = kill1 and get_reveal_role(var, target1)
    role2 = kill2 and get_reveal_role(var, target2)
    if kill1 and kill2:
        to_send = "mad_scientist_kill"
    elif kill1:
        to_send = "mad_scientist_kill_single"
    elif kill2:
        to_send = "mad_scientist_kill_single"
        # swap the targets around to show the proper target
        target1, target2 = target2, target1
        role1, role2 = role2, role1
    else:
        to_send = "mad_scientist_fail"

    if to_send != "mad_scientist_fail" and var.role_reveal not in ("on", "team"):
        to_send += "_no_reveal"

    channels.Main.send(messages[to_send].format(player, target1, role1, target2, role2))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for ms in get_all_players(var, ("mad scientist",)):
        pl = get_players(var)
        target1, target2 = _get_targets(var, pl, ms)

        ms.send(messages["mad_scientist_notify"].format(target1, target2))

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user: User):
    if user in var.ROLES["mad scientist"]:
        pl = get_players(var)
        target1, target2 = _get_targets(var, pl, user)
        evt.data["messages"].append(messages["mad_scientist_myrole_targets"].format(target1, target2))

@event_listener("revealroles_role")
def on_revealroles(evt: Event, var: GameState,  user: User, role: str):
    if role == "mad scientist":
        pl = get_players(var)
        target1, target2 = _get_targets(var, pl, user)
        evt.data["special_case"].append(messages["mad_scientist_revealroles_targets"].format(target1, target2))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["mad scientist"] = {"Village", "Cursed"}
