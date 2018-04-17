from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players
from src.decorators import cmd, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event

# handles villager and cultist

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        villroles = var.HIDDEN_VILLAGERS | {"villager"}
        if var.DEFAULT_ROLE == "villager":
            villroles |= var.HIDDEN_ROLES
        villagers = get_players(villroles)
        if villagers:
            for villager in villagers:
                to_send = "villager_notify"
                if villager.prefers_simple():
                    to_send = "villager_simple"
                villager.queue_message(messages[to_send])
            villager.send_messages()

        cultroles = {"cultist"}
        if var.DEFAULT_ROLE == "cultist":
            cultroles |= var.HIDDEN_ROLES
        cultists = get_players(cultroles)
        if cultists:
            for cultist in cultists:
                to_send = "cultist_notify"
                if cultist.prefers_simple():
                    to_send = "cultist_simple"
                cultist.queue_message(messages[to_send])
            cultist.send_messages()

# No listeners should register before this one
# This sets up the initial state, based on village/wolfteam/neutral affiliation
@event_listener("player_win", priority=0)
def on_player_win(evt, var, user, role, winner, survived):
    # init won/iwon to False
    evt.data["won"] = False
    evt.data["iwon"] = False

    if role in var.WOLFTEAM_ROLES or (var.DEFAULT_ROLE == "cultist" and role in var.HIDDEN_ROLES):
        if winner == "wolves":
            evt.data["won"] = True
            evt.data["iwon"] = survived
    elif role in var.TRUE_NEUTRAL_ROLES:
        # handled in their individual files
        pass
    elif winner == "villagers":
        evt.data["won"] = True
        evt.data["iwon"] = survived

@event_listener("chk_win", priority=3)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    if evt.data["winner"] is not None:
        return
    if lrealwolves == 0:
        evt.data["winner"] = "villagers"
        evt.data["message"] = messages["villager_win"]
    elif lwolves == lpl / 2:
        evt.data["winner"] = "wolves"
        evt.data["message"] = messages["wolf_win_equal"]
    elif lwolves > lpl / 2:
        evt.data["winner"] = "wolves"
        evt.data["message"] = messages["wolf_win_greater"]

# vim: set sw=4 expandtab:
