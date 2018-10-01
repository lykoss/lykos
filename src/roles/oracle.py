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
from src.cats import Cursed, Safe, Innocent, Wolf

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
    if not evt.dispatch(var, wrapper.source, target):
        return

    target = evt.data["target"]
    targrole = get_main_role(target)
    trole = targrole # keep a copy for logging

    for i in range(2): # need to go through loop twice
        iswolf = False
        if targrole in Cursed:
            targrole = "wolf"
            iswolf = True
        elif targrole in Safe | Innocent:
            targrole = var.HIDDEN_ROLE
        elif targrole in Wolf:
            targrole = "wolf"
            iswolf = True
        else:
            targrole = var.HIDDEN_ROLE

        if i:
            break

        evt = Event("see", {"role": targrole})
        evt.dispatch(var, wrapper.source, target)
        targrole = evt.data["role"]

    wrapper.send(messages["oracle_success"].format(target, "" if iswolf else "\u0002not\u0002 ", "\u0002" if iswolf else ""))
    debuglog("{0} (oracle) SEE: {1} ({2}) (Wolf: {3})".format(wrapper.source, target, trole, str(iswolf)))

    SEEN.add(wrapper.source)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["oracle"] = {"Village", "Nocturnal", "Spy", "Safe"}
    elif kind == "lycanthropy_role":
        evt.data["oracle"] = {"role": "doomsayer", "prefix": "seer"}

# vim: set sw=4 expandtab:
