from __future__ import annotations

from src.containers import UserSet
from src.gamestate import GameState
from src.events import Event, event_listener
from src.messages import messages
from src.users import User

__all__ = ["add_silent", "is_silent"]

SILENT: UserSet[User] = UserSet()

def add_silent(var: GameState, user: User):
    """Silence the target, preventing them from using actions for a day."""
    # silence should work on dead players; don't add an alive check here
    SILENT.add(user)

def is_silent(var: GameState, user: User):
    """Return True if the user is silent, False otherwise."""
    return user in SILENT

# No del_player listener - we want roles that can act when dead to remain silenced (e.g. vengeful ghost)

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if SILENT:
        evt.data["output"].append(messages["silence_revealroles"].format(SILENT))

@event_listener("transition_day_end")
def on_transition_day_end(evt: Event, var: GameState):
    SILENT.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    SILENT.clear()
