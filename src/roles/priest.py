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
from src.events import Event
from src.status import add_absent

PRIESTS = UserSet() # type: Set[users.User]

@command("bless", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("priest",))
def bless(var, wrapper, message):
    """Bless a player, preventing them from being killed for the remainder of the game."""
    if wrapper.source in PRIESTS:
        wrapper.pm(messages["already_blessed"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_bless_self")
    if not target:
        return

    evt = Event("targeted_command", {"target": target, "exchange": True, "misdirection": True})
    if not evt.dispatch(var, wrapper.source, target):
        return

    PRIESTS.add(wrapper.source)
    var.ROLES["blessed villager"].add(target)
    wrapper.pm(messages["blessed_success"].format(target))
    target.send(messages["blessed_notify_target"])
    debuglog("{0} (priest) BLESS: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("consecrate", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("priest",))
def consecrate(var, wrapper, message):
    """Consecrates a corpse, putting its spirit to rest and preventing other unpleasant things from happening."""
    alive = get_players()
    targ = re.split(" +", message)[0]
    if not targ:
        wrapper.pm(messages["not_enough_parameters"])
        return

    dead = set(var.ALL_PLAYERS) - set(alive)
    target, _ = users.complete_match(targ, dead)
    if target is None:
        wrapper.pm(messages["consecrate_fail"].format(targ))
        return

    # we have a target, so mark them as consecrated, right now all this does is silence a VG for a night
    # but other roles that do stuff after death or impact dead players should have functionality here as well
    # (for example, if there was a role that could raise corpses as undead somethings, this would prevent that from working)
    # regardless if this has any actual effect or not, it still removes the priest from being able to vote

    evt = Event("consecrate", {})
    evt.dispatch(var, wrapper.source, target)

    add_absent(var, wrapper.source, "consecrating_no_vote")
    wrapper.pm(messages["consecrate_success"].format(target))
    debuglog("{0} (priest) CONSECRATE: {1}".format(wrapper.source, target))

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for priest in get_all_players(("priest",)):
        if priest.prefers_simple():
            priest.send(messages["priest_simple"])
        else:
            priest.send(messages["priest_notify"])

@event_listener("reset")
def on_reset(evt, var):
    PRIESTS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["priest"] = {"Village", "Safe", "Innocent"}
