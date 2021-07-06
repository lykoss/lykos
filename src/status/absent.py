from __future__ import annotations

from typing import TYPE_CHECKING, Set

from src.events import Event, event_listener
from src.containers import UserDict
from src.functions import get_players
from src.messages import messages

if TYPE_CHECKING:
    from src.gamestate import GameState
    from src.users import User

__all__ = ["add_absent", "try_absent", "get_absent"]

ABSENT: UserDict[User, str] = UserDict()

def add_absent(var: GameState, target: User, reason: str):
    if target not in get_players(var):
        return

    ABSENT[target] = reason
    from src.votes import VOTES

    for votee, voters in list(VOTES.items()):
        if target in voters:
            voters.remove(target)
            if not voters:
                del VOTES[votee]
            break

def try_absent(var: GameState, user: User):
    if user in ABSENT:
        user.send(messages[ABSENT[user] + "_absent"])
        return True
    return False

def get_absent(var: GameState):
    return set(ABSENT)

@event_listener("del_player")
def on_del_player(evt: Event, var: GameState, player: User, allroles: Set[str], death_triggers: bool):
    del ABSENT[:player:]

@event_listener("revealroles")
def on_revealroles(evt: Event, var: GameState):
    if ABSENT:
        evt.data["output"].append(messages["absent_revealroles"].format(ABSENT))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt: Event, var: GameState):
    ABSENT.clear()

@event_listener("reset")
def on_reset(evt: Event, var: GameState):
    ABSENT.clear()
