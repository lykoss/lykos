import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

@event_listener("transition_day", priority=4.3)
def on_transition_day(evt, var):
    pl = get_players()
    vs = set(evt.data["victims"])
    for v in pl:
        if v in vs:
            if v in var.DYING:
                continue
            if v in get_all_players(("blessed villager",)):
                evt.data["numkills"][v] -= 1
                if evt.data["numkills"][v] >= 0:
                    evt.data["killers"][v].pop(0)
                if evt.data["numkills"][v] <= 0 and v not in evt.data["protected"]:
                    evt.data["protected"][v] = "blessing"
                elif evt.data["numkills"][v] <= 0:
                    var.ACTIVE_PROTECTIONS[v.nick].append("blessing")
        elif v in get_all_players(("blessed villager",)):
            var.ACTIVE_PROTECTIONS[v.nick].append("blessing")

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
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        for blessed in get_all_players(("blessed villager",)):
            to_send = "blessed_notify"
            if blessed.prefers_simple():
                to_send = "blessed_simple"
            blessed.send(messages[to_send])

@event_listener("desperation_totem")
def on_desperation(evt, var, votee, target, prot):
    if prot == "blessing":
        var.ACTIVE_PROTECTIONS[target.nick].remove("blessing")
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("retribution_totem")
def on_retribution(evt, var, victim, target, prot):
    if prot == "blessing":
        var.ACTIVE_PROTECTIONS[target.nick].remove("blessing")
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("assassinate")
def on_assassinate(evt, var, killer, target, prot):
    if prot == "blessing":
        var.ACTIVE_PROTECTIONS[target.nick].remove("blessing")
        evt.prevent_default = True
        evt.stop_processing = True
        # don't message the channel whenever a blessing blocks a kill, but *do* let the killer know so they don't try to report it as a bug
        killer.send(messages["assassin_fail_blessed"].format(target))

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in var.ROLES["blessed villager"]:
        evt.data["messages"].append(messages["blessed_simple"])

# vim: set sw=4 expandtab:
