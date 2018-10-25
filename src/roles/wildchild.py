import re
import random
import itertools
import math
from collections import defaultdict

from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_all_roles, get_target, change_role
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange

from src.roles.helper.wolves import get_wolfchat_roles

IDOLS = UserDict()

@command("choose", chan=False, pm=True, playing=True, phases=("night",), roles=("wild child",))
def choose_idol(var, wrapper, message):
    """Pick your idol, if they die, you'll become a wolf!"""
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
    if target in get_all_players(("wild child",)):
        evt.data["role"] = "wild child"

@event_listener("new_role")
def on_new_role(evt, var, user, old_role):
    if evt.data["role"] == "wolf" and old_role == "wild child" and evt.params.inherit_from and "wild child" in get_all_roles(evt.params.inherit_from):
        evt.data["role"] = "wild child"

    if evt.params.inherit_from in IDOLS and "wild child" not in get_all_roles(user):
        IDOLS[user] = IDOLS.pop(evt.params.inherit_from)
        evt.data["messages"].append(messages["wild_child_idol"].format(IDOLS[user]))

@event_listener("swap_role_state")
def on_swap_role_state(evt, var, actor, target, role):
    if role == "wild child":
        IDOLS[actor], IDOLS[target] = IDOLS[target], IDOLS[actor]
        if IDOLS[actor] in get_players():
            evt.data["actor_messages"].append(messages["wild_child_idol"].format(IDOLS[actor]))
        else: # The King is dead, long live the King!
            change_role(var, actor, "wild child", "wolf", message="wild_child_idol_died")
            var.ROLES["wild child"].add(actor)

        if IDOLS[target] in get_players():
            evt.data["target_messages"].append(messages["wild_child_idol"].format(IDOLS[target]))
        else:
            change_role(var, target, "wild child", "wolf", message="wild_child_idol_died")
            var.ROLES["wild child"].add(target)

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in IDOLS and user not in get_players(get_wolfchat_roles(var)):
        evt.data["messages"].append(messages["wild_child_idol"].format(IDOLS[user]))

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    del IDOLS[:player:]
    if not death_triggers:
        return

    for child in get_all_players(("wild child",)):
        if IDOLS.get(child) is player:
            # Change their main role to wolf
            change_role(var, child, get_main_role(child), "wolf", message="wild_child_idol_died")
            var.ROLES["wild child"].add(child)

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["actedcount"] += len(IDOLS)
    evt.data["nightroles"].extend(get_all_players(("wild child",)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    if not var.START_WITH_DAY or not var.FIRST_DAY:
        for child in get_all_players(("wild child",)):
            if child not in IDOLS:
                players = get_players()
                players.remove(child)
                if players:
                    idol = random.choice(players)
                    IDOLS[child] = idol
                    child.send(messages["wild_child_random_idol"].format(idol))
                    idol_role = get_main_role(idol)
                    debuglog("{0} (wild child) IDOLIZE RANDOM: {1} ({2})".format(child, idol, idol_role))

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    wolves = get_players(get_wolfchat_roles(var))
    for child in get_all_players(("wild child",)):
        if child in wolves:
            continue
        if child.prefers_simple():
            child.send(messages["wild_child_simple"])
        else:
            child.send(messages["wild_child_notify"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "wild child" and user not in get_players(get_wolfchat_roles(var)):
        if user in IDOLS:
            evt.data["special_case"].append(messages["wild_child_revealroles_picked"].format(IDOLS[user]))
        else:
            evt.data["special_case"].append(messages["wild_child_revealroles_no_idol"])

@event_listener("get_reveal_role")
def on_get_reveal_role(evt, var, user):
    if evt.data["role"] == "wolf" and user in get_all_players(("wild child",)):
        evt.data["role"] = "wild child"

@event_listener("reset")
def on_reset(evt, var):
    IDOLS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["wild child"] = {"Village", "Team Switcher"}

# vim: set sw=4 expandtab:
