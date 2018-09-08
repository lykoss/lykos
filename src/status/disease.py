from src.decorators import event_listener
from src.containers import UserSet
from src.events import Event

__all__ = ["add_disease", "remove_disease", "wolves_diseased"]

DISEASED = UserSet() # type: Set[users.User]
DISEASED_WOLVES = False

def add_disease(var, target):
    """Effect the target with disease. Fire the add_disease event."""
    if target in DISEASED:
        return

    if Event("add_disease", {}).dispatch(var, target):
        DISEASED.add(target)

def remove_disease(var, target):
    """Remove the disease effect from the player."""
    DISEASED.discard(target)

def wolves_diseased(var):
    """Return whether or not wolves are currently diseased."""
    return DISEASED_WOLVES

@event_listener("transition_day_resolve_end")
def on_transition_day_resolve(evt, var, victims):
    global DISEASED_WOLVES
    for victim in evt.data["dead"]:
        if victim in evt.data["bywolves"] and victim in DISEASED: # Silly wolves, eating a sick person... tsk tsk
            DISEASED_WOLVES = True
            break
    else:
        DISEASED_WOLVES = False

@event_listener("begin_day")
def on_begin_day(evt, var):
    DISEASED.clear()

@event_listener("reset")
def on_reset(evt, var):
    global DISEASED_WOLVES
    DISEASED.clear()
    DISEASED_WOLVES = False

# vim: set sw=4 expandtab:
