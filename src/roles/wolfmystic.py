import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange

from src.roles.helper.mystics import register_mystic
from src.roles.helper.wolves import register_wolf

register_mystic("wolf mystic", send_role=False, types=("Safe", "Win Stealer"))
register_wolf("wolf mystic")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["wolf mystic"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Intuitive", "Village Objective", "Wolf Objective"}
