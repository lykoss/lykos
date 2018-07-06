import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

from src.roles._mystic_helper import setup_variables

LAST_COUNT = setup_variables("wolf mystic", send_role=False, types=("safe", "win stealer"))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["wolf mystic"] = {"wolf", "wolfchat", "wolfteam"}

# vim: set sw=4 expandtab:
