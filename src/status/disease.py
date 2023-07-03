from __future__ import annotations
from typing import Union

from src.containers import UserSet
from src.gamestate import GameState
from src.functions import get_players
from src.events import Event, event_listener
from src.users import User

__all__ = ["add_disease", "remove_disease", "wolves_diseased"]

DISEASED = UserSet()
DISEASED_WOLVES = False

def add_disease(var: GameState, target: User):
    """Effect the target with disease. Fire the add_disease event."""
    if target in DISEASED or target not in get_players(var):
        return

    if Event("add_disease", {}).dispatch(var, target):
        DISEASED.add(target)

def remove_disease(var: GameState, target: User):
    """Remove the disease effect from the player."""
    DISEASED.discard(target)

def wolves_diseased(var: GameState):
    """Return whether wolves are currently diseased."""
    return DISEASED_WOLVES

@event_listener("transition_day_resolve")
def on_transition_day_resolve(evt: Event, var: GameState, dead: set[User], killers: dict[User, Union[User, str]]):
    global DISEASED_WOLVES
    for victim in dead:
        # Silly wolves, eating a sick person... tsk tsk
        if killers[victim] == "@wolves" and victim in DISEASED:
            DISEASED_WOLVES = True
            break
    else:
        DISEASED_WOLVES = False

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    DISEASED.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    global DISEASED_WOLVES
    DISEASED.clear()
    DISEASED_WOLVES = False

@event_listener("wolf_numkills", priority=10)
def on_wolf_numkills(evt: Event, var: GameState, wolf: User):
    if wolves_diseased(var):
        evt.data["numkills"] = 0
        evt.data["message"] = "ill_wolves"
        evt.stop_processing = True
