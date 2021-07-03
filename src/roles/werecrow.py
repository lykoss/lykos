from __future__ import annotations

import re
import random
import typing

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_all_roles, get_target, get_main_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Nocturnal
from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, register_wolf

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

register_wolf("werecrow")

OBSERVED = UserDict() # type: UserDict[users.User, users.User]

@command("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("werecrow",))
def observe(wrapper: MessageDispatcher, message: str):
    """Observe a player to see whether they are able to act at night."""
    if wrapper.source in OBSERVED:
        wrapper.pm(messages["werecrow_already_observing"].format(OBSERVED[wrapper.source]))
        return
    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="werecrow_no_observe_self")
    if not target:
        return
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["werecrow_no_target_wolf"])
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    OBSERVED[wrapper.source] = target
    wrapper.pm(messages["werecrow_observe_success"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["wolfchat_observe"].format(wrapper.source, target), {"werecrow"}, role="werecrow", command="observe")
    debuglog("{0} (werecrow) OBSERVE: {1} ({2})".format(wrapper.source, target, get_main_role(var, target)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    for crow, target in OBSERVED.items():
        # if any of target's roles (primary or secondary) are Nocturnal, we see them as awake
        roles = get_all_roles(target)
        if roles & Nocturnal:
            crow.send(messages["werecrow_success"].format(target))
        else:
            crow.send(messages["werecrow_failure"].format(target))

@event_listener("begin_day")
def on_begin_day(evt, var):
    OBSERVED.clear()

@event_listener("reset")
def on_reset(evt, var):
    OBSERVED.clear()

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(OBSERVED)
    evt.data["nightroles"].extend(get_all_players(var, ("werecrow",)))

@event_listener("new_role")
def on_new_role(evt, var, player, oldrole):
    # remove the observation if they're turning from a crow into a not-crow
    if oldrole == "werecrow" and evt.data["role"] != "werecrow":
        OBSERVED.pop(player, None)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["werecrow"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Spy", "Village Objective", "Wolf Objective"}
