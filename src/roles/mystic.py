import re
import random
from typing import Optional

from src.utilities import *
from src import users, channels
from src.functions import get_players, get_all_players
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener

from src.roles.helper.mystics import register_mystic

register_mystic("mystic", send_role=True, types=("Wolfteam",))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["mystic"] = {"Village", "Safe", "Intuitive"}
