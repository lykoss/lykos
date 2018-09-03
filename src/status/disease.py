from src.decorators import event_listener
from src.containers import UserSet
from src.events import Event

__all__ = ["make_diseased", "cure_disease", "wolves_diseased"]

DISEASED = UserSet() # type: Set[users.User]
DISEASED_WOLVES = False

def make_diseased(var, target):
    if target in DISEASED:
        return

    if Event("make_diseased", {}).dispatch(var, target):
        DISEASED.add(target)

def cure_disease(var, target):
    DISEASED.discard(target)

def wolves_diseased(var):
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
