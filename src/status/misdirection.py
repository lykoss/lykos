import random

from src.decorators import event_listener
from src.containers import UserSet
from src.functions import get_players

__all__ = ["add_misdirection", "try_misdirection"]

AS_ACTOR = UserSet() # type: Set[users.User]
AS_TARGET = UserSet() # type: Set[users.User]

def _get_target(target):
    """Internal helper for try_misdirection. Return one target over."""
    pl = get_players()
    index = pl.index(target)
    if random.randint(0, 1):
        index -= 2
    if index == len(pl) - 1: # last item
        index = -1
    return pl[index+1]

def add_misdirection(var, user, *, as_actor=False, as_target=False):
    # misdirection as_actor should work on dead players as well; don't do an alive check here
    if as_actor:
        AS_ACTOR.add(user)
    if as_target and user in get_players():
        AS_TARGET.add(user)

def try_misdirection(var, actor, target):
    """Check if misdirection can apply. Return the target."""
    if actor is not target:
        if actor in AS_ACTOR:
            target = _get_target(target)
        if target in AS_TARGET:
            target = _get_target(target)
    return target

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    # don't clear AS_ACTOR here; we want dead players to still be misdirected (e.g. vengeful ghost)
    AS_TARGET.discard(player)

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if AS_ACTOR or AS_TARGET:
        misdirected = AS_ACTOR | AS_TARGET
        out = []
        for user in misdirected:
            as_what = []
            if user in AS_ACTOR:
                as_what.append("actor")
            if user in AS_TARGET:
                as_what.append("target")
            out.append("{0} (as {1})".format(user, " and ".join(as_what)))
        evt.data["output"].append("\u0002misdirected\u0002: {0}".format(", ".join(out)))

@event_listener("transition_day_begin")
def on_transition_day_begin(evt, var):
    AS_ACTOR.clear()
    AS_TARGET.clear()

@event_listener("reset")
def on_reset(evt, var):
    AS_ACTOR.clear()
    AS_TARGET.clear()
