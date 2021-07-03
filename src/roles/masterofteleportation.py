from __future__ import annotations

import random
import re
import typing

from src.utilities import singular
from src.decorators import command, event_listener
from src.functions import get_target, get_players, get_all_players
from src.messages import messages
from src.containers import UserSet
from src.cats import Win_Stealer

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

ACTED = UserSet()

@command("choose", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("master of teleportation",))
def choose(wrapper: MessageDispatcher, message: str):
    pieces = re.split(" +", message)
    if len(pieces) < 2:
        return
    var = wrapper.game_state
    target1 = get_target(var, wrapper, pieces[0], allow_self=True)
    target2 = get_target(var, wrapper, pieces[1], allow_self=True)
    if not target1 or not target2:
        return

    if target1 is target2:
        wrapper.send(messages["choose_different_people"])
        return

    ACTED.add(wrapper.source)
    index1 = var.ALL_PLAYERS.index(target1)
    index2 = var.ALL_PLAYERS.index(target2)
    var.ALL_PLAYERS[index2] = target1
    var.ALL_PLAYERS[index1] = target2
    wrapper.send(messages["master_of_teleportation_success"].format(target1, target2))

@event_listener("send_role")
def on_send_role(evt, var):
    for player in get_all_players(("master of teleportation",)):
        player.send(messages["master_of_teleportation_notify"])
        if var.NIGHT_COUNT > 0:
            player.send(messages["players_list"].format(get_players(var)))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(ACTED)
    evt.data["nightroles"].extend(get_all_players(var, ("master of teleportation",)))

@event_listener("player_win")
def on_player_win(evt, var, player, main_role, all_roles, winner, team_win, survived):
    if main_role == "master of teleportation" and survived and singular(winner) not in Win_Stealer:
        evt.data["individual_win"] = True

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    ACTED.clear()

@event_listener("reset")
def on_reset(evt, var):
    ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["master of teleportation"] = {"Neutral", "Nocturnal"}
