import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Hidden

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
        liberals = get_players({"liberal"})
        if liberals:
            for liberal in liberals:
                liberal.queue_message(messages["liberal_notify"])
            liberal.send_messages()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["liberal"] = {"Village"}
