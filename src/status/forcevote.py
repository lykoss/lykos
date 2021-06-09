from __future__ import annotations

from typing import Iterable, Set

from src.decorators import event_listener
from src.containers import UserDict, UserSet
from src.functions import get_players
from src.messages import messages
from src.events import Event
from src.users import User
from src import channels

__all__ = ["add_force_vote", "add_force_abstain", "can_vote", "can_abstain", "get_forced_votes", "get_all_forced_votes", "get_forced_abstains"]

# FORCED_COUNTS is incremented whenever we're forcing someone to vote for someone else
# A positive number indicates that their vote is being forced towards any number of targets
# whereas a negative number indicates that their vote is being forced towards abstention.
# 0 indicates not being forced.
# FORCED_TARGETS is used to see which targets are being force-voted for.
# If multiple calls to force_vote() force different targets, the union of all of those targets is taken.

FORCED_COUNTS: UserDict[User, int] = UserDict()
FORCED_TARGETS: UserDict[User, UserSet] = UserDict()

def _add_count(var, votee: User, amount: int) -> None:
    FORCED_COUNTS[votee] = FORCED_COUNTS.get(votee, 0) + amount
    if FORCED_COUNTS[votee] == 0:
        # don't clear out FORCED_TARGETS, in case a future call re-forces votes
        # we want to maintain the full set of people to vote for
        del FORCED_COUNTS[votee]

def add_force_vote(var, votee: User, targets: Iterable[User]) -> None:
    """Force votee to vote for the specified targets."""
    if votee not in get_players():
        return
    _add_count(var, votee, 1)
    FORCED_TARGETS.setdefault(votee, UserSet()).update(targets)

def add_force_abstain(var, votee: User) -> None:
    """Force votee to abstain."""
    if votee not in get_players():
        return
    _add_count(var, votee, -1)

def can_vote(var, votee: User, target: User) -> bool:
    """Check whether the votee can vote the target."""
    c = FORCED_COUNTS.get(votee, 0)
    if c < 0:
        return False
    elif c == 0:
        return True
    return target in FORCED_TARGETS[votee]

def can_abstain(var, votee: User) -> bool:
    """Check whether the votee can abstain."""
    return FORCED_COUNTS.get(votee, 0) <= 0

def get_forced_votes(var, target: User) -> Set[User]:
    """Retrieve the players who are being forced to vote target."""
    return {votee for votee, targets in FORCED_TARGETS.items() if target in targets}

def get_all_forced_votes(var) -> Set[User]:
    """Retrieve the players who are being forced to vote."""
    return {player for player, count in FORCED_COUNTS.items() if count > 0}

def get_forced_abstains(var) -> Set[User]:
    """Retrieve the players who are being forced to abstain."""
    return {player for player, count in FORCED_COUNTS.items() if count < 0}

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
def on_revealroles(evt, var):
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
            evt.data["output"].append(messages["forced_votes_revealroles"].format(vlist))
        if alist:
            evt.data["output"].append(messages["forced_abstentions_revealroles"].format(alist))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    FORCED_COUNTS.clear()
    FORCED_TARGETS.clear()

@event_listener("reset")
def on_reset(evt, var):
    FORCED_COUNTS.clear()
    FORCED_TARGETS.clear()
