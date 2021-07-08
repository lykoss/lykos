from __future__ import annotations

import re
import random
import itertools
import typing
import math
from collections import defaultdict

from src import channels, users
from src.functions import get_players, get_all_players, get_main_role, get_reveal_role, get_target
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener
from src.cats import Spy
from src.roles.helper.wolves import is_known_wolf_ally, send_wolfchat_message, register_wolf

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState
    from src.users import User
    from typing import Optional, Set

register_wolf("sorcerer")

OBSERVED = UserSet()

@command("observe", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("sorcerer",))
def observe(wrapper: MessageDispatcher, message: str):
    """Observe a player to obtain various information."""
    var = wrapper.game_state
    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_observe_self")
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
    targrole = get_main_role(var, target)
    if targrole == "amnesiac":
        from src.roles.amnesiac import ROLES as amn_roles
        targrole = amn_roles[target]

    key = "sorcerer_fail"
    if targrole in Spy:
        key = "sorcerer_success"

    wrapper.pm(messages[key].format(target, targrole))
    send_wolfchat_message(var, wrapper.source, messages["sorcerer_success_wolfchat"].format(wrapper.source, target), {"sorcerer"}, role="sorcerer", command="observe")

@event_listener("chk_nightdone")
def on_chk_nightdone(evt: Event, var: GameState):
    evt.data["acted"].extend(OBSERVED)
    evt.data["nightroles"].extend(get_all_players(var, ("sorcerer",)))

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: Set[str], death_triggers: bool):
    OBSERVED.discard(player)

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if old_role == "sorcerer" and evt.data["role"] != "sorcerer":
        OBSERVED.discard(player)

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    OBSERVED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    OBSERVED.clear()

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["sorcerer"] = {"Wolfchat", "Wolfteam", "Nocturnal", "Spy", "Wolf Objective"}
