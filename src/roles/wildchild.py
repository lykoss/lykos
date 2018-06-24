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

WILD_CHILDREN = UserSet()
IDOLS = UserDict()

def _set_random_idol(child):
    idol = None
    if child not in IDOLS:
        players = get_players()
        players.remove(child)
        if players:
            idol = random.choice(players)
            IDOLS[child] = idol
            idol_role = get_main_role(idol)
            debuglog("{0} (wild child) IDOLIZE RANDOM: {1} ({2})".format(child, idol, idol_role))

    return idol

@command("choose", chan=False, pm=True, playing=True, phases=("night",), roles=("wild child",))
def choose_idol(var, wrapper, message):
    """Pick your idol, if they die, you'll become a wolf!"""
    if not var.FIRST_NIGHT:
        return
    if wrapper.source in IDOLS:
        wrapper.pm(messages["wild_child_already_picked"])
        return

    idol = get_target(var, wrapper, re.split(" +", message)[0])
    if not idol:
        return

    IDOLS[wrapper.source] = idol
    wrapper.send(messages["wild_child_success"].format(idol))
    debuglog("{0} (wild child) IDOLIZE: {1} ({2})".format(wrapper.source, idol, get_main_role(idol)))

@event_listener("see")
def on_see(evt, var, seer, target):
    if target in WILD_CHILDREN:
        evt.data["role"] = "wild child"

@event_listener("new_role")
def on_new_role(evt, var, user):
    if user in IDOLS and evt.params.old_player in IDOLS: # very special case: two wild children exchanging (one or both might be wolf)
        if evt.params.old_role == "wolf" and user in WILD_CHILDREN or evt.data["role"] == "wolf" and evt.params.old_player in WILD_CHILDREN:
            evt.data["role"] = "wild_child_event_handler" # special key so our swap_role_state listener can do stuff properly
            return # FIXME: I do not like this hack even though I made it. Anyone's got a better idea how to do this? -Vgr

    if evt.data["role"] == "wolf" and evt.params.old_player in WILD_CHILDREN and user not in WILD_CHILDREN:
        WILD_CHILDREN.discard(evt.params.old_player)
        WILD_CHILDREN.add(user)
        IDOLS[user] = IDOLS.pop(evt.params.old_player)
    elif evt.params.old_player is not None and evt.data["role"] == "wild child" and evt.params.old_role != "wild child":
        if evt.params.old_player in IDOLS:
            IDOLS[user] = IDOLS.pop(evt.params.old_player)
        _set_random_idol(user) # No-op if user is already in IDOLS
        evt.data["messages"].append(messages["wild_child_idol"].format(IDOLS[user]))

@event_listener("swap_role_state")
def on_swap_role_state(evt, var, actor, target, role):
    if role == "wild child":
        IDOLS[actor], IDOLS[target] = IDOLS.pop(target), IDOLS.pop(actor)
        evt.data["actor_messages"].append(messages["wild_child_idol"].format(IDOLS[actor]))
        evt.data["target_messages"].append(messages["wild_child_idol"].format(IDOLS[target]))

    elif role == "wild_child_event_handler": # special handling for two wild children who might have turned
        if actor in WILD_CHILDREN:
            WILD_CHILDREN.discard(actor)
            WILD_CHILDREN.add(target)
            evt.data["actor_role"] = "wolf"
        else:
            evt.data["actor_role"] = "wild child"
        if target in WILD_CHILDREN:
            WILD_CHILDREN.discard(target)
            WILD_CHILDREN.add(actor)
            evt.data["target_role"] = "wolf"
        else:
            evt.data["target_role"] = "wild child"

        IDOLS[actor], IDOLS[target] = IDOLS.pop(target), IDOLS.pop(actor)

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in IDOLS and user not in WILD_CHILDREN:
        evt.data["messages"].append(messages["wild_child_idol"].format(IDOLS[user]))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    if var.PHASE not in var.GAME_PHASES:
        return

    for child in get_all_players(("wild child",)):
        if child in evt.params.deadlist or IDOLS.get(child) not in evt.params.deadlist:
            continue

        # Change their main role to wolf
        child.send(messages["wild_child_idol_died"])
        WILD_CHILDREN.add(child)
        new_evt = Event("new_role", {"messages": [], "role": "wolf"}, old_player=None, old_role=get_main_role(child))
        new_evt.dispatch(var, child)
        var.ROLES["wild child"].discard(child)

        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}

            wolves = get_players(wcroles)
            wolves.remove(child)
            if wolves:
                for wolf in wolves:
                    wolf.queue_message(messages["wild_child_as_wolf"].format(child))
                wolf.send_messages()

            # Send wolf list
            if var.PHASE == "day":
                random.shuffle(wolves)
                names = []
                cursed_list = get_all_players(("cursed villager",))
                for i, wolf in enumerate(wolves):
                    role = get_main_role(wolf)
                    cursed = "cursed " if wolf in cursed_list else ""
                    names.append("\u0002{0}\u0002 ({1}{2})".format(wolf, cursed, role))

                if names:
                    child.send(messages["wolves_list"].format(", ".join(names)))
                else:
                    child.send(messages["no_other_wolves"])

        child.send(*new_evt.data["messages"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    if var.FIRST_NIGHT:
        evt.data["actedcount"] += len(IDOLS.keys())
        evt.data["nightroles"].extend(get_all_players(("wild child",)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    if (not var.START_WITH_DAY or not var.FIRST_DAY) and var.FIRST_NIGHT:
        for child in get_all_players(("wild child",)):
            idol = _set_random_idol(child)
            if idol is not None:
                child.send(messages["wild_child_random_idol"].format(idol))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    for child in get_all_players(("wild child",)):
        if child.prefers_simple():
            child.send(messages["child_simple"])
        else:
            child.send(messages["child_notify"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "wild child":
        if user in IDOLS:
            evt.data["special_case"].append(messages["wild_child_revealroles_picked"].format(IDOLS[user]))
        else:
            evt.data["special_case"].append(messages["wild_child_revealroles_no_idol"])

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, user):
    if user in WILD_CHILDREN:
        evt.data["role"] = "wild child"

@event_listener("reset")
def on_reset(evt, var):
    WILD_CHILDREN.clear()
    IDOLS.clear()

# vim: set sw=4 expandtab:
