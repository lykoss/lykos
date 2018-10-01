import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

@event_listener("see")
def on_see(evt, var, seer, target):
    if target in var.ROLES["cursed villager"]:
        evt.data["role"] = "wolf"

@event_listener("wolflist")
def on_wolflist(evt, var, player, wolf):
    if player in var.ROLES["cursed villager"]:
        evt.data["tags"].add("cursed")

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["cursed villager"] = {"Village", "Cursed"}

# vim: set sw=4 expandtab:
