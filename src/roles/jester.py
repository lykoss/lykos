from __future__ import annotations

import re
import random
import itertools
import math
from collections import defaultdict
from typing import Optional, TYPE_CHECKING

from src import channels, users
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.users import User

JESTERS = UserSet()

@event_listener("lynch")
def on_lynch(evt: Event, var: GameState, votee, voters):
    if votee in get_all_players(var, ("jester",)):
        JESTERS.add(votee)

@event_listener("player_win")
def on_player_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: set[str], winner: str, team_win: bool, survived: bool):
    if player in JESTERS:
        evt.data["individual_win"] = True

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for jester in get_all_players(var, ("jester",)):
        jester.send(messages["jester_notify"])

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    JESTERS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["jester"] = {"Neutral", "Innocent"}
