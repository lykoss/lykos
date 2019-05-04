from src.containers import UserSet
from src.decorators import event_listener

__all__ = ["add_silent", "is_silent"]

SILENT = UserSet() # type: UserSet[users.User]

def add_silent(var, user):
    """Silence the target, preventing them from using actions for a day."""
    SILENT.add(user)

def is_silent(var, user):
    """Return True if the user is silent, False otherwise."""
    return user in SILENT

# No del_player listener - we want roles that can act when dead to remain silenced (e.g. vengeful ghost)

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if SILENT:
        evt.data["output"].append("\u0002silent\u0002: {0}".format(", ".join(p.nick for p in SILENT)))

@event_listener("transition_day_end")
def on_transition_day_end(evt, var):
    SILENT.clear()

@event_listener("reset")
def on_reset(evt, var):
    SILENT.clear()
