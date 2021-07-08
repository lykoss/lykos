from __future__ import annotations

import re
import random
import typing

from src import users, channels
from src.decorators import command
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.functions import get_players, get_all_players, get_main_role, get_target
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.events import Event, event_listener
from src.cats import Cursed, Safe, Innocent, Wolf

from src.roles.helper.seers import setup_variables

if typing.TYPE_CHECKING:
    from src.dispatcher import MessageDispatcher
    from src.gamestate import GameState
    from typing import Optional

SEEN = setup_variables("oracle")

@command("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("oracle",))
def see(wrapper: MessageDispatcher, message: str):
    """Use your paranormal powers to determine the role or alignment of a player."""
    if wrapper.source in SEEN:
        wrapper.send(messages["seer_fail"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0], not_self_message="no_see_self")
    if target is None:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    targrole = get_main_role(var, target)
    trole = targrole # keep a copy for logging

    if targrole in Cursed:
        targrole = "wolf"
    elif targrole in Safe | Innocent:
        targrole = var.hidden_role
    elif targrole in Wolf:
        targrole = "wolf"

    evt = Event("see", {"role": targrole})
    evt.dispatch(var, wrapper.source, target)
    targrole = evt.data["role"]

    to_send = "oracle_success_not_wolf"
    if targrole == "wolf":
        to_send = "oracle_success_wolf"
    wrapper.send(messages[to_send].format(target))

    SEEN.add(wrapper.source)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["oracle"] = {"Village", "Nocturnal", "Spy", "Safe"}
    elif kind == "lycanthropy_role":
        evt.data["oracle"] = {"role": "doomsayer", "prefix": "seer"}
