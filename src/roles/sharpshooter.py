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
from src.events import Event

from src.roles._gunner_helper import setup_variables

GUNNERS = setup_variables("sharpshooter")

@event_listener("gun_chances")
def on_gun_chances(evt, var, user, target, role):
    if role == "sharpshooter":
        hit, miss, suicide, headshot = var.SHARPSHOOTER_GUN_CHANCES
        evt.data["hit"] = hit
        evt.data["miss"] = miss
        evt.data["suicide"] = suicide
        evt.data["headshot"] = headshot

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "sharpshooter":
        if evt.data["role"] != "sharpshooter":
            del GUNNERS[user]

    elif evt.data["role"] == "sharpshooter":
        GUNNERS[user] = math.ceil(var.SHARPSHOOTER_MULTIPLIER * len(get_players()))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categoriers":
        evt.data["sharpshooter"] = {"Village", "Safe", "Killer"}
