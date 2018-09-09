import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

@event_listener("transition_day_resolve", priority=2)
def on_transition_day_resolve(evt, var, victim):
    if evt.data["protected"].get(victim) == "blessing":
        # don't play any special message for a blessed target, this means in a game with priest and monster it's not really possible
        # for wolves to tell which is which. May want to change that in the future to be more obvious to wolves since there's not really
        # any good reason to hide that info from them. In any case, we don't want to say the blessed person was attacked to the channel
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_night_end", priority=5)
def on_transition_night_end(evt, var):
    for blessed in get_all_players(("blessed villager",)):
        status.add_protection(var, blessed, blessed, "blessed villager")
        if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
            to_send = "blessed_notify"
            if blessed.prefers_simple():
                to_send = "blessed_simple"
            blessed.send(messages[to_send])

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in var.ROLES["blessed villager"]:
        evt.data["messages"].append(messages["blessed_simple"])

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["blessed villager"] = {"Village"}

# vim: set sw=4 expandtab:
