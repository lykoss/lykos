import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

def wolf_list(var):
    wolves = [wolf.nick for wolf in get_all_players(var.WOLF_ROLES)]
    random.shuffle(wolves)
    return messages["wolves_list"].format(", ".join(wolves))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        for minion in get_all_players(("minion",)):
            if minion.prefers_simple():
                to_send = "minion_simple"
            else:
                to_send = "minion_notify"
            minion.send(messages[to_send])
            minion.send(wolf_list(var))

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "minion":
        evt.data["target_messages"].append(wolf_list(var))
    elif target_role == "minion":
        evt.data["actor_messages"].append(wolf_list(var))

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in get_all_players(("minion",)):
        wolves = []
        for wolfrole in var.WOLF_ROLES:
            for player in var.ORIGINAL_ROLES[wolfrole]:
                wolves.append(player.nick)
        evt.data["messages"].append(messages["original_wolves"].format(", ".join(wolves)))

# vim: set sw=4 expandtab:
