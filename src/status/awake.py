from __future__ import annotations

from src.events import Event, event_listener
from src.containers import UserSet
from src.cats import Nocturnal
from src.functions import get_all_roles
from src.gamestate import GameState
from src.users import User

__all__ = ["add_awake", "add_asleep", "is_awake"]

AWAKE = UserSet()
ASLEEP = UserSet()

# marking someone awake overrides asleep and non-Nocturnal roles
def add_awake(var: GameState, player: User):
    AWAKE.add(player)

# marking someone asleep overrides a Nocturnal role
def add_asleep(var: GameState, player: User):
    ASLEEP.add(player)

def is_awake(var: GameState, player: User):
    return player in AWAKE or (player not in ASLEEP and get_all_roles(var, player) & Nocturnal)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: set[str], death_triggers: bool):
    AWAKE.discard(player)
    ASLEEP.discard(player)

@event_listener("begin_day")
def on_begin_day(evt: Event, var: GameState):
    AWAKE.clear()
    ASLEEP.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    AWAKE.clear()
    ASLEEP.clear()
