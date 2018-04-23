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

SEEN = setup_variables("oracle")

@command("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("oracle",))
def see(var, wrapper, message):
    """Use your paranormal powers to determine the role or alignment of a player."""
    if wrapper.source in SEEN:
        wrapper.send(messages["seer_fail"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_see_self")
    if target is None:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, "see", wrapper.source, target, frozenset({"info", "immediate"})):
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

    iswolf = False
    if targrole in var.SEEN_WOLF and targrole not in var.SEEN_DEFAULT:
        iswolf = True
    wrapper.send(messages["oracle_success"].format(target, "" if iswolf else "\u0002not\u0002 ", "\u0002" if iswolf else ""))
    debuglog("{0} (oracle) SEE: {1} ({2}) (Wolf: {3})".format(wrapper.source, target, trole, str(iswolf)))

    SEEN.add(wrapper.source)

# vim: set sw=4 expandtab:
