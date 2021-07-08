from __future__ import annotations

import re
import random
import itertools
import typing
import math
from collections import defaultdict

from src.functions import get_players, get_all_players, get_target, get_main_role
from src import channels, users
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState
    from src.users import User
    from typing import Optional, Dict, Set

TOBECHARMED = UserDict() # type: UserDict[users.User, UserSet]
CHARMED = UserSet()
PASSED = UserSet()

@command("charm", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def charm(wrapper: MessageDispatcher, message: str):
    """Charm a player or two, slowly leading to your win!"""
    pieces = re.split(" +", message)
    target1 = pieces[0]
    if len(pieces) > 1:
        target2 = pieces[1]
    else:
        target2 = None

    var = wrapper.game_state

    target1 = get_target(wrapper, target1)
    if not target1:
        return

    if target2 is not None:
        target2 = get_target(wrapper, target2)
        if not target2:
            return

    orig1 = target1
    orig2 = target2

    target1 = try_misdirection(var, wrapper.source, target1)
    if target2 is not None:
        target2 = try_misdirection(var, wrapper.source, target2)

    if try_exchange(var, wrapper.source, target1) or try_exchange(var, wrapper.source, target2):
        return

    # Do these checks based on original targets, so piper doesn't know to change due to misdirection/luck totem
    if orig1 is orig2:
        wrapper.send(messages["must_charm_multiple"])
        return

    if orig1 in CHARMED and orig2 in CHARMED:
        wrapper.send(messages["targets_already_charmed"].format(orig1, orig2))
        return
    elif orig1 in CHARMED:
        wrapper.send(messages["target_already_charmed"].format(orig1))
        return
    elif orig2 in CHARMED:
        wrapper.send(messages["target_already_charmed"].format(orig2))
        return

    if wrapper.source in TOBECHARMED:
        TOBECHARMED[wrapper.source].clear()
    else:
        TOBECHARMED[wrapper.source] = UserSet()

    TOBECHARMED[wrapper.source].update({target1, target2} - {None})
    PASSED.discard(wrapper.source)

    if orig2:
        wrapper.send(messages["charm_multiple_success"].format(orig1, orig2))
    else:
        wrapper.send(messages["charm_success"].format(orig1))

@command("pass", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def pass_cmd(wrapper: MessageDispatcher, message: str):
    """Do not charm anyone tonight."""
    del TOBECHARMED[:wrapper.source:]
    PASSED.add(wrapper.source)

    wrapper.send(messages["piper_pass"])

@command("retract", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("piper",))
def retract(wrapper: MessageDispatcher, message: str):
    """Remove your decision to charm people."""
    if wrapper.source in TOBECHARMED or wrapper.source in PASSED:
        del TOBECHARMED[:wrapper.source:]
        PASSED.discard(wrapper.source)

        wrapper.send(messages["piper_retract"])

@event_listener("chk_win", priority=2)
def on_chk_win(evt: Event, var: GameState, rolemap: Dict[str, Set[User]], mainroles: Dict[User, str], lpl: int, lwolves: int, lrealwolves: int):
    # lpl doesn't included wounded/sick people or consecrating priests
    # whereas we want to ensure EVERYONE (even wounded people) are charmed for piper win
    pipers = rolemap.get("piper", set())
    lp = len(pipers)
    if lp == 0: # no alive pipers, short-circuit this check
        return

    uncharmed = set(get_players(var, mainroles=mainroles)) - CHARMED - pipers

    if var.PHASE == "day" and not uncharmed:
        evt.data["winner"] = "pipers"
        evt.data["message"] = messages["piper_win"].format(lp)

@event_listener("team_win")
def on_team_win(evt: Event, var: GameState, player: User, main_role: str, all_roles: Set[str], winner: str):
    if winner == "pipers" and main_role == "piper":
        evt.data["team_win"] = True

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, all_roles: Set[str], death_triggers: bool):
    CHARMED.discard(player)
    del TOBECHARMED[:player:]

@event_listener("transition_day_begin")
def on_transition_day_begin(evt: Event, var: GameState):
    tocharm = set(itertools.chain.from_iterable(TOBECHARMED.values()))
    # remove pipers from set; they can never be charmed
    # but might end up in there due to misdirection/luck totems
    tocharm.difference_update(get_all_players(var, ("piper",)))

    # Send out PMs to players who have been charmed
    for target in tocharm:
        charmedlist = list(CHARMED | tocharm - {target})
        message = messages["charmed"]

        to_send = "charmed_players"
        if not charmedlist:
            to_send = "no_charmed_players"
        target.send(messages["charmed"] + messages[to_send].format(charmedlist))

    if len(tocharm) > 0:
        for target in CHARMED:
            previouscharmed = CHARMED - {target}
            if previouscharmed:
                target.send(messages["players_charmed"].format(tocharm) + messages["previously_charmed"].format(previouscharmed))
            else:
                target.send(messages["players_charmed"].format(tocharm))

    CHARMED.update(tocharm)
    TOBECHARMED.clear()
    PASSED.clear()

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(TOBECHARMED)
    evt.data["acted"].extend(PASSED)
    evt.data["nightroles"].extend(get_all_players(var, ("piper",)))

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = set(get_players(var)) - CHARMED
    for piper in get_all_players(var, ("piper",)):
        pl = list(ps)
        random.shuffle(pl)
        pl.remove(piper)
        piper.send(messages["piper_notify"])
        if var.NIGHT_COUNT > 0:
            piper.send(messages["players_list"].format(pl))

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "piper" and evt.data["role"] != "piper":
        del TOBECHARMED[:player:]
        PASSED.discard(player)

    if evt.data["role"] == "piper" and player in CHARMED:
        CHARMED.remove(player)

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    CHARMED.clear()
    TOBECHARMED.clear()
    PASSED.clear()

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if CHARMED:
        evt.data["output"].append(messages["piper_revealroles_charmed"].format(CHARMED))

@event_listener("revealroles_role")
def on_revealroles_role(evt: Event, var: GameState, user: User, role: str):
    players = TOBECHARMED.get(user)
    if players:
        evt.data["special_case"].append(messages["piper_revealroles_charming"].format(players))

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["piper"] = {"Neutral", "Win Stealer", "Nocturnal"}
