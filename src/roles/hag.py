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
from src.status import try_misdirection, try_exchange, add_silent

from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, register_wolf

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

register_wolf("hag")

HEXED = UserDict() # type: UserDict[users.User, users.User]
LASTHEXED = UserDict() # type: UserDict[users.User, users.User]

@command("hex", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("hag",))
def hex_cmd(wrapper: MessageDispatcher, message: str):
    """Hex someone, preventing them from acting the next day and night."""
    if wrapper.source in HEXED:
        wrapper.pm(messages["already_hexed"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    if LASTHEXED.get(wrapper.source) is target:
        wrapper.pm(messages["no_multiple_hex"].format(target))
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["no_hex_wolf"])
        return

    HEXED[wrapper.source] = target

    wrapper.pm(messages["hex_success"].format(target))

    send_wolfchat_message(var, wrapper.source, messages["hex_success_wolfchat"].format(wrapper.source, target), {"hag"}, role="hag", command="hex")
    debuglog("{0} (hag) HEX: {1} ({2})".format(wrapper.source, target, get_main_role(var, target)))

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del LASTHEXED[:player:]

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(HEXED)
    evt.data["nightroles"].extend(get_all_players(var, ("hag",)))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    HEXED.clear()

@event_listener("begin_day")
def on_begin_day(evt, var):
    LASTHEXED.clear()
    for hag, target in HEXED.items():
        LASTHEXED[hag] = target
        add_silent(var, target)

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "hag" and evt.data["role"] != "hag":
        del HEXED[:user:]
        del LASTHEXED[:user:]

@event_listener("reset")
def on_reset(evt, var):
    LASTHEXED.clear()
    HEXED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["hag"] = {"Wolfchat", "Wolfteam", "Nocturnal", "Wolf Objective"}
