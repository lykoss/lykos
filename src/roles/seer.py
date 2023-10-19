from __future__ import annotations

import re
from typing import Optional

from src.cats import Cursed, Safe, Innocent, Neutral, Win_Stealer, Team_Switcher, Wolf
from src.decorators import command
from src.events import Event, event_listener
from src.functions import get_main_role, get_target
from src.messages import messages
from src.roles.helper.seers import setup_variables
from src.status import try_misdirection, try_exchange
from src.dispatcher import MessageDispatcher
from src.gamestate import GameState


SEEN = setup_variables("seer")

@command("see", chan=False, pm=True, playing=True, silenced=True, phases=("night",), roles=("seer",))
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

    if targrole in Cursed:
        targrole = "wolf"
    elif targrole in Safe:
        pass # Keep the same role
    elif targrole in Innocent:
        targrole = var.hidden_role
    elif targrole in (Neutral - Win_Stealer - Team_Switcher):
        pass # Keep the same role
    elif targrole in Wolf:
        targrole = "wolf"
    else:
        targrole = var.hidden_role

    evt = Event("see", {"role": targrole})
    evt.dispatch(var, wrapper.source, target)
    targrole = evt.data["role"]

    wrapper.send(messages["seer_success"].format(target, targrole))

    SEEN.add(wrapper.source)

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["seer"] = {"Village", "Nocturnal", "Spy", "Safe"}
    elif kind == "lycanthropy_role":
        evt.data["seer"] = {"role": "doomsayer", "prefix": "seer"}
