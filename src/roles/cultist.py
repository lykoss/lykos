import re
import random
import itertools
import math
from collections import defaultdict
from typing import Optional, Dict, Set

from src import channels, users
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener
from src.users import User
from src.cats import Hidden

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    if not var.ROLES_SENT or var.always_pm_role:
        cultroles = {"cultist"}
        if var.hidden_role == "cultist":
            cultroles |= Hidden
        cultists = get_players(var, cultroles)
        if cultists:
            for cultist in cultists:
                cultist.queue_message(messages["cultist_notify"])
            cultist.send_messages()

@event_listener("chk_win", priority=3)
def on_chk_win(evt: Event, var: GameState, rolemap: Dict[str, Set[User]], mainroles: Dict[User, str], lpl: int, lwolves: int, lrealwolves: int):
    if evt.data["winner"] is not None:
        return
    if lwolves == lpl / 2:
        evt.data["winner"] = "wolves"
        evt.data["message"] = messages["wolf_win_equal"]
    elif lwolves > lpl / 2:
        evt.data["winner"] = "wolves"
        evt.data["message"] = messages["wolf_win_greater"]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["cultist"] = {"Wolfteam"}
