from __future__ import annotations
from lykos.src.gamestate import GameState

import re
import random
import itertools
import math
import typing
from collections import defaultdict, deque

from src.utilities import *
from src import channels, users, errlog, plog
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.status import try_misdirection, try_exchange, try_protection, add_dying, is_silent

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher

TARGETED = UserDict() # type: UserDict[users.User, users.User]
PREV_ACTED = UserSet()

@command("target", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("assassin",))
def target(wrapper: MessageDispatcher, message: str):
    """Pick a player as your target, killing them if you die."""
    if wrapper.source in PREV_ACTED:
        wrapper.send(messages["assassin_already_targeted"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0])
    if not target:
        return

    orig = target
    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    TARGETED[wrapper.source] = target

    wrapper.send(messages["assassin_target_success"].format(orig))

@event_listener("chk_nightdone")
def on_chk_nightdone(evt, var):
    evt.data["nightroles"].extend(get_all_players(var, ("assassin",)) - PREV_ACTED)
    evt.data["acted"].extend(TARGETED.keys() - PREV_ACTED)

@event_listener("transition_day", priority=7)
def on_transition_day(evt, var):
    # Select a random target for assassin that isn't already going to die if they didn't target
    pl = get_players(var)
    for ass in get_all_players(var, ("assassin",)):
        if ass not in TARGETED and not is_silent(var, ass):
            ps = pl[:]
            ps.remove(ass)
            for victim in set(evt.data["victims"]):
                if victim in ps:
                    ps.remove(victim)
            if ps:
                target = random.choice(ps)
                TARGETED[ass] = target
                ass.send(messages["assassin_random"].format(target))
    PREV_ACTED.update(TARGETED.keys())

@event_listener("send_role")
def on_send_role(evt, var):
    for ass in get_all_players(var, ("assassin",)):
        if ass in TARGETED:
            continue # someone already targeted

        pl = get_players(var)
        random.shuffle(pl)
        pl.remove(ass)

        ass_evt = Event("assassin_target", {"target": None})
        ass_evt.dispatch(var, ass, pl)

        if ass_evt.data["target"] is not None:
            TARGETED[ass] = ass_evt.data["target"]
            PREV_ACTED.add(ass)
        else:
            ass.send(messages["assassin_notify"])
            if var.NIGHT_COUNT > 0:
                ass.send(messages["players_list"].format(pl))

@event_listener("del_player")
def on_del_player(evt, var: GameState, player, all_roles, death_triggers):
    if player in TARGETED.values():
        for x, y in list(TARGETED.items()):
            if y is player:
                del TARGETED[x]
                PREV_ACTED.discard(x)

    if death_triggers and "assassin" in all_roles and player in TARGETED:
        target = TARGETED[player]
        del TARGETED[player]
        PREV_ACTED.discard(player)
        if target in get_players(var):
            protected = try_protection(var, target, player, "assassin", "assassin_fail")
            if protected is not None:
                channels.Main.send(*protected)
                return
            to_send = "assassin_success_no_reveal"
            if var.role_reveal in ("on", "team"):
                to_send = "assassin_success"
            channels.Main.send(messages[to_send].format(player, target, get_reveal_role(var, target)))
            add_dying(var, target, killer_role=evt.params.main_role, reason="assassin")

@event_listener("myrole")
def on_myrole(evt, var, user):
    if user in get_all_players(var, ("assassin",)):
        if user in TARGETED:
            evt.data["messages"].append(messages["assassin_targeting"].format(TARGETED[user]))
        else:
            evt.data["messages"].append(messages["assassin_no_target"])

@event_listener("revealroles_role")
def on_revealroles_role(evt, var, user, role):
    if role == "assassin" and user in TARGETED:
        evt.data["special_case"].append(messages["assassin_revealroles"].format(TARGETED[user]))

@event_listener("reset")
def on_reset(evt, var):
    TARGETED.clear()
    PREV_ACTED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["assassin"] = {"Village"}
