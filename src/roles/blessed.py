import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

# TODO: some additional stuff with blessed villager has not been split yet,
# notably the interactions with assassin and mad scientist, need to split those out too
# as part of splitting assassin/MS (new events will be required)

@event_listener("transition_day", priority=4.3)
def on_transition_day(evt, cli, var):
    pl = list_players()
    vs = set(evt.data["victims"])
    for v in pl:
        if v in vs:
            if v in var.DYING:
                continue
            if v in var.ROLES["blessed villager"]:
                evt.data["numkills"][v] -= 1
                if evt.data["numkills"][v] >= 0:
                    evt.data["killers"][v].pop(0)
                if evt.data["numkills"][v] <= 0 and v not in evt.data["protected"]:
                    evt.data["protected"][v] = "blessing"
                elif evt.data["numkills"][v] <= 0:
                    var.ACTIVE_PROTECTIONS[v].append("blessing")
        elif v in var.ROLES["blessed villager"]:
            var.ACTIVE_PROTECTIONS[v].append("blessing")

@event_listener("transition_day_resolve", priority=2)
def on_transition_day_resolve(evt, cli, var, victim):
    if evt.data["protected"].get(victim) == "blessing":
        # don't play any special message for a blessed target, this means in a game with priest and monster it's not really possible
        # for wolves to tell which is which. May want to change that in the future to be more obvious to wolves since there's not really
        # any good reason to hide that info from them. In any case, we don't want to say the blessed person was attacked to the channel
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("transition_night_end", priority=5)
def on_transition_night_end(evt, cli, var):
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        for blessed in var.ROLES["blessed villager"]:
            if blessed in var.PLAYERS and not is_user_simple(blessed):
                pm(cli, blessed, messages["blessed_notify"])
            else:
                pm(cli, blessed, messages["blessed_simple"])

@event_listener("desperation_totem")
def on_desperation(evt, cli, var, votee, target, prot):
    if prot == "blessing":
        var.ACTIVE_PROTECTIONS[target].remove("blessing")
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("retribution_totem")
def on_retribution(evt, cli, var, victim, loser, prot):
    if prot == "blessing":
        var.ACTIVE_PROTECTIONS[target].remove("blessing")
        evt.prevent_default = True
        evt.stop_processing = True

@event_listener("assassinate")
def on_assassinate(evt, cli, var, nick, target, prot):
    if prot == "blessing":
        var.ACTIVE_PROTECTIONS[target].remove("blessing")
        evt.prevent_default = True
        evt.stop_processing = True
        # don't message the channel whenever a blessing blocks a kill, but *do* let the killer know so they don't try to report it as a bug
        pm(cli, nick, messages["assassin_fail_blessed"].format(target))

@event_listener("myrole")
def on_myrole(evt, cli, var, nick):
    if nick in var.ROLES["blessed villager"]:
        evt.data["messages"].append(messages["blessed_simple"])

# vim: set sw=4 expandtab:
