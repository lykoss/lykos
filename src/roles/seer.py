import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.messages import messages
from src.events import Event

from src.roles._seer_helper import setup_variables

SEEN = setup_variables("seer")

@command("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("seer",))
def see(var, wrapper, message):
    """Use your paranormal powers to determine the role or alignment of a player."""
    if wrapper.source in SEEN:
        wrapper.send(messages["seer_fail"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_see_self")
    if target is None:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]
    targrole = get_main_role(target)
    trole = targrole # keep a copy for logging

    if targrole in var.SEEN_WOLF and targrole not in var.SEEN_DEFAULT:
        targrole = "wolf"
    elif targrole in var.SEEN_DEFAULT:
        targrole = var.DEFAULT_ROLE
        if var.DEFAULT_SEEN_AS_VILL:
            targrole = "villager"

    evt = Event("see", {"role": targrole})
    evt.dispatch(var, wrapper.source, target)
    targrole = evt.data["role"]

    wrapper.send(messages["seer_success"].format(target, targrole))
    debuglog("{0} (seer) SEE: {1} ({2}) as {3}".format(wrapper.source, target, trole, targrole))

    SEEN.add(wrapper.source)

# vim: set sw=4 expandtab:
