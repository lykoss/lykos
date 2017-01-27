import src.settings as var
from src.utilities import *
from src import debuglog, errlog, plog
from src.decorators import cmd, event_listener
from src.messages import messages
from src.events import Event

# handles villager and cultist

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, cli, var):
    if var.FIRST_NIGHT or var.ALWAYS_PM_ROLE:
        villroles = var.HIDDEN_VILLAGERS | {"villager"}
        if var.DEFAULT_ROLE == "villager":
            villroles |= var.HIDDEN_ROLES
        villagers = list_players(villroles)
        for villager in villagers:
            if villager in var.PLAYERS and not is_user_simple(villager):
                pm(cli, villager, messages["villager_notify"])
            else:
                pm(cli, villager, messages["villager_simple"])

        cultroles = {"cultist"}
        if var.DEFAULT_ROLE == "cultist":
            cultroles |= var.HIDDEN_ROLES
        cultists = list_players(cultroles)
        for cultist in cultists:
            if cultist in var.PLAYERS and not is_user_simple(cultist):
                pm(cli, cultist, messages["cultist_notify"])
            else:
                pm(cli, cultist, messages["cultist_simple"])

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
def on_chk_win(evt, cli, var, rolemap, lpl, lwolves, lrealwolves):
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
