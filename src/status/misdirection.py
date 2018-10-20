import random

from src.decorators import event_listener
from src.containers import UserSet
from src.functions import get_players

__all__ = ["add_misdirection", "try_misdirection"]

MISDIRECTED = UserSet() # type: Set[users.User]
LUCKY = UserSet() # type: Set[users.User]

def _get_target(target):
    """Internal helper for try_misdirection. Return one target overt."""
    pl = get_players()
    index = pl.index(target)
    if random.randint(0, 1):
        index -= 2
    if index == len(pl) - 1: # last item
        index = -1
    return pl[index+1]

def add_misdirection(var, user, *, as_actor=False, as_target=False):
    if as_actor:
        MISDIRECTED.add(user)
    if as_target:
        LUCKY.add(user)

def try_misdirection(var, actor, target):
    """Check if misdirection can apply. Return the target."""
    if actor is not target:
        if actor in MISDIRECTED:
            target = _get_target(target)
        if target in LUCKY:
            target = _get_target(target)
    return target

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    MISDIRECTED.discard(player)
    LUCKY.discard(player)

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if MISDIRECTED or LUCKY:
        misdirected = MISDIRECTED | LUCKY
        out = []
        for user in misdirected:
            as_what = []
            if user in MISDIRECTED:
                as_what.append("actor")
            if user in LUCKY:
                as_what.append("target")
            out.append("{0} (as {1})".format(user, " and ".join(as_what)))
        evt.data["output"].append("\u0002misdirected\u0002: {0}".format(", ".join(out)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    MISDIRECTED.clear()
    LUCKY.clear()

@event_listener("reset")
def on_reset(evt, var):
    MISDIRECTED.clear()
    LUCKY.clear()
