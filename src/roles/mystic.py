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

register_mystic("mystic", send_role=True, types=("Wolfteam",))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["mystic"] = {"Village", "Safe", "Intuitive"}

# vim: set sw=4 expandtab:
