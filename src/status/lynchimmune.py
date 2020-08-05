from src.containers import DefaultUserDict
from src.functions import get_players
from src.messages import messages
from src.events import Event, event_listener
from src.users import User

__all__ = ["add_lynch_immunity", "try_lynch_immunity"]

IMMUNITY = DefaultUserDict(set) # type: DefaultUserDict[User, set]

def add_lynch_immunity(var, user, reason):
    """Make user immune to lynching for one day."""
    if user not in get_players():
        return
    IMMUNITY[user].add(reason)

def try_lynch_immunity(var, user) -> bool:
    if user in IMMUNITY:
        reason = IMMUNITY[user].pop() # get a random reason
        evt = Event("lynch_immunity", {"immune": False})
        evt.dispatch(var, user, reason)
        return evt.data["immune"]

    return False

@event_listener("revealroles")
def on_revealroles(evt, var):
    if IMMUNITY:
        evt.data["output"].append(messages["lynch_immune_revealroles"].format(IMMUNITY))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    IMMUNITY.clear()

@event_listener("reset")
def on_reset(evt, var):
    IMMUNITY.clear()
