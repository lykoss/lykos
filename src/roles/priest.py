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

PRIESTS = UserSet() # type: Set[users.User]
CONSECRATING = UserSet() # type: Set[users.User]

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

    CONSECRATING.add(wrapper.source)
    wrapper.pm(messages["consecrate_success"].format(target))
    debuglog("{0} (priest) CONSECRATE: {1}".format(wrapper.source, target))
    # consecrating can possibly cause game to end, so check for that
    from src.wolfgame import chk_win
    chk_win()

@event_listener("transition_night_end")
def on_transition_night_end(evt, var):
    for priest in get_all_players(("priest",)):
        if priest.prefers_simple():
            priest.send(messages["priest_simple"])
        else:
            priest.send(messages["priest_notify"])

@event_listener("del_player")
def on_del_player(evt, var, player, mainrole, allroles, death_triggers):
    CONSECRATING.discard(player)

@event_listener("get_voters")
def on_get_voters(evt, var):
    evt.data["voters"].difference_update(CONSECRATING)

@event_listener("lynch")
def on_lynch(evt, var, user):
    if user in CONSECRATING:
        user.send(messages["consecrating_no_vote"])
        evt.prevent_default = True

@event_listener("abstain")
def on_abstain(evt, var, user):
    if user in CONSECRATING:
        user.send(messages["consecrating_no_vote"])
        evt.prevent_default = True

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_players(("priest",)))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    CONSECRATING.clear()

@event_listener("reset")
def on_reset(evt, var):
    PRIESTS.clear()
    CONSECRATING.clear()
