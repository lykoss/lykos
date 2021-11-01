from __future__ import annotations

from src.containers import DefaultUserDict
from src.functions import get_players
from src.messages import messages
from src.events import Event, event_listener
from src.gamestate import GameState
from src.users import User

__all__ = ["add_lynch_immunity", "try_lynch_immunity"]

IMMUNITY: DefaultUserDict[User, set[str]] = DefaultUserDict(set)

def add_lynch_immunity(var: GameState, user: User, reason: str):
    """Make user immune to lynching for one day."""
    if user not in get_players(var):
        return
    IMMUNITY[user].add(reason)

def try_lynch_immunity(var: GameState, user: User) -> bool:
    if user in IMMUNITY:
        reason = IMMUNITY[user].pop() # get a random reason
        evt = Event("lynch_immunity", {"immune": False})
        evt.dispatch(var, user, reason)
        return evt.data["immune"]

    return False

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if IMMUNITY:
        evt.data["output"].append(messages["lynch_immune_revealroles"].format(IMMUNITY))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    IMMUNITY.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    IMMUNITY.clear()
