from src.decorators import event_listener
from src.containers import UserDict
from src.functions import get_players
from src import users

__all__ = ["add_influence", "remove_influence", "get_influence"]

INFLUENCE = UserDict() # type: UserDict[users.User, int]

def add_influence(var, target : users.User, amount : int = 1) -> None:
    """Make the target's votes more influential."""
    if target not in get_players():
        return

    INFLUENCE[target] = INFLUENCE.get(target, 1) + amount
    if INFLUENCE[target] == 1:
        del INFLUENCE[target]

def remove_influence(var, target : users.User, amount : int = 1) -> None:
    """Make the target's votes less influential."""
    add_influence(var, target, -amount)

def get_influence(var, target : users.User) -> int:
    """Get how much weight the target's votes have."""
    # ensure we don't return negative numbers here;
    # we still track them for stacking purposes but anything below 0 counts as 0
    return max(INFLUENCE.get(target, 1), 0)

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del INFLUENCE[:player:]

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if INFLUENCE:
        ilist = []
        for p, n in INFLUENCE.items():
            ilist.append("{0} ({1})".format(p, min(n, 0)))
        evt.data["output"].append("\u0002influence\u0002: {0}".format(", ".join(ilist)))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    INFLUENCE.clear()

@event_listener("reset")
def on_reset(evt, var):
    INFLUENCE.clear()
