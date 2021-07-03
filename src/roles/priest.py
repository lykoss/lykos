from __future__ import annotations

import re
import random
import itertools
import typing
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.status import try_misdirection, try_exchange, add_absent

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

PRIESTS = UserSet()

@command("bless", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("priest",))
def bless(wrapper: MessageDispatcher, message: str):
    """Bless a player, preventing them from being killed for the remainder of the game."""
    if wrapper.source in PRIESTS:
        wrapper.pm(messages["already_blessed"])
        return

    var = wrapper.game_state

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_bless_self")
    if not target:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    PRIESTS.add(wrapper.source)
    var.ROLES["blessed villager"].add(target)
    wrapper.pm(messages["blessed_success"].format(target))
    target.send(messages["blessed_notify_target"])
    debuglog("{0} (priest) BLESS: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("consecrate", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("priest",))
def consecrate(wrapper: MessageDispatcher, message: str):
    """Consecrates a corpse, putting its spirit to rest and preventing other unpleasant things from happening."""
    var = wrapper.game_state
    alive = get_players(var)
    targ = re.split(" +", message)[0]
    if not targ:
        wrapper.pm(messages["not_enough_parameters"])
        return

    var = wrapper.game_state

    dead = set(var.ALL_PLAYERS) - set(alive)
    target = users.complete_match(targ, dead)
    if not target:
        wrapper.pm(messages["consecrate_fail"].format(targ))
        return
    target = target.get()

    # we have a target, so mark them as consecrated, right now all this does is silence a VG for a night
    # but other roles that do stuff after death or impact dead players should have functionality here as well
    # (for example, if there was a role that could raise corpses as undead somethings, this would prevent that from working)
    # regardless if this has any actual effect or not, it still removes the priest from being able to vote

    evt = Event("consecrate", {})
    evt.dispatch(var, wrapper.source, target)

    wrapper.pm(messages["consecrate_success"].format(target))
    debuglog("{0} (priest) CONSECRATE: {1}".format(wrapper.source, target))
    add_absent(var, wrapper.source, "consecrating")
    from src.votes import chk_decision
    from src.wolfgame import chk_win
    if not chk_win():
        # game didn't immediately end due to marking as absent, see if we should force through a lynch
        chk_decision(var)

@event_listener("send_role")
def on_send_role(evt, var):
    for priest in get_all_players(var, ("priest",)):
        priest.send(messages["priest_notify"])

@event_listener("reset")
def on_reset(evt, var):
    PRIESTS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["priest"] = {"Village", "Safe", "Innocent"}
