from __future__ import annotations

import re
import random
import itertools
import math
from collections import defaultdict
from typing import TYPE_CHECKING

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.roles.helper.wolves import get_wolfchat_roles, is_known_wolf_ally, send_wolfchat_message, get_wolflist, register_wolf

if TYPE_CHECKING:
    from src.users import User
    from src.dispatcher import MessageDispatcher

register_wolf("warlock")

CURSED: UserDict[User, User] = UserDict()
PASSED: UserSet = UserSet()

@command("curse", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def curse(wrapper: MessageDispatcher, message: str):
    var = wrapper.game_state
    target = get_target(var, wrapper, re.split(" +", message)[0])
    if not target:
        return

    if target in get_all_players(("cursed villager",)):
        wrapper.pm(messages["target_already_cursed"].format(target))
        return

    # There may actually be valid strategy in cursing other wolfteam members,
    # but for now it is not allowed. If someone seems suspicious and shows as
    # villager across multiple nights, safes can use that as a tell that the
    # person is likely wolf-aligned.
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["no_curse_wolf"])
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    CURSED[wrapper.source] = target
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["curse_success"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["curse_success_wolfchat"].format(wrapper.source, orig), {"warlock"}, role="warlock", command="curse")

    debuglog("{0} (warlock) CURSE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Decline to use your special power for that night."""
    del CURSED[:wrapper.source:]
    PASSED.add(wrapper.source)

    wrapper.pm(messages["warlock_pass"])
    send_wolfchat_message(wrapper.game_state, wrapper.source, messages["warlock_pass_wolfchat"].format(wrapper.source), {"warlock"}, role="warlock", command="pass")

    debuglog("{0} (warlock) PASS".format(wrapper.source))

@command("retract", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("warlock",))
def retract(wrapper: MessageDispatcher, message: str):
    """Retract your curse or pass."""
    del CURSED[:wrapper.source:]
    PASSED.discard(wrapper.source)

    wrapper.pm(messages["warlock_retract"])
    send_wolfchat_message(wrapper.game_state, wrapper.source, messages["warlock_retract_wolfchat"].format(wrapper.source), {"warlock"}, role="warlock", command="retract")

    debuglog("{0} (warlock) RETRACT".format(wrapper.source))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(CURSED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_all_players(("warlock",)))

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del CURSED[:player:]
    PASSED.discard(player)

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "warlock" and evt.data["role"] != "warlock":
        del CURSED[:user:]
        PASSED.discard(user)

    if not evt.data["in_wolfchat"] and evt.data["role"] == "warlock":
        # this means warlock isn't in wolfchat, so only give cursed list
        user.send(messages["players_list"].format(get_wolflist(var, user)))

@event_listener("begin_day")
def on_begin_day(evt, var):
    pl = get_players(var)
    wroles = get_wolfchat_roles(var)
    for warlock, target in CURSED.items():
        if target in pl and get_main_role(target) not in wroles:
            var.ROLES["cursed villager"].add(target)

    CURSED.clear()
    PASSED.clear()

@event_listener("reset")
def on_reset(evt, var):
    CURSED.clear()
    PASSED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["warlock"] = {"Wolfchat", "Wolfteam", "Nocturnal", "Wolf Objective"}
