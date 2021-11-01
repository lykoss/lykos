from __future__ import annotations

import math
import random
import re
from typing import Optional

from src import config, users
from src.containers import UserSet, UserDict
from src.decorators import command
from src.dispatcher import MessageDispatcher
from src.events import Event, event_listener
from src.functions import get_players, get_all_players, get_target
from src.gamestate import GameState
from src.messages import messages
from src.status import try_misdirection, try_exchange, remove_lycanthropy, remove_disease
from src.users import User

IMMUNIZED = UserSet()
DOCTORS: UserDict[users.User, int] = UserDict()

@command("immunize", chan=False, pm=True, playing=True, silenced=True, phases=("day",), roles=("doctor",))
def immunize(wrapper: MessageDispatcher, message: str):
    """Immunize a player, preventing them from turning into a wolf."""
    if not DOCTORS[wrapper.source]:
        wrapper.pm(messages["doctor_fail"])
        return

    var = wrapper.game_state

    target = get_target(wrapper, re.split(" +", message)[0], allow_self=True)
    if not target:
        return

    target = try_misdirection(var, wrapper.source, target)
    if try_exchange(var, wrapper.source, target):
        return

    doctor_evt = Event("doctor_immunize", {"message": "villager_immunized"})
    doctor_evt.dispatch(var, wrapper.source, target)

    wrapper.pm(messages["doctor_success"].format(target))

    target.send(messages["immunization_success"].format(messages[doctor_evt.data["message"]]))

    IMMUNIZED.add(target)
    DOCTORS[wrapper.source] -= 1
    remove_lycanthropy(var, target)
    remove_disease(var, target)

@event_listener("add_lycanthropy")
def on_add_lycanthropy(evt: Event, var: GameState, target):
    if target in IMMUNIZED:
        evt.prevent_default = True

@event_listener("add_disease")
def on_add_disease(evt: Event, var: GameState, target):
    if target in IMMUNIZED:
        evt.prevent_default = True

@event_listener("send_role")
def on_send_role(evt: Event, var: GameState):
    ps = get_players(var)
    for doctor in get_all_players(var, ("doctor",)):
        if DOCTORS[doctor]: # has immunizations remaining
            pl = ps[:]
            random.shuffle(pl)
            doctor.send(messages["doctor_notify"])
            doctor.send(messages["doctor_immunizations"].format(DOCTORS[doctor]))

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if IMMUNIZED:
        evt.data["output"].append(messages["immunized_revealroles"].format(IMMUNIZED))

@event_listener("new_role")
def on_new_role(evt: Event, var: GameState, player: User, old_role: Optional[str]):
    if evt.data["role"] == "doctor" and old_role != "doctor":
        DOCTORS[player] = math.ceil(config.Main.get("gameplay.safes.doctor_shots") * len(get_players(var)))
    if evt.data["role"] != "doctor" and old_role == "doctor":
        del DOCTORS[player]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt: Event, var: Optional[GameState], kind: str):
    if kind == "role_categories":
        evt.data["doctor"] = {"Village", "Safe"}

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    DOCTORS.clear()
    IMMUNIZED.clear()
