import re
import random

from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_all_roles, get_target, get_main_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Nocturnal
from src.roles._wolf_helper import is_known_wolf_ally, send_wolfchat_message

OBSERVED = UserDict() # type: UserDict[users.User, users.User]

@command("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("werecrow",))
def observe(var, wrapper, message):
    """Observe a player to see whether they are able to act at night."""
    if wrapper.source in OBSERVED:
        wrapper.pm(messages["werecrow_already_observing"].format(OBSERVED[wrapper.source]))
        return
    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="werecrow_no_observe_self")
    if not target:
        return
    if is_known_wolf_ally(var, wrapper.source, target):
        wrapper.pm(messages["werecrow_no_target_wolf"])
        return

    orig = target
    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    evt.dispatch(var, wrapper.source, target)
    if evt.prevent_default:
        return

    target = evt.data["target"]
    OBSERVED[wrapper.source] = target
    wrapper.pm(messages["werecrow_observe_success"].format(orig))
    send_wolfchat_message(var, wrapper.source, messages["wolfchat_observe"].format(wrapper.source, target), {"werecrow"}, role="werecrow", command="observe")
    debuglog("{0} (werecrow) OBSERVE: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

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
    evt.data["actedcount"] += len(OBSERVED)
    evt.data["nightroles"].extend(get_all_players(("werecrow",)))

@event_listener("new_role")
def on_new_role(evt, var, player, oldrole):
    # remove the observation if they're turning from a crow into a not-crow
    if oldrole == "werecrow" and evt.data["role"] != "werecrow":
        OBSERVED.pop(player, None)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["werecrow"] = {"Wolf", "Wolfchat", "Wolfteam", "Killer", "Nocturnal", "Spy"}

# vim: set sw=4 expandtab:
