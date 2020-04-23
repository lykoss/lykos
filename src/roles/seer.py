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
from src.status import try_misdirection, try_exchange
from src.cats import Cursed, Safe, Innocent, Neutral, Win_Stealer, Team_Switcher, Wolf

from src.roles.helper.seers import setup_variables

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

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    targrole = get_main_role(target)
    trole = targrole # keep a copy for logging

    if targrole in Cursed:
        targrole = "wolf"
    elif targrole in Safe:
        pass # Keep the same role
    elif targrole in Innocent:
        targrole = var.HIDDEN_ROLE
    elif targrole in (Neutral - Win_Stealer - Team_Switcher):
        pass # Keep the same role
    elif targrole in Wolf:
        targrole = "wolf"
    else:
        targrole = var.HIDDEN_ROLE

    evt = Event("see", {"role": targrole})
    evt.dispatch(var, wrapper.source, target)
    targrole = evt.data["role"]

    wrapper.send(messages["seer_success"].format(target, targrole))
    debuglog("{0} (seer) SEE: {1} ({2}) as {3}".format(wrapper.source, target, trole, targrole))

    SEEN.add(wrapper.source)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["seer"] = {"Village", "Nocturnal", "Spy", "Safe"}
    elif kind == "lycanthropy_role":
        evt.data["seer"] = {"role": "doomsayer", "prefix": "seer"}
