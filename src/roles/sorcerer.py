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
from src.status import try_misdirection, try_exchange
from src.cats import Spy
from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, register_wolf

register_wolf("sorcerer")

OBSERVED = UserSet() # type: UserSet[users.User]

@command("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("sorcerer",))
def observe(var, wrapper, message):
    """Observe a player to obtain various information."""
    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_observe_self")
    if not target:
        return

    if wrapper.source in OBSERVED:
        wrapper.pm(messages["already_observed"])
        return

    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["no_observe_wolf"])
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    OBSERVED.add(wrapper.source)
    targrole = get_main_role(target)
    if targrole == "amnesiac":
        from src.roles.amnesiac import ROLES as amn_roles
        targrole = amn_roles[target]

    key = "sorcerer_fail"
    if targrole in Spy:
        key = "sorcerer_success"

    wrapper.pm(messages[key].format(target, targrole))
    send_wolfchat_message(var, wrapper.source, messages["sorcerer_success_wolfchat"].format(wrapper.source, target), {"sorcerer"}, role="sorcerer", command="observe")

    debuglog("{0} (sorcerer) OBSERVE: {1} ({2})".format(wrapper.source, target, targrole))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["acted"].extend(OBSERVED)
    evt.data["nightroles"].extend(get_all_players(("sorcerer",)))

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    OBSERVED.discard(player)

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "sorcerer" and evt.data["role"] != "sorcerer":
        OBSERVED.discard(user)

@event_listener("begin_day")
def on_begin_day(evt, var):
    OBSERVED.clear()

@event_listener("reset")
def on_reset(evt, var):
    OBSERVED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["sorcerer"] = {"Wolfchat", "Wolfteam", "Nocturnal", "Spy"}
