from src.decorators import event_listener
from src.containers import UserDict
from src.functions import get_players
from src.messages import messages

__all__ = ["add_absent", "try_absent", "get_absent"]

ABSENT = UserDict() # type: UserDict[users.User, str]

def add_absent(var, target, reason):
    if target not in get_players():
        return

    ABSENT[target] = reason
    from src.votes import VOTES

    for votee, voters in list(VOTES.items()):
        if target in voters:
            voters.remove(target)
            if not voters:
                del VOTES[votee]
            break

def try_absent(var, user):
    if user in ABSENT:
        user.send(messages[ABSENT[user] + "_absent"])
        return True
    return False

def get_absent(var):
    return set(ABSENT)

@event_listener("del_player")
def on_del_player(evt, var, player, allroles, death_triggers):
    del ABSENT[:player:]

@event_listener("revealroles")
def on_revealroles(evt, var):
    if ABSENT:
        evt.data["output"].append(messages["absent_revealroles"].format(ABSENT))

@event_listener("transition_night_begin")
def on_transition_night_begin(evt, var):
    ABSENT.clear()

@event_listener("reset")
def on_reset(evt, var):
    ABSENT.clear()
