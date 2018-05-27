import re
import random
import itertools
import math
from collections import defaultdict

import botconfig
from src.utilities import *
from src import channels, users, debuglog, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

WILD_CHILDREN = UserSet()
IDOLS = UserDict()

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
    if target.nick in WILD_CHILDREN:
        evt.data["role"] = "wild child"

@event_listener("exchange_roles")
def on_exchange(evt, var, actor, target, actor_role, target_role):
    if actor_role == "wolf" and actor.nick in WILD_CHILDREN and target.nick not in WILD_CHILDREN:
        WILD_CHILDREN.discard(actor)
        WILD_CHILDREN.add(target)
    elif actor_role == "wild child":
        if target_role == "wild child":
            IDOLS[actor], IDOLS[target] = IDOLS[target], IDOLS[actor]
            evt.data["actor_messages"].append(messages["wild_child_idol"].format(IDOLS[actor]))
            evt.data["target_messages"].append(messages["wild_child_idol"].format(IDOLS[target]))
        else:
            IDOLS[target] = IDOLS.pop(actor)
            evt.data["target_messages"].append(messages["wild_child_idol"].format(IDOLS[target]))
    if target_role == "wolf" and target in WILD_CHILDREN and actor not in WILD_CHILDREN:
        WILD_CHILDREN.discard(target)
        WILD_CHILDREN.add(actor)
    elif target_role == "wild child" and actor_role != "wild child":
        # if they're both wild children, already swapped idols above
        IDOLS[actor] = IDOLS.pop(target)
        evt.data["actor_messages"].append(messages["wild_child_idol"].format(IDOLS[actor]))

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user.nick in IDOLS:
        evt.data["messages"].append(messages["wild_child_idol"].format(IDOLS[user.nick]))

@event_listener("del_player")
def on_del_player(evt, var, user, mainrole, allroles, death_triggers):
    for child in get_all_players(("wild child",)):
        if child in evt.params.deadlist or IDOLS.get(child) not in evt.params.deadlist:
            continue

        # Change their main role to wolf
        child.send(messages["wild_child_idol_died"])
        WILD_CHILDREN.add(child)
        change_role(child, get_main_role(child), "wolf")
        var.ROLES["wild child"].discard(child)

        if var.RESTRICT_WOLFCHAT & var.RW_REM_NON_WOLVES:
            if var.RESTRICT_WOLFCHAT & var.RW_TRAITOR_NON_WOLF:
                wcroles = var.WOLF_ROLES
            else:
                wcroles = var.WOLF_ROLES | {"traitor"}

            wolves = get_players(wcroles)
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

                if players:
                    child.send(messages["wolves_list"].format(", ".join(names)))
                else:
                    child.send(messages["no_other_wolves"])

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    if var.FIRST_NIGHT:
        evt.data["actedcount"] += len(IDOLS.keys())
        evt.data["nightroles"].extend(get_all_players(("wild child",)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    if (not var.START_WITH_DAY or not var.FIRST_DAY) and var.FIRST_NIGHT:
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
    if user.nick in WILD_CHILDREN:
        evt.data["role"] = "wild child"

@event_listener("reset")
def on_reset(evt, var):
    WILD_CHILDREN.clear()
    IDOLS.clear()

# vim: set sw=4 expandtab:
