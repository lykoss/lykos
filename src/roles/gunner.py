import re
import random
import itertools
import math
from collections import defaultdict
from typing import Optional

from src import channels, users
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener

from src.roles.helper.gunners import setup_variables

HIT_CHANCE       = 3/4
HEADSHOT_CHANCE  = 1/5
EXPLODE_CHANCE   = 1/20
SHOTS_MULTIPLIER = 0.12

GUNNERS = setup_variables("gunner", hit=HIT_CHANCE, headshot=HEADSHOT_CHANCE, explode=EXPLODE_CHANCE, multiplier=SHOTS_MULTIPLIER)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["gunner"] = {"Village", "Safe", "Killer"}
