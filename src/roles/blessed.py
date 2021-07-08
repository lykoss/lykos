import re
import random
import itertools
import math
from collections import defaultdict
from typing import Optional

from src import users, channels, status
from src.functions import get_players, get_all_players
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.gamestate import GameState
from src.events import Event, event_listener
from src.messages import messages
from src.status import try_misdirection, try_exchange

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    for blessed in get_all_players(var, ("blessed villager",)):
        status.add_protection(var, blessed, blessed, "blessed villager")
        if not var.setup_completed or var.always_pm_role:
            blessed.send(messages["blessed_notify"])

@event_listener("myrole")
def on_myrole(evt: Event, var: GameState, user):
    if user in var.ROLES["blessed villager"]:
        evt.data["messages"].append(messages["blessed_myrole"])

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["blessed villager"] = {"Village", "Innocent"}
