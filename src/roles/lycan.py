import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange, add_lycanthropy, add_lycanthropy_scope, remove_lycanthropy
from src.cats import Wolf

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    lycans = get_all_players(("lycan",))
    if lycans:
        add_lycanthropy_scope(var, {"lycan"})
    for lycan in lycans:
        add_lycanthropy(var, lycan)
        if lycan.prefers_simple():
            lycan.send(messages["role_simple"].format("lycan"))
        else:
            lycan.send(messages["lycan_notify"])

@event_listener("doctor_immunize")
def on_doctor_immunize(evt, var, doctor, target):
    if target in get_all_players(("lycan",)):
        evt.data["message"] = "lycan_cured"

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "lycan" and evt.data["role"] != "lycan":
        remove_lycanthropy(var, user) # FIXME: We might be a lycanthrope from more than just the lycan role

# TODO: We want to remove lycan from someone who was just turned into a wolf if it was a template
# There's no easy way to do this right now and it doesn't really matter, so it's fine for now

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["lycan"] = {"Village", "Team Switcher"}
