from __future__ import annotations

import math
import re
import random
import typing
from collections import defaultdict, deque

from src.utilities import *
from src.functions import get_players, get_all_players, get_target, get_main_role, get_reveal_role
from src import users, channels, debuglog, errlog, plog
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.status import try_misdirection, try_exchange, try_protection, add_dying

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

KILLS = UserDict() # type: UserDict[users.User, users.User]
TARGETS = UserDict() # type: UserDict[users.User, UserSet]

@command("kill", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("dullahan",))
def dullahan_kill(wrapper: MessageDispatcher, message: str):
    """Kill someone at night as a dullahan until everyone on your list is dead."""
    if not TARGETS[wrapper.source] & set(get_players()):
        wrapper.pm(messages["dullahan_targets_dead"])
        return

    var = wrapper.game_state
    target = get_target(var, wrapper, re.split(" +", message)[0], not_self_message="no_suicide")
    if not target:
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    KILLS[wrapper.source] = target

    wrapper.pm(messages["player_kill"].format(orig))

    debuglog("{0} (dullahan) KILL: {1} ({2})".format(wrapper.source, target, get_main_role(target)))

@command("retract", chan=False, pm=True, playing=True, phases=("night",), roles=("dullahan",))
def dullahan_retract(wrapper: MessageDispatcher, message: str):
    """Removes a dullahan's kill selection."""
    if wrapper.source in KILLS:
        del KILLS[wrapper.source]
        wrapper.pm(messages["retracted_kill"])
        debuglog("{0} (dullahan) RETRACT".format(wrapper.source))

@event_listener("player_win")
def on_player_win(evt, var, player, main_role, all_roles, winner, team_win, survived):
    if main_role != "dullahan":
        return
    alive = set(get_players())
    if not TARGETS[player] & alive:
        evt.data["individual_win"] = True

@event_listener("del_player")
def on_del_player(evt, var, player, all_roles, death_triggers):
    for h, v in list(KILLS.items()):
        if v is player:
            h.send(messages["hunter_discard"])
            del KILLS[h]
        elif h is player:
            del KILLS[h]
    if death_triggers and "dullahan" in all_roles:
        pl = get_players()
        with TARGETS[player].intersection(pl) as targets:
            if targets:
                target = random.choice(list(targets))
                protected = try_protection(var, target, player, "dullahan", "dullahan_die")
                if protected is not None:
                    channels.Main.send(*protected)
                    return

                if var.ROLE_REVEAL in ("on", "team"):
                    role = get_reveal_role(target)
                    channels.Main.send(messages["dullahan_die_success"].format(player, target, role))
                else:
                    channels.Main.send(messages["dullahan_die_success_noreveal"].format(player, target))
                debuglog("{0} (dullahan) DULLAHAN ASSASSINATE: {1} ({2})".format(player, target, get_main_role(target)))
                add_dying(var, target, "dullahan", "dullahan_die")

@event_listener("transition_day", priority=2)
def on_transition_day(evt, var):
    while KILLS:
        k, d = KILLS.popitem()
        evt.data["victims"].append(d)
        evt.data["killers"][d].append(k)

@event_listener("new_role")
def on_new_role(evt, var, player, old_role):
    if player in TARGETS and old_role == "dullahan" and evt.data["role"] != "dullahan":
        del KILLS[:player:]
        del TARGETS[player]

    if player not in TARGETS and evt.data["role"] == "dullahan":
        ps = get_players()
        max_targets = math.ceil(8.1 * math.log(len(ps), 10) - 5)
        TARGETS[player] = UserSet()

        dull_targets = Event("dullahan_targets", {"targets": TARGETS[player]}) # support sleepy
        dull_targets.dispatch(var, player, max_targets)

        ps.remove(player)
        while len(TARGETS[player]) < max_targets:
            target = random.choice(ps)
            ps.remove(target)
            TARGETS[player].add(target)

@event_listener("swap_role_state")
def on_swap_role_state(evt, var, actor, target, role):
    if role == "dullahan":
        targ_targets = TARGETS.pop(target)
        if actor in targ_targets:
            targ_targets.remove(actor)
            targ_targets.add(target)
        act_targets = TARGETS.pop(actor)
        if target in act_targets:
            act_targets.remove(target)
            act_targets.add(actor)

        TARGETS[actor] = targ_targets
        TARGETS[target] = act_targets

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    spl = set(get_players())
    evt.data["acted"].extend(KILLS)
    for dullahan, targets in TARGETS.items():
        if targets & spl and dullahan in spl:
            evt.data["nightroles"].append(dullahan)

@event_listener("send_role")
def on_transition_night_end(evt, var):
    for dullahan in get_all_players(("dullahan",)):
        targets = list(TARGETS[dullahan])
        for target in targets[:]:
            if target in var.DEAD:
                targets.remove(target)
        if not targets: # already all dead
            continue
        random.shuffle(targets)
        t = messages["dullahan_targets"] if targets == list(TARGETS[dullahan]) else messages["dullahan_remaining_targets"]
        dullahan.send(messages["dullahan_notify"])
        if var.NIGHT_COUNT > 0:
            dullahan.send(t.format(targets))

@event_listener("visit")
def on_visit(evt, var, visitor_role, visitor, visited):
    if visitor_role == "succubus":
        succubi = get_all_players(("succubus",))
        if visited in TARGETS and TARGETS[visited].intersection(succubi):
            TARGETS[visited].difference_update(succubi)
            visited.send(messages["dullahan_no_kill_succubus"])

@event_listener("myrole")
def on_myrole(evt, var, user):
    # Remind dullahans of their targets
    if user in var.ROLES["dullahan"]:
        targets = list(TARGETS[user])
        for target in list(targets):
            if target in var.DEAD:
                targets.remove(target)
        random.shuffle(targets)
        if targets:
            t = messages["dullahan_targets"] if set(targets) == TARGETS[user] else messages["dullahan_remaining_targets"]
            evt.data["messages"].append(t.format(targets))
        else:
            evt.data["messages"].append(messages["dullahan_targets_dead"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "dullahan" and user in TARGETS:
        targets = set(TARGETS[user])
        for target in TARGETS[user]:
            if target in var.DEAD:
                targets.remove(target)
        if targets:
            evt.data["special_case"].append(messages["dullahan_to_kill"].format(targets))
        else:
            evt.data["special_case"].append(messages["dullahan_all_dead"])

@event_listener("begin_day")
def on_begin_day(evt, var):
    KILLS.clear()

@event_listener("reset")
def on_reset(evt, var):
    KILLS.clear()
    TARGETS.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "night_kills":
        num = 0
        for dull in var.ROLES["dullahan"]:
            for target in TARGETS[dull]:
                if target not in var.DEAD:
                    num += 1
                    break
        evt.data["dullahan"] = num
    elif kind == "role_categories":
        evt.data["dullahan"] = {"Killer", "Nocturnal", "Neutral"}
