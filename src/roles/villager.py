from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.events import Event
from src.cats import Hidden

# handles villager and cultist

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
        villroles = {"villager"}
        if var.HIDDEN_ROLE == "villager":
            villroles |= Hidden
        villagers = get_players(villroles)
        if villagers:
            for villager in villagers:
                to_send = "villager_notify"
                if villager.prefers_simple():
                    to_send = "villager_simple"
                villager.queue_message(messages[to_send])
            villager.send_messages()

        cultroles = {"cultist"}
        if var.HIDDEN_ROLE == "cultist":
            cultroles |= Hidden
        cultists = get_players(cultroles)
        if cultists:
            for cultist in cultists:
                to_send = "cultist_notify"
                if cultist.prefers_simple():
                    to_send = "cultist_simple"
                cultist.queue_message(messages[to_send])
            cultist.send_messages()

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

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["villager"] = {"Village"}
        # FIXME: split this into individual files once split from wolfgame.py
        evt.data["fool"] = {"Neutral", "Win Stealer", "Innocent"}
        evt.data["demoniac"] = {"Neutral", "Win Stealer"}
        evt.data["village drunk"] = {"Village", "Safe"}

# vim: set sw=4 expandtab:
