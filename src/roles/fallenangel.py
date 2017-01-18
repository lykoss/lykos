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

@event_listener("transition_day", priority=4.8)
def on_transition_day(evt, cli, var):
    # now that all protections are finished, add people back to onlybywolves
    # if they're down to 1 active kill and wolves were a valid killer
    victims = set(list_players()) & set(evt.data["victims"]) - var.DYING
    for v in victims:
        if evt.data["numkills"][v] == 1 and v in evt.data["bywolves"]:
            evt.data["onlybywolves"].add(v)

    if len(var.ROLES["fallen angel"]) > 0:
        for p, t in list(evt.data["protected"].items()):
            if p in evt.data["bywolves"]:
                if p in evt.data["protected"]:
                    pm(cli, p, messages["fallen_angel_deprotect"])

                # let other roles do special things when we bypass their guards
                killer = random.choice(list(var.ROLES["fallen angel"]))
                fevt = Event("fallen_angel_guard_break", evt.data)
                fevt.dispatch(cli, var, p, killer)

                if p in evt.data["protected"]:
                    del evt.data["protected"][p]
                if p in var.ACTIVE_PROTECTIONS:
                    del var.ACTIVE_PROTECTIONS[p]
                # mark kill as performed by a random FA
                # this is important as there may otherwise be no killers if every kill was blocked
                evt.data["killers"][p].append(killer)

@event_listener("assassinate", priority=1)
def on_assassinate(evt, cli, var, nick, target, prot):
    # bypass all protection if FA is doing the killing
    # we do this by stopping propagation, meaning future events won't fire
    if evt.params.nickrole == "fallen angel":
        evt.params.prots.clear()
        evt.stop_processing = True
        evt.prevent_default = True

# vim: set sw=4 expandtab:
