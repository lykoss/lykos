from src.utilities import *
from src import users, channels, debuglog, errlog, plog
from src.functions import get_players
from src.decorators import command, event_listener
from src.containers import UserList, UserSet, UserDict, DefaultUserDict
from src.messages import messages
from src.status import try_misdirection, try_exchange
from src.cats import Hidden

@event_listener("transition_night_end", priority=2)
def on_transition_night_end(evt, var):
    if var.NIGHT_COUNT == 1 or var.ALWAYS_PM_ROLE:
        villroles = {"villager"}
        if var.HIDDEN_ROLE == "villager":
            villroles |= Hidden
        villagers = get_players(villroles)
        if villagers:
            for villager in villagers:
                villager.queue_message(messages["villager_notify"])
            villager.send_messages()

@event_listener("chk_win", priority=3)
def on_chk_win(evt, var, rolemap, mainroles, lpl, lwolves, lrealwolves):
    if evt.data["winner"] is not None:
        return
    if lrealwolves == 0:
        evt.data["winner"] = "villagers"
        evt.data["message"] = messages["villager_win"]

@event_listener("get_role_metadata")
def on_get_role_metadata(evt, var, kind):
    if kind == "role_categories":
        evt.data["villager"] = {"Village"}

# vim: set sw=4 expandtab:
