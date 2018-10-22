from typing import Iterable, Set

from src.decorators import event_listener
from src.containers import UserDict, UserSet
from src.functions import get_players
from src.events import Event
from src import users

__all__ = ["add_force_vote", "add_force_abstain", "can_vote", "can_abstain", "get_forced_votes"]

# FORCED_COUNTS is incremented whenever we're forcing someone to vote for someone else
# A positive number indicates that their vote is being forced towards any number of targets
# whereas a negative number indicates that their vote is being forced towards abstention.
# 0 indicates not being forced.
# FORCED_TARGETS is used to see which targets are being force-voted for.
# If multiple calls to force_vote() force different targets, the union of all of those targets is taken.

FORCED_COUNTS = UserDict() # type: UserDict[users.User, int]
FORCED_TARGETS = UserDict() # type: UserDict[users.User, UserSet]

def _add_count(var, votee : users.User, amount : users.User) -> None:
    FORCED_COUNTS[votee] = FORCED_COUNTS.get(votee, 0) + amount
    if FORCED_COUNTS[votee] == 0:
        # don't clear out FORCED_TARGETS, in case a future call re-forces votes
        # we want to maintain the full set of people to vote for
        del FORCED_COUNTS[votee]

def add_force_vote(var, votee : users.User, targets : Iterable[users.User]) -> None:
    """Force votee to vote for the specified targets."""
    evt = Event("force_vote", {})
    if not evt.dispatch(var, votee, targets):
        return
    _add_count(var, votee, 1)
    FORCED_TARGETS.get(votee, UserSet()).update(targets)

def add_force_abstain(var, votee : users.User) -> None:
    """Force votee to abstain."""
    evt = Event("force_vote", {})
    if not evt.dispatch(var, votee, None):
        return
    _add_count(var, votee, -1)

def can_vote(var, votee : users.User, target : users.User) -> bool:
    """Check whether the votee can vote the target."""
    c = FORCED_COUNTS.get(votee, 0)
    if c < 0:
        return False
    elif c == 0:
        return True
    return target in FORCED_TARGETS[votee]

def can_abstain(var, votee : users.User) -> bool:
    """Check whether the votee can abstain."""
    return FORCED_COUNTS.get(votee, 0) <= 0

def get_forced_votes(var, target : users.User) -> Set[users.User]:
    """Retrieve the players who are being forced to vote target."""
    return {votee for votee, targets in FORCED_TARGETS if target in targets}

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del FORCED_COUNTS[:player:]
    del FORCED_TARGETS[:player:]
    for votee, targets in list(FORCED_TARGETS.items()):
        targets.discard(player)
        if not FORCED_TARGETS[votee]:
            # nothing left to force a vote on
            del FORCED_TARGETS[votee]
            if FORCED_COUNTS[votee] > 0:
                del FORCED_COUNTS[votee]

@event_listener("revealroles")
def on_revealroles(evt, var, wrapper):
    if FORCED_COUNTS:
        num_players = len(get_players())
        vlist = []
        alist = []
        for p, n in FORCED_COUNTS.items():
            if n < 0:
                alist.append(p.nick)
            elif len(FORCED_TARGETS[p]) == num_players:
                vlist.append("{0} (*)".format(p))
            else:
                vlist.append("{0} ({1})".format(p, ", ".join(v.nick for v in FORCED_TARGETS[p])))

        if vlist:
            evt.data["output"].append("\u0002forced votes\u0002: {0}".format(", ".join(vlist)))
        if alist:
            evt.data["output"].append("\u0002forced abstentions\u0002: {0}".format(", ".join(alist)))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    FORCED_COUNTS.clear()
    FORCED_TARGETS.clear()

@event_listener("reset")
def on_reset(evt, var):
    FORCED_COUNTS.clear()
    FORCED_TARGETS.clear()
