import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, status, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Wolf

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    lycans = get_all_players(("lycan",))
    if lycans:
        status.add_lycanthropy_scope(var, {"lycan"})
    for lycan in lycans:
        status.add_lycanthropy(var, lycan)
        if lycan.prefers_simple():
            lycan.send(messages["lycan_simple"])
        else:
            lycan.send(messages["lycan_notify"])

@event_listener("doctor_immunize")
def on_doctor_immunize(evt, var, doctor, target):
    if target in get_all_players(("lycan",)):
        evt.data["message"] = "lycan_cured"

#@event_listener("new_role") # FIXME: Disabled for now because we don't want to remove this if it's the main role
def on_new_role(evt, var, player, old_role):
    if evt.data["role"] in Wolf and old_role is not None:
        var.ROLES["lycan"].discard(player) # remove the lycan template if the person becomes a wolf

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["lycan"] = {"Village", "Team Switcher"}
