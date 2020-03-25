import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_all_players
from src.messages import messages
from src.status import add_lynch_immunity

REVEALED_MAYORS = UserSet()

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    for user in get_all_players(("mayor",)):
        if user not in REVEALED_MAYORS:
            add_lynch_immunity(var, user, "mayor")

@event_listener("lynch_immunity")
def on_lynch_immunity(evt, var, user, reason):
    if reason == "mayor":
        channels.Main.send(messages["mayor_reveal"].format(user))
        evt.data["immune"] = True
        REVEALED_MAYORS.add(user)

@event_listener("reset")
def on_reset(evt, var):
    REVEALED_MAYORS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["mayor"] = {"Village", "Safe"}
