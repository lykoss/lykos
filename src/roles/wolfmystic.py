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

LAST_COUNT = setup_variables("wolf mystic", send_role=False, types=("villagers", "win_stealers"))

# No need for get_special, as wolf.py does it for us (for now)

# vim: set sw=4 expandtab:
