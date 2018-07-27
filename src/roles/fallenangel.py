import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players
from src.messages import messages
from src.events import Event

@event_listener("transition_day", priority=4.8)
def on_transition_day(evt, var):
    # now that all protections are finished, add people back to onlybywolves
    # if they're down to 1 active kill and wolves were a valid killer
    victims = set(get_players()) & set(evt.data["victims"]) - var.DYING
    for v in victims:
        if evt.data["numkills"][v] == 1 and v in evt.data["bywolves"]:
            evt.data["onlybywolves"].add(v)

    if len(var.ROLES["fallen angel"]) > 0:
        for p, t in list(evt.data["protected"].items()):
            if p in evt.data["bywolves"]:
                if p in evt.data["protected"]:
                    p.send(messages["fallen_angel_deprotect"])

                # let other roles do special things when we bypass their guards
                killer = random.choice(list(get_all_players(("fallen angel",))))
                fevt = Event("fallen_angel_guard_break", evt.data)
                fevt.dispatch(var, p, killer)

                if p in evt.data["protected"]:
                    del evt.data["protected"][p]
                if p in var.ACTIVE_PROTECTIONS:
                    del var.ACTIVE_PROTECTIONS[p.nick]
                # mark kill as performed by a random FA
                # this is important as there may otherwise be no killers if every kill was blocked
                evt.data["killers"][p].append(killer)

@event_listener("assassinate", priority=1)
def on_assassinate(evt, var, killer, target, prot):
    # bypass all protection if FA is doing the killing
    # we do this by stopping propagation, meaning future events won't fire
    if "fallen angel" in evt.params.killer_allroles:
        evt.params.prots.clear()
        evt.stop_processing = True
        evt.prevent_default = True

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["fallen angel"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal"}

# vim: set sw=4 expandtab:
