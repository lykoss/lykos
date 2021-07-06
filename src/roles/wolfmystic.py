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
from src.roles.helper.wolves import register_wolf

register_mystic("wolf mystic", send_role=False, types=("Safe", "Win Stealer"))
register_wolf("wolf mystic")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["wolf mystic"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Intuitive", "Village Objective", "Wolf Objective"}
