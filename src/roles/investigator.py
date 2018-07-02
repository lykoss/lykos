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

INVESTIGATED = UserSet()

@command("id", "investigate", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("investigator",))
def investigate(var, wrapper, message):
    """Investigate two players to determine their relationship to each other."""
    if wrapper.source in INVESTIGATED:
        wrapper.pm(messages["already_investigated"])
        return
    pieces = re.split(" +", message)
    if len(pieces) == 1:
        wrapper.pm(messages["investigator_help"])
        return
    target1 = pieces[0]
    target2 = pieces[1]
    if target2.lower() == "and" and len(pieces) > 2:
        target2 = pieces[2]
    target1 = get_target(var, wrapper, target1, not_self_message="no_investigate_self")
    target2 = get_target(var, wrapper, target2, not_self_message="no_investigate_self")
    if not target1 or not target2:
        return
    elif target1 is target2:
        wrapper.pm(messages["investigator_help"])
        return

    evt = Event("targeted_command", {"target": target1, "misdirection": True, "exchange": True})
    evt.dispatch(var, wrapper.source, target1)
    if evt.prevent_default:
        return
    target1 = evt.data["target"]

    evt = Event("targeted_command", {"target": target2, "misdirection": True, "exchange": True})
    evt.dispatch(var, wrapper.source, target2)
    if evt.prevent_default:
        return
    target2 = evt.data["target"]

    t1role = get_main_role(target1)
    t2role = get_main_role(target2)

    evt = Event("investigate", {"role": t1role})
    evt.dispatch(var, wrapper.source, target1)
    t1role = evt.data["role"]

    evt = Event("investigate", {"role": t2role})
    evt.dispatch(var, wrapper.source, target2)
    t2role = evt.data["role"]

    # FIXME: make a standardized way of getting team affiliation, and make
    # augur and investigator both use it (and make it events-aware so other
    # teams can be added more easily)
    if t1role in var.WOLFTEAM_ROLES:
        t1role = "red"
    elif t1role in var.TRUE_NEUTRAL_ROLES:
        t1role = "grey"
    else:
        t1role = "blue"

    if t2role in var.WOLFTEAM_ROLES:
        t2role = "red"
    elif t2role in var.TRUE_NEUTRAL_ROLES:
        t2role = "grey"
    else:
        t2role = "blue"

    evt = Event("get_team_affiliation", {"same": (t1role == t2role)})
    evt.dispatch(evt, target1, target2)

    if evt.data["same"]:
        wrapper.pm(messages["investigator_results_same"].format(target1, target2))
    else:
        wrapper.pm(messages["investigator_results_different"].format(target1, target2))

    INVESTIGATED.add(wrapper.source)
    debuglog("{0} (investigator) ID: {1} ({2}) and {3} ({4}) as {5}".format(
        wrapper.source, target1, get_main_role(target1), target2, get_main_role(target2),
        "same" if evt.data["same"] else "different"))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    INVESTIGATED.discard(user)

@event_listener("get_special")
def on_get_special(evt, var):
    evt.data["villagers"].update(get_players(("investigator",)))

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if old_role == "investigator" and evt.data["role"] != "investigator":
        INVESTIGATED.discard(user)

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    ps = get_players()
    for inv in var.ROLES["investigator"]:
        pl = ps[:]
        random.shuffle(pl)
        pl.remove(inv)
        to_send = "investigator_notify"
        if inv.prefers_simple():
            to_send = "investigator_simple"
        inv.send(messages[to_send], messages["players_list"].format(", ".join(p.nick for p in pl)), sep="\n")

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    INVESTIGATED.clear()

@event_listener("reset")
def on_reset(evt, var):
    INVESTIGATED.clear()

# vim: set sw=4 expandtab:
