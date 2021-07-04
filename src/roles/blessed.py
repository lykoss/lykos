import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, status, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange

@event_listener("send_role")
def on_send_role(evt, var):
    for blessed in get_all_players(var, ("blessed villager",)):
        status.add_protection(var, blessed, blessed, "blessed villager")
        if not var.ROLES_SENT or var.ALWAYS_PM_ROLE:
            blessed.send(messages["blessed_notify"])

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in var.ROLES["blessed villager"]:
        evt.data["messages"].append(messages["blessed_myrole"])

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["blessed villager"] = {"Village", "Innocent"}
