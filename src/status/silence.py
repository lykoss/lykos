from __future__ import annotations

from typing import TYPE_CHECKING

from src.containers import UserSet
from src.decorators import event_listener
from src.messages import messages

__all__ = ["add_silent", "is_silent"]

SILENT: UserSet = UserSet()

def add_silent(var, user):
    """Silence the target, preventing them from using actions for a day."""
    # silence should work on dead players; don't add an alive check here
    SILENT.add(user)

def is_silent(var, user):
    """Return True if the user is silent, False otherwise."""
    return user in SILENT

# No del_player listener - we want roles that can act when dead to remain silenced (e.g. vengeful ghost)

@event_listener("revealroles")
def on_revealroles(evt, var):
    if SILENT:
        evt.data["output"].append(messages["silence_revealroles"].format(SILENT))

@event_listener("transition_day_end")
def on_transition_day_end(evt, var):
    SILENT.clear()

@event_listener("reset")
def on_reset(evt, var):
    SILENT.clear()
