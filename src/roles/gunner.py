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

from src.roles.helper.gunners import setup_variables

GUNNERS = setup_variables("gunner")

@event_listener("gun_chances")
def on_gun_chances(evt, var, user, role):
    if role == "gunner":
        hit, miss, headshot = var.GUN_CHANCES
        evt.data["hit"] = hit
        evt.data["miss"] = miss
        evt.data["headshot"] = headshot

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "gunner":
        if evt.data["role"] != "gunner":
            del GUNNERS[user]

    elif evt.data["role"] == "gunner":
        GUNNERS[user] = math.ceil(var.SHOTS_MULTIPLIER * len(get_players()))
        if user in get_all_players(("village drunk",)):
            GUNNERS[user] *= var.DRUNK_SHOTS_MULTIPLIER

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["gunner"] = {"Village", "Safe", "Killer"}
