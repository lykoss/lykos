import math
import re
import random

import src.settings as var
from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

INVESTIGATED = UserSet()

@command("id", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("detective",))
def investigate(var, wrapper, message):
    """Investigate a player to determine their exact role."""
    if wrapper.source in INVESTIGATED:
        wrapper.send(messages["already_investigated"])
        return

    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_investigate_self")
    if target is None:
        return

    evt = Event("targeted_command", {"target": target, "misdirection": True, "exchange": True})
    if not evt.dispatch(var, "identify", wrapper.source, target, frozenset({"info", "immediate"})):
        return

    target = evt.data["target"]
    targrole = get_main_role(target)

    evt = Event("investigate", {"role": targrole})
    evt.dispatch(var, wrapper.source, target)
    targrole = evt.data["role"]

    INVESTIGATED.add(wrapper.source)
    wrapper.send(messages["investigate_success"].format(target, targrole))
    debuglog("{0} (detective) ID: {1} ({2})".format(wrapper.source, target, targrole))

    if random.random() < var.DETECTIVE_REVEALED_CHANCE:  # a 2/5 chance (should be changeable in settings)
        # The detective's identity is compromised!
        wcroles = var.WOLFCHAT_ROLES
        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}

        wolves = get_all_players(wcroles)
        if wolves:
            for wolf in wolves:
                wolf.queue_message(messages["detective_reveal"].format(wrapper.source))
            wolf.send_messages()

        debuglog("{0} (detective) PAPER DROP".format(wrapper.source))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    INVESTIGATED.discard(user)

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_players(("detective",)))

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "detective" and target_role != "detective":
        INVESTIGATED.discard(actor)
    elif target_role == "detective" and actor_role != "detective":
        INVESTIGATED.discard(target)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    for dttv in var.ROLES["detective"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(dttv)
        chance = math.floor(var.DETECTIVE_REVEALED_CHANCE * 100)
        warning = ""
        if chance > 0:
            warning = messages["detective_chance"].format(chance)
        to_send = "detective_notify"
        if dttv.prefers_simple():
            to_send = "detective_simple"
        dttv.send(messages[to_send].format(warning), "Players: " + ", ".join(p.nick for p in pl), sep="\n")

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    INVESTIGATED.clear()

@event_listener("reset")
def on_reset(evt, var):
    INVESTIGATED.clear()

# vim: set sw=4 expandtab:
