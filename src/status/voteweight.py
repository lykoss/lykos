from src.decorators import event_listener
from src.containers import UserDict
from src.functions import get_players
from src.messages import messages
from src import users

__all__ = ["add_vote_weight", "remove_vote_weight", "get_vote_weight"]

WEIGHT = UserDict() # type: UserDict[users.User, int]

def add_vote_weight(var, target : users.User, amount : int = 1) -> None:
    """Make the target's votes as having more weight."""
    if target not in get_players():
        return

    WEIGHT[target] = WEIGHT.get(target, 1) + amount
    if WEIGHT[target] == 1:
        del WEIGHT[target]

def remove_vote_weight(var, target : users.User, amount : int = 1) -> None:
    """Make the target's votes as having less weight."""
    add_vote_weight(var, target, -amount)

def get_vote_weight(var, target : users.User) -> int:
    """Get how much weight the target's votes have."""
    # ensure we don't return negative numbers here;
    # we still track them for stacking purposes but anything below 0 counts as 0
    return max(WEIGHT.get(target, 1), 0)

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del WEIGHT[:player:]

@event_listener("revealroles")
def on_revealroles(evt, var):
    if WEIGHT:
        ilist = []
        for p, n in WEIGHT.items():
            ilist.append("{0} ({1})".format(p, max(n, 0)))
        evt.data["output"].append(messages["vote_weight_revealroles"].format(ilist))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    WEIGHT.clear()

@event_listener("reset")
def on_reset(evt, var):
    WEIGHT.clear()
