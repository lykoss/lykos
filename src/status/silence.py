from __future__ import annotations

from src.containers import UserSet
from src.gamestate import GameState
from src.events import Event, event_listener
from src.messages import messages
from src.users import User

__all__ = ["add_silent", "is_silent"]

SILENT = UserSet()
PENDING = UserSet()

def add_silent(var: GameState, user: User):
    """Silence the target, preventing them from using actions for a day."""
    # silence should work on dead players; don't add an alive check here
    # silence lasts until the end of the night; if it's currently the end of a night
    # then make it end the *next* night instead of the current one
    if var.in_phase_transition and var.next_phase == "day":
        PENDING.add(user)
    else:
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
    SILENT.update(PENDING)
    PENDING.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    SILENT.clear()
    PENDING.clear()
